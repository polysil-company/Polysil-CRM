"""Which price list wins (FS-010 rule 3).

**Per product, not per document.** A document-wide resolution refuses a forty-line
quotation because one product is missing a rate, and it makes a state list a
wholesale replacement for the base rather than a partial override. Per product, a
state list carrying three corrections over a complete base list does what anyone
would expect.

**The most specific published list in force wins, and state outranks tier.** That
ordering is a deliberate guess in the reversible direction (GAP-087): the client's
own file is state-based and complete, so a tier list, when it arrives, is far more
likely a discount layer than a replacement. Tier-above-state would silently
override every state's own rates the day one tier list is loaded, which is the
expensive way to be wrong.

**When one document draws from more than one list, it says so.** That is the case
the precedence creates and cannot resolve on its own: a half-filled state list
published deliberately leaves some lines on the state's rates and some on the
base's. Right if the state list is a layer, a mispricing if it is a replacement,
and nobody has told us which.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from api.domain.pricing.types import PriceList, Rate

MIXED = "mixed_price_lists"


def pick(rates: Iterable[Rate]) -> Rate | None:
    """The winner among the rates one product has, across the lists in force.

    Ties are resolved on the later `effective_from`, then on the list id, so the
    answer is deterministic. A tie at the same specificity should be impossible:
    the exclusion constraints refuse two published lists whose scope and range
    overlap, and this is the belt to that braces.
    """
    best: Rate | None = None
    for candidate in rates:
        if best is None or _outranks(candidate, best):
            best = candidate
    return best


def _outranks(candidate: Rate, incumbent: Rate) -> bool:
    a, b = candidate.price_list, incumbent.price_list
    if a.specificity != b.specificity:
        return a.specificity > b.specificity
    if a.effective_from != b.effective_from:
        return a.effective_from > b.effective_from
    return a.id > b.id


def mixed_list_warning(chosen: Mapping[str, Rate]) -> str | None:
    """Rule 3's warning. `None` when every line came from one list."""
    counts: dict[str, tuple[str, int]] = {}
    for rate in chosen.values():
        name, n = counts.get(rate.price_list.id, (rate.price_list.name, 0))
        counts[rate.price_list.id] = (name, n + 1)
    if len(counts) < 2:
        return None
    parts = ", ".join(f"{n} from {name!r}" for name, n in
                      sorted(counts.values(), key=lambda c: (-c[1], c[0])))
    return (f"{MIXED}: the lines resolved from more than one price list ({parts}). "
            "That is correct if a state list is a discount layer over the base and a "
            "mispricing if it replaces it, which is still an open question.")


def applicable(lists: Iterable[PriceList], *, state_territory_id: str | None,
               tier: str | None) -> list[PriceList]:
    """The lists whose scope a caller in this state and tier may draw from.

    A list scoped to another state or another tier is not applicable, regardless
    of what the read policy allowed. The policy stops a partner *seeing* a tier
    above them; this stops anyone *pricing* from a scope that is not theirs.
    """
    out = []
    for pl in lists:
        if pl.state_territory_id is not None and pl.state_territory_id != state_territory_id:
            continue
        if pl.channel_tier is not None and pl.channel_tier != tier:
            continue
        out.append(pl)
    return out
