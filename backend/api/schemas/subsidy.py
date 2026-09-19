"""The subsidy calculation contract (FS-008 section 4).

Money and areas cross the wire as decimal **strings**, never floats: a float
`0.1` is not a tenth and a quotation that disagrees with the client's workbook by
a paisa is a support call. Areas carry three decimals, money two, Jantri figures
four.

**The field descriptions below become the notes in `docs/api/subsidy.md`**
(CLAUDE.md 2.3), which is what the frontend track builds against.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SystemType = Literal["drip", "mini_sprinkler", "sprinkler"]
Nozzle = Literal["plastic", "brass"]

MAX_LINES = 200
MAX_CROPS = 10


def _places(value: Decimal, places: int, what: str) -> Decimal:
    if value != value.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f"{what} carries at most {places} decimals")
    return value


class Line(BaseModel):
    """One row of the bill of quantities, as the designer typed it.

    GAP-080: keyed on the description and carrying its own rate, because there is
    no product master with item codes yet. When module F lands, this becomes a
    `product_id` and the rate comes from the price list in force.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(min_length=1, max_length=300,
                             description="The item, as it prints on the quotation.")
    uom: str = Field(min_length=1, max_length=20, description="Unit of measure, for the document.")
    rate: Decimal = Field(ge=0, description="Rate per unit in rupees, at most two decimals.")
    qty: Decimal = Field(ge=0, description="Quantity, at most three decimals.")

    @field_validator("rate")
    @classmethod
    def _rate_paise(cls, v: Decimal) -> Decimal:
        return _places(v, 2, "rate")

    @field_validator("qty")
    @classmethod
    def _qty_places(cls, v: Decimal) -> Decimal:
        return _places(v, 3, "qty")


