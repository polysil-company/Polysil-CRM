"""The products, tax and pricing contract (FS-010 section 4).

Money, rates and quantities cross the wire as decimal **strings**, never floats.
A float 0.1 is not a tenth, and these figures end up on an invoice.

**The field descriptions below become the notes in `docs/api/products.md`**
(CLAUDE.md 2.3), which is what the frontend track builds against.

Two shapes here differ from the rest of the API on purpose:

* **Offset paging, not the keyset paging the lead list uses.** The catalogue is a
  fixed 1,092 rows that every user sees in full, so a total is cheap and a picker
  wants one. A scoped, growing table is the case keyset paging exists for.
* **`provisional_fields` is a list, not a boolean.** It names which commercials
  are still our stand-ins rather than the client's, per field. One boolean over
  four would let a `PATCH` that sets a pack multiple mark a guessed tax slab as
  confirmed.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from api.schemas.leads import UUID_RE

QuotationCategory = Literal["head", "field", "both"]
PriceListStatus = Literal["draft", "published"]
TaxTreatment = Literal["domestic", "export_lut", "export_igst"]
Tier = Literal["distributor", "dealer", "sub_dealer", "farmer"]
ProvisionalField = Literal["hsn_code", "gst_slab", "mrp", "pack_multiple"]

MAX_LINES = 200
MAX_ITEMS = 2000
HSN_RE = r"^[0-9]{4,8}$"


class StateRef(BaseModel):
    """A state, as a price list names it. `code` is the two-letter code that also
    numbers that state's leads; it is null until an administrator sets one."""

    id: str
    name: str
    code: str | None


def _places(value: Decimal, places: int, what: str) -> Decimal:
    if value != value.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f"{what} carries at most {places} decimals")
    return value


class OffsetMeta(BaseModel):
    page: int = Field(description="The page that was returned, counting from 1.")
    limit: int = Field(description="The page size that was applied.")
    total: int = Field(description="Rows matching the filters, across all pages.")


# ── products ─────────────────────────────────────────────────────────────────

class Product(BaseModel):
    """One catalogue row, with the classification and slab resolved for the date
    asked about. `hsn_code` and `gst_slab` are null when nothing is in force."""

    id: str
    item_code: str | None = Field(description="The client's own code, once they send one.")
    description: str = Field(description="As it prints on a quotation.")
    product_category: str = Field(description="The category code, for grouping the picker.")
    quotation_category: QuotationCategory = Field(
        description="Which block of a subsidised quotation this may appear in: the head "
                    "unit, the field, or either.")
    uom: str
    uom_decimals: int = Field(
        description="Decimal places this unit admits. A quantity with more is refused, so "
                    "a NOS. item cannot be ordered 1.5 of.")
    hsn_code: str | None
    gst_slab: str | None = Field(description="A percentage as a decimal string, 5.00.")
    mrp: str | None
    pack_multiple: str | None = Field(
        description="Quantities must be a multiple of this when it is set.")
    is_subsidy_eligible: bool
    is_active: bool
    provisional_fields: list[ProvisionalField] = Field(
        description="Which of these figures are still our stand-ins rather than the "
                    "client's. Show it per field. An empty list means everything is theirs.")


class ProductPage(BaseModel):
    data: list[Product]
    meta: OffsetMeta


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    description: Annotated[str, Field(min_length=3, max_length=200,
                                      description="Unique, matched case-insensitively.")]
    product_category: Annotated[str, Field(min_length=1, max_length=50,
                                           description="An existing category code.")]
    quotation_category: QuotationCategory
    uom: Annotated[str, Field(min_length=1, max_length=20, description="An existing unit code.")]
    item_code: Annotated[str | None, Field(default=None, max_length=50)]
    mrp: Annotated[Decimal | None, Field(default=None, gt=0)]
    pack_multiple: Annotated[Decimal | None, Field(default=None, gt=0)]
    is_subsidy_eligible: bool = True

    @field_validator("mrp")
    @classmethod
    def _mrp_paise(cls, v: Decimal | None) -> Decimal | None:
        return v if v is None else _places(v, 2, "mrp")

    @field_validator("pack_multiple")
    @classmethod
    def _pack_places(cls, v: Decimal | None) -> Decimal | None:
        return v if v is None else _places(v, 3, "pack_multiple")


