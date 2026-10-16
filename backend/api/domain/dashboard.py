"""The dashboard's arithmetic (FS-017): the relative change, the rate and the
rounding. Pure Decimal; no float, no database."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_MONEY = Decimal("0.01")
_ONE_PLACE = Decimal("0.1")


def one_place(d: Decimal) -> str:
    """Half up, never Postgres's round() or Python's half-even default; zero is
    "0.0", not "-0.0" (review B-3)."""
    q = d.quantize(_ONE_PLACE, rounding=ROUND_HALF_UP)
    return format(Decimal("0.0") if q == 0 else q, "f")


def money(d: Decimal | None) -> str:
    return format((d or Decimal(0)).quantize(_MONEY, rounding=ROUND_HALF_UP), "f")


def delta_percent(current: Decimal, previous: Decimal) -> str | None:
    """The relative change, for every period figure, the rate included."""
    if previous == 0:
        return None
    return one_place((current - previous) / previous * 100)


def rate(won: int, total: int) -> Decimal:
    return Decimal(won) / Decimal(total) * 100 if total else Decimal(0)
