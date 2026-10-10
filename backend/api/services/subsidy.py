"""Resolve the masters in force, run the domain, shape the answer (FS-008).

The service is the only part that touches the database. It reads the master rows
for a date, builds the plain dataclasses the domain takes, calls one of the two
pipelines and turns exact `Decimal`s into the two-decimal strings the API
returns. No calculation lives here.

**The resolved master set is cached behind a short TTL.** Roughly 250 rows over
six round trips at 150 ms each is a quarter-second per debounced keystroke
otherwise. The TTL is the point rather than an optimisation detail: a row already
in force is immutable, but the loader can write a revision whose `effective_from`
is today, and a process that has already answered for today would go on serving
the superseded set until it restarted.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.subsidy.jantri import Matrix2D, OutsideTable
from api.domain.subsidy.money import RoundingPolicy, round2
from api.domain.subsidy.pipeline import seven_block
from api.domain.subsidy.sprinkler import field_inspection, missing_quantity_rows, required_rates
from api.domain.subsidy.types import (
    Category,
    ComponentRate,
    CropInput,
    Line,
    Masters,
    QuantityMatrix,
    QuotationInput,
    QuotationResult,
    SubsidyError,
    SystemPolicy,
    rate_matches,
)
from api.errors import NotFoundError, ValidationFailed
from api.schemas.subsidy import (
    Blocks,
    CalculateRequest,
    CalculateResponse,
    CategoryItem,
    CategoryOut,
    ConfigOut,
    CropItem,
    CropOut,
    JantriOut,
    MastersOut,
    SprinklerLineOut,
    SprinklerOut,
    SystemConfig,
    SystemType,
    TotalOut,
)
from api.services.clock import today_ist

_SYSTEMS: tuple[SystemType, ...] = ("drip", "mini_sprinkler", "sprinkler")
CACHE_TTL_SECONDS = 60.0
BLOCK_FIELDS = tuple(Blocks.model_fields)


@dataclass(frozen=True)
class ResolvedMasters:
    masters: Masters
    policy: SystemPolicy
    regular_matrix_id: str
    seven_year_matrix_id: str
    quantity_matrix_id: str | None
    formula_version: str
    sprinkler_areas: tuple[Decimal, ...] | None
    crop_count_max: int
    has_head_unit: bool
    supports_group: bool
    quantity_source: str


_CACHE: dict[tuple[str, str, dt.date], tuple[float, ResolvedMasters]] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _dec(v: Any) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _s(v: Decimal) -> str:
    return f"{round2(v):.2f}"


def _s4(v: Decimal) -> str:
    return f"{v.quantize(Decimal('0.0001')):.4f}"


# ── reading the masters ──────────────────────────────────────────────────────

_IN_FORCE = "AND daterange(effective_from, effective_to, '[)') @> CAST(:d AS date) AND is_active"


async def _system_row(db: AsyncSession, scheme: str, system: str) -> Any:
    got = await db.execute(text(
        "SELECT y.id, y.crop_count_max, y.has_head_unit, y.supports_group, y.rounded_blocks, "
        "y.rounded_lines, y.spacing_rule::text, y.seven_year_spacing_floor, "
        "y.spacing_outside_table::text, y.formula_version, y.quantity_source::text, "
        "y.jantri_variant::text, s.id "
        "FROM subsidy_system y JOIN subsidy_scheme s ON s.id = y.scheme_id "
        "WHERE s.code = upper(:c) AND s.is_active "
        "AND y.system_type = CAST(:t AS subsidy_system_type) AND y.is_active"),
        {"c": scheme, "t": system})
    row = got.one_or_none()
    if row is None:
        # Section 4 lists an unknown or inactive scheme in the validation list and
        # reserves `not_found` for a master that is not in force on the date. The
        # two were one answer here; the scheme is the caller's field (code review
        # F-12), and a scheme that exists without this system is not.
        known = await db.execute(text(
            "SELECT 1 FROM subsidy_scheme WHERE code = upper(:c) AND is_active"), {"c": scheme})
        if known.one_or_none() is None:
            raise ValidationFailed(fields={"scheme": f"{scheme!r} is not an active scheme."})
        raise NotFoundError(f"No active {system} configuration for scheme {scheme}.")
    return row


async def _matrix(db: AsyncSession, scheme_id: str, system: str, variant: str,
                  as_of: dt.date) -> tuple[str, int, list[tuple[Any, Any, Any]]]:
    got = await db.execute(text(
        "SELECT id, dimensionality FROM unit_cost_matrix WHERE scheme_id = :s "
        "AND system_type = CAST(:t AS subsidy_system_type) "
        "AND variant = CAST(:v AS subsidy_matrix_variant) " + _IN_FORCE),
        {"s": scheme_id, "t": system, "v": variant, "d": as_of})
    row = got.one_or_none()
    if row is None:
        raise NotFoundError(f"No {system} {variant} unit cost table is in force on {as_of}.")
    cells = (await db.execute(text(
        "SELECT lateral_spacing, area_breakpoint, unit_cost FROM unit_cost_cell "
        "WHERE matrix_id = :m ORDER BY lateral_spacing DESC NULLS LAST, area_breakpoint"),
        {"m": row.id})).all()
    if not cells:
        raise NotFoundError(
            f"The {system} {variant} unit cost table in force on {as_of} has no cells.")
    return str(row.id), row.dimensionality, [tuple(c) for c in cells]


def _ragged(cells: list[tuple[Any, Any, Any]]) -> bool:
    """A 2-D table whose spacings do not all hold the same areas: `_as_matrix_2d`
    would raise a KeyError on it (FS-039 code review F-1)."""
    by_spacing: dict[Any, set[Any]] = {}
    for spacing, area, _cost in cells:
        by_spacing.setdefault(spacing, set()).add(_dec(area))
    return len({frozenset(a) for a in by_spacing.values()}) > 1


def _as_matrix_2d(cells: list[tuple[Any, Any, Any]]) -> Matrix2D:
    by_spacing: dict[Decimal, dict[Decimal, Decimal]] = {}
    for spacing, area, cost in cells:
        by_spacing.setdefault(_dec(spacing), {})[_dec(area)] = _dec(cost)
    areas = sorted(next(iter(by_spacing.values())))
    return Matrix2D.from_rows(areas, [(s, [row[a] for a in areas])
                                      for s, row in sorted(by_spacing.items(), reverse=True)])


def _as_table_1d(cells: list[tuple[Any, Any, Any]]) -> dict[Decimal, Decimal]:
    return {_dec(area): _dec(cost) for _spacing, area, cost in cells}


async def _categories(db: AsyncSession, scheme_id: str, system: str,
                      as_of: dt.date) -> tuple[Category, ...]:
    cats = (await db.execute(text(
        "SELECT code::text, name, pct, variant::text, per_ha_cap, gsdma_pct, sort_order "
        "FROM subsidy_category WHERE scheme_id = :s "
        "AND system_type = CAST(:t AS subsidy_system_type) " + _IN_FORCE + " ORDER BY sort_order"),
        {"s": scheme_id, "t": system, "d": as_of})).all()
    if not cats:
        raise NotFoundError(f"No {system} categories are in force on {as_of}.")
    return tuple(Category(c[0], c[1], _dec(c[2]), c[3],
                          _dec(c[4]) if c[4] is not None else None,
                          _dec(c[5]) if c[5] is not None else None, c[6]) for c in cats)


async def _crop_spacings(db: AsyncSession, scheme_id: str, as_of: dt.date) -> dict[str, Decimal]:
    crops = (await db.execute(text(
        "SELECT crop::text, standard_spacing FROM crop_lateral_spacing WHERE scheme_id = :s "
        + _IN_FORCE), {"s": scheme_id, "d": as_of})).all()
    if not crops:
        # Without this the engine would give every crop a standard spacing of 0 and
        # answer 200 with a Jantri read off the wrong row, or blame the caller for
        # a crop name that is missing because the master is (code review F-7).
        raise NotFoundError(f"No crop spacings are in force on {as_of}.")
    return {" ".join(c[0].split()).lower(): _dec(c[1]) for c in crops}


async def _parameters(db: AsyncSession, scheme_id: str, system: str,
                      as_of: dt.date) -> dict[str, tuple[Decimal, str]]:
    """The system's row wins over the scheme-wide one: NULLS FIRST, later keys overwrite."""
    return {p[0]: (_dec(p[1]), p[2]) for p in (await db.execute(text(
        "SELECT key::text, value, unit::text FROM subsidy_parameter WHERE scheme_id = :s "
        "AND (system_type IS NULL OR system_type = CAST(:t AS subsidy_system_type)) " + _IN_FORCE
        + " ORDER BY system_type NULLS FIRST"), {"s": scheme_id, "t": system, "d": as_of})).all()}