class ProductPatch(ProductCreate):
    """Send only what changes. Setting a field clears its `provisional_fields`
    entry, because the value is now the client's; the others are untouched."""

    model_config = ConfigDict(str_strip_whitespace=True)

    description: Annotated[str | None, Field(default=None, min_length=3, max_length=200)]
    product_category: Annotated[str | None, Field(default=None, min_length=1, max_length=50)]
    quotation_category: QuotationCategory | None = None
    uom: Annotated[str | None, Field(default=None, min_length=1, max_length=20)]
    is_subsidy_eligible: bool | None = None
    is_active: bool | None = None


class HsnAssign(BaseModel):
    """Classify a product from a date. The row in force is closed at that date."""

    hsn_code: Annotated[str, Field(pattern=HSN_RE, description="Four to eight digits.")]
    effective_from: dt.date = Field(
        description="The day this classification starts. Equal to the current row's own "
                    "start date is refused, because that row has nowhere to be closed.")


class HsnRow(BaseModel):
    id: str
    hsn_code: str
    effective_from: dt.date
    effective_to: dt.date | None = Field(description="Exclusive. Null while in force.")


# ── tax rates ────────────────────────────────────────────────────────────────

class TaxRate(BaseModel):
    id: str
    hsn_code: str
    rate: str = Field(description="A percentage as a decimal string, 5.000.")
    effective_from: dt.date
    effective_to: dt.date | None = Field(description="Exclusive. Null while in force.")
    is_active: bool


class TaxRatePage(BaseModel):
    data: list[TaxRate]
    meta: OffsetMeta


class TaxRateUpsert(BaseModel):
    """The Council's rate for a code, from a date. One row per change, not one per
    product: a slab change is a legal event affecting every product on that code."""

    rate: Annotated[Decimal, Field(
        ge=0, description="One of 0, 0.25, 3, 5, 12, 18, 28. Anything else is refused.")]
    effective_from: dt.date

    @field_validator("rate")
    @classmethod
    def _rate_places(cls, v: Decimal) -> Decimal:
        return _places(v, 3, "rate")


# ── price lists ──────────────────────────────────────────────────────────────

PriceListSalesType = Literal["commercial", "industrial", "subsidised"]
# Every quotation sale type and order type, so a form can send its own value as is.
DocumentSalesType = Literal["commercial", "industrial", "subsidised", "export", "sample",
                            "marketing", "marketing_material", "replacement"]


class PriceList(BaseModel):
    id: str
    name: str
    state_territory: StateRef | None = Field(
        description="The state this list prices for; null means it applies everywhere.")
    channel_tier: Tier | None = Field(
        description="The tier this list prices for; null means every tier.")
    status: PriceListStatus
    published_at: str | None
    effective_from: dt.date
    effective_to: dt.date | None = Field(description="Exclusive. Null while open-ended.")
    is_active: bool
    is_provisional: bool = Field(
        description="True while the rates are our stand-ins rather than the client's.")
    item_count: int
    unpriced_count: int = Field(
        description="Active products this list holds no rate for. They fall through to a "
                    "less specific list, or the line is refused.")
    sales_type: PriceListSalesType | None = Field(
        default=None,
        description="The sale type this list prices: commercial, industrial or subsidised. "
                    "Null is a general list, used for every sale type. A list for the "
                    "document's sale type outranks every general list (FS-061).")


class PriceListPage(BaseModel):
    data: list[PriceList]
    meta: OffsetMeta


