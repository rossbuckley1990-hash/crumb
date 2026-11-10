"""Independent CLI acceptance tests.

The fixtures implement observable bugs rather than importing reducer internals.
Every successful reduction is rerun outside Crumb to check the reported result.
These tests establish bounded engineering behavior, not market demand.
"""

from __future__ import annotations

import csv
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="crumb independent ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.out = self.base / "reduction output"

    def script(self, code: str, name: str = "consumer.py") -> Path:
        path = self.base / name
        path.write_text(textwrap.dedent(code), encoding="utf-8")
        return path

    def run_crumb(self, source: Path, command: list[str], *options: str):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT)
        return subprocess.run(
            [sys.executable, "-m", "crumb", str(source), "--out", str(self.out),
             "--json", "--max-runs", "120", *options, "--", *command],
            cwd=self.base, env=env, text=True, capture_output=True, timeout=45,
        )

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertIsInstance(data, dict)
        self.assertTrue((self.out / "report.json").is_file())
        self.assertTrue((self.out / "report.html").is_file())
        json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        return data

    def reproduce(self, command: list[str], path: Path):
        return subprocess.run(
            [arg.replace("{input}", str(path)) for arg in command],
            cwd=self.base, capture_output=True, text=True, timeout=5,
        )

    def test_two_distant_records_survive_together(self):
        source = self.base / "wide data.csv"
        rows = [[f"item-{i}", str(i)] for i in range(240)]
        rows[7] = ["collision", "first"]
        rows[227] = ["collision", "second"]
        with source.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["id", "payload"])
            writer.writerows(rows)
        original = source.read_bytes()
        consumer = self.script('''
            import csv, sys
            with open(sys.argv[1], newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames != ["id", "payload"]:
                    sys.stderr.write("schema invalid\\n"); sys.exit(1)
                seen = set()
                for row in reader:
                    if row["id"] in seen:
                        sys.stderr.write("duplicate identifier\\n"); sys.exit(1)
                    seen.add(row["id"])
        ''')
        command = [sys.executable, str(consumer), "{input}"]
        self.assert_success(self.run_crumb(source, command))
        repro = self.out / "repro.csv"
        with repro.open(newline="", encoding="utf-8-sig") as f:
            reduced = list(csv.DictReader(f))
        self.assertEqual(len(reduced), 2)
        self.assertEqual({row["payload"] for row in reduced}, {"first", "second"})
        external = self.reproduce(command, repro)
        self.assertEqual((external.returncode, external.stderr), (1, "duplicate identifier\n"))
        self.assertEqual(source.read_bytes(), original)

    def test_csv_preserves_bom_crlf_multiline_and_quoting(self):
        source = self.base / "multiline.csv"
        header = b'\xef\xbb\xbfid,description\r\n'
        witness = b'"bad","a, comma\r\nand a ""quoted"" newline"\r\n'
        original = header + b'good,ordinary\r\n' * 50 + witness + b'fine,last\r\n'
        source.write_bytes(original)
        consumer = self.script('''
            import csv, sys
            with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            if any(r["description"] == 'a, comma\\r\\nand a "quoted" newline' for r in rows):
                sys.stderr.write("multiline-field failure\\n"); sys.exit(7)
        ''')
        command = [sys.executable, str(consumer), "{input}"]
        self.assert_success(self.run_crumb(source, command))
        self.assertEqual((self.out / "repro.csv").read_bytes(), header + witness)
        external = self.reproduce(command, self.out / "repro.csv")
        self.assertEqual((external.returncode, external.stderr), (7, "multiline-field failure\n"))
        self.assertEqual(source.read_bytes(), original)

    def test_nested_json_retains_scaffolding(self):
        source = self.base / "nested.json"
        events = [{"id": i, "value": 1} for i in range(160)]
        events[9] = {"id": "target", "value": 4}
        events[142] = {"id": "target", "value": 9}
        original_obj = {
            "metadata": {"version": 4, "active": True},
            "bundle": {"events": events, "required": ["stable", 3]},
        }
        source.write_text(json.dumps(original_obj), encoding="utf-8")
        original_bytes = source.read_bytes()
        consumer = self.script('''
            import json, sys
            try:
                data = json.load(open(sys.argv[1], encoding="utf-8"))
                assert data["metadata"] == {"version": 4, "active": True}
                assert data["bundle"]["required"] == ["stable", 3]
                events = data["bundle"]["events"]
                values = [r["value"] for r in events if r["id"] == "target"]
            except Exception:
                sys.stderr.write("invalid schema\\n"); sys.exit(1)
            if 4 in values and 9 in values:
                sys.stderr.write("incompatible events\\n"); sys.exit(1)
        ''')
        command = [sys.executable, str(consumer), "{input}"]
        self.assert_success(self.run_crumb(source, command, "--json-pointer", "/bundle/events"))
        repro = self.out / "repro.json"
        reduced = json.loads(repro.read_text())
        self.assertEqual(reduced["metadata"], original_obj["metadata"])
        self.assertEqual(reduced["bundle"]["required"], original_obj["bundle"]["required"])
        self.assertEqual(len(reduced["bundle"]["events"]), 2)
        self.assertEqual(self.reproduce(command, repro).stderr, "incompatible events\n")
        self.assertEqual(source.read_bytes(), original_bytes)

    def test_common_error_footer_cannot_hide_a_different_failure(self):
        source = self.base / "with_header.txt"
        source.write_text("SCHEMA=1\n" + "noise\n" * 30 + "left\n" + "noise\n" * 30 + "right\n")
        consumer = self.script('''
            import pathlib, sys
            lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
            if not lines or lines[0] != "SCHEMA=1":
                sys.stderr.write("missing schema header\\nimport failed\\n"); sys.exit(1)
            if "left" in lines and "right" in lines:
                sys.stderr.write("incompatible pair\\nimport failed\\n"); sys.exit(1)
        ''')
        command = [sys.executable, str(consumer), "{input}"]
        self.assert_success(self.run_crumb(source, command))
        repro = self.out / "repro.txt"
        self.assertEqual(repro.read_text(), "SCHEMA=1\nleft\nright\n")
        self.assertEqual(self.reproduce(command, repro).stderr, "incompatible pair\nimport failed\n")

    def test_successful_baseline_is_rejected(self):
        source = self.base / "passing.txt"
        source.write_text("ordinary\n" * 30)
        result = self.run_crumb(source, [sys.executable, "-c", "pass", "{input}"])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse((self.out / "repro.txt").exists())

    def test_flaky_baseline_is_rejected(self):
        source = self.base / "flaky.txt"
        source.write_text("data\n" * 5)
        counter = self.base / "counter"
        consumer = self.script('''
            import pathlib, sys
            state = pathlib.Path(sys.argv[2])
            n = int(state.read_text()) + 1 if state.exists() else 1
            state.write_text(str(n))
            sys.stderr.write("odd failure\\n" if n % 2 else "even failure\\n")
            sys.exit(1)
        ''')
        result = self.run_crumb(source, [sys.executable, str(consumer), "{input}", str(counter)])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse((self.out / "repro.txt").exists())

    def test_timeout_is_not_a_preserved_failure(self):
        source = self.base / "sleep.txt"
        source.write_text("data\n" * 5)
        result = self.run_crumb(source, [sys.executable, "-c", "import time; time.sleep(10)", "{input}"], "--timeout", "0.15")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse((self.out / "repro.txt").exists())

    @unittest.skipUnless(os.name == "posix", "POSIX process-group cleanup contract")
    def test_timeout_stops_children_in_the_command_process_group(self):
        source = self.base / "sleep.txt"
        source.write_text("data\n")
        marker = self.base / "child-lived"
        child_pid = self.base / "child.pid"
        child = self.script('''
            import pathlib, sys, time
            time.sleep(1)
            pathlib.Path(sys.argv[1]).write_text("child survived")
        ''', "child.py")
        consumer = self.script('''
            import pathlib, subprocess, sys, time
            child = subprocess.Popen([sys.executable, sys.argv[2], sys.argv[3]])
            pathlib.Path(sys.argv[4]).write_text(str(child.pid))
            time.sleep(10)
        ''')
        result = self.run_crumb(
            source, [sys.executable, str(consumer), "{input}", str(child), str(marker), str(child_pid)],
            "--timeout", "0.25",
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        time.sleep(1.1)
        self.assertFalse(marker.exists(), "A timed-out child process remained active")

    def test_empty_failure_needs_explicit_opt_in(self):
        source = self.base / "empty_error.txt"
        source.write_text("data\n" * 4)
        result = self.run_crumb(source, [sys.executable, "-c", "import sys; sys.exit(3)", "{input}"])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_command_cannot_silently_mutate_source(self):
        source = self.base / "mutating.txt"
        source.write_text("original\n")
        consumer = self.script('''
            import pathlib, sys
            pathlib.Path(sys.argv[2]).write_text("changed\\n")
            sys.stderr.write("original changed\\n")
            sys.exit(1)
        ''')
        result = self.run_crumb(source, [sys.executable, str(consumer), "{input}", str(source)])
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_existing_output_is_not_overwritten(self):
        source = self.base / "input.txt"
        source.write_text("trigger\n")
        self.out.mkdir()
        sentinel = self.out / "report.json"
        sentinel.write_text("existing work\n")
        command = [sys.executable, "-c", "import sys; sys.stderr.write('failure\\n');sys.exit(1)", "{input}"]
        result = self.run_crumb(source, command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(sentinel.read_text(), "existing work\n")

    def test_shell_metacharacters_are_literal_arguments(self):
        source = self.base / "data;touch HACKED.txt"
        source.write_text("noise\n" * 20 + "trigger\n")
        marker = self.base / "UNEXPECTED_EXECUTION"
        literal = ";touch " + str(marker)
        consumer = self.script('''
            import pathlib, sys
            assert sys.argv[2].startswith(";touch ")
            if "trigger" in pathlib.Path(sys.argv[1]).read_text():
                sys.stderr.write("trigger failure\\n"); sys.exit(1)
        ''')
        command = [sys.executable, str(consumer), "{input}", literal]
        self.assert_success(self.run_crumb(source, command, "--format", "lines"))
        self.assertFalse(marker.exists())
        self.assertFalse((self.base / "HACKED.txt").exists())
        self.assertEqual((self.out / "repro.txt").read_text(), "trigger\n")

    def test_malformed_json_is_rejected_without_false_reduction(self):
        source = self.base / "broken.json"
        source.write_text('{"broken": [1, 2,}')
        command = [sys.executable, "-c", "import json,sys;json.load(open(sys.argv[1]))", "{input}"]
        result = self.run_crumb(source, command)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse((self.out / "repro.json").exists())

    def test_jsonl_reduction_keeps_whole_records(self):
        source = self.base / "events.jsonl"
        records = [{"key": i, "message": "ordinary"} for i in range(40)]
        records[24] = {"key": "target", "message": "line\\nbreak"}
        source.write_text("".join(json.dumps(r) + "\n" for r in records))
        consumer = self.script('''
            import json, sys
            try:
                rows = [json.loads(line) for line in open(sys.argv[1]) if line.strip()]
            except Exception:
                sys.stderr.write("invalid record\\n"); sys.exit(2)
            if any(row["key"] == "target" for row in rows):
                sys.stderr.write("event failed\\n"); sys.exit(2)
        ''')
        command = [sys.executable, str(consumer), "{input}"]
        self.assert_success(self.run_crumb(source, command))
        repro = self.out / "repro.jsonl"
        reduced = [json.loads(line) for line in repro.read_text().splitlines()]
        self.assertEqual(reduced, [records[24]])
        self.assertEqual(self.reproduce(command, repro).stderr, "event failed\n")

    def test_html_report_escapes_command_output(self):
        source = self.base / "html_error.txt"
        source.write_text("noise\n" * 5 + "trigger\n")
        consumer = self.script('''
            import pathlib, sys
            if "trigger" in pathlib.Path(sys.argv[1]).read_text():
                sys.stderr.write('<img data-crumb-injected="true" src="x" onerror="alert(1)">\\n')
                sys.exit(1)
        ''')
        self.assert_success(self.run_crumb(source, [sys.executable, str(consumer), "{input}"]))
        class TagCollector(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append((tag, dict(attrs)))
        parser = TagCollector()
        parser.feed((self.out / "report.html").read_text())
        self.assertFalse(any("data-crumb-injected" in attrs for _, attrs in parser.tags))

    def test_only_input_path_in_error_is_normalized(self):
        source = self.base / "error path.txt"
        source.write_text("noise\n" * 20 + "trigger\n")
        consumer = self.script('''
            import pathlib, sys
            if "trigger" in pathlib.Path(sys.argv[1]).read_text():
                sys.stderr.write(sys.argv[1] + ": invalid value\\n"); sys.exit(4)
        ''')
        self.assert_success(self.run_crumb(source, [sys.executable, str(consumer), "{input}"]))
        self.assertEqual((self.out / "repro.txt").read_text(), "trigger\n")

    def test_explicit_match_handles_a_changing_record_number(self):
        source = self.base / "numbered.txt"
        source.write_text("noise\n" * 20 + "trigger\n" + "fine\n" * 5)
        consumer = self.script('''
            import pathlib, sys
            lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
            if "trigger" in lines:
                sys.stderr.write(f"record {lines.index('trigger')}: invalid value\\n"); sys.exit(4)
        ''')
        self.assert_success(self.run_crumb(
            source, [sys.executable, str(consumer), "{input}"],
            "--match", r"record [0-9]+: invalid value",
        ))
        self.assertEqual((self.out / "repro.txt").read_text(), "trigger\n")

    def test_stdout_failure_is_handled_without_stderr(self):
        source = self.base / "stdout.txt"
        source.write_text("noise\n" * 20 + "trigger\n")
        consumer = self.script('''
            import pathlib, sys
            if "trigger" in pathlib.Path(sys.argv[1]).read_text():
                print("command failed"); sys.exit(4)
        ''')
        self.assert_success(self.run_crumb(source, [sys.executable, str(consumer), "{input}"]))
        self.assertEqual((self.out / "repro.txt").read_text(), "trigger\n")


if __name__ == "__main__":
    unittest.main()