class CropRequest(BaseModel):
    """One crop block: its area, its spacings and its field-unit lines. Head-unit
    lines belong to the quotation, not here (rule 12)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    crop: str | None = Field(default=None, max_length=120,
                             description="From GET /subsidy/crops. Null means no crop chosen, "
                                         "which the workbook writes as 'Select Crop here' and "
                                         "which gives a standard spacing of zero.")
    inter_crop: str | None = Field(default=None, max_length=120,
                                   description="The second crop of the same block. When present "
                                               "it, not the main crop, sets the standard spacing.")
    area: Decimal = Field(gt=0, description="Hectares, at most three decimals.")
    crop_spacing: str = Field(default="", max_length=60,
                              description="Free text such as '1.37 x 0.50'. Echoed on the "
                                          "document; the calculation does not read it.")
    lateral_spacing: Decimal = Field(gt=0, description="The designed lateral spacing in metres.")
    lines: list[Line] = Field(default_factory=list, max_length=MAX_LINES,
                              description="Field-unit lines only. Empty for Sprinkler, which "
                                          "derives its own.")

    @field_validator("area")
    @classmethod
    def _area_places(cls, v: Decimal) -> Decimal:
        return _places(v, 3, "area")


class Sump(BaseModel):
    rate_per_ha: Decimal = Field(default=Decimal("0"), ge=0,
                                 description="Zero or absent means no sump.")


class CalculateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    scheme: str = Field(default="GGRC", max_length=30, description="Subsidy scheme code.")
    system_type: SystemType = Field(description="Which of the three calculation models to run.")
    as_of: dt.date | None = Field(default=None,
                                  description="The masters in force on this date. Today in India "
                                              "by default; a future date is refused.")
    crops: list[CropRequest] = Field(min_length=1, max_length=MAX_CROPS)
    head_lines: list[Line] = Field(default_factory=list, max_length=MAX_LINES,
                                   description="The head unit, sent once for the whole quotation "
                                               "and shared across crops by area.")
    sump: Sump | None = Field(default=None)
    group_total_area: Decimal | None = Field(default=None, gt=0,
                                             description="Every member's area sharing the water "
                                                         "source. At least the sum of the crop "
                                                         "areas. Absent means a single farmer.")
    installation_rate_per_ha: Decimal = Field(default=Decimal("0"), ge=0,
                                              description="The installation line's rate; its "
                                                          "quantity is the area.")
    nozzle: Nozzle | None = Field(default=None,
                                  description="Sprinkler only. The pipe size is not an input: it "
                                              "follows the area band and is returned.")

    @field_validator("group_total_area")
    @classmethod
    def _group_places(cls, v: Decimal | None) -> Decimal | None:
        return None if v is None else _places(v, 3, "group_total_area")


# ── the response ─────────────────────────────────────────────────────────────

class Blocks(BaseModel):
    """One column of the quotation summary. Every key is always present; a block a
    system does not have is "0.00" rather than absent. Each value is rounded for
    display, so a column may not add up where the system rounds nothing above it."""

    head_unit: str
    field_unit: str
    a_plus_b: str
    cgst_ab: str
    sgst_ab: str
    installation: str
    cgst_c: str
    sgst_c: str
    total_abc_gst: str
    insurance: str
    cgst_d: str
    sgst_d: str
    inspection: str
    cgst_e: str
    sgst_e: str
    education: str
    sump: str
    cost_excl_gst: str
    total_cgst: str
    total_sgst: str
    total_gst: str
    total_incl_gst: str


class JantriOut(BaseModel):
    regular: str = Field(description="The unit cost per hectare, four decimals.")
    regular_with_sump: str = Field(description="Plus the sump rate times the area (rule 9).")
    regular_for_cap: str = Field(
        description="What the subsidy is actually capped on: the figure above, pro-rated for a "
                    "Mini Sprinkler block below 0.2 Ha. Equal to `regular_with_sump` everywhere "
                    "else. This is the unit cost the scheme's own sheet prints.")
    seven_year: str | None = Field(description="Null when the area is outside the window.")


class CategoryOut(BaseModel):
    code: str
    name: str
    pct: str = Field(description="The category's percentage, as the scheme prints it.")
    variant: Literal["regular", "seven_year"]
    applicable: bool
    reason: str | None = Field(description="Why a row does not apply. Null when it does.")
    subsidy: str
    farmer_share: str
    subsidy_pct: str = Field(description="Subsidy over cost, as a percentage with two decimals.")
    gsdma_farmer_share: str | None = Field(
        description="Mini Sprinkler up to 2 Ha only; null elsewhere.")


class CropOut(BaseModel):
    crop: str | None
    inter_crop: str | None
    area: str
    lateral_spacing_designed: str
    lateral_spacing_standard: str
    lateral_spacing_for_subsidy: str
    blocks: Blocks
    jantri: JantriOut
    categories: list[CategoryOut]
    warnings: list[str]


class SprinklerLineOut(BaseModel):
    component: str
    description: str
    uom: str
    qty: str
    rate: str
    amount: str


class SprinklerOut(BaseModel):
    pipe_size_mm: int = Field(description="75 up to 2.0 Ha, 90 from 2.01 (rule 19).")
    nozzle: Nozzle
    lines: list[SprinklerLineOut]
    dbt_farmer_payable: str = Field(
        description="The field unit with its GST. The workbook computes it; what it is for is "
                    "still the client's question (GAP-077).")


class MastersOut(BaseModel):
    as_of: str
    formula_version: str
    regular_matrix_id: str
    seven_year_matrix_id: str
    quantity_matrix_id: str | None


class TotalOut(BaseModel):
    blocks: Blocks


class CalculateResponse(BaseModel):
    system_type: SystemType
    scheme: str
    masters: MastersOut
    crops: list[CropOut]
    total: TotalOut
    sprinkler: SprinklerOut | None
    warnings: list[str]


# ── the lookups ──────────────────────────────────────────────────────────────

class CropItem(BaseModel):
    crop: str
    standard_spacing: str


class CategoryItem(BaseModel):
    code: str
    name: str
    pct: str
    variant: Literal["regular", "seven_year"]
    gsdma_pct: str | None


class SystemConfig(BaseModel):
    system_type: SystemType
    has_head_unit: bool
    supports_group: bool
    crop_count_max: int
    spacing_rule: str
    seven_year_spacing_floor: str | None
    quantity_source: str
    formula_version: str
    sprinkler_areas: list[str] | None = Field(
        description="The tabulated areas a Sprinkler quotation may use. Null for the other two "
                    "systems, which accept any area.")


class ConfigOut(BaseModel):
    scheme: str
    as_of: str
    systems: list[SystemConfig]
    parameters: dict[str, str]


Area = Annotated[Decimal, Field(gt=0)]
