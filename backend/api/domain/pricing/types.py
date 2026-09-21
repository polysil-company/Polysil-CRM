"""The pricing engine's inputs and outputs: frozen dataclasses of `Decimal`,
nothing from SQLAlchemy or pydantic (CLAUDE.md rule 1).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")


class PricingError(Exception):
    """A refusal the service turns into a 422 naming the field."""

    def __init__(self, code: str, message: str, field_path: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field_path = field_path


class Tier(StrEnum):
    """`channel_tier`, created by migration 004 and shared with `price_list`.
    `FARMER` is the tier no partner holds: a request with no partner resolves it."""

    DISTRIBUTOR = "distributor"
    DEALER = "dealer"
    SUB_DEALER = "sub_dealer"
    FARMER = "farmer"


# ── masters, as the service hands them to the domain ─────────────────────────

@dataclass(frozen=True)
class PriceList:
    id: str
    name: str
    state_territory_id: str | None
    channel_tier: Tier | None
    effective_from: dt.date
    effective_to: dt.date | None
    is_provisional: bool

    @property
    def specificity(self) -> int:
        """Rule 3's precedence, as a number. State outranks tier: a tier list is
        far more likely a discount layer than a wholesale replacement, and the
        other order would silently override every state's own rates the day one
        tier list arrives (GAP-087)."""
        if self.state_territory_id is not None and self.channel_tier is not None:
            return 3
        if self.state_territory_id is not None:
            return 2
        if self.channel_tier is not None:
            return 1
        return 0


@dataclass(frozen=True)
class Rate:
    """One product's rate inside one list."""

    price_list_item_id: str
    price_list: PriceList
    rate: Decimal


@dataclass(frozen=True)
class TaxRate:
    """The slab for an HSN code, and the classification that reached it. Two dated
    masters, so both ids travel: a document snapshots what it was taxed with."""

    gst_rate_id: str
    hsn_code: str
    slab: Decimal                  # a percentage: 5.00, 18.00
    is_provisional: bool


@dataclass(frozen=True)
class Product:
    id: str
    description: str
    uom_code: str
    uom_decimals: int
    pack_multiple: Decimal | None
    is_active: bool
    provisional_fields: frozenset[str] = field(default_factory=frozenset)


# ── a line, in and out ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class LineInput:
    product: Product
    qty: Decimal
    discount_pct: Decimal = ZERO


@dataclass(frozen=True)
class LineTax:
    """Every figure the invoice prints, in the order it prints them. `gross` is
    returned so no client derives it and lands on a different paisa."""

    gross: Decimal
    discount: Decimal
    taxable: Decimal
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal


@dataclass(frozen=True)
class PricedLine:
    product: Product
    qty: Decimal
    discount_pct: Decimal
    rate: Rate
    tax: TaxRate
    money: LineTax

    @property
    def provisional_fields(self) -> tuple[str, ...]:
        """What on this line is still a stand-in of ours rather than the client's.
        `rate` comes from the list, the tax fields from the product."""
        out = {f for f in self.product.provisional_fields if f in ("hsn_code", "gst_slab")}
        if self.rate.price_list.is_provisional:
            out.add("rate")
        if self.tax.is_provisional:
            out.add("gst_slab")
        return tuple(sorted(out))


@dataclass(frozen=True)
class DocumentTotals:
    gross: Decimal
    discount: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total: Decimal


@dataclass(frozen=True)
class PricedDocument:
    lines: tuple[PricedLine, ...]
    totals: DocumentTotals
    intra_state: bool
    warnings: tuple[str, ...]
