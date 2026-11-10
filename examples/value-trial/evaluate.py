"""Independent oracle. Keep outside both agent workspaces during the trial."""
from pathlib import Path
import csv
from decimal import Decimal
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
FIELDS = ["supplier", "order_ref", "line_number", "sku", "qty", "unit_price", "currency"]


def run(consumer, data):
    result = subprocess.run([sys.executable, str(consumer), str(data)],
                            text=True, capture_output=True, timeout=15)
    return result


def expected_summary(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        raw = list(csv.DictReader(stream))
    records = {}
    repeats = 0
    for row in raw:
        key = (row["supplier"], row["order_ref"], int(row["line_number"]))
        normalized = (row["sku"], int(row["qty"]), Decimal(row["unit_price"]), row["currency"])
        if key in records:
            if records[key] != normalized:
                raise ValueError("independent oracle found conflicting record")
            repeats += 1
        else:
            records[key] = normalized
    totals = {}
    for (supplier, order, line), (_, qty, price, currency) in records.items():
        key = (supplier, currency)
        totals[key] = totals.get(key, Decimal(0)) + qty * price
    return {
        "unique_lines": len(records),
        "retransmissions": repeats,
        "orders": len({(supplier, order) for supplier, order, _ in records}),
        "totals": [{"supplier": supplier, "currency": currency, "amount": f"{amount:.2f}"}
                   for (supplier, currency), amount in sorted(totals.items())],
    }


def main():
    workspace = Path(sys.argv[1]).resolve()
    consumer = workspace / "import_orders.py"
    data = workspace / "orders.csv"
    findings = {}
    findings["original_unchanged"] = hashlib.sha256(data.read_bytes()).hexdigest() == (ROOT / "original-input.sha256").read_text().strip()
    result = run(consumer, data)
    try:
        actual = json.loads(result.stdout)
    except ValueError:
        actual = None
    findings["full_input_correct"] = result.returncode == 0 and actual == expected_summary(data)
    findings["full_input_exit"] = result.returncode
    with tempfile.TemporaryDirectory(prefix="crumb-independent-oracle-") as td:
        case = Path(td) / "probe.csv"
        a = ["vendor-a", "ORDER-1", "1", "ITEM-X", "2", "12.50", "GBP"]
        b = ["vendor-b", "ORDER-1", "1", "ITEM-Y", "3", "9.99", "EUR"]
        for name, rows, success in [
            ("retransmission_deduplicated", [a, a], True),
            ("different_supplier_separate", [a, b], True),
            ("same_key_conflict_rejected", [a, [*a[:4], "7", *a[5:]]], False),
        ]:
            with case.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(FIELDS)
                writer.writerows(rows)
            observed = run(consumer, case)
            if success:
                try:
                    findings[name] = observed.returncode == 0 and json.loads(observed.stdout) == expected_summary(case)
                except ValueError:
                    findings[name] = False
            else:
                findings[name] = observed.returncode == 1 and "conflict" in observed.stderr.lower() or observed.returncode == 1 and "disagree" in observed.stderr.lower()
    repros = []
    for candidate in workspace.rglob("*.csv"):
        if candidate == data:
            continue
        try:
            with candidate.open(newline="", encoding="utf-8-sig") as stream:
                rows = list(csv.reader(stream))
            if not rows or rows[0] != FIELDS or len(rows) > 11:
                continue
            before = run(ROOT / "original_importer.py", candidate)
            after = run(consumer, candidate)
            if before.returncode == 1 and "two revisions disagree" in before.stderr and after.returncode == 0:
                repros.append({"path": str(candidate.relative_to(workspace)), "records": len(rows) - 1})
        except (OSError, csv.Error, UnicodeError, subprocess.TimeoutExpired):
            pass
    findings["compact_reproducer_verified"] = bool(repros)
    findings["reproducers"] = sorted(repros, key=lambda r: r["records"])
    gates = ["original_unchanged", "full_input_correct", "retransmission_deduplicated", "different_supplier_separate", "same_key_conflict_rejected", "compact_reproducer_verified"]
    findings["all_gates_pass"] = all(findings[key] for key in gates)
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
