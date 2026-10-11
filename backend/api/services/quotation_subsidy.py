"""The subsidy block on a subsidised quotation (FS-057).

One calculator answer for one category, stored with the quotation. The
calculation runs on the lead's scheme; a request that names no scheme takes the
lead's (the request model defaults to GGRC, so an absent key is read from
`model_fields_set`, plan review B-3). Writes go through the definers: the app
role holds SELECT only on `quotation_subsidy`.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import quotations as sch
from api.services import subsidy as engine
from api.services import subsidy_schemes
from api.services.subsidy_applications import _prefixed, figures_for

DRIFT = Decimal("0.01")      # GAP-462: the 1 % is ours; a setting when the client names one
CENT = Decimal("0.01")


def _state(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(getattr(exc.orig, "__cause__", None),
                                                          "sqlstate", None)


async def lead_scheme(db: AsyncSession, lead_id: str) -> str:
    sid = await subsidy_schemes.scheme_id_for_lead(db, lead_id)
    code: str = (await db.execute(text("SELECT code::text FROM subsidy_scheme WHERE id = :i"),
                                  {"i": sid})).scalar_one()
    return code


async def set_block(db: AsyncSession, row: Any, body: sch.QuotationSubsidyIn) -> list[str]:
    """Rule 2. `row` is the quotation, already locked behind its lead. Returns the
    warnings the calculation raised."""
    if row.status != "draft":
        raise ConflictError("Only a draft takes a subsidy.", code="quotation_not_draft")
    if row.sales_type != "subsidised":
        raise ValidationFailed("Only a subsidised quotation takes a subsidy.",
                               code="not_subsidised", fields={"sales_type": row.sales_type})
    lead_id = str(row.lead_id)
    mis = (await db.execute(text(
        "SELECT ms.code FROM lead l JOIN mis_system ms ON ms.id = l.mis_system_id "
        "WHERE l.id = CAST(:l AS uuid)"), {"l": lead_id})).scalar_one_or_none()
    if mis is not None and body.calculation.system_type != mis:
        raise ValidationFailed(fields={"calculation.system_type": f"the lead's system is {mis}"})
    scheme = await lead_scheme(db, lead_id)
    calc_req = body.calculation
    if "scheme" not in calc_req.model_fields_set:
        calc_req = calc_req.model_copy(update={"scheme": scheme})
    elif calc_req.scheme.upper() != scheme.upper():
        raise ValidationFailed(fields={"calculation.scheme": f"This lead's scheme is {scheme}."})
    try:
        calc = await engine.calculate(db, calc_req)
    except ValidationFailed as exc:
        raise _prefixed(exc) from exc
    except NotFoundError as exc:
        # no masters in force on that date is the caller's date, not a missing quotation
        raise ValidationFailed(str(exc), code="masters_not_in_force",
                               fields={"calculation.as_of": str(exc)}) from exc
    subsidy, farmer, name, pct = figures_for(calc, body.category_code)
    total = Decimal(calc.total.blocks.total_incl_gst)
    flat = Decimal(calc.total.blocks.flat_inspection)
    warnings = list(calc.warnings)
    if subsidy > total + flat:
        # FS-056 GAP-458: a scheme that pays above the cost is held to the cost here,
        # so the order's checks (subsidy at most the material) hold
        warnings.append(f"subsidy_capped_at_cost: the scheme's {subsidy} is held to the cost "
                        f"{total + flat}")
        subsidy, farmer = total + flat, Decimal(0)
    try:
        async with db.begin_nested():
            await db.execute(text(
                "SELECT quotation_subsidy_set(CAST(:q AS uuid), :sc, :sy, :cc, :cn, "
                "CAST(:cp AS numeric), CAST(:req AS jsonb), CAST(:calc AS jsonb), :tc, :fl, :sub, "
                ":fs, :fv, :as_of)"),
                {"q": str(row.id), "sc": scheme.upper(), "sy": calc_req.system_type,
                 "cc": body.category_code, "cn": name, "cp": pct,
                 "req": calc_req.model_dump_json(), "calc": calc.model_dump_json(),
                 "tc": total, "fl": flat, "sub": subsidy, "fs": farmer,
                 "fv": calc.masters.formula_version,
                 "as_of": dt.date.fromisoformat(calc.masters.as_of)})
    except DBAPIError as exc:
        state = _state(exc)
        if state == "42501":
            raise ForbiddenError("You may not set a quotation's subsidy.") from exc
        if state == "QSBNF":
            raise NotFoundError("No such quotation.") from exc
        if state == "QSBND":
            raise ConflictError("Only a draft takes a subsidy.",
                                code="quotation_not_draft") from exc
        if state == "QSBTY":
            raise ValidationFailed("Only a subsidised quotation takes a subsidy.",
                                   code="not_subsidised",
                                   fields={"sales_type": "not subsidised"}) from exc
        raise
    return warnings


async def block(db: AsyncSession, quotation_id: str,
                quotation_total: Decimal) -> tuple[sch.QuotationSubsidy | None, list[str]]:
    r = (await db.execute(text(
        "SELECT scheme_code, system_type, category_code, category_name, category_pct, total_cost, "
        "flat_charge, subsidy, farmer_share, as_of, formula_version FROM quotation_subsidy "
        "WHERE quotation_id = CAST(:q AS uuid)"), {"q": quotation_id})).one_or_none()
    if r is None:
        return None, []
    cost = Decimal(r.total_cost) + Decimal(r.flat_charge)
    warnings = []
    # rule 4: the lines are what is sold; the calculation is what the scheme pays on
    if quotation_total <= 0 or abs(cost - quotation_total) > quotation_total * DRIFT:
        warnings.append(f"calculation_total_differs: the calculation's total {cost} differs from "
                        f"the quotation's {quotation_total}")
    out = sch.QuotationSubsidy(
        scheme=r.scheme_code, system_type=r.system_type,
        category=sch.SubsidyCategory(code=r.category_code, name=r.category_name,
                                     pct=f"{Decimal(r.category_pct).normalize():f}"),
        total_cost=f"{cost.quantize(CENT):.2f}", flat_charge=f"{Decimal(r.flat_charge):.2f}",
        subsidy=f"{Decimal(r.subsidy):.2f}", farmer_share=f"{Decimal(r.farmer_share):.2f}",
        as_of=r.as_of.isoformat(), formula_version=r.formula_version)
    return out, warnings


async def _lead_system(db: AsyncSession, lead_id: str) -> str | None:
    got: str | None = (await db.execute(text(
        "SELECT ms.code FROM lead l JOIN mis_system ms ON ms.id = l.mis_system_id "
        "WHERE l.id = CAST(:l AS uuid)"), {"l": lead_id})).scalar_one_or_none()
    return got


async def _same_system(db: AsyncSession, lead_id: str, held: str, field: str) -> None:
    """Code review F-3: the lead's system can be corrected after the calculation."""
    now = await _lead_system(db, lead_id)
    if now is not None and now != held:
        raise ValidationFailed(f"The lead's system is now {now}. Calculate the subsidy again.",
                               code="subsidy_system_changed", fields={field: "recalculate"})


