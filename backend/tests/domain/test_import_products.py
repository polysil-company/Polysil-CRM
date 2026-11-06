"""FS-083: which product a row means, what it changes, and what it refuses.

Pure: a hand-built catalogue of three products, two categories and two units.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from api.domain.imports.cells import name_key
from api.domain.imports.fields import FIELDS, header_score, mapping_problems, suggest
from api.domain.imports.products import (
    UNIT_CHANGE,
    CatalogueLookups,
    Current,
    Master,
    change_counts,
    fingerprint,
    parse_products,
    preview_order,
)
from api.domain.imports.reader import SheetRow
from api.domain.imports.rows import ProductLookups, ProductRef, RowResult

TODAY = dt.date(2026, 11, 6)
DRIP = Master("cat-drip", "DRIP COMPONENTS")
MKT = Master("cat-mkt", "Marketing")
NOS = Master("uom-nos", "NOS.")
MTR = Master("uom-mtr", "MTR")
COLS = ("item_code", "description", "product_category", "quotation_category", "uom",
        "hsn_code", "mrp", "pack_multiple", "is_subsidy_eligible", "is_active")
MAP = {c: i for i, c in enumerate(COLS)}


def _current(pid: str, desc: str, code: str | None = None, *, hsn: str | None = "3917",
             hsn_from: dt.date = dt.date(2026, 4, 1), later: bool = False,
             active: bool = True, provisional: frozenset[str] = frozenset()) -> Current:
    ref = ProductRef(id=pid, description=desc, item_code=code, is_active=active,
                     uom_code="NOS.", uom_decimals=0, pack_multiple=None)
    return Current(ref=ref, category=DRIP, quotation_category="field", uom=NOS, mrp=None,
                   pack_multiple=None, is_subsidy_eligible=True, hsn_code=hsn,
                   hsn_from=hsn_from, hsn_later=later, provisional=provisional)


def _lookups(*cur: Current, deleted: dict[str, tuple[str, str | None]] | None = None
             ) -> CatalogueLookups:
    descriptions = {name_key(c.ref.description): c.ref.id for c in cur}
    codes = {name_key(c.ref.item_code): c.ref.id for c in cur if c.ref.item_code}
    for pid, (d, code) in (deleted or {}).items():
        descriptions[name_key(d)] = pid
        if code:
            codes[name_key(code)] = pid
    masters = {"dripcomponents": DRIP, "marketing": MKT}
    units = {"nos": NOS, "numbers": NOS, "mtr": MTR, "metres": MTR}
    return CatalogueLookups(
        products=ProductLookups.build(c.ref for c in cur), current={c.ref.id: c for c in cur},
        categories=masters, uoms=units, rated_hsn=frozenset({"3917", "3926", "8424"}),
        today=TODAY, descriptions=descriptions, codes=codes,
        deleted=frozenset((deleted or {}).keys()))


CATALOGUE = _lookups(_current("p1", "DRIP PIPE 16MM", "DP16"),
                     _current("p2", "ELBOW 90 MM PN 6"),
                     _current("p3", "OLD FILTER", "OF1", active=False))


def _row(n: int, **cells: str) -> SheetRow:
    return SheetRow(row=n, cells=tuple(cells.get(c, "") for c in COLS))


def _one(lk: CatalogueLookups = CATALOGUE, **cells: str) -> RowResult:
    return parse_products([_row(2, **cells)], MAP, lk)[0]


# ── rule 1: which product ────────────────────────────────────────────────────

def test_the_item_code_finds_the_product_and_a_new_description_renames_it() -> None:
    r = _one(item_code="dp16", description="DRIP PIPE 16 MM CLASS 2")
    assert r.ok, r.errors
    assert r.values["action"] == "update" and r.values["product_id"] == "p1"
    assert r.values["changes"] == {"description": {"from": "DRIP PIPE 16MM",
                                                    "to": "DRIP PIPE 16 MM CLASS 2"}}


def test_a_description_match_keeps_the_catalogue_spelling() -> None:
    """Rule 4: spaces and case differ, so it is the same product, and no rename."""
    r = _one(description="elbow  90 mm pn 6")
    assert r.ok and r.values["action"] == "unchanged" and r.values["product_id"] == "p2"


def test_a_code_on_a_product_without_one_is_set() -> None:
    r = _one(item_code="EL90", description="ELBOW 90 MM PN 6")
    assert r.ok and r.values["changes"] == {"item_code": {"from": None, "to": "EL90"}}


def test_a_description_whose_product_has_another_code_is_refused() -> None:
    r = _one(item_code="NEW1", description="DRIP PIPE 16MM")
    assert "is not this product's item code (DP16)" in r.errors["item_code"]


def test_a_code_and_a_description_naming_two_products_are_refused() -> None:
    r = _one(item_code="DP16", description="ELBOW 90 MM PN 6")
    assert r.errors == {"description": "names a different product from the item code"}


def test_a_product_name_in_the_code_column_is_refused() -> None:
    r = _one(item_code="ELBOW 90 MM PN 6", description="SOMETHING NEW",
             product_category="DRIP COMPONENTS", quotation_category="field", uom="NOS")
    assert "not an item code" in r.errors["item_code"]


def test_a_switched_off_product_still_matches_and_can_be_switched_on() -> None:
    r = _one(item_code="OF1", is_active="yes")
    assert r.ok and r.values["changes"] == {"is_active": {"from": False, "to": True}}


def test_nothing_found_is_a_new_product() -> None:
    r = _one(item_code="NP1", description="NEW PIPE 20MM", product_category="drip components",
             quotation_category="Field", uom="Numbers", hsn_code="3917", mrp="120.5")
    assert r.ok, r.errors
    assert r.values["action"] == "new" and r.values["product_id"] is None
    w = r.values["write"]
    assert w["category_id"] == "cat-drip" and w["uom_id"] == "uom-nos"
    assert w["quotation_category"] == "field" and w["hsn_code"] == "3917"
    assert w["mrp"] == "120.50" and w["is_active"] is True and w["is_subsidy_eligible"] is True


def test_a_new_product_needs_its_description_category_quotation_category_and_unit() -> None:
    r = _one(item_code="NP2")
    assert set(r.errors) == {"description", "product_category", "quotation_category", "uom"}


def test_a_new_marketing_product_is_not_subsidy_eligible_by_default() -> None:
    """FS-010 rule 2."""
    r = _one(description="COMPANY UMBRELLA", product_category="Marketing",
             quotation_category="both", uom="NOS.")
    assert r.ok and r.values["write"]["is_subsidy_eligible"] is False
    r = _one(description="COMPANY UMBRELLA", product_category="Marketing",
             quotation_category="both", uom="NOS.", is_subsidy_eligible="yes")
    assert r.values["write"]["is_subsidy_eligible"] is True


def test_excel_escapes_and_runs_of_spaces_are_tidied_before_saving() -> None:
    r = _one(description="NEW  PIPE_x000D_ ", product_category="DRIP COMPONENTS",
             quotation_category="head", uom="MTR")
    assert r.ok and r.values["write"]["description"] == "NEW PIPE"


# ── what a row changes ───────────────────────────────────────────────────────

def test_a_blank_cell_changes_nothing() -> None:
    """Rule 3."""
    r = _one(item_code="DP16", description="", mrp="", is_active="")
    assert r.ok and r.values["action"] == "unchanged"


def test_an_update_writes_only_the_changed_columns() -> None:
    r = _one(item_code="DP16", product_category="DRIP COMPONENTS", uom="nos", mrp="99",
             is_active="inactive", quotation_category="HEAD")
    assert r.values["write"] == {"id": "p1", "confirm": [], "mrp": "99.00",
                                 "is_active": False, "quotation_category": "head"}
    assert set(r.values["changes"]) == {"quotation_category", "mrp", "is_active"}
    assert r.values["changes"]["is_active"] == {"from": True, "to": False}


def test_a_unit_change_on_an_existing_product_is_refused() -> None:
    """EC-4: stock and open documents are counted in the old unit."""
    assert _one(item_code="DP16", uom="MTR").errors == {"uom": UNIT_CHANGE}


def test_a_change_of_case_or_spacing_alone_is_not_a_rename() -> None:
    """EC-8: it would stamp updated_by on every product, for nothing."""
    assert _one(item_code="DP16", description="drip  pipe 16mm").values["action"] == "unchanged"


def test_a_stand_in_value_stated_again_is_confirmed_without_a_new_hsn_row() -> None:
    """EC-10."""
    lk = _lookups(_current("p1", "DRIP PIPE 16MM", "DP16",
                           provisional=frozenset({"hsn_code", "gst_slab"})))
    r = _one(lk, item_code="DP16", hsn_code="3917")
    assert r.values["action"] == "update"
    assert r.values["write"] == {"id": "p1", "confirm": ["hsn_code", "gst_slab"]}
    assert r.values["changes"]["hsn_code"]["confirmed"] is True
    assert change_counts([r])["hsn_changed"] == 0


def test_a_product_moved_into_marketing_loses_subsidy_eligibility() -> None:
    """EC-15, FS-010 rule 2."""
    r = _one(item_code="DP16", product_category="Marketing")
    assert r.values["write"]["is_subsidy_eligible"] is False


def test_a_row_leaving_a_product_off_is_noted_and_counted() -> None:
    """EC-9."""
    r = _one(item_code="OF1", mrp="10")
    assert r.notes["is_active"] == "switched off"
    assert change_counts([r])["still_off"] == 1


def test_renames_and_switch_offs_are_counted_and_shown_first() -> None:
    """EC-7: past the preview's twentieth row they would be unseen."""
    rows = parse_products([_row(2, description="ELBOW 90 MM PN 6", mrp="5"),
                           _row(3, item_code="DP16", description="DRIP PIPE RENAMED"),
                           _row(4, item_code="OF1", is_active="yes")], MAP, CATALOGUE)
    c = change_counts(rows)
    assert (c["update"], c["renamed"], c["switched_on"], c["switched_off"]) == (3, 1, 1, 0)
    assert [r.row for r in sorted(rows, key=preview_order)] == [3, 2, 4]


