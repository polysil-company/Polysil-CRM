"""FS-046 warranty arithmetic. The SQL twin is held equal in tests/db/test_warranty_db.py."""

from __future__ import annotations

import datetime as dt

import pytest

from api.domain import warranty as w

D = dt.date


@pytest.mark.parametrize(("start", "months", "end"), [
    (D(2026, 10, 2), 12, D(2027, 10, 1)),
    (D(2026, 1, 1), 1, D(2026, 1, 31)),
    (D(2026, 1, 28), 1, D(2026, 2, 27)),
    (D(2026, 1, 29), 1, D(2026, 2, 28)),     # 29 Feb does not exist: the month end
    (D(2026, 1, 31), 1, D(2026, 2, 28)),
    (D(2028, 1, 31), 1, D(2028, 2, 29)),     # leap year
    (D(2024, 2, 29), 12, D(2025, 2, 28)),
    (D(2027, 3, 1), 12, D(2028, 2, 29)),     # no day lost in a leap year
    (D(2026, 2, 1), 1, D(2026, 2, 28)),
    (D(2026, 12, 15), 1, D(2027, 1, 14)),
    (D(2026, 3, 31), 6, D(2026, 9, 30)),
    (D(2026, 5, 10), 120, D(2036, 5, 9)),
])
def test_end_date(start: dt.date, months: int, end: dt.date) -> None:
    assert w.end_date(start, months) == end


def test_zero_months_is_no_warranty() -> None:
    assert w.end_date(D(2026, 1, 1), 0) is None


@pytest.mark.parametrize("months", [-1, 121])
def test_months_out_of_range(months: int) -> None:
    with pytest.raises(ValueError):
        w.end_date(D(2026, 1, 1), months)


def test_ends_never_go_backwards_and_cover_about_the_span() -> None:
    for months in (1, 6, 12, 18, 24, 60, 120):
        day, prev = D(2024, 1, 1), None
        while day < D(2029, 1, 1):
            end = w.end_date(day, months)
            assert end is not None and day <= end <= w.add_months(day, months)
            assert prev is None or end >= prev
            prev = end
            day += dt.timedelta(days=1)


def test_status_is_inclusive_of_the_end_day() -> None:
    end = D(2027, 10, 1)
    assert w.status_on(12, end, end) == "active"
    assert w.status_on(12, end, end + dt.timedelta(days=1)) == "expired"
    assert w.status_on(0, None, end) == "none"
    assert w.status_on(None, None, end) == "unknown"
    assert w.claim_status(12, end, end) == "in_warranty"
    assert w.claim_status(12, end, D(2020, 1, 1)) == "in_warranty"   # before the start (EC-11)
    assert w.claim_status(12, end, end + dt.timedelta(days=1)) == "expired"
    assert w.claim_status(0, None, end) == "none"
    assert w.claim_status(None, None, end) == "unknown"


def test_the_anchor_prefers_a_dated_end_then_the_later_one() -> None:
    """Plan review M-2: the order tab's anchor, the same order as complaint_warranty()."""
    from types import SimpleNamespace as R

    from api.services.warranty import _later
    dated = R(end_day=D(2027, 1, 1), start_day=D(2026, 1, 2))
    undated_later_start = R(end_day=None, start_day=D(2026, 6, 1))
    assert _later(dated, undated_later_start) and not _later(undated_later_start, dated)
    assert _later(R(end_day=D(2027, 6, 1), start_day=D(2026, 1, 1)), dated)
    assert _later(R(end_day=None, start_day=D(2026, 7, 1)), undated_later_start)
