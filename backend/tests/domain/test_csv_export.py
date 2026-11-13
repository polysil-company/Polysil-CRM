"""FS-077: the CSV writer. No database.

Each case is an edge-case or plan-review finding: blanks stay blank (ADR-047),
formulas are neutralised but mobiles are not, money has two places and no
exponent, times are IST minutes."""

# ruff: noqa: RUF001  (inline cases; the full-width signs are the test)

from __future__ import annotations

import csv
import io
from decimal import Decimal

import pytest

from api.services import exports
from api.services.exports import Column, csv_bytes, decimal_text, formula_safe, money_text

COLS = (Column("Name", "n"), Column("Mobile", "m"), Column("Amount", "a", "money"),
        Column("At", "t", "datetime"), Column("Count", "i", "int"), Column("Pct", "p", "decimal"),
        Column("On", "d", "date"), Column("Crops", "c", "names"), Column("Active", "b", "bool"))


def _text(rows: list[dict]) -> str:
    return csv_bytes(COLS, rows).decode("utf-8")


def _parsed(rows: list[dict]) -> list[list[str]]:
    return list(csv.reader(io.StringIO(_text(rows).lstrip("﻿"))))


def test_starts_with_a_bom_and_uses_crlf() -> None:
    body = csv_bytes(COLS, [{"n": "Ravi"}])
    assert body.startswith("﻿".encode())
    assert b"\r\n" in body and body.count(b"\r\n") == 2


def test_a_hidden_figure_is_an_empty_unquoted_field_and_zero_is_zero() -> None:
    """EC-16, ADR-047: `,,` reads as null in a database import; a real 0 is "0"."""
    line = _text([{"n": "Ravi", "i": 0, "a": None}]).split("\r\n")[1]
    assert line.startswith('"Ravi",,"0.00"') is False
    assert line == '"Ravi",,,,"0",,,,'


@pytest.mark.parametrize(("value", "expected"), [
    ("=HYPERLINK(\"x\")", "'=HYPERLINK(\"x\")"),
    ("+1+cmd|' /C calc'!A0", "'+1+cmd|' /C calc'!A0"),
    ("@SUM(A1)", "'@SUM(A1)"),
    ("-2+3", "'-2+3"),
    ("\tx", "'\tx"),
    ("＝1+1", "'＝1+1"),          # full-width equals (N-4)
    ("+919876543210", "+919876543210"),    # a mobile is a plain number (EC-4)
    ("-5", "-5"),
    ("-12.50", "-12.50"),
    ("Ravi", "Ravi"),
])
def test_formula_guard(value: str, expected: str) -> None:
    assert formula_safe(value) == expected


def test_the_guard_runs_after_control_characters_are_stripped() -> None:
    """EC-17: `\\x01=1+1` must not slip past a check made before cleaning."""
    assert _parsed([{"n": "\x01=1+1"}])[1][0] == "'=1+1"


def test_names_lists_are_guarded_too() -> None:
    """EC-17: a crop named `=1+1` reaches the cell through a `names` column."""
    assert _parsed([{"c": [{"name": "=1+1"}, {"name": "Cotton"}]}])[1][7] == "'=1+1, Cotton"


@pytest.mark.parametrize(("value", "expected"), [
    ("1.05E+3", "1050.00"), (0, "0.00"), ("-0.004", "0.00"), ("1050", "1050.00"),
    ("-50", "-50.00"), ("125000.5", "125000.50"),
])
def test_money(value: object, expected: str) -> None:
    """Plan review S-8, EC-20."""
    assert _parsed([{"a": value}])[1][2] == expected


def test_money_and_decimal_text_helpers() -> None:
    assert money_text(Decimal("-0.00")) == "0.00"
    assert decimal_text(Decimal("1E+2")) == "100"
    assert decimal_text(Decimal("-0.0")) == "0.0"


def test_times_are_ist_minutes() -> None:
    """EC-5: no seconds, no microseconds, IST."""
    row = _parsed([{"t": "2026-10-25T09:00:00.123456+00:00", "d": "2026-10-25"}])[1]
    assert row[3] == "2026-10-25 14:30" and row[6] == "2026-10-25"


def test_commas_quotes_newlines_and_unicode_round_trip() -> None:
    name = 'પટેલ, "Ravi"\nline two'
    assert _parsed([{"n": name}])[1][0] == name


def test_bools_are_yes_and_no() -> None:
    assert _parsed([{"b": True}, {"b": False}])[1][8] == "Yes"
    assert _parsed([{"b": False}])[1][8] == "No"


def test_filename_keeps_its_positional_date_and_takes_an_extension() -> None:
    """EC-24: the existing caller passes the date positionally."""
    import datetime as dt
    assert exports.filename("leads", dt.date(2026, 10, 3)) == "leads-2026-10-03.xlsx"
    assert exports.filename("leads", dt.date(2026, 10, 3), ext="csv") == "leads-2026-10-03.csv"


def test_the_log_line_names_the_format() -> None:
    seen: list[dict] = []

    class Spy:
        def info(self, event: str, **kw: object) -> None:
            seen.append({"event": event, **kw})

    real = exports.log
    exports.log = Spy()  # type: ignore[assignment]
    try:
        exports.log_export("u1", "leads", {"q": "98765", "stage": None}, 3, fmt="csv")
    finally:
        exports.log = real
    assert seen == [{"event": "export", "list": "leads", "user": "u1", "filters": ["q"],
                     "rows": 3, "format": "csv"}]
    assert "98765" not in str(seen), "the search term never reaches the log (N-5)"
