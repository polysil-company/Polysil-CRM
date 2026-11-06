"""Money arithmetic every module shares.

One place, because two engines need it and neither may import the other. The
subsidy engine taxes a block from the scheme's own parameters; the commercial
engine taxes a line from the product's rate in force (FS-010 rule 13). They are
allowed to disagree about tax and they are not allowed to disagree about what
rounding means.

**Half away from zero, never banker's.** Indian money convention, and the same
thing Excel's `ROUND` does, which matters because the client's workbooks are the
specification for the subsidy figures. The two modes differ on a value ending in
exactly half a paisa, and that is not rare: a discount of 2.5 % lands there about
once in forty lines, and FS-008's boundary suite has two cases (609.375 and
390.625) that separate them in opposite directions.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


def round2(value: Decimal) -> Decimal:
    """Excel's `ROUND(x, 2)`: half away from zero, which is half-up for money."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_pct(whole: Decimal) -> Decimal:
    """A percentage as the ratio the arithmetic multiplies by: `70` to `0.7`."""
    return whole / HUNDRED
