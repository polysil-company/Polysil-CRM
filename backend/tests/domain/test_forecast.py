"""FS-079: the forecast's arithmetic. No database. Each case names the edge-case
(EC) or plan-review (S) finding it pins."""

# ruff: noqa: E501  (inline cases)

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

import pytest

from api.domain import forecast as f


def test_every_lead_reached_new() -> None:
    """Plan review S-1: no event ever says a lead reached `new`."""
    assert f.stages_reached("won", None, []) == {"new"}
    assert f.stages_reached("lost", None, []) == {"new"}


def test_a_lead_won_straight_from_quoted_never_reached_negotiation() -> None:
    """EC-1: the old `_reached()` counted every won lead as having negotiated."""
    reached = f.stages_reached("won", None, ["contacted", "qualified", "quoted", "won"])
    assert reached == {"new", "contacted", "qualified", "quoted"}


def test_a_lost_lead_reached_every_stage_up_to_where_it_was_lost() -> None:
    assert f.stages_reached("lost", "quoted", []) == {"new", "contacted", "qualified", "quoted"}
    assert f.stages_reached("lost", "unknown", []) == {"new"}


def test_negotiation_rate_counts_only_leads_that_negotiated() -> None:
    """EC-1's fixture: 35 won from quoted, 5 won and 10 lost from negotiation."""
    rows = ([(True, f.stages_reached("won", None, ["contacted", "qualified", "quoted"]))] * 35
            + [(True, f.stages_reached("won", None, ["contacted", "qualified", "quoted", "negotiation"]))] * 5
            + [(False, f.stages_reached("lost", "negotiation", []))] * 10)
    rates = f.win_rates(rows)
    assert rates is not None
    neg = rates["negotiation"]
    assert (neg.won, neg.closed) == (5, 15) and neg.pct == Decimal("33.3"), "not 80%"


def test_too_thin_history_gives_no_rates() -> None:
    """EC-6: never 0."""
    assert f.win_rates([(True, frozenset({"new"}))] * 9) is None


def test_a_thin_stage_borrows_the_nearest_earlier_stage_not_the_overall_rate() -> None:
    """EC-9: moving a lead forward must not cut its weight eightfold."""
    rows = ([(False, f.stages_reached("lost", "new", []))] * 200
            + [(True, f.stages_reached("won", None, ["contacted", "qualified", "quoted"]))] * 12
            + [(False, f.stages_reached("lost", "quoted", []))] * 26
            + [(True, f.stages_reached("won", None, ["contacted", "qualified", "quoted", "negotiation"]))] * 3
            + [(False, f.stages_reached("lost", "negotiation", []))] * 3)
    rates = f.win_rates(rows)
    assert rates is not None
    quoted, neg = rates["quoted"], rates["negotiation"]
    assert not quoted.low_confidence and neg.low_confidence and neg.own_closed == 6
    assert (neg.won, neg.closed) == (quoted.won, quoted.closed), "borrowed from quoted"
    overall = Decimal(15 * 100) / Decimal(244)
    assert neg.pct > overall


def test_weighting_uses_the_exact_fraction_and_rounds_half_up() -> None:
    """EC-4: 18/57 of 1,00,000 is 31,578.95, not 31.5% of it."""
    rate = f.Rate("quoted", 18, 57, 57, False)
    assert f.weighted(Decimal("100000"), rate) == Decimal("31578.95")
    assert rate.pct == Decimal("31.6")
    assert f.weighted(Decimal("0.05"), f.Rate("x", 1, 2, 2, False)) == Decimal("0.03"), "half up"


@pytest.mark.parametrize(("days", "expected"), [
    ([5] * 9, None), (list(range(1, 11)), 5), (list(range(1, 12)), 6), ([10, 11] * 5, 10),
    ([-3, *range(1, 11)], 5),
])
def test_median_days(days: list[int], expected: int | None) -> None:
    """EC-12, EC-13: percentile_disc, negatives left out, none under 10."""
    assert f.median_days(days) == expected


def test_months_roll_over_the_year() -> None:
    assert f.months(dt.date(2026, 11, 30)) == ["2026-11", "2026-12", "2027-01"]


@pytest.mark.parametrize(("created", "median", "today", "expected"), [
    (dt.date(2026, 10, 1), 34, dt.date(2026, 10, 25), "2026-11"),
    (dt.date(2026, 9, 1), 34, dt.date(2026, 10, 25), "2026-10"),     # past: this month
    (dt.date(2025, 9, 1), 34, dt.date(2026, 10, 25), "later"),       # stale, over 3 x the median (EC-10)
    (dt.date(2026, 10, 25), 120, dt.date(2026, 10, 25), "later"),    # beyond the third month
    (dt.date(2026, 10, 25), None, dt.date(2026, 10, 25), "later"),   # no median
    (dt.date(2026, 10, 31), 1, dt.date(2026, 10, 31), "2026-11"),    # month end
])
def test_expected_month(created: dt.date, median: int | None, today: dt.date, expected: str) -> None:
    assert f.expected_month(created, median, today) == expected


@pytest.mark.parametrize(("q", "e", "expected"), [
    (Decimal("150000"), Decimal("90000"), (Decimal("150000"), "quotation")),
    (Decimal("0"), Decimal("150000"), (Decimal("150000"), "estimate")),     # EC-14
    (None, Decimal("0"), (None, None)),                                      # EC-17
    (None, None, (None, None)),
])
def test_value_of(q: Decimal | None, e: Decimal | None, expected: tuple) -> None:
    assert f.value_of(q, e) == expected


def test_properties_on_random_pipelines() -> None:
    """Weighted never exceeds the pipeline; rates stay 0 to 100; month buckets add
    up to the weighted total. Seeded, so a failure reproduces."""
    rng = random.Random(79)
    today = dt.date(2026, 10, 25)
    for _ in range(300):
        rows = []
        for _ in range(rng.randint(10, 120)):
            if rng.random() < 0.3:
                path = f.OPEN_STAGES[1:rng.randint(1, 5)]
                rows.append((True, f.stages_reached("won", None, list(path))))
            else:
                rows.append((False, f.stages_reached("lost", rng.choice(f.OPEN_STAGES), [])))
        rates = f.win_rates(rows)
        assert rates is not None
        median = rng.choice([None, rng.randint(1, 90)])
        buckets: dict[str, Decimal] = {}
        pipeline = total = Decimal(0)
        for _ in range(rng.randint(0, 50)):
            stage = rng.choice(f.OPEN_STAGES)
            value = Decimal(rng.randint(0, 10**7)) / 100
            w = f.weighted(value, rates[stage])
            assert 0 <= rates[stage].pct <= 100
            assert w <= value
            pipeline += value
            total += w
            key = f.expected_month(today - dt.timedelta(days=rng.randint(0, 400)), median, today)
            buckets[key] = buckets.get(key, Decimal(0)) + w
        assert total <= pipeline
        assert sum(buckets.values(), Decimal(0)) == total
