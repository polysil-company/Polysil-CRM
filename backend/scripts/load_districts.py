"""Load the districts under each state from a CSV of the official list (LGD).

The CSV lives outside the repository's shared tree (`data/masters/districts.csv`),
one row per district: state_code, district, lgd_code.

What it does, in one transaction:

- finds each state by its code; a state that does not exist is reported and its
  rows are skipped (seed_prod and load_seller_gstins create the states);
- inserts each district that is not under its state yet, with its LGD code.

**Idempotent.** A district already present is left as it is. "Present" is FS-085
rule 2 (`api/domain/district_offices.py` `match_districts`): the same LGD code, the
same name ignoring case, spaces and punctuation, a known renaming (Kutch is
Kachchh), or one close spelling. Before 6 Nov it was the exact name only, so a
rerun on a database spelling a district differently added a second copy. Two
candidates for one row stop the load before any write. Nothing is renamed or
removed: a district dropped from the official list stays, because leads and users
may point at it.

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
    from api.domain.district_offices import HeldDistrict, ListedDistrict, match_districts

    out: list[str] = []
    cur = conn.cursor()
    plans = []
    problems: list[str] = []
    for code in sorted({r["state_code"].upper() for r in rows}):
        cur.execute("SELECT id FROM territory WHERE level = 'state' AND code = %s "
                    "AND deleted_at IS NULL", (code,))
        found = cur.fetchone()
        if found is None:
            out.append(f"skipped   {code}: no such state")
            continue
        state_id = found[0]
        cur.execute("SELECT id, name, lgd_code FROM territory WHERE parent_id = %s "
                    "AND level = 'district' AND deleted_at IS NULL", (state_id,))
        held = [HeldDistrict(str(i), n, lgd) for i, n, lgd in cur.fetchall()]
        listed = [ListedDistrict(r["district"], r["lgd_code"]) for r in rows
                  if r["state_code"].upper() == code]
        result = match_districts(code, listed, held)
        problems.extend(result.problems)
        plans.append((code, state_id, result))
    if problems:
        raise SystemExit("nothing loaded; the list and the database disagree:\n  "
                         + "\n  ".join(problems))
    for code, state_id, result in plans:
        for m in result.new:
            cur.execute("INSERT INTO territory (parent_id, level, name, lgd_code) "
                        "VALUES (%s, 'district', %s, nullif(%s, ''))",
                        (state_id, m.listed.name, m.listed.lgd_code))
        how = Counter(m.how for m in result.matches if m.existing is not None)
        found_by = ", ".join(f"{n} by {k}" for k, n in sorted(how.items())) or "none"
        out.append(f"{code:<9} {len(result.new)} added; already there: {found_by}")
        for m in result.matches:
            if m.how in ("alias", "close") and m.existing is not None:
                out.append(f"          {m.listed.name!r} is {m.existing.name!r} ({m.how})")
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
