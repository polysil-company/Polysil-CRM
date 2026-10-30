"""The client's product change list of 28 Oct 2026 (Delete and Add sheets), applied
on top of the master by `scripts/load_product_master.py`."""

# ruff: noqa: E501  (inline SQL and test names)

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import openpyxl
import pytest

from scripts.load_product_master import (
    BOOK,
    CHANGES,
    Loader,
    apply_changes,
    read_changes,
    read_products,
    stand_in_rate,
)

REPLACED = {"HDPE PIPES", "HDPE SPRINKLER SYSTEM", "SPRINKLER COMPONENTS"}

# The client's workbooks stay in this repository only; the shared one has no copy.
pytestmark = pytest.mark.skipif(not (BOOK.exists() and CHANGES.exists()),
                                reason="the client's master workbooks are not in this checkout")


@pytest.fixture(scope="module")
def parts() -> tuple[list[dict], list[str], list[dict]]:
    master, _ = read_products(BOOK)
    retire, adds = read_changes(CHANGES)
    return master, retire, adds


def test_the_list_retires_exactly_the_three_categories(parts: tuple) -> None:
    master, retire, _ = parts
    in_three = {r["description"].casefold() for r in master if r["category"] in REPLACED}
    assert len(retire) == 352
    assert {d.casefold() for d in retire} == in_three


def test_the_adds_read_as_the_client_gave_them_without_the_unheaded_column(parts: tuple) -> None:
    _, _, adds = parts
    assert len(adds) == 671
    assert Counter(r["category"] for r in adds) == {
        "HDPE PIPES": 585, "SPRINKLER COMPONENTS": 65, "HDPE SPRINKLER SYSTEM": 21}
    assert {r["quotation_category"] for r in adds} == {"field"}
    # the sixth column is not a price we load (client, 29 Oct); rates are stand-ins
    assert all(set(r) == set(adds[0]) for r in adds) and "price" not in adds[0]
    assert all(r["rate"] == stand_in_rate(r["description"], r["category"]) for r in adds)
    pipe = next(r for r in adds if r["description"] == "HDPE PIPE PE63 PN2 SDR41 DN75MM (IS:4984)")
    assert pipe["uom"] == "MTR"


def test_sprinkler_components_given_field_as_a_unit_get_nos(parts: tuple) -> None:
    """GAP-552."""
    _, _, adds = parts
    units = Counter((r["category"], r["uom"]) for r in adds)
    assert units == {("HDPE PIPES", "MTR"): 585, ("SPRINKLER COMPONENTS", "NOS."): 65,
                     ("HDPE SPRINKLER SYSTEM", "NOS."): 21}


def test_a_product_on_both_sheets_is_kept_as_the_master_has_it(parts: tuple) -> None:
    master, retire, adds = parts
    rows, retire_keys, notes = apply_changes(master, retire, adds)
    assert len(retire_keys) == 349 and len(rows) == 1092 - 349 + 668
    sets = [r for r in rows if re.fullmatch(r"sprinkler set (63mm/3\.2|75mm/2\.5|75mm/3\.2) kg",
                                            r["description"].casefold())]
    assert len(sets) == 3 and {r["uom"] for r in sets} == {"Set."}
    assert all(r["source_file"] == BOOK.name for r in sets)
    assert not any(r["description"].casefold() in retire_keys for r in rows)
    assert "3 on both sheets" in notes[1]


def _book(tmp_path: Path, delete: list[str], add: list[tuple]) -> Path:
    wb = openpyxl.Workbook()
    d = wb.active
    d.title = "Delete"
    d.append(["Item Code", "Description", "Category"])
    for x in delete:
        d.append([None, x, "HDPE PIPES"])
    a = wb.create_sheet("Add")
    a.append(["Item Code", "Product Description", "Product Category", "Quotation Category", "Unit"])
    for row in add:
        a.append([None, *row])
    path = tmp_path / "changes.xlsx"
    wb.save(path)
    return path


def test_a_retire_entry_the_master_does_not_hold_is_reported_and_still_retired(tmp_path: Path, parts: tuple) -> None:
    """A later master that already leaves the product out must not stop seed-prod (review F-7)."""
    master, _, _ = parts
    retire, adds = read_changes(_book(tmp_path, ["NO SUCH PIPE 1MM"], []))
    rows, keys, notes = apply_changes(master, retire, adds)
    assert keys == {"no such pipe 1mm"} and len(rows) == len(master)
    assert any("WARNING 1 to retire are not in the master" in n for n in notes)


def test_a_cell_of_only_spaces_is_no_product(tmp_path: Path) -> None:
    retire, adds = read_changes(_book(tmp_path, ["   "], [("\u00a0 ", "HDPE PIPES", "Field", "MTR")]))
    assert retire == [] and adds == []