class PriceListCreate(BaseModel):
    """`is_provisional` is deliberately absent. Only the master loader marks a list
    as carrying stand-in rates, and it writes directly rather than through here; a
    request field let anyone mark a genuine list a stand-in, which puts a warning
    on every quotation drawn from it telling the user not to send it."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)]
    effective_from: dt.date
    state_territory_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE, description="A state territory, or null for every state.")]
    channel_tier: Tier | None = Field(default=None,
                                      description="Null for every tier. `farmer` prices retail.")
    effective_to: Annotated[dt.date | None, Field(default=None)]
    source_note: Annotated[str | None, Field(default=None, max_length=500,
                                             description="Where the rates came from.")]
    sales_type: PriceListSalesType | None = Field(
        default=None,
        description="Null for every sale type. Set to price only commercial, industrial or "
                    "subsidised documents; fixed once published (FS-061).")


class PriceListPatch(BaseModel):
    """`effective_to` only, and forward only. A published list's rates never change:
    a correction is a new list (ADR-033), because changing one restates past orders."""

    effective_to: dt.date = Field(
        description="Exclusive, and must be later than the list's own start and not before "
                    "today.")


class PriceListItem(BaseModel):
    product_id: str
    description: str
    uom: str
    rate: str | None = Field(description="Null when this list holds no rate for the product.")
    is_active: bool


class PriceListItemsPage(BaseModel):
    data: list[PriceListItem]
    meta: OffsetMeta
    unpriced: int = Field(description="Active products with no rate in this list.")


class PriceListItemIn(BaseModel):
    product_id: Annotated[str, Field(pattern=UUID_RE)]
    rate: Annotated[Decimal, Field(
        gt=0, description="Rupees per unit, at most two decimals. More is refused, not "
                          "rounded: it is the client's number.")]

    @field_validator("rate")
    @classmethod
    def _rate_paise(cls, v: Decimal) -> Decimal:
        return _places(v, 2, "rate")


class PriceListItemsPut(BaseModel):
    """Replaces the draft's rates wholesale. A product left out has no rate."""

    items: Annotated[list[PriceListItemIn], Field(max_length=MAX_ITEMS)]


class PublishRequest(BaseModel):
    allow_unpriced: bool = Field(
        default=False,
        description="Publish even though some active products have no rate in this list. "
                    "Those lines fall through to a less specific list, and a document that "
                    "draws from more than one says so.")


class PublishResult(BaseModel):
    price_list: PriceList
    closed_predecessor_id: str | None = Field(
        description="The list this one superseded, closed at the same date in the same "
                    "transaction.")
    unpriced_count: int


# ── the pricing preview ──────────────────────────────────────────────────────

GST_SLAB_DOC = ("FS-069: the GST slab the user picked from `GET /pricing/gst-slabs`, a "
                "percentage such as 18. Commercial and industrial only. Omit, null, or the "
                "line's own HSN slab: the line follows the HSN rate. Send it only for a slab "
                "picked in the dropdown, and re-send it for every line whose "
                "`gst_slab_chosen` is true when saving the whole basket.")


def _slab_places(v: Decimal | None) -> Decimal | None:
    return None if v is None else _places(v, 3, "gst_slab")


class FreightIn(BaseModel):
    """FS-069: one freight or transport charge per document, before tax."""

    model_config = ConfigDict(extra="forbid")

    amount: Annotated[Decimal, Field(
        allow_inf_nan=False,
        description="Rupees before tax: above 0, at most two decimals, at most "
                    "99,999,999.99. Anything else is 422 freight_amount_invalid.")]
    gst_slab: Annotated[Decimal | None, Field(
        default=None, ge=0, le=100,
        description="A slab from `GET /pricing/gst-slabs`. Omit for the default: the "
                    "highest slab among the goods lines.")]

    @field_validator("gst_slab")
    @classmethod
    def _gst_places(cls, v: Decimal | None) -> Decimal | None:
        return _slab_places(v)