async def _rates(db: AsyncSession, scheme_id: str, system: str,
                 as_of: dt.date) -> tuple[ComponentRate, ...]:
    return tuple(ComponentRate(r[0], r[1], r[2], _dec(r[3]), r[4], r[5])
                 for r in (await db.execute(text(
                     "SELECT component_code::text, description, uom, rate, pipe_size_mm, "
                     "nozzle::text FROM subsidy_component_rate WHERE scheme_id = :s "
                     "AND system_type = CAST(:t AS subsidy_system_type) " + _IN_FORCE),
                     {"s": scheme_id, "t": system, "d": as_of})).all())


async def _resolve(db: AsyncSession, scheme: str, system: str, as_of: dt.date) -> ResolvedMasters:
    row = await _system_row(db, scheme, system)
    scheme_id = str(row[12])

    reg_id, reg_dim, reg_cells = await _matrix(db, scheme_id, system, "regular", as_of)
    sy_id, sy_dim, sy_cells = await _matrix(db, scheme_id, system, "seven_year", as_of)
    # Each table is shaped from its own `dimensionality`, and both must agree with
    # the system's declared variant. Reading the regular table's for both would
    # turn a mis-loaded 7-year table into a silently wrong subsidy rather than a
    # refusal: 1-D cells through the 2-D reader interpolate on nothing, and 2-D
    # cells through the 1-D reader collapse onto one row per area (code review F-6).
    wanted = 2 if row.jantri_variant == "bilinear_2d" else 1
    if reg_dim != wanted or sy_dim != wanted:
        raise NotFoundError(
            f"The {system} tables in force on {as_of} are {reg_dim}-D and {sy_dim}-D, but the "
            f"system is configured as {row.jantri_variant}.")
    for variant, dim, cells in (("regular", reg_dim, reg_cells), ("seven_year", sy_dim, sy_cells)):
        if dim == 2 and _ragged(cells):
            raise NotFoundError(
                f"The {system} {variant} unit cost table in force on {as_of} is missing cells.")
    regular: Any = _as_matrix_2d(reg_cells) if reg_dim == 2 else _as_table_1d(reg_cells)
    seven_year: Any = _as_matrix_2d(sy_cells) if sy_dim == 2 else _as_table_1d(sy_cells)

    categories = await _categories(db, scheme_id, system, as_of)
    spacings = await _crop_spacings(db, scheme_id, as_of)
    params = await _parameters(db, scheme_id, system, as_of)

    quantities = qty_id = None
    rates: tuple[ComponentRate, ...] = ()
    areas: tuple[Decimal, ...] | None = None
    if row.quantity_source == "area_matrix":
        quantities, qty_id, areas = await _quantities(db, scheme_id, system, as_of)
        gaps = missing_quantity_rows(quantities)
        if gaps:
            raise NotFoundError(f"The {system} quantity table in force on {as_of} lacks a full "
                                f"row for: {', '.join(gaps)}.")
        rates = await _rates(db, scheme_id, system, as_of)

    masters = Masters(regular, seven_year, categories, spacings, quantities, rates,
                      row.formula_version)
    return ResolvedMasters(masters, _policy(system, row, params), reg_id, sy_id, qty_id,
                           row.formula_version, areas, row.crop_count_max, row.has_head_unit,
                           row.supports_group, row.quantity_source)