def test_a_repeated_add_stops_the_run(tmp_path: Path) -> None:
    row = ("NEW PIPE 20MM", "HDPE PIPES", "Field", "MTR", 12.5)
    with pytest.raises(SystemExit, match="repeats row 2"):
        read_changes(_book(tmp_path, [], [row, row]))


# ── against the database, inside one transaction that is rolled back ──────────

def _as(conn: object, user: str) -> None:
    """Who the next writes are by: an administrator's id, or '' for the loader."""
    conn.execute("SELECT set_config('app.current_user_id', %s, true)", (user,))  # type: ignore[attr-defined]


def _count(conn: object, sql: str, args: tuple = ()) -> int:
    return conn.execute(sql, args).fetchone()[0]  # type: ignore[attr-defined]


def _run(conn: object, rows: list[dict], keys: set[str]) -> list[str]:
    loader = Loader(conn, dry_run=False, with_prices=True)
    loader.products(rows)
    loader.retire(keys)
    loader.classifications(rows)
    loader.prices(rows)
    return loader.notes


@pytest.mark.db
def test_the_load_retires_adds_prices_and_reruns_without_writing(parts: tuple) -> None:
    import psycopg

    from api.config import get_settings

    master, retire, adds = parts
    rows, retire_keys, _ = apply_changes(master, retire, adds)
    dsn = re.sub(r"^postgresql\+\w+://", "postgresql://", str(get_settings().database_url))
    with psycopg.connect(dsn, prepare_threshold=None) as conn:
        try:
            _as(conn, "")
            # production before the list: the master loaded, classified and priced
            before = Loader(conn, dry_run=False, with_prices=True)
            before.products(master)
            before.classifications(master)
            before.prices(master)
            admin = str(conn.execute("SELECT id FROM app_user ORDER BY created_at LIMIT 1").fetchone()[0])

            # An administrator confirms the GST slab of 3917, the way set_tax_rate does:
            # updated_by lands on hundreds of products the list retires (review F-1).
            _as(conn, admin)
            conn.execute("UPDATE product SET updated_by = app_current_user_id() WHERE id IN ("
                         " SELECT product_id FROM product_hsn WHERE hsn_code = '3917' AND effective_to IS NULL)")
            _as(conn, "")
            stamped = _count(conn, "SELECT count(*) FROM product WHERE updated_by IS NOT NULL "
                                   "AND lower(description::text) = ANY(%s)", (sorted(retire_keys),))
            assert stamped > 100

            notes = _run(conn, rows, retire_keys)
            active = {d.casefold() for (d,) in conn.execute(
                "SELECT description::text FROM product WHERE is_active").fetchall()}
            assert not retire_keys & active, "a GST confirmation must not keep a retired product on"
            assert {r["description"].casefold() for r in rows} <= active
            assert not any("WARNING" in n for n in notes), notes

            unit = conn.execute("SELECT u.code::text FROM product p JOIN uom u ON u.id = p.uom_id "
                                "WHERE p.description = %s",
                                ("SPRINKLER PCN (NIPPLE) 63MM WITH GI C CLAMP PN4",)).fetchone()
            assert unit == ("NOS.",)
            # the catalogue the loader owns; other tests leave products of their own
            catalogue = [r["description"] for r in rows]
            assert _count(conn,
                "SELECT count(*) FROM product p WHERE p.description = ANY(%s::citext[]) AND NOT EXISTS ("
                " SELECT 1 FROM price_list_item i JOIN price_list l ON l.id = i.price_list_id"
                " WHERE i.product_id = p.id AND l.is_provisional)", (catalogue,)) == 0
            assert _count(conn,
                "SELECT count(*) FROM product p WHERE p.description = ANY(%s::citext[]) AND NOT EXISTS ("
                " SELECT 1 FROM product_hsn h WHERE h.product_id = p.id AND h.effective_to IS NULL)",
                (catalogue,)) == 0
            assert _count(conn,
                "SELECT count(*) FROM product p JOIN price_list_item i ON i.product_id = p.id "
                "WHERE NOT p.is_active AND i.created_at > now() - interval '1 hour'") == 0, \
                "a retired product was priced"

            # An administrator switches one retired pipe back on; a rerun keeps it on.
            back = sorted(retire_keys)[0]
            _as(conn, admin)
            conn.execute("UPDATE product SET is_active = true WHERE lower(description::text) = %s", (back,))
            _as(conn, "")
            audit_before = _count(conn, "SELECT count(*) FROM audit_log WHERE table_name = 'product'")
            again = _run(conn, rows, retire_keys)
            assert any(n.startswith("retire: 0 switched off") for n in again), again
            assert any("1 switched back on by someone since" in n for n in again), again
            assert any(n.startswith("product: 0 written, 0 corrected") for n in again), again
            assert _count(conn, "SELECT count(*) FROM audit_log WHERE table_name = 'product'") == audit_before, \
                "a rerun wrote to product"
        finally:
            conn.rollback()