class FreightOut(BaseModel):
    """The freight as priced. Its tax is part of the document's taxable, tax and
    total figures, never its gross or discount."""

    amount: str
    gst_slab: str
    gst_slab_chosen: bool = Field(description="False when the slab is the default, which "
                                              "follows the goods lines on every save.")
    cgst_rate: str = Field(description="Half the slab when intra-state, else 0.")
    sgst_rate: str = Field(description="Half the slab when intra-state, else 0.")
    igst_rate: str = Field(description="The slab when inter-state, else 0.")
    cgst: str = Field(description="Freight's CGST, rounded on its own.")
    sgst: str = Field(description="Freight's SGST, always equal to its CGST.")
    igst: str = Field(description="Freight's IGST.")
    total: str = Field(description="The amount plus its tax.")


class ProductCategoryItem(BaseModel):
    """FS-070 (BE-024): a category the product form can offer."""

    id: str = Field(description="What a scheme's `product_category` target takes.")
    code: str = Field(description="What `POST /products` takes as `product_category`.")
    name: str
    sort_order: int = Field(description="Lower first; the list is already in this order.")
    is_active: bool = Field(description="A switched-off category is listed; offer it only "
                                        "when the product already has it.")


class UomItem(BaseModel):
    """FS-070 (BE-024): a unit the product form can offer."""

    id: str
    code: str = Field(description="What `POST /products` takes as `uom`.")
    name: str
    decimals: int = Field(description="How many decimals a quantity in this unit takes, 0 to 3.")
    is_active: bool = Field(description="A switched-off unit is listed; offer it only when "
                                        "the product already has it.")


class GstSlabChoices(BaseModel):
    choices: list[str] = Field(description="The slabs the dropdown offers, from the admin "
                                           "setting `gst_slab_choices`.")


class QuoteLineIn(BaseModel):
    product_id: Annotated[str, Field(pattern=UUID_RE)]
    qty: Annotated[Decimal, Field(
        gt=0, description="At most as many decimals as the unit admits, and a multiple of "
                          "`pack_multiple` when the product sets one.")]
    discount_pct: Annotated[Decimal, Field(
        default=Decimal("0"), ge=0, le=100,
        description="The first discount tier: per cent off the gross, at most three "
                    "decimals.")]
    discount2_pct: Annotated[Decimal, Field(
        default=Decimal("0"), ge=0, le=100,
        description="The second tier, per cent off the balance after the first. "
                    "Each tier's amount is rounded to the paisa before the next applies.")]
    discount3_pct: Annotated[Decimal, Field(
        default=Decimal("0"), ge=0, le=100,
        description="The third tier, per cent off the balance after the second.")]
    gst_slab: Annotated[Decimal | None, Field(default=None, ge=0, le=100,
                                              description=GST_SLAB_DOC)]

    @field_validator("qty")
    @classmethod
    def _qty_places(cls, v: Decimal) -> Decimal:
        return _places(v, 3, "qty")

    @field_validator("discount_pct", "discount2_pct", "discount3_pct")
    @classmethod
    def _discount_places(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        return _places(v, 3, str(info.field_name))

    @field_validator("gst_slab")
    @classmethod
    def _gst_places(cls, v: Decimal | None) -> Decimal | None:
        return _slab_places(v)

    @property
    def discounts(self) -> tuple[Decimal, Decimal, Decimal]:
        return (self.discount_pct, self.discount2_pct, self.discount3_pct)


class QuoteLinesRequest(BaseModel):
    place_of_supply_territory_id: Annotated[str, Field(
        pattern=UUID_RE,
        description="Where the goods are delivered. Resolved up to its state, which decides "
                    "whether the supply is intra-state. Not the partner's own territory.")]
    lines: Annotated[list[QuoteLineIn], Field(min_length=1, max_length=MAX_LINES)]
    as_of: dt.date | None = Field(
        default=None,
        description="Price against the masters in force on this date. Today in India by "
                    "default. A future date is allowed and warns; more than a year ahead "
                    "is refused.")
    partner_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Staff only, to price for a partner. A partner caller's tier comes from "
                    "their own account and this field is refused.")]
    seller_gstin_id: Annotated[str | None, Field(
        default=None, pattern=UUID_RE,
        description="Which of our registrations supplies. Defaults to the one in force.")]
    tax_treatment: TaxTreatment = Field(
        default="domestic",
        description="An export document's stored treatment, so the preview shows the tax it "
                    "will store: export_lut prices every line at 0 % IGST, export_igst at its "
                    "slab, and neither is ever intra-state.")
    sales_type: DocumentSalesType | None = Field(
        default=None,
        description="The quotation's sale type or the order's type, so the preview prices "
                    "from the same lists the save will. commercial, industrial and subsidised "
                    "use their own lists first; every other value, and null, use general "
                    "lists only (FS-061). A GST choice and freight need commercial or "
                    "industrial.")
    freight: FreightIn | None = Field(default=None, description="FS-069: optional freight.")