async def check_ready(db: AsyncSession, quotation_id: str, lead_id: str) -> None:
    """Rule 5 and EC-2: a subsidised quotation is sent with a block on the lead's
    current scheme."""
    held = (await db.execute(text(
        "SELECT scheme_code, system_type FROM quotation_subsidy "
        "WHERE quotation_id = CAST(:q AS uuid)"),
        {"q": quotation_id})).one_or_none()
    if held is None:
        raise ValidationFailed("Calculate the subsidy before sending.", code="subsidy_missing",
                               fields={"subsidy": "required"})
    scheme = held.scheme_code
    await _same_system(db, lead_id, held.system_type, "subsidy")
    now = await lead_scheme(db, lead_id)
    if now.upper() != scheme.upper():
        raise ValidationFailed(f"The lead's scheme is now {now}. Calculate the subsidy again.",
                               code="subsidy_scheme_changed", fields={"subsidy": "recalculate"})


async def copy(db: AsyncSession, src: str, dst: str, lead_id: str) -> list[str]:
    """Rule 6: a revision carries the block while the lead's scheme is unchanged."""
    scheme = (await db.execute(text(
        "SELECT scheme_code FROM quotation_subsidy WHERE quotation_id = CAST(:q AS uuid)"),
        {"q": src})).scalar_one_or_none()
    if scheme is None:
        return []
    try:
        now = await lead_scheme(db, lead_id)
    except (ValidationFailed, NotFoundError):
        now = None
    if now is None or now.upper() != scheme.upper():
        return ["subsidy_not_carried: the lead's scheme changed; calculate the subsidy again"]
    await db.execute(text("SELECT quotation_subsidy_copy(CAST(:f AS uuid), CAST(:t AS uuid))"),
                     {"f": src, "t": dst})
    return []


async def calculation(db: AsyncSession, quotation_id: str) -> dict[str, Any]:
    got = (await db.execute(text(
        "SELECT calculation FROM quotation_subsidy WHERE quotation_id = CAST(:q AS uuid)"),
        {"q": quotation_id})).scalar_one_or_none()
    if got is None:
        raise NotFoundError("This quotation has no subsidy calculation.")
    data: dict[str, Any] = got
    return data


async def for_order(db: AsyncSession, quotation_id: str, lead_id: str) -> dict[str, Decimal]:
    """Rule 8: the order's subsidy from the quotation's block. Material is the
    calculation's total with any flat charge, so subsidy and share stay within it
    whatever the order's lines come to (plan review S-3)."""
    r = (await db.execute(text(
        "SELECT scheme_code, system_type, total_cost, flat_charge, subsidy, farmer_share "
        "FROM quotation_subsidy WHERE quotation_id = CAST(:q AS uuid)"),
        {"q": quotation_id})).one_or_none()
    if r is None:
        raise ValidationFailed("The quotation has no subsidy calculation.",
                               code="quotation_subsidy_missing",
                               fields={"quotation_ids": quotation_id})
    await _same_system(db, lead_id, r.system_type, "quotation_ids")
    now = await lead_scheme(db, lead_id)
    if now.upper() != r.scheme_code.upper():
        raise ValidationFailed(f"The lead's scheme is now {now}. Revise the quotation.",
                               code="subsidy_scheme_changed",
                               fields={"quotation_ids": quotation_id})
    return {"material": Decimal(r.total_cost) + Decimal(r.flat_charge),
            "subsidy": Decimal(r.subsidy), "farmer": Decimal(r.farmer_share)}
