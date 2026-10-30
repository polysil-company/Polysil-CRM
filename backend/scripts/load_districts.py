"""Load the districts under each state from a CSV of the official list (LGD).

The CSV lives outside the repository's shared tree (`data/masters/districts.csv`),
one row per district: state_code, district, lgd_code.

What it does, in one transaction:

- finds each state by its code; a state that does not exist is reported and its
  rows are skipped (seed_prod and load_seller_gstins create the states);
- inserts each district that is not under its state yet, with its LGD code.

**Idempotent.** A district already present (same name under the same state, any
case) is left as it is. Nothing is renamed or removed: a district dropped from the
official list stays, because leads and users may point at it.

    python scripts/load_districts.py --csv data/masters/districts.csv --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as fh:
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
    missing = [r for r in rows if not r["state_code"] or not r["district"]]
    if missing:
        raise SystemExit(f"{len(missing)} rows lack a state code or a district name")
    dupes = [k for k, n in Counter((r["state_code"].upper(), r["district"].lower())
                                   for r in rows).items() if n > 1]
    if dupes:
        raise SystemExit(f"duplicate districts: {dupes}")
    return rows


def load(conn: Any, rows: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    added: Counter[str] = Counter()
    cur = conn.cursor()
    for code in sorted({r["state_code"].upper() for r in rows}):
        cur.execute("SELECT id FROM territory WHERE level = 'state' AND code = %s "
                    "AND deleted_at IS NULL", (code,))
        found = cur.fetchone()
        if found is None:
            out.append(f"skipped   {code}: no such state")
            continue
        state_id = found[0]
        for r in rows:
            if r["state_code"].upper() != code:
                continue
            cur.execute(
                "INSERT INTO territory (parent_id, level, name, lgd_code) "
                "SELECT %s, 'district', %s, nullif(%s, '') WHERE NOT EXISTS ("
                "SELECT 1 FROM territory WHERE parent_id = %s AND deleted_at IS NULL "
                "AND lower(btrim(name)) = lower(btrim(%s)))",
                (state_id, r["district"], r["lgd_code"], state_id, r["district"]))
            added[code] += cur.rowcount
        total = sum(r["state_code"].upper() == code for r in rows)
        out.append(f"{code:<9} {added[code]} added, {total - added[code]} already there")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, required=True, help="the districts CSV")
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