async def _quantities(db: AsyncSession, scheme_id: str, system: str,
                      as_of: dt.date) -> tuple[QuantityMatrix, str, tuple[Decimal, ...]]:
    got = await db.execute(text(
        "SELECT id FROM quantity_matrix WHERE scheme_id = :s "
        "AND system_type = CAST(:t AS subsidy_system_type) " + _IN_FORCE),
        {"s": scheme_id, "t": system, "d": as_of})
    row = got.one_or_none()
    if row is None:
        raise NotFoundError(f"No {system} quantity table is in force on {as_of}.")
    cells = (await db.execute(text(
        "SELECT component_code::text, area_breakpoint, qty FROM quantity_matrix_cell "
        "WHERE matrix_id = :m ORDER BY area_breakpoint"), {"m": row.id})).all()
    if not cells:
        raise NotFoundError(f"The {system} quantity table in force on {as_of} has no cells.")
    rows: dict[str, dict[Decimal, Decimal]] = {}
    for code, area, qty in cells:
        rows.setdefault(code, {})[_dec(area)] = _dec(qty)
    areas = tuple(sorted({_dec(c[1]) for c in cells}))
    return QuantityMatrix(areas, rows), str(row.id), areas


def _policy(system: str, row: Any, params: dict[str, tuple[Decimal, str]]) -> SystemPolicy:
    def p(key: str, default: Decimal | None = None) -> Decimal:
        if key in params:
            return params[key][0]
        if default is None:
            raise NotFoundError(f"The subsidy parameter {key} is not in force.")
        return default

    return SystemPolicy(
        system_type=system,
        rounding=RoundingPolicy(frozenset(row.rounded_blocks), frozenset(row.rounded_lines)),
        spacing_rule=row.spacing_rule,
        seven_year_spacing_floor=(_dec(row.seven_year_spacing_floor)
                                  if row.seven_year_spacing_floor is not None else None),
        spacing_outside_table=OutsideTable(row.spacing_outside_table),
        inspection_floor=p("inspection_floor"),
        min_area_prorate=bool(p("min_area_prorate")),
        max_area_scaling=bool(p("max_area_scaling")),
        warn_sump_divergence=system == "mini_sprinkler",
        education_amount=p("education_amount"),
        insurance_rate=p("insurance_rate"),
        inspection_rate=p("inspection_rate"),
        gst_material_half=p("gst_material_half"),
        gst_service_half=p("gst_service_half"),
        seven_year_area_min=p("seven_year_area_min"),
        seven_year_area_max=p("seven_year_area_max"),
        gsdma_max_area=params["gsdma_max_area"][0] if "gsdma_max_area" in params else None,
        pipe_size_band_ha=p("pipe_size_band_ha", Decimal("2.0")),
        exact_area_match_required=bool(p("exact_area_match_required", Decimal(1))),
    )