def test_unknown_values_are_refused_never_created() -> None:
    r = _one(item_code="DP16", product_category="PUMPS", uom="KG", quotation_category="crop",
             is_active="maybe", mrp="0", pack_multiple="1.2345")
    assert r.errors["product_category"] == "no category 'PUMPS'"
    assert r.errors["uom"] == "no unit 'KG'"
    assert "is not head, field or both" in r.errors["quotation_category"]
    assert set(r.errors) >= {"is_active", "mrp", "pack_multiple"}


# ── HSN (rule 9) ─────────────────────────────────────────────────────────────

def test_a_changed_hsn_is_written_and_the_same_one_is_not() -> None:
    assert _one(item_code="DP16", hsn_code="3917").values["action"] == "unchanged"
    r = _one(item_code="DP16", hsn_code="3926")
    assert r.values["write"] == {"id": "p1", "confirm": [], "hsn_code": "3926"}
    # EC-16: dots and spaces are the same code
    assert _one(item_code="DP16", hsn_code="39.17").values["action"] == "unchanged"


def test_an_hsn_without_a_rate_today_or_badly_formed_is_refused() -> None:
    r = _one(item_code="DP16", hsn_code="9999")
    assert "no GST rate in force today" in r.errors["hsn_code"]
    assert "4 to 8 digits" in _one(item_code="DP16", hsn_code="39A7").errors["hsn_code"]


