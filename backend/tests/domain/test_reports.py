"""FS-024 domain: percentages, the date window, follow-up ageing."""

# ruff: noqa: E501  (cases inline)

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

import pytest

from api.domain import reports as r

TODAY = dt.date(2026, 10, 4)


@pytest.mark.parametrize(("part", "whole", "want"), [(0, 0, "0.0"), (5, 0, "0.0"), (1, 3, "33.3"),
                                                     (2, 3, "66.7"), (1, 8, "12.5"), (1, 400, "0.3"),
                                                     (3, 3, "100.0")])
def test_pct(part: int, whole: int, want: str) -> None:
    assert str(r.pct(part, whole)) == want


@pytest.mark.parametrize("seed", range(500))
def test_pct_stays_in_range_for_a_part_of_a_whole(seed: int) -> None:
    rng = random.Random(seed)
    whole = rng.randint(1, 100_000)
    assert Decimal("0") <= r.pct(rng.randint(0, whole), whole) <= Decimal("100")


def test_the_default_window_is_thirty_days_ending_today() -> None:
    assert r.window(None, None, TODAY) == (TODAY - dt.timedelta(days=29), TODAY)
    assert r.window(dt.date(2026, 9, 1), None, TODAY) == (dt.date(2026, 9, 1), TODAY)


def test_a_bad_window_is_refused() -> None:
    with pytest.raises(ValueError):
        r.window(TODAY, TODAY - dt.timedelta(days=1), TODAY)
    with pytest.raises(ValueError):
        r.window(TODAY - dt.timedelta(days=366), TODAY, TODAY)
    assert r.window(TODAY - dt.timedelta(days=365), TODAY, TODAY)[0] == TODAY - dt.timedelta(days=365)


def test_instants_are_ist_and_half_open() -> None:
    a, b = r.instants(TODAY, TODAY)
    assert a.astimezone(dt.UTC) == dt.datetime(2026, 10, 3, 18, 30, tzinfo=dt.UTC)
    assert b - a == dt.timedelta(days=1)


def test_ageing_buckets() -> None:
    now = dt.datetime(2026, 10, 4, 10, 0, tzinfo=r.IST)
    def due(days_ago: int, hour: int = 18) -> dt.datetime:
        return dt.datetime.combine(TODAY - dt.timedelta(days=days_ago), dt.time(hour), tzinfo=r.IST)
    assert r.ageing_bucket(due(-1), now) is None
    assert r.ageing_bucket(due(0), now) == "due_today", "later today is due today"
    assert [r.ageing_bucket(due(d), now) for d in (1, 2, 3, 7, 8, 30, 31, 400)] == [
        "overdue_1_2", "overdue_1_2", "overdue_3_7", "overdue_3_7", "overdue_8_30", "overdue_8_30",
        "overdue_31_plus", "overdue_31_plus"]


def test_ageing_counts_ist_days_not_utc() -> None:
    late = dt.datetime(2026, 10, 3, 23, 30, tzinfo=r.IST)      # 18:00 UTC on the 3rd
    just_after = dt.datetime(2026, 10, 4, 0, 30, tzinfo=r.IST)  # 19:00 UTC on the 3rd
    assert r.ageing_bucket(late, just_after) == "overdue_1_2"