async def resolve(db: AsyncSession, scheme: str, system: str, as_of: dt.date) -> ResolvedMasters:
    key = (scheme.upper(), system, as_of)
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    resolved = await _resolve(db, scheme, system, as_of)
    _CACHE[key] = (now, resolved)
    return resolved


# The keys `_policy` reads with no default: a scheme lacking one cannot calculate.
REQUIRED_PARAMETERS: tuple[str, ...] = (
    "inspection_floor", "min_area_prorate", "max_area_scaling", "education_amount",
    "insurance_rate", "inspection_rate", "gst_material_half", "gst_service_half",
    "seven_year_area_min", "seven_year_area_max")


async def readiness(db: AsyncSession, scheme_id: str, system: str, jantri_variant: str,
                    quantity_source: str, as_of: dt.date) -> list[str]:
    """What a calculation on this system would refuse on, in `_resolve`'s order, read
    through `_resolve`'s own helpers and never through the cache (FS-039 rule 7).
    Component rates are not a `_resolve` refusal; `required_rates` lists the ones
    `field_inspection` will ask for."""
    missing: list[str] = []
    wanted = 2 if jantri_variant == "bilinear_2d" else 1
    for variant in ("regular", "seven_year"):
        try:
            _id, dim, cells = await _matrix(db, scheme_id, system, variant, as_of)
        except NotFoundError:
            missing.append(f"unit_cost_matrix:{variant}")
            continue
        if dim != wanted or (dim == 2 and _ragged(cells)):
            missing.append(f"unit_cost_matrix:{variant}")
    for name, read in (("categories", _categories(db, scheme_id, system, as_of)),
                       ("crop_spacings", _crop_spacings(db, scheme_id, as_of))):
        try:
            await read
        except NotFoundError:
            missing.append(name)
    params = await _parameters(db, scheme_id, system, as_of)
    areas: tuple[Decimal, ...] | None = None
    if quantity_source == "area_matrix":
        try:
            quantities, _qid, areas = await _quantities(db, scheme_id, system, as_of)
        except NotFoundError:
            missing.append("quantity_matrix")
        else:
            missing += [f"quantity_matrix:{code}" for code in missing_quantity_rows(quantities)]
    missing += [f"parameters:{k}" for k in REQUIRED_PARAMETERS if k not in params]
    if areas:
        rates = await _rates(db, scheme_id, system, as_of)
        band = params["pipe_size_band_ha"][0] if "pipe_size_band_ha" in params else Decimal("2.0")
        for code, size, nozzle in required_rates(areas, band):
            if not any(rate_matches(r, code, size, nozzle) for r in rates):
                tail = size if size is not None else nozzle
                missing.append(f"component_rate:{code}" + (f":{tail}" if tail is not None else ""))
    return missing


