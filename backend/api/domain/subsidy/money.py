"""Rounding, the way the workbooks round (FS-008 rules 2, 4, 25).

Every intermediate value is an exact `Decimal`. The workbooks round at specific
cells and nowhere else, and the three of them round at different cells: Drip
rounds every block, Mini Sprinkler rounds one block (insurance) and two kinds of
line, Sprinkler rounds every line and every block but the inspection amount. A
`RoundingPolicy` names the cells; the pipeline asks it at each one. The policy is
data (`subsidy_system.rounded_blocks`, `rounded_lines`); the constants below are
the seeds the loader writes and the tests read.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


def round2(value: Decimal) -> Decimal:
    """Excel's `ROUND(x, 2)`: half away from zero, which is half-up for money."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_pct(whole: Decimal) -> Decimal:
    """A category's `70` as the ratio the arithmetic multiplies by."""
    return whole / HUNDRED


# The cells a workbook may round, in the order the summary sheet lists them.
BLOCK_KEYS: tuple[str, ...] = (
    "a_plus_b",         # Drip I20 = ROUND(I18+I19,2); Mini I20 = I18+I19
    "gst_ab",           # the two 2.5 % lines on A+B
    "gst_c",            # the two 2.5 % lines on the installation
    "total_abc_gst",    # Drip I26 = ROUND(SUM(I20:I25),2)
    "insurance",        # both: ROUND(I26*0.28%,2), the one block Mini rounds
    "gst_d",            # the two 9 % lines on the insurance
    "inspection",       # Drip I30 = ROUND((I20+I35)*0.4%,2); Mini and Sprinkler unrounded
    "gst_e",            # the two 9 % lines on the inspection
    "education_split",  # Drip I34 = ROUND(K34*I12/K12,2)
    "sump",             # Drip I35 = ROUND(H35*I12,2); Mini I35 = H35*I12
    "dbt",              # Sprinkler J29 = ROUND(J27+J26+J28,2)
    "cost_of_mis",      # Drip I36 = ROUND(...,2); Mini I36 a bare sum
    "gst_totals",       # the total CGST and SGST lines
    "total_gst",
    "total_incl_gst",
)

# The kinds of line a workbook may round: Mini 'Quo A'!J58 = ROUND(H58*I58,2) for a
# field line against J25 = H25*I25 for a head line; Sprinkler rounds every line.
LINE_KINDS: tuple[str, ...] = ("head", "field", "installation", "transport")


@dataclass(frozen=True)
class RoundingPolicy:
    blocks: frozenset[str]
    lines: frozenset[str]

    def __post_init__(self) -> None:
        unknown = (self.blocks - set(BLOCK_KEYS)) | (self.lines - set(LINE_KINDS))
        if unknown:
            raise ValueError(f"unknown rounding keys: {sorted(unknown)}")

    def block(self, key: str, value: Decimal) -> Decimal:
        return round2(value) if key in self.blocks else value

    def line(self, kind: str, value: Decimal) -> Decimal:
        return round2(value) if kind in self.lines else value


DRIP_ROUNDING = RoundingPolicy(blocks=frozenset(BLOCK_KEYS), lines=frozenset())
MINI_SPRINKLER_ROUNDING = RoundingPolicy(blocks=frozenset({"insurance"}),
                                         lines=frozenset({"field", "installation"}))
# Sprinkler names only the blocks it actually asks for. Declaring `a_plus_b`
# would round `'BOQ'!J26`, which the workbook leaves alone (code review F-11).
SPRINKLER_ROUNDING = RoundingPolicy(
    blocks=frozenset({"gst_ab", "dbt", "gst_e", "cost_of_mis", "gst_totals", "total_gst",
                      "total_incl_gst"}),
    lines=frozenset({"field", "transport"}))
