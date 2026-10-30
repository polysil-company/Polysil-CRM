"""FS-025 domain: months, the open window, values."""

# ruff: noqa: E501  (cases inline)

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from api.domain import targets as t

TODAY = dt.date(2026, 10, 4)


@pytest.mark.parametrize("raw", ["2026-1", "26-10", "2026/10", "2026-13", "2026-00", "abcd-ef", ""])
def test_bad_months(raw: str) -> None:
    with pytest.raises(ValueError):
        t.parse_month(raw)


def test_month_window() -> None:
    oct_, sep, next_oct, nov_next = (t.parse_month(x) for x in ("2026-10", "2026-09", "2027-10", "2027-11"))
    assert t.month_problem(oct_, TODAY, global_scope=False) is None
    assert t.month_problem(next_oct, TODAY, global_scope=False) is None
    assert t.month_problem(nov_next, TODAY, global_scope=True) == "more than 12 months ahead"
    assert t.month_problem(sep, TODAY, global_scope=False) == "month_closed"
    assert t.month_problem(sep, TODAY, global_scope=True) is None


@pytest.mark.parametrize(("metric", "value", "ok"), [
    ("order_value", "500000.00", True), ("order_value", "1.005", False), ("orders", "10", True),
    ("orders", "10.5", False), ("visits", "0", True), ("leads_won", "-1", False), ("calls", "1", False)])
def test_values(metric: str, value: str, ok: bool) -> None:
    assert (t.value_problem(metric, Decimal(value)) is None) is ok


@pytest.mark.parametrize("m", range(1, 13))
def test_month_end(m: int) -> None:
    first = dt.date(2028, m, 1)
    end = t.month_end(first)
    assert end.month == m and (end + dt.timedelta(days=1)).day == 1