def test_an_hsn_set_today_or_with_a_later_change_is_refused() -> None:
    lk = _lookups(_current("p1", "DRIP PIPE 16MM", "DP16", hsn_from=TODAY),
                  _current("p2", "ELBOW 90 MM PN 6", later=True))
    assert "set today already" in _one(lk, item_code="DP16", hsn_code="3926").errors["hsn_code"]
    assert "later HSN change" in _one(lk, description="ELBOW 90 MM PN 6",
                                      hsn_code="3926").errors["hsn_code"]


# ── uniqueness (rule 8) ──────────────────────────────────────────────────────

def test_one_row_per_product() -> None:
    a, b = parse_products([_row(2, item_code="DP16", mrp="10"),
                           _row(3, description="drip pipe 16mm", mrp="11")], MAP, CATALOGUE)
    assert a.errors == {"item_code": "the same product as row 3"}
    assert b.errors == {"description": "the same product as row 2"}


def test_two_new_rows_with_one_description_are_both_refused() -> None:
    new = {"product_category": "DRIP COMPONENTS", "quotation_category": "field", "uom": "NOS"}
    a, b = parse_products([_row(2, description="NEW A", **new),
                           _row(3, description="new a", item_code="X1", **new)], MAP, CATALOGUE)
    assert a.errors == {"description": "also on row 3"}
    assert b.errors == {"description": "also on row 2"}