class QuoteLine(BaseModel):
    """Every figure the quotation prints, in the order it prints them.

    `gross`, `cgst_rate` and `sgst_rate` are returned so nothing on the client
    derives them and lands on a different paisa. `price_list_item_id` and
    `gst_rate_id` are returned so the save step can re-resolve and compare.
    """

    product_id: str
    description: str
    uom: str
    qty: str
    rate: str
    price_list_id: str
    price_list_item_id: str
    gross: str
    discount_pct: str = Field(description="The first tier's percentage.")
    discount1_amt: str = Field(description="What the first tier took off the gross.")
    after_discount1: str
    discount2_pct: str
    discount2_amt: str = Field(description="What the second tier took off after_discount1.")
    after_discount2: str
    discount3_pct: str
    discount3_amt: str = Field(description="What the third tier took off after_discount2.")
    discount: str = Field(description="The three amounts summed. Not gross x discount_pct: "
                                      "that is only the first tier.")
    taxable: str = Field(description="The balance after the third tier.")
    hsn_code: str
    gst_slab: str = Field(description="The line's slab: the one picked, else the HSN's.")
    hsn_slab: str = Field(description="The product's HSN slab, whatever was picked.")
    gst_slab_chosen: bool = Field(description="True when the slab was picked and differs "
                                              "from the HSN's. Show it as changed.")
    gst_rate_id: str
    cgst_rate: str
    sgst_rate: str
    igst_rate: str
    cgst: str
    sgst: str
    igst: str
    total: str
    provisional_fields: list[str] = Field(
        description="Which of this line's commercials are stand-ins: rate, gst_slab.")


class QuoteTotals(BaseModel):
    """The sum of the rounded lines, never a recomputation on the summed values.
    The two differ by paise, and a hundred-line document by rupees. `gross` and
    `discount` are the goods only; `taxable`, the taxes and `total` include freight,
    so `taxable = gross - discount + freight.amount` (FS-069)."""

    gross: str
    discount: str
    taxable: str
    cgst: str
    sgst: str
    igst: str
    total: str


class QuoteLinesResponse(BaseModel):
    as_of: dt.date
    seller_gstin_id: str
    seller_state: str = Field(description="The state code of the registration supplying.")
    place_of_supply_state: str
    intra_state: bool = Field(
        description="True when both states match, so the tax splits into CGST and SGST. "
                    "Returned so the document never re-derives it.")
    price_list_ids: list[str] = Field(
        description="Every list the lines resolved from. More than one raises the "
                    "`mixed_price_lists` warning.")
    lines: list[QuoteLine]
    freight: FreightOut | None = None
    totals: QuoteTotals
    warnings: list[str] = Field(
        description="Each is `code: sentence`. Split on the first colon, switch on the "
                    "code, show the sentence.")
