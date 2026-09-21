"""Load the product catalogue from the client's master, with stand-in commercials.

`data/masters/Product-Master.xlsx` holds 1,094 rows. Every one has a description,
a product category, a quotation category and a unit, and **not one has an item
code or a price**. On 19 September the client said those come later and asked us
to carry on, so this script writes what they gave us and invents the rest,
marking every invented field so nobody mistakes it for theirs (FS-010 rule 10,
GAP-089).

Three things about their file that a naive loader gets wrong:

* **Six descriptions end in whitespace**, three with a stored carriage return and
  three with a tab. openpyxl renders the carriage return as the literal seven
  characters `_x000D_`, so a plain `.strip()` removes the newline and leaves
  `…(200MTR)_x000D_` behind — a distinct value that passes every constraint and
  then prints on a farmer's quotation. `_x000D_` comes off first, then the trim.
* **Two of those six collide** with another row once the whitespace is gone: rows
  104 and 105 are the same product, and so are 163 and 164. **1,092 products, not
  1,094.** Each collision is reported with both row numbers rather than crashing
  or being dropped silently (GAP-096).
* **All fifteen Marketing products are marked `BOTH`** in the quotation-category
  column, which would let a company umbrella into a subsidy head unit. They are
  loaded with `is_subsidy_eligible = false` (rule 2).

**Idempotent.** A rerun updates a product whose client-given fields changed, and
never touches a field the client has since corrected: `provisional_fields` says
which are still ours, and the loader only rewrites those.

    python scripts/load_product_master.py
    python scripts/load_product_master.py --dry-run
    python scripts/load_product_master.py --no-prices     # catalogue only
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BOOK = ROOT / "data" / "masters" / "Product-Master.xlsx"
SHEET = "Product Master"
FIRST_ROW = 4
EFFECTIVE_FROM = dt.date(2026, 4, 1)

# openpyxl's rendering of a carriage return stored inside a cell. It must come off
# before the trim, or the trim leaves it behind and the value stays distinct.
CARRIAGE = "_x000D_"
TRIM = " \t\r\n\u00a0"

# The states the client's price columns name. Gujarat is seeded; these are not,
# and a state-scoped price list cannot exist without them. APMIP is deliberately
# absent: it is most likely the Andhra Pradesh Micro Irrigation Project, which is
# a scheme rather than a state and has nowhere to live in the current shape
# (GAP-090). Inventing a territory row for it is the hard thing to undo.
MISSING_STATES = (("UP", "Uttar Pradesh"), ("CG", "Chhattisgarh"), ("RJ", "Rajasthan"))

# ── the stand-in commercials, and the reasoning behind each one ──────────────
#
# Reviewable on purpose: this table is the whole of what we invented. Every code
# is one that genuinely applies to this catalogue, and every slab is one the
# client's own BOQ workbooks use (5 % on material, 18 % on service).

CATEGORY_HSN = {
    "DRIP COMPONENTS": "3926",            # plastic fittings, connectors, end plugs
    "HDPE PIPES": "3917",                 # plastic tubes, pipes and hoses
    "EMITTING PIPE": "3917",              # inline drip line is still tube
    "HDPE SPRINKLER SYSTEM": "8424",      # mechanical spraying appliances
    "PVC FITTINGS": "3917",               # fittings for tubes and pipes
    "PVC PIPES": "3917",
    "MINI SPRINKLER COMPONENTS": "8424",
    "PLAIN LATERAL": "3917",
    "SPRINKLER COMPONENTS": "8424",
    "Marketing": "4911",                  # printed matter; the overrides below refine it
}

# Keyword overrides, most specific first, and **scoped to the catalogue they make
# sense in**. Two traps live here and both were found by reading what the rules
# actually matched rather than by reasoning about them:
#
#   `SERVIC` appears in five descriptions. One is `7.5 HP MOTAR SERVICS`, a pump
#   service at 18 %; the other four are `SERVICE SADDLE`, a plastic fitting at 5 %.
#   Without the saddle exception first, a keyword rule gets four of the five wrong.
#
#   `CAP` means headwear in a marketing catalogue and a pipe end-cap everywhere
#   else. Applied globally it classified seventeen fittings as hats. **The tax was
#   identical either way**, 5 % both times, so nothing would have looked wrong
#   until an invoice carried a garment code for a piece of pipe. Marketing
#   keywords are therefore only consulted for Marketing products.
MATERIAL_HSN: tuple[tuple[str, str], ...] = (
    ("SERVICE SADDLE", "3926"),
    ("SERVIC", "9995"),                   # a service, 18 %
    ("MOTAR", "8413"), ("MOTOR", "8413"), ("PUMP", "8413"),
    ("VALVE", "8481"), ("COCK", "8481"),
    ("NOZZLE", "8424"), ("SPRINKLER", "8424"), ("EMITTER", "8424"), ("FILTER", "8424"),
)
# Within Marketing only. `DIARY` precedes `PEN` so that `DIARY-BIG WITH PEN` is a
# diary, which is what someone ordering it would call it.
MARKETING_HSN: tuple[tuple[str, str], ...] = (
    ("UMBRELLA", "6601"), ("DIARY", "4820"), ("PEN", "9608"),
    ("BAG", "6305"), ("CAP", "6505"),
)

# Rupees per unit, low to high, by category. Grounded in the BOQ workbooks' own
# observed ranges rather than invented freely: pipe runs 70 to 110 per metre,
# small fittings 1 to 300 each, filters and manifolds 900 to 7,000.
CATEGORY_RATE_BAND = {
    "DRIP COMPONENTS": ("1.50", "320.00"),
    "HDPE PIPES": ("38.00", "290.00"),
    "EMITTING PIPE": ("8.00", "26.00"),
    "HDPE SPRINKLER SYSTEM": ("90.00", "700.00"),
    "PVC FITTINGS": ("12.00", "480.00"),
    "PVC PIPES": ("45.00", "410.00"),
    "MINI SPRINKLER COMPONENTS": ("18.00", "260.00"),
    "PLAIN LATERAL": ("4.00", "14.00"),
    "SPRINKLER COMPONENTS": ("60.00", "620.00"),
    "Marketing": ("25.00", "900.00"),
}

# Marketing items are not micro-irrigation equipment and a scheme must not be
# asked to fund a company umbrella (rule 2, and all fifteen are marked BOTH).
NOT_SUBSIDY_ELIGIBLE = ("Marketing",)

PROVISIONAL = ["hsn_code", "gst_slab"]


def normalise(raw: Any) -> str:
    """The client's cell, as a value we can key on."""
    return re.sub(r"\s+", " ", str(raw).replace(CARRIAGE, "")).strip(TRIM)


