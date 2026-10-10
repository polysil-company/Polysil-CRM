"""FS-015's pure rules: working time, the complaint number, file sniffing, and the
date and line checks."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from api.domain import complaints as c
from api.domain.leads import financial_year

IST = c.IST
UTC = dt.UTC


def ist(y: int, m: int, d: int, hh: int = 0, mm: int = 0, ss: int = 0) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, ss, tzinfo=IST)


# 2026-10-03 is a Saturday, 2026-10-04 a Sunday, 2026-10-05 a Monday.

@pytest.mark.parametrize(("start", "hours", "due"), [
    (ist(2026, 10, 3, 18, 0), 4, ist(2026, 10, 5, 13, 0)),     # half an hour Saturday, 3.5 Monday
    (ist(2026, 10, 4, 11, 0), 4, ist(2026, 10, 5, 13, 30)),    # Sunday counts nothing
    (ist(2026, 10, 3, 18, 30), 4, ist(2026, 10, 5, 13, 30)),   # closing time exactly: next opening
    (ist(2026, 10, 5, 7, 0), 4, ist(2026, 10, 5, 13, 30)),     # before opening
    (ist(2026, 10, 5, 14, 30), 4, ist(2026, 10, 5, 18, 30)),   # lands exactly on closing
    (ist(2026, 10, 5, 9, 30), 18, ist(2026, 10, 6, 18, 30)),   # two working days of 9 hours
    (ist(2026, 10, 5, 9, 30), 45, ist(2026, 10, 9, 18, 30)),   # five
])
def test_working_hours(start: dt.datetime, hours: int, due: dt.datetime) -> None:
    assert c.add_working_hours(start, hours) == due


def test_working_hours_are_ist_whatever_the_zone_given() -> None:
    """23:30 UTC on Saturday is 05:00 IST on Sunday: a UTC weekday would say
    Saturday and count the evening."""
    start = dt.datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
    assert c.add_working_hours(start, 4) == ist(2026, 10, 5, 13, 30)


def test_a_27_hour_target_from_friday_afternoon() -> None:
    # Fri 17:00: 1.5 h; Sat 9 h (10.5); Mon 9 h (19.5); Tue 7.5 h to 17:00
    assert c.add_working_hours(ist(2026, 10, 2, 17, 0), 27) == ist(2026, 10, 6, 17, 0)


def test_a_plain_clock_policy_crosses_sunday() -> None:
    start = ist(2026, 10, 3, 20, 0)
    assert c.due_at(start, 24, business_hours_only=False) == ist(2026, 10, 4, 20, 0)
    assert c.due_at(start, None, business_hours_only=True) is None, "no policy row, no target"


def test_a_naive_start_is_refused() -> None:
    with pytest.raises(ValueError):
        c.add_working_hours(dt.datetime(2026, 10, 5, 10, 0), 4)


def test_breached_is_met_late_or_past_due_and_unmet() -> None:
    now = ist(2026, 10, 5, 12, 0)
    assert c.breached(ist(2026, 10, 5, 11, 0), None, now)
    assert not c.breached(ist(2026, 10, 5, 11, 0), ist(2026, 10, 5, 10, 0), now), "met in time"
    late = ist(2026, 10, 5, 11, 30)
    assert c.breached(ist(2026, 10, 5, 11, 0), late, now), "met late is a breach"
    assert not c.breached(ist(2026, 10, 5, 13, 0), None, now)
    assert not c.breached(None, None, now), "no target, never breached"


@pytest.mark.parametrize(("n", "text"), [(1, "01"), (99, "99"), (100, "100"), (12345, "12345")])
def test_the_number_pads_to_two_digits_and_grows(n: int, text: str) -> None:
    assert c.complaint_no("2026-27", "GJ", n) == f"Poly/Comp./2026-27/GJ/{text}"


def test_the_year_turns_at_ist_midnight() -> None:
    assert financial_year(dt.datetime(2027, 3, 31, 23, 45, tzinfo=UTC)) == "2027-28"
    assert financial_year(dt.datetime(2027, 3, 31, 18, 0, tzinfo=UTC)) == "2026-27"


@pytest.mark.parametrize(("head", "kind"), [
    (b"\xff\xd8\xff\xe0" + b"\0" * 12, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n" + b"\0" * 8, "image/png"),
    (b"RIFF\0\0\0\0WEBPVP8 ", "image/webp"),
    (b"%PDF-1.7\n" + b"\0" * 7, "application/pdf"),
    (b"\0\0\0\x18ftypheic" + b"\0" * 4, "image/heic"),
    (b"\0\0\0\x18ftypmif1" + b"\0" * 4, "image/heic"),
])
def test_files_are_known_by_their_bytes(head: bytes, kind: str) -> None:
    found = c.sniff(head)
    assert found is not None and found.content_type == kind
    assert found.inline is (kind != "image/heic"), "HEIC is a download (EC-7)"


@pytest.mark.parametrize("head", [b"<!DOCTYPE html><html>", b"MZ\x90\x00", b"", b"GIF89a"])
def test_anything_else_is_refused(head: bytes) -> None:
    assert c.sniff(head) is None


def test_dates_after_today_and_out_of_order() -> None:
    today = dt.date(2026, 10, 5)
    assert c.date_problems(today=today, supply_date=dt.date(2026, 10, 6)) == {
        "supply_date": "cannot be after today"}
    got = c.date_problems(today=today, supply_date=dt.date(2026, 9, 1),
                          sample_courier_date=dt.date(2026, 8, 30),
                          sample_received_on=dt.date(2026, 9, 10), tested_on=dt.date(2026, 9, 9))
    assert set(got) == {"sample_courier_date", "tested_on"}
    assert c.date_problems(today=today, supply_date=dt.date(2026, 9, 1),
                           sample_received_on=dt.date(2026, 9, 1),
                           tested_on=dt.date(2026, 9, 1)) == {}, "the same day is fine"


def test_ist_today_is_the_indian_date() -> None:
    assert c.ist_today(dt.datetime(2026, 10, 4, 20, 0, tzinfo=UTC)) == dt.date(2026, 10, 5)


def _line(pid: str, supplied: str, defective: str) -> c.Line:
    return c.Line(pid, Decimal(supplied), Decimal(defective))


def test_line_rules() -> None:
    assert c.line_problems([]) == {"lines": "1 to 20 products"}
    assert c.line_problems([_line("a", "10", "3")]) == {}
    got = c.line_problems([_line("a", "10", "11"), _line("a", "0", "0"), _line("b", "5", "-1")])
    assert got == {"lines[0].defective_qty": "not more than supplied",
                   "lines[1].product_id": "each product once",
                   "lines[1].supplied_qty": "more than zero",
                   "lines[2].defective_qty": "zero or more"}
    assert "lines" in c.line_problems([_line(str(i), "1", "0") for i in range(21)])


def test_a_submit_needs_something_defective() -> None:
    assert c.nothing_defective([_line("a", "10", "0"), _line("b", "5", "0")])
    assert not c.nothing_defective([_line("a", "10", "0"), _line("b", "5", "0.5")])


def test_text_is_trimmed_and_blank_is_absent() -> None:
    assert c.clean_text("  DC-44 ") == "DC-44"
    assert c.clean_text("   ") is None
    assert c.clean_text(None) is None
