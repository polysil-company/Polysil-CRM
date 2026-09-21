"""The engine's inputs and outputs: frozen dataclasses of `Decimal`, nothing from
SQLAlchemy or pydantic (CLAUDE.md rule 1). The service builds the inputs from the
request and the master rows; the schema layer turns the outputs into strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from api.domain.subsidy.jantri import Matrix2D, OutsideTable
from api.domain.subsidy.money import ZERO, RoundingPolicy


class SubsidyError(Exception):
    """A domain refusal the service turns into a 422 naming the field."""

    def __init__(self, code: str, message: str, field_path: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field_path = field_path


# ── inputs ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Line:
    description: str
    uom: str
    rate: Decimal
    qty: Decimal


@dataclass(frozen=True)
class CropInput:
    crop: str | None
    inter_crop: str | None
    area: Decimal
    crop_spacing: str
    lateral_spacing: Decimal
    lines: tuple[Line, ...] = ()


@dataclass(frozen=True)
class QuotationInput:
    system_type: str
    crops: tuple[CropInput, ...]
    head_lines: tuple[Line, ...] = ()
    sump_rate_per_ha: Decimal = ZERO
    group_total_area: Decimal | None = None
    installation_rate_per_ha: Decimal = ZERO
    nozzle: str | None = None


# ── masters ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Category:
    code: str
    name: str
    pct: Decimal                      # whole-number percent: 70
    variant: str                      # regular | seven_year
    per_ha_cap: Decimal | None = None
    gsdma_pct: Decimal | None = None  # whole-number percent: 10
    sort_order: int = 0


@dataclass(frozen=True)
class ComponentRate:
    code: str
    description: str
    uom: str
    rate: Decimal
    pipe_size_mm: int | None = None
    nozzle: str | None = None


@dataclass(frozen=True)
class QuantityMatrix:
    """Sprinkler quantities by component code and tabulated area (rule 18)."""

    areas: tuple[Decimal, ...]
    rows: Mapping[str, Mapping[Decimal, Decimal]]


@dataclass(frozen=True)
class SystemPolicy:
    """Everything about a system that is not a matrix: the rounding cells, the
    spacing rules, the floors and the rates. Ratios are ratios (`0.025`), never
    percents, except where the workbook's own figure is a percent."""

    system_type: str
    rounding: RoundingPolicy
    spacing_rule: str = "max_of_standard_and_design"
    seven_year_spacing_floor: Decimal | None = None
    spacing_outside_table: OutsideTable = OutsideTable.CLAMP
    inspection_floor: Decimal = ZERO
    min_area_prorate: bool = False
    max_area_scaling: bool = True
    warn_sump_divergence: bool = False
    education_amount: Decimal = Decimal("1000")
    insurance_rate: Decimal = Decimal("0.0028")
    inspection_rate: Decimal = Decimal("0.004")
    gst_material_half: Decimal = Decimal("0.025")
    gst_service_half: Decimal = Decimal("0.09")
    seven_year_area_min: Decimal = Decimal("0.2")
    seven_year_area_max: Decimal = Decimal("5")
    gsdma_max_area: Decimal | None = None
    pipe_size_band_ha: Decimal = Decimal("2.0")
    # GAP-076's lever: the parameter names itself as the place the client's
    # answer lands, so the refusal reads it rather than being hard-coded.
    exact_area_match_required: bool = True


@dataclass(frozen=True)
class Masters:
    regular: Matrix2D | Mapping[Decimal, Decimal]
    seven_year: Matrix2D | Mapping[Decimal, Decimal]
    categories: tuple[Category, ...]
    # keyed on the trimmed, lower-cased crop name
    standard_spacings: Mapping[str, Decimal] = field(default_factory=dict)
    quantities: QuantityMatrix | None = None
    component_rates: tuple[ComponentRate, ...] = ()
    formula_version: str = ""

    def standard_spacing(self, crop: str | None) -> Decimal:
        """Rule 6: the crop's row; no crop ("Select Crop here") is 0. A name that
        is not in the table is a refusal, never a silent 0 (rule 27)."""
        if crop is None or not crop.strip():
            return ZERO
        key = " ".join(crop.split()).lower()
        try:
            return self.standard_spacings[key]
        except KeyError:
            raise SubsidyError("crop_not_found",
                               f"{crop.strip()!r} is not in the crop table") from None

    def rate_for(self, code: str, *, pipe_size_mm: int | None = None,
                 nozzle: str | None = None) -> ComponentRate:
        for row in self.component_rates:
            if row.code != code:
                continue
            if pipe_size_mm is not None and row.pipe_size_mm != pipe_size_mm:
                continue
            if nozzle is not None and row.nozzle != nozzle:
                continue
            return row
        raise SubsidyError("component_rate_missing",
                           f"no rate for {code} (size {pipe_size_mm}, nozzle {nozzle})")


# ── outputs ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Blocks:
    """One column of the summary sheet, exact. The API rounds on output."""

    head_unit: Decimal = ZERO
    field_unit: Decimal = ZERO
    a_plus_b: Decimal = ZERO
    cgst_ab: Decimal = ZERO
    sgst_ab: Decimal = ZERO
    installation: Decimal = ZERO
    cgst_c: Decimal = ZERO
    sgst_c: Decimal = ZERO
    total_abc_gst: Decimal = ZERO
    insurance: Decimal = ZERO
    cgst_d: Decimal = ZERO
    sgst_d: Decimal = ZERO
    inspection_before_floor: Decimal = ZERO
    inspection: Decimal = ZERO
    cgst_e: Decimal = ZERO
    sgst_e: Decimal = ZERO
    education: Decimal = ZERO
    sump: Decimal = ZERO
    cost_excl_gst: Decimal = ZERO
    total_cgst: Decimal = ZERO
    total_sgst: Decimal = ZERO
    total_gst: Decimal = ZERO
    total_incl_gst: Decimal = ZERO


@dataclass(frozen=True)
class JantriFigures:
    regular: Decimal
    regular_with_sump: Decimal
    regular_for_cap: Decimal      # after the Mini pro-rate (rule 8): what the categories cap on
    seven_year: Decimal | None
    spacing_standard: Decimal
    spacing_for_subsidy: Decimal
    seven_year_spacing: Decimal | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryMoney:
    subsidy: Decimal
    farmer_share: Decimal
    subsidy_pct: Decimal               # a percent: 26.10
    gsdma_farmer_share: Decimal | None


@dataclass(frozen=True)
class CategoryResult:
    code: str
    name: str
    pct: Decimal
    variant: str
    applicable: bool
    reason: str | None
    exact: CategoryMoney               # the workbook's own figures, unrounded
    money: CategoryMoney               # rounded to the paisa and tied (rule 10b)


@dataclass(frozen=True)
class CropResult:
    crop: str | None
    inter_crop: str | None
    area: Decimal
    lateral_spacing_designed: Decimal
    jantri: JantriFigures
    blocks: Blocks
    categories: tuple[CategoryResult, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SprinklerLine:
    component: str
    description: str
    uom: str
    qty: Decimal
    rate: Decimal
    amount: Decimal


@dataclass(frozen=True)
class SprinklerFigures:
    pipe_size_mm: int
    lines: tuple[SprinklerLine, ...]
    field_unit_before_transport: Decimal
    dbt_farmer_payable: Decimal


@dataclass(frozen=True)
class QuotationResult:
    system_type: str
    crops: tuple[CropResult, ...]
    total: Blocks
    sprinkler: SprinklerFigures | None
    warnings: tuple[str, ...]
