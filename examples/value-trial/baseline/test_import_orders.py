"""Regression checks for supplier-scoped identity and importer CLI behavior."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from import_orders import FIELDS


ROOT = Path(__file__).resolve().parent


class ImportOrdersRegression(unittest.TestCase):
    def run_file(self, path):
        return subprocess.run(
            [sys.executable, str(ROOT / "import_orders.py"), str(path)],
            capture_output=True, text=True,
        )

    def run_rows(self, rows):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "input.csv"
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(FIELDS)
                writer.writerows(rows)
            return self.run_file(path)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_original_failure_reproducer(self):
        result = self.assert_success(self.run_file(ROOT / "reproducer.csv"))
        self.assertEqual(result, {
            "unique_lines": 2, "retransmissions": 0, "orders": 2,
            "totals": [
                {"supplier": "north-star", "currency": "GBP", "amount": "73.50"},
                {"supplier": "south-bay", "currency": "GBP", "amount": "83.50"},
            ],
        })

    def test_identical_retransmissions_count_once(self):
        row = ["supplier-a", "PO-1", 1, "SKU", 3, "0.10", "GBP"]
        result = self.assert_success(self.run_rows([row, row, row]))
        self.assertEqual(result["unique_lines"], 1)
        self.assertEqual(result["retransmissions"], 2)
        self.assertEqual(result["totals"][0]["amount"], "0.30")

    def test_conflicting_content_remains_an_error(self):
        row = ["supplier-a", "PO-1", 1, "SKU", 3, "0.10", "GBP"]
        for index, value in [(3, "OTHER-SKU"), (4, 4), (5, "0.11"), (6, "EUR")]:
            with self.subTest(field=FIELDS[index]):
                revision = row.copy()
                revision[index] = value
                result = self.run_rows([row, revision])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "Import failed: two revisions disagree on an order line\n")

    def test_totals_are_separate_by_supplier_and_currency(self):
        result = self.assert_success(self.run_rows([
            ["a", "PO-1", 1, "SKU", 3, "0.10", "GBP"],
            ["a", "PO-2", 1, "SKU", 2, "0.20", "EUR"],
            ["b", "PO-1", 1, "SKU", 5, "0.10", "GBP"],
        ]))
        self.assertEqual(result["totals"], [
            {"supplier": "a", "currency": "EUR", "amount": "0.40"},
            {"supplier": "a", "currency": "GBP", "amount": "0.30"},
            {"supplier": "b", "currency": "GBP", "amount": "0.50"},
        ])

    def test_invalid_values_remain_errors(self):
        row = ["a", "PO-1", 1, "SKU", 3, "0.10", "GBP"]
        for index, value in [(0, ""), (2, 0), (4, 0), (4, "1.5"), (5, "-0.01"), (5, "0.001"), (5, "NaN"), (6, "CAD")]:
            with self.subTest(field=FIELDS[index], value=value):
                invalid = row.copy()
                invalid[index] = value
                result = self.run_rows([invalid])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("Import failed: "))

    def test_complete_original_fixture(self):
        result = self.assert_success(self.run_file(ROOT / "orders.csv"))
        expected = json.loads((ROOT / "expected_full_result.json").read_text())
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
