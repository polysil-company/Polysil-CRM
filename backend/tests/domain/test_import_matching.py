"""Import matching fixes (FS-067): the header row found by its names, labels from
above, empty columns never suggested, product names compared as the catalogue
loader wrote them, and the order in which a row finds its product.

The client's master template is rebuilt here: `data/` is not in the CI snapshot.
One test reads the real file when it is present."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest

from api.domain.imports.cells import name_key, redact
from api.domain.imports.fields import header_score, suggest
from api.domain.imports.reader import (
    MAX_DATA_ROWS,
    ImportUnreadableError,
    SheetRow,
    read_upload,
)
from api.domain.imports.rows import (
    NAME_IN_CODE,
    ProductLookups,
    ProductRef,
    parse_lines,
    parse_price_items,
)

PRICE = header_score("price_list_items")
STATES = ["GJ", "UP", "CG", "RJ", "APMIP"]


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _template(products: list[tuple[str, list[object]]]) -> bytes:
    """The shape of `data/masters/Product-Master.xlsx`: a title in A1, the state codes
    over the price columns in F1:J1, "wef" in E2, the header in row 3 with "Price "
    over column F only, and an empty Item Code column."""
    rows: list[list[object]] = [
        ["Product Master List", None, None, None, None, *STATES],
        [None, None, None, None, "wef"],
        ["Item Code", "Product Description", "Product Category", "Quotation Category",
         "Unit", "Price "],
    ]
    rows += [[None, name, "PIPE", "Field", "MTR", *rates] for name, rates in products]
    return _xlsx(rows)


# ── the header row (rule 1) ──────────────────────────────────────────────────

def test_the_template_header_is_row_three_and_the_states_name_their_columns() -> None:
    sheet = read_upload(_template([("PIPE 16MM", [10, 20, 30, 40, 50])]), "t.xlsx", score=PRICE)
    assert sheet.header_row == 3
    assert sheet.headers[:5] == ["Item Code", "Product Description", "Product Category",
                                 "Quotation Category", "Unit"]
    assert sheet.headers[5:] == ["Price (GJ)", "UP", "CG", "RJ", "APMIP"]
    assert [r.row for r in sheet.rows] == [4]


def test_the_template_suggests_the_description_and_no_rate() -> None:
    sheet = read_upload(_template([("PIPE 16MM", [10, 20, 30, 40, 50])]), "t.xlsx", score=PRICE)
    empty = {c for c in range(len(sheet.headers)) if not any(r.cells[c] for r in sheet.rows)}
    got = suggest("price_list_items", sheet.headers, empty=empty)
    assert got == {"description": 1}, "the empty Item Code and Gujarat's Price stay unmatched"


def test_without_a_score_the_first_row_is_the_header_as_before() -> None:
    sheet = read_upload(_template([("PIPE 16MM", [10])]), "t.xlsx")
    assert sheet.header_row == 1
    assert sheet.headers[0] == "Product Master List"


def test_a_given_header_row_wins_and_gets_no_labels() -> None:
    sheet = read_upload(_template([("PIPE 16MM", [10])]), "t.xlsx", header_row=3, score=PRICE)
    assert sheet.header_row == 3
    assert sheet.headers[5:7] == ["Price", "Column G"]


def test_a_header_on_row_one_is_kept() -> None:
    sheet = read_upload(b"Item Code,Description,Rate\nC1,PIPE,10\n", "p.csv", score=PRICE)
    assert sheet.header_row == 1 and sheet.headers == ["Item Code", "Description", "Rate"]


def test_one_known_word_in_a_data_row_does_not_make_it_the_header() -> None:
    # unknown header names; a data cell "Nos" is a quantity alias
    data = b"Vastu,Sankhya\nPIPE,Nos\nVALVE,Nos\n"
    sheet = read_upload(data, "l.csv", score=header_score("lines"))
    assert sheet.header_row == 1
    assert len(sheet.rows) == 2


def test_a_data_row_must_beat_the_first_row() -> None:
    # the first row already names two fields; a later row naming two does not win
    data = b"Item Code,Rate,x\nDescription,Price,y\nC1,10,z\n"
    sheet = read_upload(data, "p.csv", score=PRICE)
    assert sheet.header_row == 1


def test_a_lower_header_still_counts_every_data_row() -> None:
    # B1, EC-4: title, a note, the header on row 3, then one row over the cap
    lines = ["Polysil price list,,", ",wef,", "Item Code,Description,Rate"]
    lines += [f"C{i},PIPE {i},10" for i in range(MAX_DATA_ROWS + 1)]
    with pytest.raises(ImportUnreadableError) as exc:
        read_upload("\n".join(lines).encode(), "p.csv", score=PRICE)
    assert exc.value.code == "import_too_many_rows"


def test_exactly_the_cap_under_a_lower_header_is_read_whole() -> None:
    lines = ["Polysil price list,,", ",wef,", "Item Code,Description,Rate"]
    lines += [f"C{i},PIPE {i},10" for i in range(MAX_DATA_ROWS)]
    sheet = read_upload("\n".join(lines).encode(), "p.csv", score=PRICE)
    assert sheet.header_row == 3 and len(sheet.rows) == MAX_DATA_ROWS


# ── labels (rule 2) ──────────────────────────────────────────────────────────

def test_a_note_with_a_colon_is_not_a_label() -> None:
    data = _xlsx([["Polysil", None, "Date: 16-10-2026"],
                  ["Item Code", "Description", "Rate"],
                  ["C1", "PIPE", 10]])
    sheet = read_upload(data, "p.xlsx", score=PRICE)
    assert sheet.header_row == 2
    assert sheet.headers == ["Item Code", "Description", "Rate"]


def test_a_long_label_is_not_a_label() -> None:
    data = _xlsx([["Polysil", None, "Prepared by the accounts office"],
                  ["Item Code", "Description", "Rate"],
                  ["C1", "PIPE", 10]])
    assert read_upload(data, "p.xlsx", score=PRICE).headers[2] == "Rate"


def test_labels_from_two_rows_join_and_a_rows_only_cell_is_a_title() -> None:
    data = _xlsx([["Title", None, "GJ"],
                  ["", "wef", "2026-10"],
                  ["Item Code", "Description", None],
                  ["C1", "PIPE", 10]])
    sheet = read_upload(data, "p.xlsx", score=PRICE)
    assert sheet.headers[1:] == ["Description", "GJ 2026-10"], "wef opens its row: a title"


def test_a_lone_cell_above_is_a_title_not_a_label() -> None:
    data = _xlsx([["Title", None, None],
                  [None, None, "2026-10"],
                  ["Item Code", "Description", "Rate"],
                  ["C1", "PIPE", 10]])
    assert read_upload(data, "p.xlsx", score=PRICE).headers[2] == "Rate"


# ── suggestions (rule 4) ─────────────────────────────────────────────────────

def test_an_empty_rate_does_not_hand_the_rate_to_mrp() -> None:
    got = suggest("price_list_items", ["Description", "Rate", "MRP"], empty={1})
    assert got == {"description": 0}


def test_rate_beside_mrp_still_suggests_rate() -> None:
    got = suggest("price_list_items", ["Item", "Rate", "MRP"])
    assert got == {"description": 0, "rate": 1}


def test_a_remembered_rate_is_not_used_and_empty_columns_are_skipped() -> None:
    headers = ["Item Code", "Description", "Price (GJ)", "UP"]
    got = suggest("price_list_items", headers,
                  {"rate": "Price (GJ)", "item_code": "Item Code"}, empty={0})
    assert got == {"description": 1}


@pytest.mark.parametrize("header", ["Product Description", "Desc", "Item Description"])
def test_description_names(header: str) -> None:
    assert suggest("price_list_items", [header, "Rate"]) == {"description": 0, "rate": 1}


# ── name keys (rule 5) and redaction (rule 9) ────────────────────────────────

@pytest.mark.parametrize("raw", ["HDPE PIPE  PE 100-DN63", "hdpe pipe pe 100-dn63_x000D_",
                                 " HDPE\tPIPE PE 100-DN63 ", "HDPE PIPE PE 100-DN63_x000A_"])
def test_name_keys_match_the_catalogue_loader(raw: str) -> None:
    assert name_key(raw) == "hdpe pipe pe 100-dn63"


def test_name_keys_keep_hyphens_and_dots() -> None:
    assert name_key("PE-100") != name_key("PE100")


def test_redaction_takes_out_quoted_cells_and_long_numbers() -> None:
    assert redact("no product with item code '9876543210'") == "no product with item code '…'"
    assert redact("no product 'Ramesh Patel'") == "no product '…'"
    assert redact("also on row 12") == "also on row 12"
    assert "98765" not in redact("bad value 9876543210 here")


# ── finding the product (rules 6 to 8) ───────────────────────────────────────

PIPE = ProductRef("p1", "HDPE PIPE PE 100-DN63", True, "MTR", 0, None)
VALVE = ProductRef("p2", "VALVE 2IN", True, "NOS", 0, None, item_code="V2")
OLD = ProductRef("p3", "OLD FILTER", False, "NOS", 0, None)
TWIN_A = ProductRef("p4", "ELBOW  90", True, "NOS", 0, None)
TWIN_B = ProductRef("p5", "ELBOW 90", True, "NOS", 0, None)
LK = ProductLookups.build([PIPE, VALVE, OLD, TWIN_A, TWIN_B])
M = {"item_code": 0, "description": 1, "rate": 2}


def _rows(*cells: tuple[str, ...]) -> list[SheetRow]:
    return [SheetRow(row=i + 2, cells=c) for i, c in enumerate(cells)]


def test_a_double_space_in_the_sheet_still_finds_the_product() -> None:
    out = parse_price_items(_rows(("", "HDPE PIPE  PE 100-DN63", "10")), M, LK)
    assert out[0].ok and out[0].values["product_id"] == "p1"


def test_an_unknown_code_with_a_known_name_matches_by_name_and_is_noted() -> None:
    out = parse_price_items(_rows(("X-1", "HDPE PIPE PE 100-DN63", "10")), M, LK)
    assert out[0].ok and out[0].values["product_id"] == "p1"
    assert out[0].notes == {"item_code": "matched by description"}
    assert "notes" not in out[0].values and "matched_on" not in out[0].values


def test_a_wrong_code_for_a_product_that_has_one_is_an_error() -> None:
    # EC-12: a typo'd code and a copied description must not price VALVE
    out = parse_price_items(_rows(("V9", "VALVE 2IN", "10")), M, LK)
    assert out[0].errors == {"item_code": "'V9' is not this product's item code (V2)"}


def test_a_product_name_in_the_code_column_says_so() -> None:
    # the 16 Oct file: names under Item Code, Description empty
    out = parse_price_items(_rows(("HDPE PIPE  PE 100-DN63", "", "10")), M, LK)
    assert out[0].errors == {"item_code": NAME_IN_CODE}


def test_a_code_found_with_a_different_description_is_still_ec17() -> None:
    out = parse_price_items(_rows(("V2", "HDPE PIPE PE 100-DN63", "10")), M, LK)
    assert out[0].errors == {"description": "names a different product from the item code"}


def test_an_exact_twin_wins_and_a_cleaned_twin_is_ambiguous() -> None:
    m = {"description": 0, "rate": 1}
    out = parse_price_items(_rows(("ELBOW  90", "1"), ("elbow 90", "2"), ("ELBOW   90", "3")),
                            m, LK)
    assert out[0].values["product_id"] == "p4"
    assert out[1].values["product_id"] == "p5"
    assert out[2].errors == {"description": "more than one product has the name 'ELBOW   90'"}


def test_codes_equal_after_cleaning_are_ambiguous() -> None:
    lk = ProductLookups.build([ProductRef("a", "A", True, "NOS", 0, None, item_code="AB  1"),
                               ProductRef("b", "B", True, "NOS", 0, None, item_code="AB 1")])
    out = parse_price_items(_rows(("ab   1", "", "1")), M, lk)
    assert out[0].errors == {"item_code": "more than one product has the item code 'ab   1'"}


def test_a_duplicate_found_by_name_is_reported_on_the_description() -> None:
    out = parse_price_items(_rows(("X1", "HDPE PIPE PE 100-DN63", "1"),
                                  ("X2", "HDPE PIPE PE 100-DN63", "2")), M, LK)
    assert out[0].errors == {"description": "also on row 3"}
    assert out[1].errors == {"description": "also on row 2"}


def test_an_inactive_product_found_by_name_is_refused_on_the_description() -> None:
    m = {"item_code": 0, "description": 1, "qty": 2}
    out = parse_lines(_rows(("", "OLD FILTER", "1")), m, LK)
    assert out[0].errors == {"description": "this product is no longer sold"}


def test_every_product_error_quotes_its_cell_so_it_can_be_redacted() -> None:
    out = parse_price_items(_rows(("9876543210", "", "10"), ("", "Ramesh Patel", "x9876543")),
                            M, LK)
    for res in out:
        for message in res.errors.values():
            kept = redact(message)
            assert "9876543210" not in kept and "Ramesh" not in kept and "9876543" not in kept


# ── the client's files ───────────────────────────────────────────────────────

def test_the_template_filled_in_imports_the_up_column() -> None:
    names = ["HDPE PIPE  PE 100-DN63", "VALVE 2IN"]
    data = _template([(n, [100 + i, 200 + i, 300 + i, 400 + i, 500 + i])
                      for i, n in enumerate(names)])
    sheet = read_upload(data, "t.xlsx", score=PRICE)
    up = sheet.headers.index("UP")
    out = parse_price_items(sheet.rows, {"description": 1, "rate": up}, LK)
    assert [(r.values["product_id"], r.values["rate"]) for r in out] == [
        ("p1", "200.00"), ("p2", "201.00")]


REAL = Path(__file__).resolve().parents[2] / "data" / "masters" / "Product-Master.xlsx"


@pytest.mark.skipif(not REAL.exists(), reason="the client's master is not in this checkout")
def test_the_real_master_finds_row_three_and_names_the_state_columns() -> None:
    sheet = read_upload(REAL.read_bytes(), REAL.name, score=PRICE)
    assert sheet.header_row == 3
    assert sheet.headers[5:10] == ["Price (GJ)", "UP", "CG", "RJ", "APMIP"]
    assert len(sheet.rows) == 1094