# ── the endpoint's work ──────────────────────────────────────────────────────

def _lines(rows: list[Any]) -> tuple[Line, ...]:
    return tuple(Line(r.description, r.uom, r.rate, r.qty) for r in rows)


def _validate(req: CalculateRequest, resolved: ResolvedMasters) -> None:
    """Every refusal names its field (rule 27). The schema has already checked
    shapes; these are the rules it cannot see."""
    fields: dict[str, str] = {}
    if len(req.crops) > resolved.crop_count_max:
        fields["crops"] = (f"{req.system_type} quotes at most {resolved.crop_count_max} "
                           f"crop block(s); {len(req.crops)} sent.")
    if req.head_lines and not resolved.has_head_unit:
        fields["head_lines"] = f"{req.system_type} has no head unit."
    if req.group_total_area is not None and not resolved.supports_group:
        fields["group_total_area"] = f"{req.system_type} has no group sharing."
    if req.system_type == "sprinkler":
        if req.nozzle is None:
            fields["nozzle"] = "Sprinkler needs a nozzle type: plastic or brass."
        for i, crop in enumerate(req.crops):
            if crop.lines:
                fields[f"crops[{i}].lines"] = ("Sprinkler derives its own lines from the area; "
                                               "send none.")
    elif req.nozzle is not None:
        fields["nozzle"] = "Only Sprinkler takes a nozzle type."

    total = sum((c.area for c in req.crops), Decimal(0))
    if req.group_total_area is not None and req.group_total_area < total:
        fields["group_total_area"] = (f"The group's area {req.group_total_area} is smaller than "
                                      f"the crops' {total}.")
    for i, crop in enumerate(req.crops):
        for name in ("crop", "inter_crop"):
            value = getattr(crop, name)
            if value and " ".join(value.split()).lower() not in resolved.masters.standard_spacings:
                fields[f"crops[{i}].{name}"] = f"{value!r} is not in the crop table."
    if sum(len(c.lines) for c in req.crops) + len(req.head_lines) > 200:
        fields["lines"] = "A quotation carries at most 200 lines."
    if fields:
        raise ValidationFailed(fields=fields)


# The two checks the product master makes possible (GAP-080, FS-010 rule 2).
#
# Neither reads a rate. A subsidy quotation is costed at the scheme's own figures,
# so the line still carries the rate the designer typed; what the catalogue adds is
# the ability to say that a line is not a thing that belongs in this block, or not
# a thing the scheme funds at all. Executed on the client's file: all fifteen
# marketing items are marked usable in either block, so without the eligibility
# flag a company umbrella passes the head-unit check and the scheme is asked to
# fund 70 to 90 % of it.
#
# The block check covers 983 of 1,094 rows. The 111 marked `both` get none, and 91
# of those are drip components where the block changes the group cost share. A
# stated limit, not an implied guarantee.
async def _check_products(db: AsyncSession, req: CalculateRequest) -> None:
    wanted: dict[str, list[str]] = {}
    for i, crop in enumerate(req.crops):
        for j, line in enumerate(crop.lines):
            if line.product_id:
                wanted.setdefault(line.product_id, []).append(f"crops[{i}].lines[{j}].product_id")
    for j, line in enumerate(req.head_lines):
        if line.product_id:
            wanted.setdefault(line.product_id, []).append(f"head_lines[{j}].product_id")
    if not wanted:
        return

    rows = {str(r[0]): (r[1], r[2], r[3]) for r in (await db.execute(text(
        "SELECT id::text, description::text, quotation_category::text, is_subsidy_eligible "
        "FROM product WHERE id = ANY(CAST(:ids AS uuid[])) AND deleted_at IS NULL AND is_active"),
        {"ids": list(wanted)})).all()}

    fields: dict[str, str] = {}
    for product_id, paths in wanted.items():
        found = rows.get(product_id)
        for path in paths:
            if found is None:
                fields[path] = "No such product, or it is no longer sold."
                continue
            name, category, eligible = found
            if not eligible:
                fields[path] = f"{name} is not eligible for subsidy."
            elif category != "both":
                block = "head_lines" if path.startswith("head_lines") else "a crop block"
                wants = "head_lines" if category == "head" else "a crop block"
                if (category == "head") != path.startswith("head_lines"):
                    fields[path] = f"{name} belongs in {wants}, not in {block}."
    if fields:
        raise ValidationFailed(fields=fields)


