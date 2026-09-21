"""Load the subsidy matrices and crop spacings from the client's workbooks.

Migration 009 seeds everything that is text or lives inside a formula: the
scheme, the three systems, the categories, the parameters and the Sprinkler
rates. This loads the four things that only exist as grids in the workbooks:

    unit_cost_matrix   the Drip and Mini Sprinkler unit cost tables, regular and
                       7-year, and the two Sprinkler one-dimensional tables
    quantity_matrix    the Sprinkler quantities by component and area
    crop_lateral_spacing   the 79 crops and their standard lateral spacing

Every grid comes from a **named range**, never a scan: the Sprinkler sheet also
carries a second Jantri series at `M93:M119` that is not the one the quotation
uses (GAP-079), and a scan would find it. The reader is
`scripts/extract_subsidy_fixtures.py`, so the loader and the golden fixtures read
the same cells through the same code.

**Idempotent.** A rerun compares what is in force against the workbook and writes
nothing when they match. It refuses to change a cell of a matrix that is in
force: a revised table is a new matrix, loaded with a later `--effective-from`,
and the loader closes the previous row by writing that date into its
`effective_to`. Closing is `effective_to` alone; `is_active` does not free the
range (migration 009).

    python scripts/load_subsidy_masters.py                      # first load
    python scripts/load_subsidy_masters.py --effective-from 2027-04-01
    python scripts/load_subsidy_masters.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extract_subsidy_fixtures import BOQ, FILES, Book, matrices  # noqa: E402

DEFAULT_EFFECTIVE_FROM = dt.date(2026, 6, 13)   # the date the three workbooks carry
SCHEME = "GGRC"


def _dec(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


class Loader:
    """One transaction, as the owner. The loader is the only writer of these
    tables, so it runs outside RLS and the policies exist for FS-009's screens."""

    def __init__(self, conn: Any, *, effective_from: dt.date, dry_run: bool) -> None:
        self.conn = conn
        self.frm = effective_from
        self.dry_run = dry_run
        self.written: list[str] = []
        self.skipped: list[str] = []

    # ── helpers ──────────────────────────────────────────────────────────────

    def _one(self, sql: str, args: Sequence[Any] = ()) -> Any:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            row = cur.fetchone()
        return None if row is None else row[0]

    def _all(self, sql: str, args: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def _write(self, sql: str, args: Sequence[Any] = ()) -> None:
        if self.dry_run:
            return
        with self.conn.cursor() as cur:
            cur.execute(sql, args)

    @property
    def scheme_id(self) -> str:
        got = self._one("SELECT id FROM subsidy_scheme WHERE code = %s", (SCHEME,))
        if got is None:
            raise SystemExit(f"scheme {SCHEME} is not seeded; run alembic upgrade head first")
        return str(got)

    def _in_force(self, table: str, where: str, args: Sequence[Any]) -> tuple[str, dt.date] | None:
        """The row whose range contains the load date, if any."""
        rows = self._all(
            f"SELECT id, effective_from FROM {table} WHERE {where} "
            "AND daterange(effective_from, effective_to, '[)') @> %s",
            (*args, self.frm))
        return (str(rows[0][0]), rows[0][1]) if rows else None

    def _next_start(self, table: str, where: str, args: Sequence[Any]) -> dt.date | None:
        """The start date of the next revision already on file, if any.

        A revision inserted open-ended overlaps every version that starts later, so
        loading a September table into a scheme that already holds June and November
        aborted on the exclusion constraint - even though September to November is a
        perfectly good window, and loading history before the earliest version failed
        the same way (cross-vendor review, September). Bounding the insert here makes
        both work, and an unbounded revision is still unbounded when nothing follows
        it.
        """
        rows = self._all(
            f"SELECT min(effective_from) FROM {table} WHERE {where} AND effective_from > %s",
            (*args, self.frm))
        return rows[0][0] if rows and rows[0][0] else None

    def _close_previous(self, table: str, where: str, args: Sequence[Any]) -> None:
        """A row still open at the load date is closed at that date, so the new row
        starts where the old one ends and the exclusion constraint is satisfied."""
        self._write(
            f"UPDATE {table} SET effective_to = %s "
            f"WHERE {where} AND effective_from < %s "
            "AND (effective_to IS NULL OR effective_to > %s)",
            (self.frm, *args, self.frm, self.frm))

    # ── unit cost matrices ───────────────────────────────────────────────────

    def unit_cost(self, system: str, variant: str, *, source: str,
                  cells: Iterable[tuple[Decimal | None, Decimal, Decimal]]) -> None:
        cells = list(cells)
        dim = 1 if all(s is None for s, _, _ in cells) else 2
        label = f"unit_cost_matrix {system}/{variant}"
        where = "scheme_id = %s AND system_type = %s AND variant = %s"
        args = (self.scheme_id, system, variant)
        current = self._in_force("unit_cost_matrix", where, args)
        if current is not None:
            mid, frm = current
            live = {(s, a): c for s, a, c in self._all(
                "SELECT lateral_spacing, area_breakpoint, unit_cost FROM unit_cost_cell "
                "WHERE matrix_id = %s", (mid,))}
            wanted = {(s, a): c for s, a, c in cells}
            if _same(live, wanted):
                self.skipped.append(f"{label}: unchanged ({len(cells)} cells)")
                return
            if frm == self.frm:
                raise SystemExit(
                    f"{label}: the matrix in force from {frm} differs from the workbook. A revised "
                    f"table is a new matrix: rerun with --effective-from after {frm}.")
            self._close_previous("unit_cost_matrix", where, args)
        self._insert_matrix(system, variant, dim, source, cells, label,
                            until=self._next_start("unit_cost_matrix", where, args))

    def _insert_matrix(self, system: str, variant: str, dim: int, source: str,
                       cells: list[tuple[Decimal | None, Decimal, Decimal]], label: str,
                       *, until: dt.date | None = None) -> None:
        if self.dry_run:
            window = f" to {until}" if until else ""
            self.written.append(f"{label}: would write {len(cells)} cells from {self.frm}{window}")
            return
        mid = self._one(
            "INSERT INTO unit_cost_matrix (scheme_id, system_type, variant, dimensionality, "
            "effective_from, effective_to, source) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "RETURNING id",
            (self.scheme_id, system, variant, dim, self.frm, until, source))
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO unit_cost_cell (matrix_id, lateral_spacing, area_breakpoint, "
                "unit_cost) VALUES (%s, %s, %s, %s)",
                [(mid, s, a, c) for s, a, c in cells])
        window = f" to {until}" if until else ""
        self.written.append(f"{label}: {len(cells)} cells from {self.frm}{window}")

    # ── the Sprinkler quantity matrix ────────────────────────────────────────

    def quantities(self, *, source: str, cells: list[tuple[str, Decimal, Decimal]]) -> None:
        label = "quantity_matrix sprinkler"
        where = "scheme_id = %s AND system_type = %s"
        args = (self.scheme_id, "sprinkler")
        current = self._in_force("quantity_matrix", where, args)
        if current is not None:
            mid, frm = current
            live = {(c, a): q for c, a, q in self._all(
                "SELECT component_code::text, area_breakpoint, qty FROM quantity_matrix_cell "
                "WHERE matrix_id = %s", (mid,))}
            if _same(live, {(c, a): q for c, a, q in cells}):
                self.skipped.append(f"{label}: unchanged ({len(cells)} cells)")
                return
            if frm == self.frm:
                raise SystemExit(f"{label}: differs from the workbook; use --effective-from")
            self._close_previous("quantity_matrix", where, args)
        until = self._next_start("quantity_matrix", where, args)
        window = f" to {until}" if until else ""
        if self.dry_run:
            self.written.append(f"{label}: would write {len(cells)} cells from {self.frm}{window}")
            return
        mid = self._one(
            "INSERT INTO quantity_matrix (scheme_id, system_type, effective_from, effective_to, "
            "source) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (self.scheme_id, "sprinkler", self.frm, until, source))
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO quantity_matrix_cell (matrix_id, component_code, area_breakpoint, qty)"
                " VALUES (%s, %s, %s, %s)", [(mid, c, a, q) for c, a, q in cells])
        self.written.append(f"{label}: {len(cells)} cells from {self.frm}{window}")

    # ── crops ────────────────────────────────────────────────────────────────

    def crops(self, rows: list[tuple[str, Decimal, int]]) -> None:
        """Effective-dated per crop: the standard spacing picks the Jantri row, so a
        change to one crop must not restate a quotation that used the old value."""
        live = {c: (s, f) for c, s, f in self._all(
            "SELECT crop::text, standard_spacing, effective_from FROM crop_lateral_spacing "
            "WHERE scheme_id = %s AND daterange(effective_from, effective_to, '[)') @> %s",
            (self.scheme_id, self.frm))}
        changed = [(crop, spacing, order) for crop, spacing, order in rows
                   if crop not in live or _dec(live[crop][0]) != spacing]
        gone = sorted(set(live) - {crop for crop, _s, _o in rows})
        if not changed and not gone:
            self.skipped.append(f"crop_lateral_spacing: unchanged ({len(rows)} crops)")
            return
        # The same refusal the matrices give, for the same reason: a crop row in
        # force from this very date cannot be revised in place, and without this
        # the insert below hits the exclusion constraint and the operator reads a
        # constraint name instead of the instruction (code review F-8).
        same_day = [crop for crop, _s, _o in changed
                    if crop in live and live[crop][1] == self.frm]
        if same_day:
            raise SystemExit(
                f"crop_lateral_spacing: {len(same_day)} crop(s) in force from {self.frm} differ "
                f"from the workbook, starting with {same_day[0]!r}. A revised spacing is a new "
                f"row: rerun with --effective-from after {self.frm}.")
        if self.dry_run:
            closing = f", closing {len(gone)} no longer in the workbook" if gone else ""
            self.written.append(
                f"crop_lateral_spacing: would write {len(changed)} of {len(rows)}{closing}")
            return
        for crop in gone:
            # A crop the workbook has dropped is closed, not left in force.
            self._close_previous("crop_lateral_spacing", "scheme_id = %s AND crop = %s",
                                 (self.scheme_id, crop))
        for crop, spacing, order in changed:
            where = "scheme_id = %s AND crop = %s"
            if crop in live:
                self._close_previous("crop_lateral_spacing", where, (self.scheme_id, crop))
            self._write(
                "INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, sort_order, "
                "effective_from, effective_to) VALUES (%s, %s, %s, %s, %s, %s)",
                (self.scheme_id, crop, spacing, order, self.frm,
                 self._next_start("crop_lateral_spacing", where, (self.scheme_id, crop))))
        self.written.append(f"crop_lateral_spacing: {len(changed)} of {len(rows)} crops"
                            + (f", {len(gone)} closed" if gone else ""))


def _same(live: dict[Any, Any], wanted: dict[Any, Any]) -> bool:
    """Equal at the precision the column stores, `numeric(14,4)`, which rounds
    rather than truncates the workbook's floats."""
    if set(live) != set(wanted):
        return False
    return all(_dec(live[k]).compare(_dec(v).quantize(Decimal("0.0001"))) == 0
               for k, v in wanted.items())


def _cells_2d(grid: dict[str, Any]) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    areas = [_dec(a) for a in grid["areas"]]
    return [(_dec(row["spacing"]), area, _dec(cost))
            for row in grid["rows"]
            for area, cost in zip(areas, row["costs"], strict=True)]


def _cells_1d(table: dict[str, Any]) -> list[tuple[Decimal | None, Decimal, Decimal]]:
    return [(None, _dec(r["area"]), _dec(r["cost"])) for r in table["rows"]]


def _read_books() -> dict[str, Book]:
    books = {}
    for key, name in FILES.items():
        path = BOQ / name
        if not path.exists():
            raise SystemExit(f"{key}: {name} not found under {BOQ}. The three files are named, "
                             f"never globbed: data/boq also holds a '(1)' copy and a .xls that "
                             f"openpyxl cannot open.")
        books[key] = Book(path)
    return books


def load(conn: Any, *, effective_from: dt.date, dry_run: bool = False) -> Loader:
    data = matrices(_read_books())
    loader = Loader(conn, effective_from=effective_from, dry_run=dry_run)

    for system in ("drip", "mini_sprinkler"):
        for variant in ("regular", "seven_year"):
            grid = data[system][variant]
            loader.unit_cost(system, variant, source=grid["source"], cells=_cells_2d(grid))
    for variant in ("regular", "seven_year"):
        table = data["sprinkler"][variant]
        loader.unit_cost("sprinkler", variant, source=table["source"], cells=_cells_1d(table))

    quantities = data["sprinkler"]["quantities"]
    areas = [_dec(a) for a in quantities["areas"]]
    loader.quantities(source=quantities["source"], cells=[
        (component["code"], area, _dec(qty))
        for component in quantities["components"]
        for area, qty in zip(areas, component["qty"], strict=True)])

    loader.crops([(" ".join(str(r["crop"]).split()), _dec(r["standard_spacing"]), i)
                  for i, r in enumerate(data["crops"]["rows"])])
    return loader


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--effective-from", type=dt.date.fromisoformat,
                        default=DEFAULT_EFFECTIVE_FROM,
                        help="the date the loaded tables come into force (default 2026-06-13)")
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = parser.parse_args(argv)

    import psycopg

    from api.config import get_settings

    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn) as conn:
        loader = load(conn, effective_from=args.effective_from, dry_run=args.dry_run)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    for line in loader.written:
        print("  wrote  ", line)
    for line in loader.skipped:
        print("  skipped", line)
    if args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
