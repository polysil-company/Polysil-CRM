# ruff: noqa: E501  (field declarations)

"""Subsidy follow-ups (FS-009a): ageing, reports, masters revisions."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.leads import PageMeta

SystemType = Literal["drip", "mini_sprinkler", "sprinkler"]


class AgeFigure(BaseModel):
    days: int | None = Field(description="Null when the start date is not recorded.")
    running: bool = Field(description="The end is not recorded yet; counted to today.")
    since: str | None = Field(description="The start date, when recorded.")
    until: str | None = Field(description="The end date, when recorded.")


class AgeRef(BaseModel):
    id: str
    application_no: str
    reg_no: str | None
    farmer_name: str
    status: str
    stage: str
    district: str | None


class AgeRow(BaseModel):
    application: AgeRef
    today_to_supply: AgeFigure
    inward_to_submission: AgeFigure
    wo_to_tpa_received: AgeFigure
    tpa_cleared_to_inspection_sent: AgeFigure
    inspection_sent_to_tr: AgeFigure
    fp_submitted_to_full_fp: AgeFigure


class AgePage(BaseModel):
    data: list[AgeRow]
    meta: PageMeta


class StageRow(BaseModel):
    seq: int
    code: str
    name: str
    count: int
    total_cost: str
    subsidy: str
    farmer_share: str
    oldest_days_in_stage: int | None


class StagePage(BaseModel):
    data: list[StageRow]
    meta: PageMeta


class SupplyRow(BaseModel):
    district: str
    supplied: int
    not_supplied: int
    supplied_cost: str
    not_supplied_cost: str


class SupplyPage(BaseModel):
    data: list[SupplyRow]
    meta: PageMeta


# ── masters revisions ────────────────────────────────────────────────────────

class CategoryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_type: SystemType
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=200)
    pct: Decimal = Field(gt=0, le=100, max_digits=6, decimal_places=3)
    variant: Literal["regular", "seven_year"]
    per_ha_cap: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    gsdma_pct: Decimal | None = Field(default=None, gt=0, le=100, max_digits=6, decimal_places=3)
    sort_order: int = 0


class ParameterRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_type: SystemType | None = None
    key: str = Field(min_length=1, max_length=80)
    value: Decimal = Field(max_digits=18, decimal_places=4)
    unit: str = Field(min_length=1, max_length=20, description="One of the units migration 009 knows.")


class ComponentRateRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_type: SystemType
    component_code: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=300)
    uom: str = Field(min_length=1, max_length=20)
    pipe_size_mm: int | None = Field(default=None, gt=0, le=1000)
    nozzle: str | None = Field(default=None, max_length=40)
    rate: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    source_cell: str = Field(default="admin", min_length=1, max_length=60)


class CropSpacingRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop: str = Field(min_length=1, max_length=100)
    standard_spacing: Decimal = Field(ge=0, max_digits=6, decimal_places=2)
    sort_order: int = 0


class Revision(BaseModel):
    """A revision of one table for one scheme. Each row closes the row with the same key
    in force on `effective_from` and starts from it. Rows not sent stay as they are."""

    model_config = ConfigDict(extra="forbid")

    scheme: str = "GGRC"
    effective_from: dt.date = Field(description="Today or later.")
    rows: list[dict[str, object]] = Field(min_length=1, max_length=2000,
                                          description="The table's own row shape; see the schemas "
                                                      "CategoryRow, ParameterRow, ComponentRateRow, CropSpacingRow.")


class UnitCostCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lateral_spacing: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)
    area_breakpoint: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class QuantityCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_code: str = Field(min_length=1, max_length=60)
    area_breakpoint: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    qty: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class MatrixRevision(BaseModel):
    """A new matrix from a date. The matrix in force ends the day before; its cells
    never change."""

    model_config = ConfigDict(extra="forbid")

    scheme: str = "GGRC"
    system_type: SystemType
    variant: Literal["regular", "seven_year"] | None = Field(default=None, description="Unit-cost matrices only.")
    dimensionality: Literal[1, 2] | None = Field(default=None, description="Unit-cost matrices only.")
    effective_from: dt.date
    source: str = Field(min_length=1, max_length=200, description="Where the figures come from, e.g. the GGRC circular.")
    unit_cost_cells: list[UnitCostCell] | None = Field(default=None, max_length=5000)
    quantity_cells: list[QuantityCell] | None = Field(default=None, max_length=5000)


class RevisionResult(BaseModel):
    closed: int
    inserted: int
    effective_from: str
