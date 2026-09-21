"""Which price list wins (FS-010 section 10, the resolution row; GAP-087).

The precedence is a deliberate guess in the reversible direction, so these tests
assert the direction as much as the mechanism. If someone later flips state and
tier, `test_a_state_list_outranks_a_tier_list` is what should stop them and make
them read the gap first.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from api.domain.pricing.resolve import applicable, mixed_list_warning, pick
from api.domain.pricing.types import PriceList, Rate, Tier

D = Decimal
GJ, UP = "state-gj", "state-up"
APRIL = dt.date(2026, 4, 1)


def plist(pid: str, *, state: str | None = None, tier: Tier | None = None,
          frm: dt.date = APRIL, name: str | None = None,
          provisional: bool = False) -> PriceList:
    return PriceList(id=pid, name=name or pid, state_territory_id=state, channel_tier=tier,
                     effective_from=frm, effective_to=None, is_provisional=provisional)


def rate(pl: PriceList, amount: str, item: str | None = None) -> Rate:
    return Rate(price_list_item_id=item or f"item-{pl.id}", price_list=pl, rate=D(amount))


# ── the precedence, one level at a time ──────────────────────────────────────

def test_the_most_specific_list_wins() -> None:
    base = rate(plist("base"), "100.00")
    tier = rate(plist("tier", tier=Tier.DEALER), "90.00")
    state = rate(plist("state", state=GJ), "95.00")
    both = rate(plist("both", state=GJ, tier=Tier.DEALER), "85.00")

    assert pick([base, tier, state, both]).price_list.id == "both"
    assert pick([base, tier, state]).price_list.id == "state"
    assert pick([base, tier]).price_list.id == "tier"
    assert pick([base]).price_list.id == "base"
    assert pick([]) is None


def test_a_state_list_outranks_a_tier_list() -> None:
    """**The direction is the decision** (GAP-087). The client's file is
    state-based and complete, so a tier list is far more likely a discount layer
    than a replacement; the other order would silently override every state's own
    rates the day one tier list is loaded. Do not flip this without reading the
    gap: it is the expensive direction of the guess."""
    state = rate(plist("state", state=GJ), "95.00")
    tier = rate(plist("tier", tier=Tier.DEALER), "90.00")
    assert pick([tier, state]).price_list.id == "state"
    assert pick([state, tier]).price_list.id == "state", "order of the input must not matter"


def test_specificity_is_the_same_whichever_order_the_candidates_arrive() -> None:
    lists = [rate(plist("base"), "100.00"), rate(plist("state", state=GJ), "95.00"),
             rate(plist("tier", tier=Tier.DEALER), "90.00")]
    assert pick(lists).price_list.id == pick(list(reversed(lists))).price_list.id


# ── ties, which the constraints should make impossible ───────────────────────

def test_a_tie_at_one_specificity_is_broken_by_the_later_start_date() -> None:
    """The exclusion constraints refuse two published lists whose scope and range
    overlap, so this should be unreachable. It is deterministic anyway, because an
    arbitrary winner is a bug that appears once a quarter."""
    older = rate(plist("older", state=GJ, frm=dt.date(2026, 4, 1)), "95.00")
    newer = rate(plist("newer", state=GJ, frm=dt.date(2026, 10, 1)), "97.00")
    assert pick([older, newer]).price_list.id == "newer"
    assert pick([newer, older]).price_list.id == "newer"


def test_a_tie_on_date_too_is_broken_by_the_id() -> None:
    a = rate(plist("aaa", state=GJ), "95.00")
    b = rate(plist("bbb", state=GJ), "97.00")
    assert pick([a, b]).price_list.id == pick([b, a]).price_list.id == "bbb"


# ── scope filtering, which the read policy does not do ───────────────────────

def test_a_list_for_another_state_or_tier_is_not_applicable() -> None:
    """The policy stops a partner *seeing* a tier above them. This stops anyone
    *pricing* from a scope that is not theirs, which is a different question."""
    lists = [plist("base"), plist("gj", state=GJ), plist("up", state=UP),
             plist("dealer", tier=Tier.DEALER), plist("sub", tier=Tier.SUB_DEALER)]
    got = applicable(lists, state_territory_id=GJ, tier="dealer")
    assert {pl.id for pl in got} == {"base", "gj", "dealer"}


def test_a_caller_with_no_state_still_gets_the_unscoped_lists() -> None:
    lists = [plist("base"), plist("gj", state=GJ), plist("dealer", tier=Tier.DEALER)]
    got = applicable(lists, state_territory_id=None, tier="dealer")
    assert {pl.id for pl in got} == {"base", "dealer"}


def test_a_farmer_resolves_the_farmer_tier_and_the_base() -> None:
    """Migration 004 created a `farmer` label no partner can hold, and rule 8
    resolves it when a request carries no partner. Without that the base list
    would be doing two jobs at once (GAP-091)."""
    lists = [plist("base"), plist("farmer", tier=Tier.FARMER), plist("dealer", tier=Tier.DEALER)]
    got = applicable(lists, state_territory_id=GJ, tier="farmer")
    assert {pl.id for pl in got} == {"base", "farmer"}


# ── the warning the precedence cannot resolve on its own ─────────────────────

def test_one_list_for_every_line_warns_about_nothing() -> None:
    base = plist("base", name="Base 2026-27")
    assert mixed_list_warning({"p1": rate(base, "100.00"), "p2": rate(base, "90.00")}) is None


def test_lines_from_two_lists_say_so_with_the_counts() -> None:
    """A half-filled state list published deliberately leaves some lines on the
    state's rates and some on the base's. Correct if a state list is a layer, a
    mispricing if it replaces the base, and nobody has told us which."""
    base = plist("base", name="Base 2026-27")
    gj = plist("gj", state=GJ, name="Gujarat 2026-27")
    chosen = {"p1": rate(gj, "95.00"), "p2": rate(base, "100.00"), "p3": rate(base, "90.00")}
    warning = mixed_list_warning(chosen)

    assert warning is not None
    assert warning.startswith("mixed_price_lists:")
    assert "2 from 'Base 2026-27'" in warning
    assert "1 from 'Gujarat 2026-27'" in warning
    assert warning.split(":", 1)[1].strip(), "a code alone is not a warning"


def test_the_warning_lists_the_biggest_contributor_first() -> None:
    base, gj = plist("base", name="Base"), plist("gj", state=GJ, name="GJ")
    chosen = {"a": rate(gj, "1.00"), "b": rate(gj, "1.00"), "c": rate(base, "1.00")}
    warning = mixed_list_warning(chosen)
    assert warning is not None
    assert warning.index("2 from 'GJ'") < warning.index("1 from 'Base'")


def test_an_empty_document_warns_about_nothing() -> None:
    assert mixed_list_warning({}) is None


# ── the provisional flag travels with the list ───────────────────────────────

@pytest.mark.parametrize("provisional", [True, False])
def test_a_rate_carries_its_lists_provenance(provisional: bool) -> None:
    pl = plist("seeded", provisional=provisional)
    assert rate(pl, "100.00").price_list.is_provisional is provisional
