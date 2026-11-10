"""Shrink local data while a trusted command reproduces an observed failure.

Subprocesses keep the caller's working folder, environment and permissions.
Crumb is not a sandbox. It never writes the source and checks for its mutation.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time
from typing import Callable

OUTPUT_LIMIT = 1_048_576  # Per stream, per invocation; never accumulate unbounded logs.


class CrumbError(Exception):
    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CrumbError("INPUT_UNREADABLE", f"Cannot read {path}: {exc}",
                         "Choose a readable regular file.") from exc


def _pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise CrumbError("BAD_POINTER", "Use an RFC 6901 JSON pointer.",
                         "For example: /payload/records; escape ~ as ~0 and / as ~1.")
    return [part.replace("~1", "/").replace("~0", "~")
            for part in pointer[1:].split("/")]


def _get_pointer(value, tokens: list[str]):
    try:
        for token in tokens:
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token):
                    raise KeyError(token)
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise KeyError(token)
        return value
    except (KeyError, IndexError) as exc:
        raise CrumbError("BAD_POINTER", "The JSON pointer does not exist.",
                         "Point to an existing JSON array.") from exc


def _json_load(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CrumbError("BAD_JSON", f"Duplicate JSON object key: {key!r}.",
                                 "Use --format lines for malformed or duplicate-key JSON.")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"Non-standard JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, RecursionError) as exc:
        raise CrumbError("BAD_JSON", f"Cannot parse JSON: {exc}",
                         "Use --format lines if the malformed JSON is the bug.") from exc


class _Units:
    def __init__(self, source: bytes, suffix: str, fmt: str,
                 pointer: str | None, header: bool):
        supported = {"auto", "csv", "tsv", "json", "jsonl", "lines"}
        if fmt not in supported:
            raise CrumbError("BAD_FORMAT", f"Unsupported format: {fmt}",
                             "Choose auto, csv, tsv, json, jsonl, or lines.")
        if fmt == "auto":
            fmt = {".csv": "csv", ".tsv": "tsv", ".json": "json",
                   ".jsonl": "jsonl", ".ndjson": "jsonl"}.get(suffix.lower(), "lines")
        if pointer is not None and fmt != "json":
            raise CrumbError("BAD_OPTIONS", "A JSON pointer requires JSON format.",
                             "Use --format json with --json-pointer.")
        self.format, self.pointer = fmt, None
        self.locations: list[dict] = []
        self.prefix = b""
        self.document = None
        self.tokens = []
        self.bom = source.startswith(b"\xef\xbb\xbf")
        try:
            text = source.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CrumbError("BAD_ENCODING", "Input is not UTF-8 text.",
                             "Convert it to UTF-8 before using Crumb.") from exc
        if fmt in {"csv", "tsv"}:
            dialect = csv.excel_tab if fmt == "tsv" else csv.excel
            if fmt == "csv" and text:
                try:
                    dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
                except csv.Error:
                    pass
            # StringIO's newline="" and physical lines preserve raw record bytes.
            lines = io.StringIO(text, newline="").readlines()
            reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect, strict=True)
            records = []
            previous = 0
            try:
                for _row in reader:
                    end = reader.line_num
                    records.append(("".join(lines[previous:end]).encode("utf-8"),
                                    previous + 1, end))
                    previous = end
            except csv.Error as exc:
                raise CrumbError("BAD_CSV", f"Cannot identify CSV records: {exc}",
                                 "Use --format lines if the malformed CSV is the bug.") from exc
            self.prefix = b"\xef\xbb\xbf" if self.bom else b""
            if header and records:
                self.prefix += records.pop(0)[0]
            self.units = [record[0] for record in records]
            self.locations = [{"index": i, "start_line": row[1], "end_line": row[2]}
                              for i, row in enumerate(records)]
        elif fmt == "json":
            self.document = _json_load(text)
            if pointer is None:
                if isinstance(self.document, list):
                    pointer = ""
                else:
                    arrays = []
                    def walk(value, path):
                        if isinstance(value, list):
                            arrays.append((len(value), path))
                            for i, item in enumerate(value):
                                walk(item, path + "/" + str(i))
                        elif isinstance(value, dict):
                            for key, item in value.items():
                                walk(item, path + "/" + key.replace("~", "~0").replace("/", "~1"))
                    try:
                        walk(self.document, "")
                    except RecursionError as exc:
                        raise CrumbError("BAD_JSON", "JSON is nested too deeply.") from exc
                    if not arrays:
                        raise CrumbError("NO_ARRAY", "JSON contains no reducible array.",
                                         "Use --format lines to reduce text instead.")
                    largest = max(size for size, _path in arrays)
                    winners = [path for size, path in arrays if size == largest]
                    if len(winners) != 1:
                        raise CrumbError("AMBIGUOUS_JSON", "Several JSON arrays have the largest size.",
                                         "Choose --json-pointer from: " + ", ".join(winners[:12]))
                    pointer = winners[0]
            self.pointer = pointer
            self.tokens = _pointer_tokens(pointer)
            value = _get_pointer(self.document, self.tokens)
            if not isinstance(value, list):
                raise CrumbError("NOT_ARRAY", "The JSON pointer must select an array.",
                                 "Choose the array whose records may be removed.")
            self.units = value
            self.locations = [{"index": i, "json_pointer": pointer + "/" + str(i)}
                              for i in range(len(value))]
        else:
            physical_lines = io.StringIO(text, newline="").readlines()
            if fmt == "jsonl":
                for line_number, line in enumerate(physical_lines, 1):
                    if line.strip():
                        try:
                            _json_load(line)
                        except CrumbError as exc:
                            raise CrumbError("BAD_JSONL", f"Invalid JSONL record at line {line_number}: {exc}",
                                             "Use --format lines if malformed JSONL is the bug.") from exc
            self.prefix = b"\xef\xbb\xbf" if self.bom else b""
            self.units = [line.encode("utf-8") for line in physical_lines]
            self.locations = [{"index": i, "start_line": i + 1, "end_line": i + 1}
                              for i in range(len(self.units))]

    def render(self, indices: tuple[int, ...]) -> bytes:
        chosen = [self.units[i] for i in indices]
        if self.format != "json":
            return self.prefix + b"".join(chosen)
        document = copy.deepcopy(self.document)
        if not self.tokens:
            document = chosen
        else:
            parent = _get_pointer(document, self.tokens[:-1])
            key = int(self.tokens[-1]) if isinstance(parent, list) else self.tokens[-1]
            parent[key] = chosen
        try:
            result = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise CrumbError("BAD_JSON", f"Cannot preserve JSON values: {exc}",
                             "Use --format lines to retain the original text.") from exc
        return (b"\xef\xbb\xbf" if self.bom else b"") + result


def _kill(process: subprocess.Popen):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, PermissionError):
        pass


def _execute(argv: list[str], timeout: float) -> dict:
    """Bound memory and elapsed time, including descendants holding open pipes."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=(os.name == "posix"))
    except (OSError, ValueError) as exc:
        raise CrumbError("COMMAND_FAILED", f"Cannot start command: {exc}",
                         "Use an installed executable and put {input} in its arguments.") from exc
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    exceeded = threading.Event()

    def drain(stream, name):
        try:
            while True:
                data = stream.read(8192)
                if not data:
                    return
                remaining = OUTPUT_LIMIT - len(buffers[name])
                buffers[name].extend(data[:max(0, remaining)])
                if len(data) > remaining:
                    exceeded.set()
        except (OSError, ValueError):
            return
        finally:
            stream.close()

    readers = [threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
               threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    reason = "finished"
    while process.poll() is None or any(reader.is_alive() for reader in readers):
        if exceeded.is_set():
            reason = "output_limit"
            break
        if time.monotonic() >= deadline:
            reason = "timeout"
            break
        time.sleep(min(.01, max(0, deadline - time.monotonic())))
    if reason != "finished":
        _kill(process)
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        _kill(process)
    for reader in readers:
        reader.join(timeout=.2)
    if exceeded.is_set() and reason == "finished":
        reason = "output_limit"
    return {"returncode": process.returncode, "reason": reason,
            **{name + "_raw": bytes(data) for name, data in buffers.items()}}


class _Runner:
    def __init__(self, source: Path, source_hash: str, command: list[str],
                 timeout: float, max_runs: int, match, exit_code_only: bool,
                 progress: Callable | None):
        self.source, self.source_hash = source, source_hash
        self.command, self.timeout, self.max_runs = command, timeout, max_runs
        self.match, self.exit_code_only, self.progress = match, exit_code_only, progress
        self.calls = 0
        self.signature = None
        self.outcomes = {"matched": 0, "different": 0, "timeout": 0, "output_limit": 0}

    def check_source(self):
        try:
            actual = _hash(self.source.read_bytes())
        except OSError as exc:
            raise CrumbError("SOURCE_MUTATED", "The command removed or made the source unreadable.",
                             "Crumb is not a sandbox. Restore your source and use a read-only command.") from exc
        if actual != self.source_hash:
            raise CrumbError("SOURCE_MUTATED", "The command changed the original input file.",
                             "Crumb is not a sandbox. Restore your source and use a read-only command.")

    def run(self, path: Path, stage: str, units: int) -> dict:
        if self.calls >= self.max_runs:
            raise CrumbError("RUN_LIMIT", "The command budget is exhausted.")
        before = _hash(_read(path))
        self.check_source()
        self.calls += 1
        started = time.monotonic()
        result = _execute([part.replace("{input}", str(path)) for part in self.command], self.timeout)
        self.check_source()
        try:
            after = _hash(path.read_bytes())
        except OSError:
            after = None
        if after != before:
            raise CrumbError("CANDIDATE_MUTATED", "The command changed or removed its input.",
                             "Use a command that reads candidates without modifying them.")
        for stream in ("stdout", "stderr"):
            # Compare raw bytes: invalid UTF-8 must not collide with literal \xNN text.
            # Only known input paths are normalized; no digits/IDs/timestamps are removed.
            raw = result.pop(stream + "_raw")
            for name in sorted({str(self.source), str(path)}, key=len, reverse=True):
                raw = raw.replace(os.fsencode(name), b"{input}")
            result[stream + "_sha256"] = _hash(raw)
            result[stream] = raw.decode("utf-8", errors="backslashreplace")
        result["elapsed_seconds"] = time.monotonic() - started
        if self.progress:
            self.progress({"stage": stage, "calls": self.calls, "max_runs": self.max_runs,
                           "units": units, "returncode": result["returncode"],
                           "reason": result["reason"]})
        return result

    def establish(self, result: dict):
        if result["reason"] != "finished":
            code = "BASELINE_TIMEOUT" if result["reason"] == "timeout" else "OUTPUT_LIMIT"
            raise CrumbError(code, "The original command did not finish within the execution limits.",
                             "Use a bounded reproducer; increase --timeout only if appropriate.")
        if result["returncode"] == 0:
            raise CrumbError("BASELINE_PASSED", "The original input did not fail.",
                             "The command must exit nonzero when it reproduces your bug.")
        signature = {"returncode": result["returncode"]}
        if self.match is not None:
            if not self.match.search(result["stderr"] + "\n" + result["stdout"]):
                raise CrumbError("MATCH_NOT_FOUND", "The requested failure pattern is absent from the original output.",
                                 "Choose a specific regex from the actual failure output.")
            signature.update(mode="regex", pattern=self.match.pattern)
        elif self.exit_code_only:
            signature.update(mode="exit_code_only")
        else:
            stream = "stderr" if result["stderr"].strip() else "stdout"
            output = result[stream]
            if not output.strip():
                raise CrumbError("NO_SIGNATURE", "The command failed without diagnostic output.",
                                 "Print a stable diagnostic or explicitly use --exit-code-only.")
            signature.update(mode="exact", stream=stream, text=output, sha256=result[stream + "_sha256"],
                             last_line=[line for line in output.splitlines() if line.strip()][-1])
        self.signature = signature

    def matches(self, result: dict) -> bool:
        if result["reason"] != "finished":
            self.outcomes[result["reason"]] += 1
            return False
        sig = self.signature
        matched = result["returncode"] == sig["returncode"]
        if matched and sig["mode"] == "exact":
            matched = result[sig["stream"] + "_sha256"] == sig["sha256"]
        elif matched and sig["mode"] == "regex":
            matched = bool(self.match.search(result["stderr"] + "\n" + result["stdout"]))
        self.outcomes["matched" if matched else "different"] += 1
        return matched


def reduce_file(input_path: Path, command: list[str], *, output_dir: Path,
                format: str = "auto", json_pointer: str | None = None,
                header: bool = True, timeout: float = 5.0, max_runs: int = 200,
                match: str | None = None, exit_code_only: bool = False,
                progress: Callable | None = None) -> dict:
    """Find a smaller order-preserving subset reproducing the observed failure.

    Exact diagnostics are the conservative default. ``match`` explicitly uses
    a regex oracle; ``exit_code_only`` explicitly accepts any same-code failure.
    A completed ddmin result is 1-minimal under this oracle, not globally minimal
    and not proof of a common root cause. ``max_runs`` includes baseline and two
    uncached confirmations at the final output path. Output must be a new folder.
    """
    started = time.monotonic()
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
    if not input_path.is_file():
        raise CrumbError("INPUT_UNREADABLE", "Input must be a readable regular file.")
    if (not command or not all(isinstance(arg, str) and "\0" not in arg for arg in command)
            or not any("{input}" in arg for arg in command)):
        raise CrumbError("BAD_COMMAND", "The command must contain a literal {input} placeholder.",
                         "Example: crumb data.csv -- python importer.py {input}")
    if not isinstance(max_runs, int) or isinstance(max_runs, bool) or max_runs < 5:
        raise CrumbError("BAD_OPTIONS", "--max-runs must be an integer of at least 5.",
                         "Five calls cover two baselines, one roundtrip and two final confirmations.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise CrumbError("BAD_OPTIONS", "--timeout must be a finite positive number.")
    if match is not None and exit_code_only:
        raise CrumbError("BAD_OPTIONS", "Choose either --match or --exit-code-only.")
    try:
        pattern = re.compile(match) if match is not None else None
    except (re.error, TypeError) as exc:
        raise CrumbError("BAD_MATCH", f"Invalid failure regex: {exc}") from exc
    if match == "":
        raise CrumbError("BAD_MATCH", "An empty regex matches every output.",
                         "Choose a specific diagnostic or explicitly use --exit-code-only.")
    source = _read(input_path)
    source_hash = _hash(source)
    units = _Units(source, input_path.suffix, format, json_pointer, header)
    full = tuple(range(len(units.units)))
    suffix = input_path.suffix or {"csv": ".csv", "tsv": ".tsv", "json": ".json",
                                  "jsonl": ".jsonl", "lines": ".txt"}[units.format]
    final_path = output_dir / ("repro" + suffix)
    if final_path == input_path:
        raise CrumbError("OUTPUT_EXISTS", "The output would overwrite the original input.")
    try:
        output_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise CrumbError("OUTPUT_EXISTS", f"Output directory already exists: {output_dir}",
                         "Choose a new output directory; Crumb never overwrites an existing result.") from exc
    except OSError as exc:
        raise CrumbError("OUTPUT_UNWRITABLE", f"Cannot create output directory: {exc}") from exc
    runner = _Runner(input_path, source_hash, command, timeout, max_runs, pattern, exit_code_only, progress)
    first = runner.run(input_path, "baseline", len(full))
    runner.establish(first)
    second = runner.run(input_path, "baseline", len(full))
    if not runner.matches(second):
        raise CrumbError("UNSTABLE_BASELINE", "The original input did not reproduce the same failure twice.",
                         "Stabilize the reproducer or choose a specific --match pattern.")
    selected, cache, exhausted = full, {}, False
    with tempfile.TemporaryDirectory(prefix=".crumb-", dir=output_dir) as temporary:
        candidate_path = Path(temporary) / ("candidate" + suffix)
        candidate_path.write_bytes(units.render(full))
        normalized = runner.run(candidate_path, "roundtrip", len(full))
        if not runner.matches(normalized):
            raise CrumbError("ROUNDTRIP_CHANGED", "The complete candidate did not reproduce the original failure.",
                             "The command may depend on filename, location or JSON formatting; try --format lines.")
        cache[full] = "matched"

        def test(indices: tuple[int, ...]):
            nonlocal exhausted
            if indices in cache:
                return cache[indices] == "matched"
            if runner.calls >= max_runs - 2:
                exhausted = True
                return None
            candidate_path.write_bytes(units.render(indices))
            result = runner.run(candidate_path, "reduce", len(indices))
            matched = runner.matches(result)
            cache[indices] = "matched" if matched else result["reason"]
            return matched

        # Empty matters: a one-record result is only 1-minimal if empty does not reproduce.
        empty = test(()) if full else True
        if empty:
            selected = ()
        elif empty is not None:
            granularity = 2
            while len(selected) >= 2 and not exhausted:
                count = len(selected)
                chunks = [selected[(i * count) // granularity:((i + 1) * count) // granularity]
                          for i in range(granularity)]
                reduced = False
                for subset_pass in (False, True):
                    for chunk in chunks:
                        chunk_set = set(chunk)
                        proposal = chunk if subset_pass else tuple(i for i in selected if i not in chunk_set)
                        if proposal == selected:
                            continue
                        outcome = test(proposal)
                        if outcome is None:
                            break
                        if outcome:
                            selected = proposal
                            granularity = min(len(selected), max(2, granularity - 1))
                            reduced = True
                            break
                    if reduced or exhausted:
                        break
                if reduced:
                    continue
                if exhausted or granularity >= len(selected):
                    break
                granularity = min(len(selected), granularity * 2)

        # Timeouts/oversized logs are inconclusive, not proof of single-deletion minimality.
        one_minimal = not selected or all(
            cache.get(selected[:i] + selected[i + 1:]) == "finished"
            for i in range(len(selected)))
        reduced_bytes = units.render(selected)
        try:
            with final_path.open("xb") as handle:
                handle.write(reduced_bytes)
        except OSError as exc:
            raise CrumbError("OUTPUT_UNWRITABLE", f"Cannot write final reproducer: {exc}") from exc
        for _ in range(2):
            final = runner.run(final_path, "verify", len(selected))
            if not runner.matches(final):
                raise CrumbError("FINAL_UNSTABLE", "The final output did not reproduce the same failure twice.",
                                 "No verified result was produced. Inspect filename dependencies or nondeterminism.")
    runner.check_source()
    output_hash = _hash(final_path.read_bytes())
    return {
        "schema_version": 1,
        "status": "budget_exhausted" if exhausted and not one_minimal else "complete",
        "format": units.format, "json_pointer": units.pointer,
        "input": {"path": str(input_path), "bytes": len(source), "units": len(full), "sha256": source_hash},
        "output": {"path": str(final_path), "bytes": len(reduced_bytes), "units": len(selected), "sha256": output_hash},
        "command": list(command), "calls": runner.calls, "max_runs": max_runs, "timeout": timeout,
        "signature": runner.signature, "verified_final": True, "confirmations": 2,
        "source_sha256_before": source_hash, "source_sha256_after": source_hash,
        "source_unchanged": True, "one_minimal": one_minimal,
        "kept_indices": list(selected),
        "source_locations": [units.locations[i] for i in selected],
        "reduction": {"units_percent": round(100 * (1 - len(selected) / len(full)), 2) if full else 0.0,
                      "bytes_percent": round(100 * (1 - len(reduced_bytes) / len(source)), 2) if source else 0.0},
        "outcomes": runner.outcomes,
        "elapsed_seconds": round(time.monotonic() - started, 4),
    }
