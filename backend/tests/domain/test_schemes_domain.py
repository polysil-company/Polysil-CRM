"""FS-031: the master's combinations and the period arithmetic, without a database.
The SQL `scheme_periods()` is compared with `periods()` in tests/api/test_schemes.py's
period test through the stored period start."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from api.domain import schemes as d


def _t(**over: object) -> d.Terms:
    base: dict[str, object] = {
        "scheme_type": "order_discount", "benefit_kind": "pct", "benefit_value": Decimal("5"),
        "benefit_cap": None, "entitlement_days": None, "period": None,
        "condition_min": Decimal("0"),
        "condition_max": None, "valid_from": dt.date(2026, 10, 1), "valid_to": None}
    base.update(over)
    return d.Terms(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(("over", "field"), [
    ({"scheme_type": "order_points"}, "benefit.kind"),
    ({"benefit_kind": "points", "benefit_value": Decimal("10")}, "benefit.kind"),
    ({"benefit_value": Decimal("100.5")}, "benefit.value"),
    ({"benefit_value": Decimal("0")}, "benefit.value"),
    ({"scheme_type": "order_points", "benefit_kind": "points", "benefit_value": Decimal("2.5")},
     "benefit.value"),
    ({"scheme_type": "order_points", "benefit_kind": "points", "benefit_value": Decimal("2"),
      "benefit_cap": Decimal("10")}, "benefit.cap"),
    ({"entitlement_days": 30}, "benefit.entitlement_days"),
    ({"scheme_type": "next_order", "entitlement_days": 0}, "benefit.entitlement_days"),
    ({"scheme_type": "period", "period": "month"}, "valid_to"),
    ({"scheme_type": "period", "valid_to": dt.date(2026, 12, 31)}, "period"),
    ({"period": "month"}, "period"),
    ({"condition_min": Decimal("10"), "condition_max": Decimal("5")}, "condition.max"),
    ({"valid_to": dt.date(2026, 9, 1)}, "valid_to"),
])
def test_each_broken_rule_names_its_field(over: dict[str, object], field: str) -> None:
    assert field in d.problems(_t(**over))


@pytest.mark.parametrize("over", [
    {},
    {"benefit_kind": "flat", "benefit_value": Decimal("250"), "benefit_cap": Decimal("200")},
    {"scheme_type": "order_points", "benefit_kind": "points", "benefit_value": Decimal("200")},
    {"scheme_type": "next_order", "entitlement_days": 90},
    {"scheme_type": "next_order"},
    {"scheme_type": "period", "period": "quarter", "valid_to": dt.date(2027, 3, 31)},
    {"scheme_type": "period", "period": "month", "valid_to": dt.date(2027, 3, 31),
     "benefit_kind": "points", "benefit_value": Decimal("500")},
])
def test_valid_combinations_pass(over: dict[str, object]) -> None:
    assert d.problems(_t(**over)) == {}


def test_entitlement_days_default_only_where_a_credit_exists() -> None:
    assert d.entitlement_days(_t(scheme_type="next_order")) == d.DEFAULT_ENTITLEMENT_DAYS
    assert d.entitlement_days(_t(scheme_type="next_order", entitlement_days=7)) == 7
    assert d.entitlement_days(_t()) is None
    assert d.entitlement_days(_t(scheme_type="period", benefit_kind="points",
                                 benefit_value=Decimal("5"))) is None


def test_targets_refuse_unknown_types_bad_partner_types_and_repeats() -> None:
    out = d.target_problems([("territory", "a"), ("partner_type", "farmer"), ("planet", "x"),
                             ("territory", "a")])
    assert set(out) == {"targets[1].id", "targets[2].type", "targets[3]"}


def test_months_are_clipped_to_the_schemes_dates() -> None:
    got = list(d.periods(dt.date(2026, 10, 15), dt.date(2027, 1, 10), "month", dt.date(2027, 6, 1)))
    assert got == [(dt.date(2026, 10, 15), dt.date(2026, 10, 31)),
                   (dt.date(2026, 11, 1), dt.date(2026, 11, 30)),
                   (dt.date(2026, 12, 1), dt.date(2026, 12, 31)),
                   (dt.date(2027, 1, 1), dt.date(2027, 1, 10))]


def test_quarters_follow_the_calendar_which_is_the_financial_years_too() -> None:
    got = list(d.periods(dt.date(2026, 5, 20), dt.date(2027, 3, 31), "quarter",
                         dt.date(2026, 12, 2)))
    assert got == [(dt.date(2026, 5, 20), dt.date(2026, 6, 30)),
                   (dt.date(2026, 7, 1), dt.date(2026, 9, 30)),
                   (dt.date(2026, 10, 1), dt.date(2026, 12, 31))]


def test_february_and_a_leap_year() -> None:
    got = list(d.periods(dt.date(2028, 2, 1), dt.date(2028, 3, 31), "month", dt.date(2028, 3, 31)))
    assert got[0] == (dt.date(2028, 2, 1), dt.date(2028, 2, 29))