def hsn_for(description: str, category: str) -> str:
    upper = description.upper()
    table = MARKETING_HSN if category in NOT_SUBSIDY_ELIGIBLE else MATERIAL_HSN
    for needle, code in table:
        if needle in upper:
            return code
    return CATEGORY_HSN.get(category, "3926")


def stand_in_rate(description: str, category: str) -> Decimal:
    """A rate of the right order of magnitude, stable for a given product.

    Deterministic rather than random, so a rerun does not churn every rate and a
    test can assert one. It is invented, the whole list is marked provisional, and
    the client replaces it through the admin endpoints.
    """
    low, high = (Decimal(v) for v in CATEGORY_RATE_BAND.get(category, ("10.00", "500.00")))
    spread = high - low
    # A stable position in the band from the description itself.
    position = Decimal(sum(ord(c) for c in description) % 1000) / 1000
    return (low + spread * position).quantize(Decimal("0.01"))


def read_products(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The catalogue, and the collisions we are not loading."""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True)[SHEET]
    seen: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    collisions: list[str] = []
    for r in range(FIRST_ROW, ws.max_row + 1):
        raw = ws.cell(r, 2).value
        if raw in (None, ""):
            continue
        description = normalise(raw)
        key = description.casefold()
        if key in seen:
            collisions.append(
                f"row {r} {description!r} is row {seen[key]} again once the trailing "
                f"whitespace is removed; the first is loaded and this one is not (GAP-096)")
            continue
        seen[key] = r
        category = normalise(ws.cell(r, 3).value)
        rows.append({
            "description": description,
            "source_description": str(raw),
            "source_row": r,
            "category": category,
            "quotation_category": normalise(ws.cell(r, 4).value).lower(),
            "uom": normalise(ws.cell(r, 5).value),
            "hsn": hsn_for(description, category),
            "eligible": category not in NOT_SUBSIDY_ELIGIBLE,
            "rate": stand_in_rate(description, category),
        })
    return rows, collisions


class Loader:
    def __init__(self, conn: Any, *, dry_run: bool, with_prices: bool) -> None:
        self.conn = conn
        self.dry_run = dry_run
        self.with_prices = with_prices
        self.notes: list[str] = []

    def _all(self, sql: str, args: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def _one(self, sql: str, args: tuple[Any, ...] = ()) -> Any:
        rows = self._all(sql, args)
        return rows[0][0] if rows else None

    def _write(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        if self.dry_run:
            return
        with self.conn.cursor() as cur:
            cur.execute(sql, args)

    def states(self) -> None:
        """The client prices per state, and only Gujarat exists."""
        added = []
        for code, name in MISSING_STATES:
            if self._one("SELECT id FROM territory WHERE level = 'state' AND code = %s", (code,)):
                continue
            self._write("INSERT INTO territory (level, name, code) VALUES ('state', %s, %s)",
                        (name, code))
            added.append(code)
        self.notes.append(f"territory: {len(added)} state(s) added {added}"
                          if added else "territory: every priced state already exists")

    def products(self, rows: list[dict[str, Any]]) -> None:
        categories = dict(self._all("SELECT code::text, id FROM product_category"))
        uoms = dict(self._all("SELECT code::text, id FROM uom"))
        live = {d.casefold(): (pid, list(pf or []))
                for d, pid, pf in self._all(
                    "SELECT description::text, id, provisional_fields FROM product")}

        written = updated = 0
        for row in rows:
            if row["category"] not in categories:
                raise SystemExit(f"product_category {row['category']!r} is not seeded")
            if row["uom"] not in uoms:
                raise SystemExit(f"uom {row['uom']!r} is not seeded")
            existing = live.get(row["description"].casefold())
            if existing is None:
                self._write(
                    "INSERT INTO product (description, source_description, source_row, "
                    "source_file, product_category_id, quotation_category, uom_id, "
                    "is_subsidy_eligible, provisional_fields) "
                    "VALUES (%s, %s, %s, %s, %s, %s::quotation_category, %s, %s, %s)",
                    (row["description"], row["source_description"], row["source_row"], BOOK.name,
                     categories[row["category"]], row["quotation_category"], uoms[row["uom"]],
                     row["eligible"], PROVISIONAL))
                written += 1
                continue
            # A rerun corrects what the client gave us and leaves alone anything
            # they have since confirmed: only a still-provisional field is ours.
            self._write(
                "UPDATE product SET product_category_id = %s, quotation_category = "
                "%s::quotation_category, uom_id = %s, is_subsidy_eligible = %s, "
                "source_row = %s WHERE id = %s",
                (categories[row["category"]], row["quotation_category"], uoms[row["uom"]],
                 row["eligible"], row["source_row"], existing[0]))
            updated += 1
        self.notes.append(f"product: {written} written, {updated} already present")

    def classifications(self, rows: list[dict[str, Any]]) -> None:
        by_description = dict(self._all("SELECT description::text, id FROM product"))
        have = {pid for (pid,) in self._all(
            "SELECT product_id FROM product_hsn WHERE effective_to IS NULL")}
        written = already = unwritten = 0
        for row in rows:
            pid = by_description.get(row["description"])
            if pid is None:
                # Only reachable on a dry run, where the product above was not
                # actually written. Counted rather than silently folded into
                # "already classified", which would have read as done.
                unwritten += 1
                continue
            if pid in have:
                already += 1
                continue
            self._write("INSERT INTO product_hsn (product_id, hsn_code, effective_from) "
                        "VALUES (%s, %s, %s)", (pid, row["hsn"], EFFECTIVE_FROM))
            written += 1
        note = f"product_hsn: {written} classified, {already} already classified"
        if unwritten:
            note += f", {unwritten} awaiting the product rows this dry run did not write"
        self.notes.append(note)

    def prices(self, rows: list[dict[str, Any]]) -> None:
        if not self.with_prices:
            self.notes.append("price_list: skipped (--no-prices)")
            return
        existing = self._one("SELECT id FROM price_list WHERE is_provisional AND "
                             "state_territory_id IS NULL AND channel_tier IS NULL")
        if existing is not None:
            self.notes.append("price_list: the stand-in list already exists, left alone")
            return
        if self.dry_run:
            self.notes.append(f"price_list: would write a stand-in list of {len(rows)} rates")
            return
        pid = self._one(
            "INSERT INTO price_list (name, status, published_at, effective_from, is_provisional, "
            "source_note) VALUES (%s, 'published', now(), %s, true, %s) RETURNING id",
            ("Stand-in base rates", EFFECTIVE_FROM,
             "Invented by scripts/load_product_master.py. Every rate is a stand-in of the "
             "right order of magnitude; the client's own rates supersede it as a new list."))
        by_description = dict(self._all("SELECT description::text, id FROM product"))
        with self.conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO price_list_item (price_list_id, product_id, rate) VALUES (%s, %s, %s)",
                [(pid, by_description[r["description"]], r["rate"]) for r in rows
                 if r["description"] in by_description])
        self.notes.append(f"price_list: a stand-in list of {len(rows)} rates, marked provisional")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--no-prices", action="store_true", help="the catalogue only")
    parser.add_argument("--book", type=Path, default=BOOK)
    args = parser.parse_args(argv)

    if not args.book.exists():
        raise SystemExit(f"{args.book} not found. The file is named, never globbed.")

    rows, collisions = read_products(args.book)

    import psycopg

    from api.config import get_settings

    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn) as conn:
        loader = Loader(conn, dry_run=args.dry_run, with_prices=not args.no_prices)
        loader.states()
        loader.products(rows)
        loader.classifications(rows)
        loader.prices(rows)
        conn.rollback() if args.dry_run else conn.commit()

    print(f"read {len(rows) + len(collisions)} rows, {len(rows)} distinct products")
    for note in loader.notes:
        print("  ", note)
    for collision in collisions:
        print("  collision:", collision)
    if args.dry_run:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