async def calculate(db: AsyncSession, req: CalculateRequest) -> CalculateResponse:
    as_of = req.as_of or today_ist()
    if as_of > today_ist():
        raise ValidationFailed(fields={"as_of": "A calculation cannot be dated in the future."})

    resolved = await resolve(db, req.scheme, req.system_type, as_of)
    _validate(req, resolved)
    await _check_products(db, req)

    crops = tuple(CropInput(c.crop, c.inter_crop, c.area, c.crop_spacing, c.lateral_spacing,
                            _lines(c.lines)) for c in req.crops)
    quotation = QuotationInput(
        req.system_type, crops, head_lines=_lines(req.head_lines),
        sump_rate_per_ha=req.sump.rate_per_ha if req.sump else Decimal(0),
        group_total_area=req.group_total_area,
        installation_rate_per_ha=req.installation_rate_per_ha, nozzle=req.nozzle)

    run = field_inspection if req.system_type == "sprinkler" else seven_block
    try:
        result = run(quotation, resolved.masters, resolved.policy)
    except SubsidyError as exc:
        raise ValidationFailed(exc.message,
                               fields={exc.field_path or "body": exc.message}) from exc
    return _shape(req, result, resolved, as_of)


def _blocks(source: Any) -> Blocks:
    return Blocks(**{name: _s(getattr(source, name)) for name in BLOCK_FIELDS})


def _shape(req: CalculateRequest, result: QuotationResult, resolved: ResolvedMasters,
           as_of: dt.date) -> CalculateResponse:
    crops = []
    for crop in result.crops:
        j = crop.jantri
        crops.append(CropOut(
            crop=crop.crop, inter_crop=crop.inter_crop, area=f"{crop.area:.3f}",
            lateral_spacing_designed=f"{crop.lateral_spacing_designed:.2f}",
            lateral_spacing_standard=f"{j.spacing_standard:.2f}",
            lateral_spacing_for_subsidy=f"{j.spacing_for_subsidy:.2f}",
            blocks=_blocks(crop.blocks),
            jantri=JantriOut(regular=_s4(j.regular), regular_with_sump=_s4(j.regular_with_sump),
                             regular_for_cap=_s4(j.regular_for_cap),
                             seven_year=_s4(j.seven_year) if j.seven_year is not None else None),
            categories=[CategoryOut(
                code=row.code, name=row.name, pct=f"{row.pct.normalize():f}",
                variant=row.variant,  # type: ignore[arg-type]
                applicable=row.applicable, reason=row.reason, subsidy=_s(row.money.subsidy),
                farmer_share=_s(row.money.farmer_share), subsidy_pct=_s(row.money.subsidy_pct),
                gsdma_farmer_share=(_s(row.money.gsdma_farmer_share)
                                    if row.money.gsdma_farmer_share is not None else None),
            ) for row in crop.categories],
            warnings=list(crop.warnings)))

    sprinkler = None
    if result.sprinkler is not None:
        assert req.nozzle is not None
        sprinkler = SprinklerOut(
            pipe_size_mm=result.sprinkler.pipe_size_mm, nozzle=req.nozzle,
            lines=[SprinklerLineOut(component=ln.component, description=ln.description,
                                    uom=ln.uom, qty=f"{ln.qty:f}", rate=_s(ln.rate),
                                    amount=_s(ln.amount))
                   for ln in result.sprinkler.lines],
            dbt_farmer_payable=_s(result.sprinkler.dbt_farmer_payable))

    return CalculateResponse(
        system_type=req.system_type, scheme=req.scheme.upper(),
        masters=MastersOut(as_of=as_of.isoformat(), formula_version=resolved.formula_version,
                           regular_matrix_id=resolved.regular_matrix_id,
                           seven_year_matrix_id=resolved.seven_year_matrix_id,
                           quantity_matrix_id=resolved.quantity_matrix_id),
        crops=crops, total=TotalOut(blocks=_blocks(result.total)), sprinkler=sprinkler,
        warnings=list(result.warnings))


