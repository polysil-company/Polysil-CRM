"""FS-081 without a database: the one-call drain, list-valued columns, and their
formula guard in Excel and CSV."""
# ruff: noqa: E501  (expected values inline)

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from pydantic import BaseModel

from api.services import exports
from api.services.exports import Column


class _Row(BaseModel):
    n: int


async def test_one_call_takes_up_to_the_cap_and_refuses_one_more() -> None:
    calls = 0

    async def fetch(size: int):
        nonlocal calls
        calls += 1
        return [_Row(n=i) for i in range(size)]

    rows = await exports.once(lambda: fetch(exports.MAX_ROWS))
    assert len(rows) == exports.MAX_ROWS and calls == 1
    with pytest.raises(exports.ExportTooLargeError):
        await exports.once(lambda: fetch(exports.MAX_ROWS + 1))
    assert calls == 2, "one call each, never a page loop"


def test_scheme_targets_never_read_hidden_as_everyone() -> None:
    """EC-6."""
    assert exports._targets([]) == "Everyone"
    assert exports._targets([{"type": "partner", "id": "x", "name": None},
                             {"type": "state", "id": "y", "name": "Gujarat"}]) == \
        "partner: (not visible); state: Gujarat"


def test_allocations_and_luts_are_written_out() -> None:
    """EC-5: neither has a `name`, so the plain join gave blank cells."""
    assert exports._allocations([{"sales_order": {"order_no": "SO/GJ/2026-27/00012"}, "amount": "1000.00"},
                                 {"sales_order": {"order_no": None}, "amount": "5.00"}]) == \
        "SO/GJ/2026-27/00012: 1000.00; : 5.00"
    assert exports._allocations([]) is None
    assert exports._luts([{"arn": "AD240", "valid_from": "2026-04-01", "valid_to": "2027-03-31"}]) == \
        "AD240 (2026-04-01 to 2027-03-31)"




def test_a_formatted_cell_is_formula_guarded_in_csv() -> None:
    """Plan review S-5: fmt output goes through cell_value() and the guard."""
    rows = exports.csv_bytes((Column("X", "x", "text", lambda v: v),), [{"x": "=1+1"}]).decode("utf-8-sig")
    assert "\"'=1+1\"" in rows


def test_a_formatted_cell_is_text_in_excel() -> None:
    data = exports.workbook("T", (Column("X", "x", "text", lambda v: v),), [{"x": "=1+1"}])
    cell = load_workbook(io.BytesIO(data)).active["A2"]
    assert cell.value == "=1+1" and cell.data_type == "s", "stored as text, never a formula"
