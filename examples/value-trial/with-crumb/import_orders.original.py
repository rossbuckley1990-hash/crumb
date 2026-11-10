"""Import supplier order lines and aggregate payable amounts.

Usage: python import_orders.py orders.csv
CSV schema: supplier,order_ref,line_number,sku,qty,unit_price,currency
Retransmitted identical order lines are deduplicated. Conflicting revisions
must be investigated rather than silently overwriting money amounts.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys

FIELDS = ["supplier", "order_ref", "line_number", "sku", "qty", "unit_price", "currency"]

class ImportFailure(ValueError):
    pass

@dataclass(frozen=True)
class OrderLine:
    supplier: str
    order_ref: str
    line_number: int
    sku: str
    qty: int
    unit_price: Decimal
    currency: str

    @property
    def identity(self):
        return self.order_ref, self.line_number

    @property
    def amount(self):
        return self.unit_price * self.qty

def parse_row(row):
    if set(row) != set(FIELDS) or None in row.values():
        raise ImportFailure("malformed CSV record")
    strings = {key: value.strip() for key, value in row.items()}
    if any(not value for value in strings.values()):
        raise ImportFailure("all fields must be populated")
    try:
        qty = int(strings["qty"])
        number = int(strings["line_number"])
        price = Decimal(strings["unit_price"])
    except (ValueError, InvalidOperation) as exc:
        raise ImportFailure("invalid number") from exc
    if qty <= 0 or number <= 0 or not price.is_finite() or price < 0:
        raise ImportFailure("quantity, line number, or price outside permitted range")
    if price != price.quantize(Decimal("0.01")):
        raise ImportFailure("prices must have at most two decimal places")
    if strings["currency"] not in {"GBP", "EUR", "USD"}:
        raise ImportFailure("unsupported currency")
    return OrderLine(strings["supplier"], strings["order_ref"], number,
                     strings["sku"], qty, price, strings["currency"])

def read_orders(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ImportFailure("unexpected CSV header")
        return [parse_row(row) for row in reader]

def consolidate(lines):
    unique = {}
    retransmissions = 0
    for line in lines:
        existing = unique.get(line.identity)
        if existing is None:
            unique[line.identity] = line
        elif existing == line:
            retransmissions += 1
        else:
            raise ImportFailure("two revisions disagree on an order line")
    return list(unique.values()), retransmissions

def summarize(lines, retransmissions):
    totals = {}
    for line in lines:
        key = (line.supplier, line.currency)
        totals[key] = totals.get(key, Decimal("0.00")) + line.amount
    return {
        "unique_lines": len(lines),
        "retransmissions": retransmissions,
        "orders": len({(line.supplier, line.order_ref) for line in lines}),
        "totals": [
            {"supplier": supplier, "currency": currency, "amount": format(amount, ".2f")}
            for (supplier, currency), amount in sorted(totals.items())
        ],
    }

def main():
    if len(sys.argv) != 2:
        print("Usage: python import_orders.py orders.csv", file=sys.stderr)
        return 1
    try:
        lines, retransmissions = consolidate(read_orders(sys.argv[1]))
        print(json.dumps(summarize(lines, retransmissions), sort_keys=True))
        return 0
    except (ImportFailure, OSError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
