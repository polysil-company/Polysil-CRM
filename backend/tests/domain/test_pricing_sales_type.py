"""Price lists scoped to a sale type (FS-061 rules 2 to 4; GAP-469, GAP-475).

A typed list outranks every general list, whatever their state or tier. A list for
another sale type is never drawn from. Sale types with no list of their own price
from general lists only.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from api.domain.pricing.resolve import applicable, mixed_list_warning, pick
from api.domain.pricing.types import (
    PRICE_LIST_SALES_TYPES,
    PriceList,
    Rate,
    Tier,
    price_sales_type,
)

GJ = "state-gj"
APRIL = dt.date(2026, 4, 1)


def plist(pid: str, *, state: str | None = None, tier: Tier | None = None,
          sales_type: str | None = None, frm: dt.date = APRIL) -> PriceList:
    return PriceList(id=pid, name=pid, state_territory_id=state, channel_tier=tier,
                     effective_from=frm, effective_to=None, is_provisional=False,
                     sales_type=sales_type)


def rate(pl: PriceList, amount: str) -> Rate:
    return Rate(price_list_item_id=f"item-{pl.id}", price_list=pl, rate=Decimal(amount))


@pytest.mark.parametrize("general", [
    plist("base"), plist("tier", tier=Tier.DEALER), plist("state", state=GJ),
    plist("both", state=GJ, tier=Tier.DEALER)])
def test_a_typed_list_outranks_every_general_list(general: PriceList) -> None:
    typed = plist("commercial", sales_type="commercial")
    assert pick([rate(general, "90.00"), rate(typed, "100.00")]).price_list.id == "commercial"
    assert pick([rate(typed, "100.00"), rate(general, "90.00")]).price_list.id == "commercial"


def test_inside_the_typed_lists_state_and_tier_rank_as_before() -> None:
    lists = [plist("t", sales_type="subsidised"),
             plist("t-tier", sales_type="subsidised", tier=Tier.DEALER),
             plist("t-state", sales_type="subsidised", state=GJ),
             plist("t-both", sales_type="subsidised", state=GJ, tier=Tier.DEALER)]
    assert [pl.specificity for pl in lists] == [4, 5, 6, 7]
    assert pick([rate(pl, "10.00") for pl in lists]).price_list.id == "t-both"


def test_a_list_for_another_sale_type_is_never_applicable() -> None:
    lists = [plist("base"), plist("com", sales_type="commercial"),
             plist("ind", sales_type="industrial"), plist("sub", sales_type="subsidised")]
    got = applicable(lists, state_territory_id=GJ, tier="farmer", sales_type="industrial")
    assert {pl.id for pl in got} == {"base", "ind"}


def test_no_sale_type_draws_from_general_lists_only() -> None:
    lists = [plist("base"), plist("com", sales_type="commercial")]
    got = applicable(lists, state_territory_id=GJ, tier="farmer", sales_type=None)
    assert [pl.id for pl in got] == ["base"]
    # the keyword's default keeps the old callers on general lists
    assert [pl.id for pl in applicable(lists, state_territory_id=GJ, tier="farmer")] == ["base"]


@pytest.mark.parametrize("kind", ["commercial", "industrial", "subsidised"])
def test_the_three_typed_kinds_price_from_their_own_lists(kind: str) -> None:
    assert price_sales_type(kind) == kind


@pytest.mark.parametrize("kind", ["export", "sample", "marketing", "marketing_material",
                                  "replacement", None, "", "Commercial"])
def test_every_other_kind_prices_from_general_lists(kind: str | None) -> None:
    assert price_sales_type(kind) is None


def test_the_typed_kinds_are_the_three() -> None:
    assert PRICE_LIST_SALES_TYPES == ("commercial", "industrial", "subsidised")


def test_a_partial_typed_list_mixes_and_says_so() -> None:
    typed = plist("Commercial India", sales_type="commercial")
    general = plist("Gujarat", state=GJ)
    chosen = {"p1": rate(typed, "10.00"), "p2": rate(general, "11.00")}
    warning = mixed_list_warning(chosen)
    assert warning is not None and "sale-type" in warning