# ── the lookups ──────────────────────────────────────────────────────────────

async def crops(db: AsyncSession, scheme: str, as_of: dt.date | None) -> list[CropItem]:
    day = as_of or today_ist()
    rows = (await db.execute(text(
        "SELECT c.crop::text, c.standard_spacing FROM crop_lateral_spacing c "
        "JOIN subsidy_scheme s ON s.id = c.scheme_id WHERE s.code = :c "
        "AND daterange(c.effective_from, c.effective_to, '[)') @> CAST(:d AS date) AND c.is_active "
        "ORDER BY c.sort_order"), {"c": scheme, "d": day})).all()
    return [CropItem(crop=r[0], standard_spacing=f"{_dec(r[1]):.2f}") for r in rows]


async def categories(db: AsyncSession, scheme: str, system: str,
                     as_of: dt.date | None) -> list[CategoryItem]:
    day = as_of or today_ist()
    rows = (await db.execute(text(
        "SELECT c.code::text, c.name, c.pct, c.variant::text, c.gsdma_pct FROM subsidy_category c "
        "JOIN subsidy_scheme s ON s.id = c.scheme_id WHERE s.code = :c "
        "AND c.system_type = CAST(:t AS subsidy_system_type) "
        "AND daterange(c.effective_from, c.effective_to, '[)') @> CAST(:d AS date) AND c.is_active "
        "ORDER BY c.sort_order"), {"c": scheme, "t": system, "d": day})).all()
    if not rows:
        raise NotFoundError(f"No {system} categories are in force on {day}.")
    return [CategoryItem(code=r[0], name=r[1], pct=f"{_dec(r[2]).normalize():f}", variant=r[3],
                         gsdma_pct=(f"{_dec(r[4]).normalize():f}" if r[4] is not None else None))
            for r in rows]


async def config(db: AsyncSession, scheme: str, as_of: dt.date | None) -> ConfigOut:
    day = as_of or today_ist()
    systems = []
    parameters: dict[str, str] = {}
    for system in _SYSTEMS:
        resolved = await resolve(db, scheme, system, day)
        policy = resolved.policy
        systems.append(SystemConfig(
            system_type=system,
            has_head_unit=resolved.has_head_unit, supports_group=resolved.supports_group,
            crop_count_max=resolved.crop_count_max, spacing_rule=policy.spacing_rule,
            seven_year_spacing_floor=(f"{policy.seven_year_spacing_floor:.2f}"
                                      if policy.seven_year_spacing_floor is not None else None),
            quantity_source=resolved.quantity_source,
            formula_version=resolved.formula_version,
            sprinkler_areas=([f"{a:.3f}" for a in resolved.sprinkler_areas]
                             if resolved.sprinkler_areas is not None else None)))
        parameters[f"{system}.inspection_floor"] = _s(policy.inspection_floor)
    # The figures every system shares, so a screen can print them without a second call.
    one = (await resolve(db, scheme, "drip", day)).policy
    parameters |= {
        "education_amount": _s(one.education_amount),
        "insurance_rate": f"{one.insurance_rate:f}",
        "inspection_rate": f"{one.inspection_rate:f}",
        "gst_material_half": f"{one.gst_material_half:f}",
        "gst_service_half": f"{one.gst_service_half:f}",
        "seven_year_area_min": f"{one.seven_year_area_min:f}",
        "seven_year_area_max": f"{one.seven_year_area_max:f}",
    }
    return ConfigOut(scheme=scheme.upper(), as_of=day.isoformat(), systems=systems,
                     parameters=parameters)
