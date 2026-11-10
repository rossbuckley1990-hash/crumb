"""First-use contract: prefix a command; refuse an ambiguous guess."""
import json
import base64
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FirstUseTests(unittest.TestCase):
    def test_empty_selection_points_to_setup_or_envelope(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            source = base / "data.csv"
            source.write_text("id\n1\n2\n")
            result = subprocess.run([sys.executable, "-m", "crumb", str(source), "--json", "--out", str(base / "out"), "--", sys.executable, "-c", "import sys; print('setup failed',file=sys.stderr); sys.exit(2)", "{input}"], cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertTrue(report["failure_on_empty_selection"])
            self.assertIn("zero selected data units", report["next_step"])
            self.assertEqual(Path(report["output"]["path"]).read_text(), "id\n")

    def test_prefix_failing_command_without_rewriting_input(self):
        with tempfile.TemporaryDirectory(prefix="crumb prefix ") as name:
            base = Path(name)
            source = base / "input.csv"
            source.write_text("id\nbenign\ntarget\nother\n", encoding="utf-8")
            script = base / "consumer.py"
            script.write_text("import pathlib,sys\np=pathlib.Path(sys.argv[1].split('=',1)[1])\nif 'target' in p.read_text():\n print('target rejected',file=sys.stderr)\n sys.exit(3)\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "crumb", "--json", "--out", str(base / "out"), "--", sys.executable, str(script), "--input=" + str(source)], cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            data = json.loads(result.stdout)
            self.assertTrue(data["verified_final"])
            self.assertEqual(data["output"]["units"], 1)
            self.assertEqual(Path(data["output"]["path"]).read_text(), "id\ntarget\n")
            self.assertEqual(source.read_text(), "id\nbenign\ntarget\nother\n")
            page = (base / "out" / "report.html").read_text(encoding="utf-8")
            download = re.search(r'data:application/octet-stream;base64,([^\"]+)', page)
            self.assertIsNotNone(download)
            self.assertEqual(base64.b64decode(download.group(1)), Path(data["output"]["path"]).read_bytes())
            report_download = re.search(r'data:application/json;base64,([^\"]+)', page)
            self.assertTrue(json.loads(base64.b64decode(report_download.group(1)))["verified_final"])

    def test_multiple_existing_inputs_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            first, second = base / "one.json", base / "two.json"
            first.write_text("[]")
            second.write_text("[]")
            result = subprocess.run([sys.executable, "-m", "crumb", "--json", "--", sys.executable, "program.py", str(first), str(second)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "INPUT_AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
