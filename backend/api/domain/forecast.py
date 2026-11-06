"""The sales forecast's arithmetic (FS-079 §5.1). Pure: no database.

These functions are the reference. The service computes the same figures in one
SQL pass for speed (rule 13), and a test holds the two equal.
"""

# ruff: noqa: E501, RUF002, RUF003  (the rules quote the spec's ×)

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

OPEN_STAGES: Final = ("new", "contacted", "qualified", "quoted", "negotiation")
MIN_CLOSED: Final = 10          # under this, a stage borrows a rate (rule 5); in all, too thin (rule 6)
MIN_WON: Final = 10             # under this, no median days to win (rule 7)
STALE_FACTOR: Final = 3         # a lead older than 3 × the median goes to later (rule 12)
LATER: Final = "later"
_CENT: Final = Decimal("0.01")


@dataclass(frozen=True)
class Rate:
    """A stage's win rate as an exact fraction. `won`/`closed` are what the weight
    uses; `own_closed` is how many closed leads reached the stage itself."""

    stage: str
    won: int
    closed: int
    own_closed: int
    low_confidence: bool

    @property
    def pct(self) -> Decimal:
        """For display only (rule 4)."""
        return (Decimal(self.won) * 100 / Decimal(self.closed)).quantize(Decimal("0.1"), ROUND_HALF_UP)


def stages_reached(stage: str, lost_from: str | None, event_targets: Iterable[str]) -> frozenset[str]:
    """Rule 3. Every lead reached `new`. A lost lead reached every stage up to its
    `lost_from_stage` (manual moves are one step at a time). A won lead reached the
    stages its stage-change events name, and no others: a lead won straight from
    `quoted` never reached `negotiation` (EC-1)."""
    reached = {"new"}
    if stage == "lost":
        if lost_from in OPEN_STAGES:
            reached.update(OPEN_STAGES[: OPEN_STAGES.index(lost_from) + 1])
    elif stage == "won":
        reached.update(t for t in event_targets if t in OPEN_STAGES)
    return frozenset(reached)


def win_rates(closed: Iterable[tuple[bool, frozenset[str]]]) -> dict[str, Rate] | None:
    """Rules 4 to 6. `closed` is (won, stages reached) per lead won or lost in the
    window. None when the history is too thin to weight anything."""
    rows = list(closed)
    total = len(rows)
    if total < MIN_CLOSED:
        return None
    total_won = sum(1 for won, _ in rows if won)
    own: dict[str, tuple[int, int]] = {}
    for stage in OPEN_STAGES:
        hit = [won for won, reached in rows if stage in reached]
        own[stage] = (sum(hit), len(hit))
    rates: dict[str, Rate] = {}
    for i, stage in enumerate(OPEN_STAGES):
        won, n = own[stage]
        if n >= MIN_CLOSED:
            rates[stage] = Rate(stage, won, n, n, False)
            continue
        # the nearest earlier stage with enough history, else the overall rate (rule 5)
        borrowed = next((own[s] for s in reversed(OPEN_STAGES[:i]) if own[s][1] >= MIN_CLOSED),
                        (total_won, total))
        rates[stage] = Rate(stage, borrowed[0], borrowed[1], n, True)
    return rates


def weighted(value: Decimal, rate: Rate) -> Decimal:
    """Rule 11: value × won ÷ closed, multiplied first, rounded half up to the paisa."""
    return (value * rate.won / Decimal(rate.closed)).quantize(_CENT, ROUND_HALF_UP)


def median_days(days: Iterable[int]) -> int | None:
    """Rule 7: `percentile_disc(0.5)`, the lower middle of an even count. None under
    MIN_WON won leads."""
    ordered = sorted(d for d in days if d >= 0)
    if len(ordered) < MIN_WON:
        return None
    return ordered[math.ceil(len(ordered) * 0.5) - 1]


def months(today: dt.date) -> list[str]:
    """This month and the next two, as `YYYY-MM`."""
    out = []
    y, m = today.year, today.month
    for _ in range(3):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def expected_month(created: dt.date, median: int | None, today: dt.date) -> str:
    """Rule 12, all dates IST. created + median; past dates come to this month; a
    lead older than 3 × the median, or beyond the third month, goes to later."""
    if median is None:
        return LATER
    if (today - created).days > STALE_FACTOR * max(median, 1):
        return LATER
    target = max(created + dt.timedelta(days=median), today)
    key = f"{target.year:04d}-{target.month:02d}"
    return key if key in months(today) else LATER


def value_of(quotation_total: Decimal | None, estimate: Decimal | None) -> tuple[Decimal | None, str | None]:
    """Rule 8: a live quotation above 0, else an estimate above 0, else none. Also
    says which, for `valued_by` (EC-19)."""
    if quotation_total is not None and quotation_total > 0:
        return quotation_total, "quotation"
    if estimate is not None and estimate > 0:
        return estimate, "estimate"
    return None, None
