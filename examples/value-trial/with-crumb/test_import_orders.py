import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import import_orders as importer

ROOT = Path(__file__).resolve().parent


class ImportRegression(unittest.TestCase):
    def run_csv(self, rows):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'input.csv'
            with path.open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(importer.FIELDS)
                writer.writerows(rows)
            return subprocess.run(
                [sys.executable, str(ROOT / 'import_orders.py'), str(path)],
                text=True, capture_output=True,
            )

    def test_reduced_original_failure(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / 'import_orders.py'),
             str(ROOT / 'orders.crumb' / 'repro.csv')],
            text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(json.loads(result.stdout), {
            'unique_lines': 2, 'retransmissions': 0, 'orders': 2,
            'totals': [
                {'supplier': 'north-star', 'currency': 'GBP', 'amount': '73.50'},
                {'supplier': 'south-bay', 'currency': 'GBP', 'amount': '83.50'},
            ],
        })

    def test_identical_retransmission_counted_once(self):
        row = ['supplier-a', 'PO-1', '1', 'SKU-A', '3', '0.10', 'GBP']
        result = self.run_csv([row, row])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {
            'unique_lines': 1, 'retransmissions': 1, 'orders': 1,
            'totals': [{'supplier': 'supplier-a', 'currency': 'GBP', 'amount': '0.30'}],
        })

    def test_conflicting_same_supplier_line_is_error(self):
        first = ['supplier-a', 'PO-1', '1', 'SKU-A', '3', '0.10', 'GBP']
        for field, replacement in [(3, 'SKU-B'), (4, '4'), (5, '0.11'), (6, 'USD')]:
            with self.subTest(field=field):
                second = first.copy()
                second[field] = replacement
                result = self.run_csv([first, second])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, 'Import failed: two revisions disagree on an order line\n')

    def test_supplier_and_currency_totals_stay_separate(self):
        result = self.run_csv([
            ['supplier-a', 'PO-1', '1', 'SKU-A', '3', '0.10', 'GBP'],
            ['supplier-a', 'PO-1', '2', 'SKU-A', '1', '0.20', 'GBP'],
            ['supplier-a', 'PO-2', '1', 'SKU-A', '2', '0.10', 'USD'],
            ['supplier-b', 'PO-1', '1', 'SKU-A', '1', '0.10', 'GBP'],
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['totals'], [
            {'supplier': 'supplier-a', 'currency': 'GBP', 'amount': '0.50'},
            {'supplier': 'supplier-a', 'currency': 'USD', 'amount': '0.20'},
            {'supplier': 'supplier-b', 'currency': 'GBP', 'amount': '0.10'},
        ])

    def test_invalid_data_remains_error(self):
        for qty, price, currency in [('0', '1.00', 'GBP'), ('1', '0.001', 'GBP'),
                                     ('1', 'NaN', 'GBP'), ('1', '1.00', 'AUD')]:
            with self.subTest(qty=qty, price=price, currency=currency):
                result = self.run_csv([['supplier-a', 'PO-1', '1', 'SKU-A', qty, price, currency]])
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertTrue(result.stderr.startswith('Import failed:'))


if __name__ == '__main__':
    unittest.main()
