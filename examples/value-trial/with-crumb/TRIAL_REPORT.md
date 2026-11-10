# With-Crumb debugging trial

## Timing and invocation accounting

- Start: 2026-11-10T13:26:28Z (first shell output).
- Full verification finished: 2026-11-10T13:33:06Z.
- Report completion: 2026-11-10T13:40:02Z.
- Actual elapsed through report completion: 814.247 seconds. The five-minute target was exceeded; no claim of meeting it is made.
- 7 shell invocations (`exec_command`), including the final report-writing invocation; 1 polling invocation (`write_stdin`); 1 source/test edit (`apply_patch`); 1 skill read. These were dispatched through 8 `functions.exec` calls. Registry filtering used in-memory metadata and no additional tool. One status message was sent to the parent coordinator. Crumb internally launched the importer 64 times; these are additional subprocess executions, not 64 shell-tool invocations.
- Runtime skill read was incidental environment overhead. Its requested environment status tool was unavailable in the registry. No network was used.

## Outcome

Fixed `OrderLine.identity` to include supplier: `(supplier, order_ref, line_number)`. Previously it returned only `(order_ref, line_number)`, putting every supplier in one namespace. Two legitimate records from different suppliers therefore entered the conflict branch.

The reduced fixture is `orders.crumb/repro.csv`, 145 bytes, header plus two records:

```csv
supplier,order_ref,line_number,sku,qty,unit_price,currency
north-star,PO-73042,1,SKU-181,3,24.50,GBP
south-bay,PO-73042,1,SKU-392,2,41.75,GBP
```

The unchanged original implementation was saved as `import_orders.original.py`; it still rejects this fixture with `Import failed: two revisions disagree on an order line`. The fixed importer accepts it, with separate supplier amounts 73.50 GBP and 83.50 GBP. The parser, decimal arithmetic, identical-line deduplication, and conflict branch were retained.

`test_import_orders.py` adds five regression tests covering the reduced failure, byte-identical retransmission counting, conflicting SKU/quantity/price/currency within one supplier, separate supplier/currency totals with decimal fractions, and invalid input error behavior. Five tests passed (0.450 seconds). No other workspace was inspected.

## Full original input

6,002 data records; 6,000 unique lines; 6,000 supplier/order pairs; 2 retransmissions. The only repeated supplier/order/line keys in the full input were identical rows for south-bay/PO-100013/4 and south-bay/PO-100201/2.

The repaired command returned exit 0, no stderr, and:

```json
{"orders": 6000, "retransmissions": 2, "totals": [{"amount": "723282.72", "currency": "EUR", "supplier": "cedar-grove"}, {"amount": "716993.00", "currency": "GBP", "supplier": "green-field"}, {"amount": "715088.06", "currency": "GBP", "supplier": "north-star"}, {"amount": "723404.77", "currency": "EUR", "supplier": "south-bay"}, {"amount": "83.50", "currency": "GBP", "supplier": "south-bay"}], "unique_lines": 6000}
```

An independent integer-cents oracle matched the entire JSON result. The original file remained 268,233 bytes and its SHA-256 before and after was `3a293ca684df18d4356c06ec24b81e6f903cbb09da64c78fd3d17d9d8008e1e2`.

## Crumb contribution and overhead

The source already made the missing supplier in the identity property apparent before reduction completed. Therefore reduction did not uniquely discover the diagnosis. It did supply the required compact reproducer automatically, with source locations, exact failure matching, two final confirmations, and input-integrity checks. This was useful for exposing both conflicting supplier identities side by side and for writing a durable regression test.

Crumb took 3.4827 seconds and 64 importer executions, shrinking 6,002 records to 2 (99.97% unit reduction, 99.95% byte reduction). It reported complete, verified_final=true, one_minimal=true, source_unchanged=true. Exact stderr signature: `Import failed: two revisions disagree on an order line\n`, return code 1. Kept zero-based indices [183, 5751], corresponding to original physical lines 185 and 5753. There were 27 matched outcomes and 36 different outcomes, with no timeout/output-limit outcome. The command/help/poll and output review were real overhead. A direct search by repeated order identity could also have produced a two-row fixture quickly for this visible bug; this trial does not establish that Crumb accelerated diagnosis or overall completion.

## Exact investigative and verification commands

All shell commands below ran in `/workspace/scratch/00545f7f48fa/research/value-trial/with-crumb`. Multiple lines within a numbered block belonged to one shell invocation. The final seventh invocation wrote this report using Python and recorded its completion timestamp; its document-writing payload is not recursively included here.

### 1. Inspect task and files

```sh
date -u +'%Y-%m-%dT%H:%M:%SZ'
pwd
cat TASK.txt
rg --files -g '!TRIAL_REPORT.md' -g '!__pycache__/**' .
```

