import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from crumb.core import CrumbError, _Units, reduce_file


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.counter = 0

    def run_case(self, source, script, suffix=".txt", **kwargs):
        self.counter += 1
        path = self.root / (f"source-{self.counter}" + suffix)
        path.write_bytes(source if isinstance(source, bytes) else source.encode())
        code = self.root / f"command-{self.counter}.py"
        code.write_text(script)
        return reduce_file(path, [sys.executable, str(code), "{input}"],
                           output_dir=self.root / f"result-{self.counter}", **kwargs)

    def assert_error(self, code, source, script, **kwargs):
        with self.assertRaises(CrumbError) as caught:
            self.run_case(source, script, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_distant_interacting_csv_records(self):
        lines = ["id,value\n"] + [f"{i},row {i}\n" for i in range(80)]
        lines[4] = "dup,alpha\n"
        lines[76] = "dup,omega\n"
        report = self.run_case("".join(lines), '''import csv,sys
with open(sys.argv[1],newline='') as f: rows=list(csv.DictReader(f))
ids=[r['id'] for r in rows]
if len(ids)!=len(set(ids)):
    print('duplicate-id',file=sys.stderr)
    raise SystemExit(7)
''', suffix=".csv")
        self.assertEqual([3, 75], report["kept_indices"])
        self.assertEqual(2, report["output"]["units"])
        self.assertTrue(report["one_minimal"])
        self.assertTrue(report["verified_final"])
        self.assertEqual("id,value\ndup,alpha\ndup,omega\n", Path(report["output"]["path"]).read_text())

    def test_csv_bom_crlf_multiline_and_vertical_char_preserved(self):
        source = b'\xef\xbb\xbfid,note\r\na,"first\r\nsecond"\r\nb,"vertical\x0btab"\r\nc,end'
        units = _Units(source, ".csv", "auto", None, True)
        self.assertEqual(3, len(units.units))
        self.assertEqual(source, units.render((0, 1, 2)))
        self.assertEqual(b'\xef\xbb\xbfid,note\r\na,"first\r\nsecond"\r\nc,end', units.render((0, 2)))
        self.assertEqual({"index": 0, "start_line": 2, "end_line": 3}, units.locations[0])

    def test_semicolon_dialect_and_no_header(self):
        source = b'1;hello\r\n2;"a;b"\r\n3;last\r\n'
        units = _Units(source, ".csv", "auto", None, False)
        self.assertEqual(b'2;"a;b"\r\n', units.render((1,)))

    def test_nested_json_preserves_scaffolding_and_pointer(self):
        original = {"schema": 42, "meta": [1], "payload": {"items": [0, 1, 2, 17, 3, 4]}}
        report = self.run_case(json.dumps(original), '''import json,sys
obj=json.load(open(sys.argv[1]))
assert obj['schema']==42 and obj['meta']==[1]
if 17 in obj['payload']['items']:
    print('unsupported 17',file=sys.stderr)
    sys.exit(2)
''', suffix=".json")
        output = json.loads(Path(report["output"]["path"]).read_text())
        self.assertEqual({"schema": 42, "meta": [1], "payload": {"items": [17]}}, output)
        self.assertEqual("/payload/items", report["json_pointer"])
        self.assertEqual([{"index": 3, "json_pointer": "/payload/items/3"}], report["source_locations"])

    def test_escaped_json_pointer(self):
        units = _Units(b'{"a/b":{"~key":[1,2]},"other":[8,9]}', ".json", "auto", "/a~1b/~0key", True)
        self.assertEqual({"a/b": {"~key": [2]}, "other": [8, 9]}, json.loads(units.render((1,))))

    def test_ambiguous_json_requires_pointer(self):
        with self.assertRaises(CrumbError) as error:
            _Units(b'{"a":[1,2],"b":[3,4]}', ".json", "auto", None, True)
        self.assertEqual("AMBIGUOUS_JSON", error.exception.code)

    def test_duplicate_json_keys_refused(self):
        with self.assertRaises(CrumbError) as error:
            _Units(b'{"a":1,"a":2,"items":[1]}', ".json", "auto", None, True)
        self.assertEqual("BAD_JSON", error.exception.code)

    def test_same_last_line_is_not_same_failure(self):
        report = self.run_case("HEADER\nnoise\nA\nmore noise\nB\n", '''import sys
lines=open(sys.argv[1]).read().splitlines()
if 'HEADER' not in lines:
    print('missing header\\nimport failed',file=sys.stderr); sys.exit(1)
if 'A' in lines and 'B' in lines:
    print('duplicate-id: target\\nimport failed',file=sys.stderr); sys.exit(1)
''')
        self.assertEqual([0, 2, 4], report["kept_indices"])
        self.assertEqual(3, report["output"]["units"])
        self.assertEqual("exact", report["signature"]["mode"])

    def test_path_normalization(self):
        report = self.run_case("safe\nBOOM\n", '''import sys
if 'BOOM' in open(sys.argv[1]).read():
    print('cannot process '+sys.argv[1]+': BOOM',file=sys.stderr); sys.exit(1)
''')
        self.assertEqual([1], report["kept_indices"])
        self.assertIn("{input}", report["signature"]["text"])

    def test_match_opt_in_handles_variable_counts(self):
        report = self.run_case("a\nb\nBOOM\nc\n", '''import sys
lines=open(sys.argv[1]).readlines()
if any('BOOM' in x for x in lines):
    print(str(len(lines))+' records; failure BOOM',file=sys.stderr); sys.exit(2)
''', match="failure BOOM")
        self.assertEqual([2], report["kept_indices"])
        self.assertEqual("regex", report["signature"]["mode"])

    def test_silent_failure_needs_explicit_opt_in(self):
        script = "import sys; sys.exit(3)"
        self.assert_error("NO_SIGNATURE", "hello\n", script)
        report = self.run_case("hello\n", script, exit_code_only=True)
        self.assertEqual(0, report["output"]["units"])
        self.assertTrue(report["one_minimal"])

    def test_budget_includes_baselines_roundtrip_and_final(self):
        report = self.run_case("a\nb\nBOOM\nc\n", '''import sys
if 'BOOM' in open(sys.argv[1]).read():
    print('BOOM',file=sys.stderr); sys.exit(1)
''', max_runs=5)
        self.assertEqual(5, report["calls"])
        self.assertEqual("budget_exhausted", report["status"])
        self.assertEqual(4, report["output"]["units"])
        self.assertFalse(report["one_minimal"])
        self.assertTrue(report["verified_final"])

    def test_passing_baseline_rejected(self):
        self.assert_error("BASELINE_PASSED", "a\n", "print('hello')")

    def test_flaky_baseline_rejected(self):
        counter = self.root / "counter"
        self.assert_error("UNSTABLE_BASELINE", "a\n", f'''from pathlib import Path
import sys
p=Path({str(counter)!r})
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
print('failure '+str(n),file=sys.stderr)
sys.exit(1)
''')

    def test_original_mutation_detected(self):
        self.assert_error("SOURCE_MUTATED", "a\n", '''import sys
open(sys.argv[1],'w').write('changed')
print('failure',file=sys.stderr)
sys.exit(1)
''')

    def test_candidate_mutation_detected(self):
        self.assert_error("CANDIDATE_MUTATED", "a\n", '''import sys
from pathlib import Path
p=Path(sys.argv[1])
if p.name.startswith('candidate'): p.write_text('changed')
print('failure',file=sys.stderr)
sys.exit(1)
''')

    def test_final_filename_independently_checked(self):
        self.assert_error("FINAL_UNSTABLE", "a\n", '''import sys
from pathlib import Path
if Path(sys.argv[1]).name.startswith('repro'): sys.exit(0)
print('failure',file=sys.stderr)
sys.exit(1)
''')

    def test_json_reserialization_must_reproduce(self):
        self.assert_error("ROUNDTRIP_CHANGED", "[1,2]", '''import sys
if open(sys.argv[1]).read()=='[1,2]':
    print('spacing failure',file=sys.stderr); sys.exit(1)
''', suffix=".json")

    def test_timeout_rejected(self):
        self.assert_error("BASELINE_TIMEOUT", "a\n", "import time; time.sleep(20)", timeout=.1)

    def test_output_limit_is_not_truncated_matching(self):
        self.assert_error("OUTPUT_LIMIT", "a\n", "import sys; sys.stderr.write('x'*2000000); sys.exit(1)")

    def test_existing_directory_is_untouched(self):
        path = self.root / "source.txt"
        path.write_text("a")
        destination = self.root / "existing"
        destination.mkdir()
        with self.assertRaises(CrumbError) as error:
            reduce_file(path, [sys.executable, "{input}"], output_dir=destination)
        self.assertEqual("OUTPUT_EXISTS", error.exception.code)
        self.assertEqual([], list(destination.iterdir()))

    def test_jsonl_physical_lines_preserved(self):
        source = b'\xef\xbb\xbf{"a":1}\r\n{"a":2}\r\n{"last":3}'
        units = _Units(source, ".jsonl", "auto", None, True)
        self.assertEqual(3, len(units.units))
        self.assertEqual(source, units.render((0, 1, 2)))
        self.assertEqual(b'\xef\xbb\xbf{"last":3}', units.render((2,)))

    def test_malformed_jsonl_has_explicit_raw_lines_escape(self):
        with self.assertRaises(CrumbError) as error:
            _Units(b'{"a":1}\n{"bad":', ".jsonl", "auto", None, True)
        self.assertEqual("BAD_JSONL", error.exception.code)
        self.assertIn("--format lines", error.exception.hint)
        units = _Units(b'{"a":1}\n{"bad":', ".jsonl", "lines", None, True)
        self.assertEqual(b'{"bad":', units.render((1,)))

    def test_invalid_utf8_diagnostics_do_not_collide_with_escape_text(self):
        report = self.run_case("keep\n", r'''import sys
if open(sys.argv[1]).read():
    sys.stderr.buffer.write(bytes([255]))
else:
    sys.stderr.buffer.write(b'\\xff')
sys.exit(1)
''')
        self.assertEqual(1, report["output"]["units"])
        self.assertTrue(report["one_minimal"])


if __name__ == "__main__":
    unittest.main()
