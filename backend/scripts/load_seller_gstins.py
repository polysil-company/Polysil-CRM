"""Load the client's GST registrations from a CSV of their certificates.

The CSV lives outside the repository's shared tree (`data/masters/seller-gstins.csv`),
one row per registration: state_code, state_name, gstin, legal_name, address,
effective_from (the certificate's date of liability), is_default, source.

What it does, in one transaction:

- creates a state territory for a row whose state does not exist yet, coded as in
  the CSV;
- inserts each registration that is not there, checking its GSTIN check digit;
- makes the row marked `is_default` the default, and retires the migration's
  placeholder (`24AAAAA0000A1Z5`): not default, not active. It lists the draft
  quotations and orders still on the placeholder, which must pick a registration
  before they can be priced again.

**Idempotent.** A registration already present is left as it is and reported.
The input service distributor registration is not a seller and is not in the CSV.

    python scripts/load_seller_gstins.py --csv ../Polysil-CRM/data/masters/seller-gstins.csv --dry-run
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLACEHOLDER = "24AAAAA0000A1Z5"
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def check_digit(gstin: str) -> str:
    """The GSTIN checksum: the 15th character from the first 14."""
    total = 0
    for i, ch in enumerate(gstin[:14]):
        v = _CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return _CHARS[(36 - total % 36) % 36]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    bad = [r["gstin"] for r in rows
           if not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}", r["gstin"])
           or check_digit(r["gstin"]) != r["gstin"][14]]
    if bad:
        raise SystemExit(f"GSTINs failing the format or check digit: {', '.join(bad)}")
    if sum(r["is_default"].strip().lower() == "true" for r in rows) != 1:
        raise SystemExit("exactly one row must have is_default = true")
    return rows


def load(conn: Any, rows: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    cur = conn.cursor()
    for r in rows:
        cur.execute("SELECT id FROM territory WHERE level = 'state' AND code = %s AND deleted_at IS NULL",
                    (r["state_code"],))
        state = cur.fetchone()
        if state is None:
            cur.execute("INSERT INTO territory (level, name, code) VALUES ('state', %s, %s) RETURNING id",
                        (r["state_name"], r["state_code"]))
            state = cur.fetchone()
            out.append(f"state     {r['state_code']} {r['state_name']} created")
        cur.execute("SELECT id FROM seller_gstin WHERE gstin = %s", (r["gstin"],))
        if cur.fetchone() is not None:
            out.append(f"present   {r['gstin']} ({r['state_code']})")
            continue
        cur.execute(
            "INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, address, effective_from) "
            "VALUES (%s, %s, %s, %s, %s)",
            (r["gstin"], r["legal_name"], state[0], r["address"],
             dt.date.fromisoformat(r["effective_from"])))
        out.append(f"added     {r['gstin']} ({r['state_code']}) from {r['effective_from']}")

    default = next(r["gstin"] for r in rows if r["is_default"].strip().lower() == "true")
    # one default at a time (uq_seller_gstin_default): clear, then set
    cur.execute("UPDATE seller_gstin SET is_default = false WHERE is_default AND gstin <> %s", (default,))
    cur.execute("UPDATE seller_gstin SET is_default = true WHERE gstin = %s AND NOT is_default", (default,))
    if cur.rowcount:
        out.append(f"default   {default}")
    cur.execute("UPDATE seller_gstin SET is_active = false WHERE gstin = %s AND is_active", (PLACEHOLDER,))
    if cur.rowcount:
        out.append(f"retired   {PLACEHOLDER} (the migration's placeholder)")
    cur.execute(
        "SELECT 'quotation ' || coalesce(q.quote_no::text, q.id::text) FROM quotation q "
        "JOIN seller_gstin g ON g.id = q.seller_gstin_id WHERE g.gstin = %s AND q.status = 'draft' "
        "AND q.deleted_at IS NULL UNION ALL "
        "SELECT 'order ' || coalesce(o.order_no::text, o.id::text) FROM sales_order o "
        "JOIN seller_gstin g ON g.id = o.seller_gstin_id WHERE g.gstin = %s AND o.status = 'draft' "
        "AND o.deleted_at IS NULL", (PLACEHOLDER, PLACEHOLDER))
    for (doc,) in cur.fetchall():
        out.append(f"re-pick   {doc}: a draft on the placeholder registration")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, required=True, help="the registrations CSV")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)
    rows = read_rows(args.csv)

    import psycopg

    from api.config import get_settings

    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn) as conn:
        lines = load(conn, rows)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    for line in lines:
        print(" ", line)
    if args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