Result: start time above; files were TASK.txt, orders.csv, and import_orders.py. Task required supplier-scoped identities, retransmission handling, conflicts as errors, separate exact monetary totals, compact reproducer, and full-input verification.

### 2. Inspect source, establish baseline, read Crumb usage

```sh
cat import_orders.py
wc -l -c orders.csv
head -n 6 orders.csv
sha256sum orders.csv
python3 import_orders.py orders.csv
PYTHONPATH=/workspace/scratch/00545f7f48fa/crumb python3 -m crumb --help
```

Result: 6,003 physical lines / 268,233 bytes, hash above. Original importer printed `Import failed: two revisions disagree on an order line`. Crumb help showed CSV support, exact failure matching, input placeholder, and a default maximum of 200 runs. The shell's aggregate exit was 0 because the final help command succeeded; Crumb subsequently independently verified the importer's failing exit code 1.

### 3. Reduce the failing input

```sh
PYTHONPATH=/workspace/scratch/00545f7f48fa/crumb python3 -m crumb orders.csv --json -- python3 import_orders.py '{input}'
```

Result: completed successfully with the measurements above. One `write_stdin` poll read the completion output. Outputs: `orders.crumb/repro.csv`, `orders.crumb/report.json`, `orders.crumb/report.html`, `orders.crumb/reproduce.txt`.

### 4. Verify reduced failure and audit complete input identities

```sh
cat orders.crumb/repro.csv
python3 import_orders.py orders.crumb/repro.csv
python3 - <<'PYCODE'
import csv
from collections import defaultdict
from pathlib import Path
rows = list(csv.DictReader(Path('orders.csv').open(newline='', encoding='utf-8-sig')))
by_key = defaultdict(list)
for row in rows:
    by_key[(row['supplier'], row['order_ref'], row['line_number'])].append(row)
print('rows',len(rows),'unique_supplier_order_lines',len(by_key),'duplicate_groups', [(key,len(group),len({tuple(x.values()) for x in group})) for key,group in by_key.items() if len(group)>1])
PYCODE
```

Observed: fixture shown above, same failure stderr, `rows 6002 unique_supplier_order_lines 6000 duplicate_groups [(('south-bay', 'PO-100013', '4'), 2, 1), (('south-bay', 'PO-100201', '2'), 2, 1)]`.

### 5. Preserve original program

```sh
cp import_orders.py import_orders.original.py
```

Result: exit 0. Then one `apply_patch` invocation changed the identity property and added `test_import_orders.py`.

### 6. Run regression suite, full input, independent oracle, original repro

```sh
python3 -m unittest -v test_import_orders.py
python3 import_orders.py orders.csv
python3 - <<'PYCODE'
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from collections import defaultdict
path = Path('orders.csv')
rows = list(csv.DictReader(path.open(newline='', encoding='utf-8-sig')))
unique = {}
retransmissions = 0
for row in rows:
    key = (row['supplier'], row['order_ref'], int(row['line_number']))
    if key in unique:
        assert row == unique[key], 'conflicting full-input records'
        retransmissions += 1
    else:
        unique[key] = row
totals = defaultdict(int)
for row in unique.values():
    whole, fraction = row['unit_price'].split('.')
    cents = int(whole) * 100 + int(fraction.ljust(2, '0'))
    totals[(row['supplier'], row['currency'])] += int(row['qty']) * cents
expected = {
    'unique_lines': len(unique), 'retransmissions': retransmissions,
    'orders': len({(row['supplier'], row['order_ref']) for row in unique.values()}),
    'totals': [{'supplier': supplier, 'currency': currency, 'amount': f'{amount//100}.{amount%100:02d}'}
               for (supplier, currency), amount in sorted(totals.items())],
}
result = subprocess.run([sys.executable, 'import_orders.py', 'orders.csv'], capture_output=True, text=True)
assert result.returncode == 0, result.stderr
assert result.stderr == ''
assert json.loads(result.stdout) == expected, (result.stdout, expected)
digest = hashlib.sha256(path.read_bytes()).hexdigest()
assert digest == '3a293ca684df18d4356c06ec24b81e6f903cbb09da64c78fd3d17d9d8008e1e2'
print('Independent integer-cents full-input oracle: PASS')
print('Input SHA-256 unchanged:', digest)
print(json.dumps(expected, sort_keys=True))
PYCODE
python3 import_orders.original.py orders.crumb/repro.csv
date -u +'%Y-%m-%dT%H:%M:%SZ'
```

Observed: all five tests passed; full-input JSON above; `Independent integer-cents full-input oracle: PASS`; unchanged SHA-256 above; original reproducer still produced the conflict error; timestamp 2026-11-10T13:33:06Z.

The heredoc delimiters above are renamed PYCODE only for document embedding; Python bodies and executable arguments are the executed commands.
