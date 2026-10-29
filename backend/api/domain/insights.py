"""The insights report's rules (FS-079 §5, rules 14 to 21). Pure: each function
takes counts and returns one row, or None when its data is too thin (rule 6).

Sentences are plain English, one idea each, no em dashes. Names sit in curly
quotes so a quote mark inside a name cannot break the sentence (EC-30).
"""

# ruff: noqa: E501  (the sentences read better whole)

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

MIN_LOSSES: Final = 10
MIN_RISE: Final = Decimal("5.0")
MIN_SOURCE_LEADS: Final = 10
MIN_ANSWERED: Final = 10
MIN_BAND: Final = 5
MIN_CONTACTED: Final = 10
WAIT_HOURS: Final = 48
STAGE_LABEL: Final = {"new": "New", "contacted": "Contacted", "qualified": "Qualified",
                      "quoted": "Quoted", "negotiation": "Negotiation"}


def pct(part: int, whole: int) -> Decimal:
    """One place, half up: the figure shown is the figure compared (rule 20)."""
    if whole <= 0:
        return Decimal("0.0")
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), ROUND_HALF_UP)


def quoted(name: str | None, fallback: str) -> str:
    return f"“{name or fallback}”"


def _row(code: str, title: str, figure: Decimal, previous: Decimal | None, unit: str,
         link: Mapping[str, str] | None) -> dict[str, Any]:
    return {"code": code, "title": title, "figure": str(figure),
            "previous": None if previous is None else str(previous), "unit": unit,
            "link": dict(link) if link else None}


def lost_reason_rising(current: Mapping[str, int], previous: Mapping[str, int],
                       labels: Mapping[str, str | None]) -> dict[str, Any] | None:
    """The reason whose share of losses grew most, by 5 points or more."""
    cur_n, prev_n = sum(current.values()), sum(previous.values())
    if cur_n < MIN_LOSSES or prev_n < MIN_LOSSES:
        return None
    ranked = sorted(
        ((pct(n, cur_n) - pct(previous.get(k, 0), prev_n), pct(n, cur_n), labels.get(k) or "Unnamed reason", k)
         for k, n in current.items()),
        # ties: the bigger share, then the name, then the id (rule 19)
        key=lambda t: (-t[0], -t[1], t[2], t[3]))
    if not ranked or ranked[0][0] < MIN_RISE:
        return None
    best = ranked[0]
    _rise, share, name, key = best
    before = pct(previous.get(key, 0), prev_n)
    return _row("lost_reason_rising",
                f"{quoted(name, 'Unnamed reason')} is now {share}% of lost leads, up from {before}%.",
                share, before, "pct", {"report": "lost-leads", "group_by": "reason"})


def drop_off_stage(current: Mapping[str, int], previous: Mapping[str, int]) -> dict[str, Any] | None:
    """The stage most losses came from. `unknown` counts in the total but is never
    the one named (rule 18)."""
    total = sum(current.values())
    if total < MIN_LOSSES:
        return None
    named = {k: v for k, v in current.items() if k in STAGE_LABEL and v > 0}
    if not named:
        return None
    stage = max(sorted(named), key=lambda k: named[k])
    share = pct(named[stage], total)
    prev_total = sum(previous.values())
    before = pct(previous.get(stage, 0), prev_total) if prev_total else None
    return _row("drop_off_stage", f"Most lost leads were lost at {STAGE_LABEL[stage]}: {share}% of them.",
                share, before, "pct", {"report": "lost-leads", "group_by": "reason"})


def source_best_worst(sources: Mapping[str, tuple[int, int]],
                      labels: Mapping[str, str | None]) -> dict[str, Any] | None:
    """The sources converting best and worst, among those with 10 or more leads.
    Equal rates: no row (rule 19)."""
    rates = sorted(((pct(won, leads), labels.get(k) or "Unnamed source", k)
                    for k, (leads, won) in sources.items() if leads >= MIN_SOURCE_LEADS),
                   key=lambda t: (-t[0], t[1], t[2]))
    if len(rates) < 2 or rates[0][0] == rates[-1][0]:
        return None
    (hi, hi_name, _), (lo, lo_name, _) = rates[0], rates[-1]
    return _row("source_best_worst",
                f"{quoted(hi_name, '')} leads convert best ({hi}%); {quoted(lo_name, '')} leads convert least ({lo}%).",
                hi, lo, "pct", {"report": "lead-conversion", "group_by": "source"})


def quotation_answers(current: tuple[int, int, int], previous: tuple[int, int, int],
                      days: int) -> dict[str, Any] | None:
    """(accepted, rejected, expired) per period. Answered = accepted + rejected;
    expired is reported apart (rule 15)."""
    (ca, cr, ce), (pa, pr, _) = current, previous
    if ca + cr < MIN_ANSWERED or pa + pr < MIN_ANSWERED:
        return None
    now, before = pct(ca, ca + cr), pct(pa, pa + pr)
    tail = f" {ce} more expired unanswered." if ce else ""
    return _row("quotation_answers",
                f"{now}% of answered quotations were accepted, against {before}% in the {days} days before.{tail}",
                now, before, "pct", None)


def quotation_discount(above: tuple[int, int], at_or_below: tuple[int, int]) -> dict[str, Any] | None:
    """(accepted, answered) for discounts above 5% and at or below (rule 16)."""
    (aa, an), (ba, bn) = above, at_or_below
    if an < MIN_BAND or bn < MIN_BAND:
        return None
    hi, lo = pct(aa, an), pct(ba, bn)
    return _row("quotation_discount",
                f"Quotations with a discount above 5% were accepted {hi}% of the time, against {lo}% at or below 5%.",
                hi, lo, "pct", None)


def first_contact_speed(hours: Sequence[float], waited: int) -> dict[str, Any] | None:
    """Median hours to first contact among contacted leads, and how many waited over
    48 hours, never-contacted ones included (rule 17). Negative durations are left
    out by the caller."""
    ordered = sorted(h for h in hours if h >= 0)
    if len(ordered) < MIN_CONTACTED:
        return None
    median = Decimal(str(ordered[math.ceil(len(ordered) * 0.5) - 1])).quantize(Decimal("0.1"), ROUND_HALF_UP)
    unit = "hour" if median == 1 else "hours"
    tail = (f" {waited} waited over {WAIT_HOURS} hours." if waited != 1
            else f" 1 waited over {WAIT_HOURS} hours.")
    return _row("first_contact_speed",
                f"New leads were first contacted after a median of {median} {unit}.{tail if waited else ''}",
                median, None, "hours", {"report": "follow-ups"})

