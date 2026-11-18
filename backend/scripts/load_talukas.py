"""Load talukas under their districts from a CSV (FS-087).

The CSV (`data/masters/talukas.csv`) has one row per taluka: state_code, district,
taluka, source_row. It is cleaned from the client's territory list first; this
script never reads the client's sheet.

In one transaction:

- each district is found under its state by name (`canonical()` equality, never a
  close spelling); a row whose state or district is missing is reported and skipped;
- a taluka already under its district is left alone; one soft-deleted there is
  reported and not re-added;
- every other row is inserted at level `taluka`. The closure trigger (002) files it
  under the district and the state.

Any problem (a repeated row, two districts that are one by name) stops the load
before a write. Idempotent: a second run adds nothing. No activity_event: the
territory master is not a tracked entity, as with load_districts.py.

    python scripts/load_talukas.py --csv data/masters/talukas.csv --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.domain.talukas import HeldDistrict, HeldTaluka, TalukaRow, plan_talukas  # noqa: E402

COLUMNS = ("state_code", "district", "taluka")


def read_rows(path: Path) -> list[TalukaRow]:
    """`-` reads stdin: deploy_staging.py sends the CSV that way."""
    if str(path) == "-":
        return parse(io.StringIO(sys.stdin.buffer.read().decode("utf-8-sig")), "stdin")
    with path.open(encoding="utf-8-sig") as fh:
        return parse(fh, path.name)


def parse(fh: Any, name: str) -> list[TalukaRow]:
    reader = csv.DictReader(fh)
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit(f"{name}: no column {', '.join(missing)}")
    return [TalukaRow((r.get("state_code") or "").strip(), (r.get("district") or "").strip(),
                      (r.get("taluka") or "").strip(), (r.get("source_row") or "").strip())
            for r in reader]


def load(conn: Any, rows: list[TalukaRow]) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT upper(code::text) FROM territory WHERE level = 'state' "
                "AND deleted_at IS NULL AND code IS NOT NULL")
    states = {c for (c,) in cur.fetchall()}
    cur.execute(
        "SELECT d.id::text, upper(s.code::text), d.name FROM territory d "
        "JOIN territory s ON s.id = d.parent_id AND s.level = 'state' AND s.deleted_at IS NULL "
        "WHERE d.level = 'district' AND d.deleted_at IS NULL AND s.code IS NOT NULL")
    districts = [HeldDistrict(i, s, n) for i, s, n in cur.fetchall()]
    # soft-deleted talukas included: rule 4 reports them rather than adding a second
    cur.execute("SELECT t.id::text, t.parent_id::text, t.name, t.deleted_at IS NOT NULL "
                "FROM territory t WHERE t.level = 'taluka' AND t.parent_id IS NOT NULL")
    talukas = [HeldTaluka(i, p, n, d) for i, p, n, d in cur.fetchall()]

    plan = plan_talukas(rows, states, districts, talukas)
    if plan.problems:
        raise SystemExit("nothing loaded; the list has problems:\n  "
                         + "\n  ".join(plan.problems))
    for add in plan.adds:
        # the parent is a district by construction (rule 3): the DB has no level check
        cur.execute("INSERT INTO territory (parent_id, level, name) VALUES (%s, 'taluka', %s)",
                    (add.district.id, add.row.taluka))
    out = [f"talukas added: {len(plan.adds)}",
           f"already there: {len(plan.present)}"]
    for row, held in plan.deleted:
        out.append(f"deleted, not re-added: {row.taluka!r} under {row.district} "
                   f"(row {row.source_row}, territory {held.id})")
    for row, why in plan.skipped:
        out.append(f"skipped row {row.source_row} {row.taluka!r}: {why}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--csv", type=Path, required=True, help="the talukas CSV, or - for stdin")
    parser.add_argument("--dry-run", action="store_true", help="do it all, report, roll back")
    args = parser.parse_args(argv)
    rows = read_rows(args.csv)

    import psycopg

    from api.config import get_settings

    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn, prepare_threshold=None) as conn:
        try:
            lines = load(conn, rows)
        except psycopg.errors.UniqueViolation:
            conn.rollback()
            raise SystemExit("nothing loaded: a taluka was added by someone else meanwhile; "
                             "run it again") from None
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    for line in lines:
        print(" ", line)
    print("  dry run: everything above was done and rolled back" if args.dry_run
          else "  committed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