def test_a_rename_onto_another_products_description_is_refused_even_in_a_swap() -> None:
    a, b = parse_products([_row(2, item_code="DP16", description="OLD FILTER"),
                           _row(3, item_code="OF1", description="DRIP PIPE 16MM")],
                          MAP, CATALOGUE)
    # the code match wins; the description names another product, so each row says so
    assert a.errors == {"description": "names a different product from the item code"}
    assert b.errors == {"description": "names a different product from the item code"}
    r = _one(item_code="DP16", description="DRIP PIPE 16MM NEW")
    assert r.ok
    # EC-1: a name another product holds once spacing is ignored
    r = _one(item_code="OF1", description="ELBOW  90 MM PN 6")
    assert r.errors == {"description": "names a different product from the item code"}


def test_a_deleted_products_description_or_code_is_refused() -> None:
    lk = _lookups(_current("p1", "DRIP PIPE 16MM", "DP16"),
                  deleted={"dead": ("GONE PIPE", "GP1")})
    new = {"product_category": "DRIP COMPONENTS", "quotation_category": "field", "uom": "NOS"}
    assert _one(lk, description="GONE PIPE", **new).errors == {
        "description": "a deleted product has this description"}
    assert _one(lk, item_code="GP1", description="FRESH PIPE", **new).errors == {
        "item_code": "a deleted product has this item code"}
    assert _one(lk, item_code="DP16", description="gone pipe").errors == {
        "description": "a deleted product has this description"}


# ── fields ───────────────────────────────────────────────────────────────────

def test_the_clients_own_header_row_matches_every_column() -> None:
    headers = ["Item Code", "Product Description", "Product Category", "Quotation Category",
               "Unit", "Price ", "", "", "", ""]
    assert header_score("products")(headers) == 5
    assert suggest("products", headers) == {"item_code": 0, "description": 1,
                                            "product_category": 2, "quotation_category": 3,
                                            "uom": 4}


def test_the_clients_price_column_is_never_suggested_as_mrp() -> None:
    """EC-3."""
    s = suggest("products", ["Item Code", "Product Description", "Price ", "Rate"],
                {"mrp": "Price "})
    assert "mrp" not in s


def test_the_clients_twin_rows_are_both_refused() -> None:
    """EC-17: the master repeats two descriptions once spacing is tidied."""
    new = {"product_category": "DRIP COMPONENTS", "quotation_category": "Field", "uom": "MTR"}
    a, b = parse_products([_row(2, description="FLAT EMITTING 16-2 (200MTR)", **new),
                           _row(3, description="FLAT EMITTING 16-2  (200MTR)_x000D_", **new)],
                          MAP, CATALOGUE)
    assert a.errors == {"description": "also on row 3"}
    assert b.errors == {"description": "also on row 2"}


def test_a_mapping_needs_the_code_or_the_description() -> None:
    assert mapping_problems("products", {"mrp": 0}, 3) == {
        "mapping.item_code": "match item_code or description"}
    assert mapping_problems("products", {"description": 0}, 3) == {}
    assert {f.key for f in FIELDS["products"]} == set(COLS)


def test_money_is_decimal_text_never_float() -> None:
    r = _one(item_code="DP16", mrp="1,234.5", pack_multiple="2.5")
    assert r.values["write"]["mrp"] == "1234.50" and r.values["write"]["pack_multiple"] == "2.500"
    assert Decimal(r.values["write"]["mrp"]) == Decimal("1234.50")


def test_the_template_says_which_columns_a_new_product_needs() -> None:
    """Plan review N-4."""
    from api.domain.imports.template import needed
    assert needed("products", "uom") == "For a new product"
    assert needed("products", "description") == "Item code or Description"
    assert needed("products", "mrp") == "No"


def test_the_fingerprint_changes_when_a_new_rows_category_resolves_elsewhere() -> None:
    """Code review F-4: a category added between check and commit, whose code
    matches the sheet's name, takes the new product with it. Commit must see it."""
    cells = {"description": "LATERAL END CAP 16MM", "product_category": "DRIP COMPONENTS",
             "quotation_category": "field", "uom": "NOS."}
    other = _lookups(*CATALOGUE.current.values())
    other.categories["dripcomponents"] = Master("cat-new", "DRIP COMPONENTS")
    before, after = _one(**cells), _one(other, **cells)
    assert before.ok and after.ok and before.values["changes"] == after.values["changes"]
    assert fingerprint([before]) != fingerprint([after])
