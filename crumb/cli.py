"""Small CLI; all reduction decisions live in core.py."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import shlex
import sys
import time

from . import __version__


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crumb",
        description="Give it the command that fails. Get a tiny input that reproduces the observed error.",
        epilog="Example: crumb orders.csv -- python import_orders.py '{input}'\n"
               "Runs your command repeatedly with your permissions. Use disposable/local targets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", type=Path, nargs="?", help="input file; omit to infer a single data-file argument after --")
    p.add_argument("--out", type=Path, help="new output directory (existing paths are never overwritten)")
    p.add_argument("--format", choices=["auto", "csv", "tsv", "json", "jsonl", "lines"], default="auto")
    p.add_argument("--json-pointer", help="JSON Pointer selecting one list, e.g. /payload/events")
    p.add_argument("--no-header", action="store_true", help="treat the first CSV/TSV record as data")
    p.add_argument("--timeout", type=float, default=5.0, help="seconds per command run (default: 5)")
    p.add_argument("--max-runs", type=int, default=200, help="total command executions, including verification (default: 200)")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--match", metavar="REGEX", help="explicit error pattern; weaker than full-output matching")
    group.add_argument("--exit-code-only", action="store_true", help="explicitly match only the failing exit code; can conflate errors")
    p.add_argument("--json", action="store_true", help="machine-readable result on stdout; progress stays on stderr")
    p.add_argument("--quiet", action="store_true", help="suppress progress")
    p.add_argument("--version", action="version", version=f"Crumb {__version__}")
    return p


def _error(code: str, message: str, hint: str = "", as_json: bool = False) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": {"code": code, "message": message, "hint": hint}}, ensure_ascii=True))
    else:
        print(f"Crumb: {message}", file=sys.stderr)
        if hint:
            print(f"  {hint}", file=sys.stderr)
    return 2


def _default_output(source: Path) -> Path:
    base = Path.cwd() / f"{source.stem}.crumb"
    if not base.exists():
        return base
    return base.with_name(f"{base.name}-{time.time_ns()}")


def _infer_input(command: list[str]) -> tuple[Path, list[str]]:
    """Infer only an unambiguous existing data-file argument, never a script."""
    candidates = []
    data_suffixes = {".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".txt", ".log", ".yaml", ".yml", ".xml", ".toml", ".ini", ".conf"}
    for index, arg in enumerate(command[1:], 1):
        prefix, value = (arg.split("=", 1) if arg.startswith("--") and "=" in arg else (None, arg))
        path = Path(value).expanduser()
        if path.suffix.lower() in data_suffixes and path.is_file():
            candidates.append((index, path, prefix))
    if len(candidates) != 1:
        raise ValueError("Provide exactly one existing data-file argument, or name the input explicitly and use '{input}'.")
    index, path, prefix = candidates[0]
    command = command.copy()
    command[index] = "{input}" if prefix is None else prefix + "={input}"
    return path, command


def _progress(quiet: bool):
    last = [0.0]

    def show(event=None, *args, **kwargs):
        if quiet or time.monotonic() - last[0] < 0.25:
            return
        last[0] = time.monotonic()
        if isinstance(event, dict):
            units = event.get("units", event.get("remaining_units", event.get("remaining")))
            calls = event.get("calls", event.get("runs"))
            if units is not None:
                print(f"  testing {units:,} units" + (f" · {calls} runs" if calls is not None else ""), file=sys.stderr)
        elif isinstance(event, str):
            print(f"  {event}", file=sys.stderr)

    return show


def _deliver(report: dict, output_dir: Path, as_json: bool) -> int:
    from .report import write_report
    report["crumb_version"] = __version__
    report["ok"] = True
    report["working_directory"] = str(Path.cwd())
    report["scope"] = "Matches an observed failure signature; does not establish the same underlying bug."
    report["failure_on_empty_selection"] = report["output"]["units"] == 0
    report["next_step"] = (
        "The failure persists with zero selected data units. Inspect command setup, the retained header or JSON envelope before blaming a record."
        if report["failure_on_empty_selection"] else
        "Diagnose this example, then test your fix on the FULL original input."
    )
    report["artifacts"] = {
        "report_json": str(output_dir / "report.json"),
        "report_html": str(output_dir / "report.html"),
        "reproduce_txt": str(output_dir / "reproduce.txt"),
    }
    output_path = str(report["output"]["path"])
    command = [str(arg).replace("{input}", output_path) for arg in report["command"]]
    report["reproduce_command"] = command
    # These are instructions, never an auto-executed script. They retain the original cwd.
    (output_dir / "reproduce.txt").write_text(
        "Run from the same environment and working directory as the original command.\n"
        "This command may have side effects. Inspect it before running.\n\n"
        f"Working directory: {Path.cwd()}\n"
        f"POSIX command: {shlex.join(command)}\n\n"
        "The command arguments as a portable JSON array are in report.json.\n"
        "The program/dependencies are not bundled; sharing this directory alone may not reproduce elsewhere.\n",
        encoding="utf-8",
    )
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    write_report(report, output_dir / "report.html")
    if as_json:
        print(json.dumps(report, ensure_ascii=True))
        return 0
    before, after = report["input"], report["output"]
    print(f"\n  CRUMB  {before['units']:,} → {after['units']:,} units")
    print(f"  {before['bytes']:,} → {after['bytes']:,} bytes · {report['calls']} command runs")
    if report["verified_final"]:
        print("  The observed failure reproduced twice on the saved result.")
    print("  Original file unchanged." if report["source_unchanged"] else "  WARNING: original file changed.")
    if report["status"] != "complete":
        print(f"  Stopped: {report['status']}. The result is verified; further reduction may be possible.")
    sig = report["signature"]
    excerpt = sig.get("last_line", sig.get("line", sig.get("pattern", sig.get("text", ""))))
    if excerpt:
        print(f"\n  {str(excerpt)[:400]}")
    print(f"\n  Reproducer: {output_path}\n  Review:     {output_dir / 'report.html'}")
    print(f"\n  Next: {report['next_step']}")
    return 0


_IMPORTER = '''"""Synthetic inventory importer: reproduces a realistic cross-record collision."""
import csv
import sqlite3
import sys
import unicodedata

with open(sys.argv[1], newline="", encoding="utf-8-sig") as stream:
    rows = list(csv.DictReader(stream))
db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE inventory (sku TEXT UNIQUE, description TEXT, stock INTEGER)")
db.executemany("INSERT INTO inventory VALUES (?, ?, ?)", [
    (unicodedata.normalize("NFKC", row["sku"]).strip().casefold(), row["description"], int(row["stock"]))
    for row in rows
])
print(f"Imported {len(rows)} records")
'''


def _demo(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="crumb demo", description="Create and reduce a synthetic 12,000-record inventory import failure.")
    p.add_argument("--out", type=Path, default=Path("crumb-demo"), help="new directory for all demo files")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    base = args.out.expanduser().absolute()
    try:
        base.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return _error("OUTPUT_EXISTS", f"Output already exists: {base}", "Choose a new --out directory.", args.json)
    source = base / "inventory.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sku", "description", "stock"])
        for index in range(12_000):
            sku = f"ITEM-{index:06}"
            if index == 1_723:
                sku = "Pump-A17"
            elif index == 10_901:
                sku = " pump-a17 "
            writer.writerow([sku, f"Warehouse item {index}", 1 + index % 80])
    importer = base / "import_inventory.py"
    importer.write_text(_IMPORTER, encoding="utf-8")
    (base / "README.txt").write_text(
        "This is a synthetic demo, not customer evidence.\n"
        "Two far-apart records collide after normalizing their SKU.\n"
        "The importer uses a disposable in-memory SQLite database.\n",
        encoding="utf-8",
    )
    if not args.quiet:
        print("Crumb demo · synthetic 12,000-record inventory upload\nReducing an actual SQLite uniqueness failure…", file=sys.stderr)
    return _run(source, [sys.executable, str(importer), "{input}"], base / "result",
                as_json=args.json, quiet=args.quiet)


def _run(source: Path, command: list[str], output: Path, *, as_json=False, quiet=False, **options) -> int:
    from .core import CrumbError, reduce_file
    output = output.expanduser().absolute()
    try:
        report = reduce_file(source.expanduser(), command, output_dir=output, progress=_progress(quiet), **options)
        return _deliver(report, output, as_json)
    except CrumbError as exc:
        return _error(exc.code, str(exc), getattr(exc, "hint", ""), as_json)
    except KeyboardInterrupt:
        return _error("INTERRUPTED", "Reduction interrupted.", "Any incomplete output is not a verified result.", as_json)
    except (OSError, ValueError) as exc:
        return _error("IO_ERROR", str(exc), "Check input/output permissions and arguments.", as_json)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["demo"]:
        return _demo(argv[1:])
    if argv[:1] == ["doctor"]:
        p = argparse.ArgumentParser(prog="crumb doctor")
        p.add_argument("--json", action="store_true")
        args = p.parse_args(argv[1:])
        report = {"ok": sys.version_info >= (3, 10), "version": __version__, "python": sys.version.split()[0],
                  "executable": sys.executable, "platform": sys.platform, "runtime_dependencies": [],
                  "network_required": False, "sandbox": False,
                  "process_cleanup": "process-group" if os.name == "posix" else "direct-child-only"}
        print(json.dumps(report) if args.json else f"Crumb {__version__} · Python {report['python']} · {sys.platform}\n"
              "Ready. No runtime packages, API keys, service or model required.\n"
              "Commands run with your permissions; use disposable test targets.")
        return 0 if report["ok"] else 2
    if argv[:1] == ["agent"]:
        print(Path(__file__).with_name("agent-guide.md").read_text(encoding="utf-8"))
        return 0
    if argv == ["--version"]:
        print(f"Crumb {__version__}")
        return 0
    p = _parser()
    if "--" not in argv:
        if not argv or "-h" in argv or "--help" in argv:
            p.print_help()
            print("\nAlso: crumb demo | crumb doctor | crumb agent")
            return 0
        p.parse_args(argv)
        return _error("COMMAND_REQUIRED", "Supply a failing command after --.", "Example: crumb data.csv -- python importer.py '{input}'", "--json" in argv)
    split = argv.index("--")
    args = p.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command:
        return _error("COMMAND_REQUIRED", "No command after --.", "Include a literal {input} argument.", args.json)
    if args.input is None:
        try:
            args.input, command = _infer_input(command)
        except ValueError as exc:
            return _error("INPUT_AMBIGUOUS", str(exc), "Example: crumb orders.csv -- python import.py '{input}'", args.json)
    if not any("{input}" in arg for arg in command):
        return _error("PLACEHOLDER_REQUIRED", "The command needs a literal {input} placeholder.", "Replace the input filename with '{input}'.", args.json)
    return _run(args.input, command, args.out or _default_output(args.input), as_json=args.json, quiet=args.quiet,
                format=args.format, json_pointer=args.json_pointer, header=not args.no_header,
                timeout=args.timeout, max_runs=args.max_runs, match=args.match, exit_code_only=args.exit_code_only)
