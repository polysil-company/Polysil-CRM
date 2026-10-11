# ruff: noqa: E501  (embedded SQL)

"""Subsidy schemes (FS-039): create a state's scheme from a template, its readiness,
and the scheme a lead's application takes.

Every write is a definer in migration 044: the create spans five tables, and the
create and the update take the locks that keep one active scheme per state and keep
legacy mode (no scheme has a state) from mixing with linked schemes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import subsidy_schemes as sch
from api.services import subsidy as engine
from api.services.clock import today_ist

log = structlog.get_logger(__name__)


def _state(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _constraint(exc: DBAPIError) -> str | None:
    for err in (exc.orig, getattr(exc.orig, "__cause__", None)):
        name = getattr(err, "constraint_name", None) or getattr(getattr(err, "diag", None), "constraint_name", None)
        if name:
            return str(name)
    return None


def _refusal(exc: DBAPIError) -> Exception | None:
    """The definers' SQLSTATEs and the two unique constraints, as FS-039 §4 lists them."""
    state = _state(exc)
    if state == "42501":
        return ForbiddenError()
    if state == "SSCNF":
        return NotFoundError()
    if state == "23505":
        if _constraint(exc) == "ux_subsidy_scheme_state":
            return ConflictError("Another active scheme already covers this state.", code="state_has_scheme",
                                 fields={"state_territory_id": "already has an active scheme"})
        return ConflictError("A scheme with this code exists.", code="code_taken",
                             fields={"code": "already used"})
    if state == "SSCUL":
        return ConflictError("An active scheme has no state. Link it to its state first.",
                             code="unlinked_scheme_exists")
    if state == "SSCSF":
        return ConflictError("The scheme already has a state; it does not change.", code="state_fixed",
                             fields={"state_territory_id": "already set"})
    if state == "SSCST":
        return ValidationFailed(fields={"state_territory_id": "Not a state."})
    if state == "SSCTM":
        return ValidationFailed(fields={"template": "Not an active scheme with stages."})
    if state == "SSCSY":
        return ValidationFailed(fields={"systems": "The template does not have every one of these."})
    return None


async def _call(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one()
    except DBAPIError as exc:
        mapped = _refusal(exc)
        if mapped is None:
            raise
        raise mapped from exc


async def _systems(db: AsyncSession, scheme_id: str) -> list[Any]:
    return list((await db.execute(text(
        "SELECT system_type::text AS system_type, jantri_variant::text AS jantri_variant, "
        "quantity_source::text AS quantity_source FROM subsidy_system "
        "WHERE scheme_id = CAST(:s AS uuid) AND is_active ORDER BY system_type"),
        {"s": scheme_id})).all())


async def _stages(db: AsyncSession, scheme_id: str) -> list[sch.StageOut]:
    rows = (await db.execute(text(
        "SELECT seq, code, name, is_active FROM subsidy_stage_def WHERE scheme_id = CAST(:s AS uuid) "
        "ORDER BY seq"), {"s": scheme_id})).all()
    return [sch.StageOut(seq=r.seq, code=r.code, name=r.name, is_active=r.is_active) for r in rows]


async def _readiness(db: AsyncSession, scheme_id: str, on: dt.date,
                     active: bool) -> tuple[list[sch.SystemReadiness], list[sch.StageOut], bool]:
    systems = []
    for y in await _systems(db, scheme_id):
        missing = await engine.readiness(db, scheme_id, y.system_type, y.jantri_variant,
                                         y.quantity_source, on)
        systems.append(sch.SystemReadiness(system_type=y.system_type, ready=not missing, missing=missing))
    stages = await _stages(db, scheme_id)
    # a switched-off scheme is never ready: no calculation or application takes it (review F-5)
    ready = active and bool(systems) and all(s.ready for s in systems) and any(s.is_active for s in stages)
    return systems, stages, ready


def _state_ref(r: Any) -> sch.SchemeState | None:
    if r.state_id is None:
        return None
    return sch.SchemeState(id=str(r.state_id), code=r.state_code, name=r.state_name)


_SCHEME = ("SELECT s.id, s.code::text AS code, s.name, s.is_active, t.id AS state_id, t.code::text AS state_code, "
           "t.name AS state_name FROM subsidy_scheme s LEFT JOIN territory t ON t.id = s.state_territory_id "
           "WHERE s.deleted_at IS NULL")


async def list_schemes(db: AsyncSession) -> list[sch.SchemeRow]:
    rows = (await db.execute(text(_SCHEME + " ORDER BY s.is_active DESC, s.code"))).all()
    counts: dict[Any, int] = dict((await db.execute(text(
        "SELECT scheme_id, count(*) FROM subsidy_application GROUP BY scheme_id"))).all())
    today = today_ist()
    out = []
    for r in rows:
        systems, _, ready = await _readiness(db, str(r.id), today, r.is_active)
        out.append(sch.SchemeRow(code=r.code, name=r.name, is_active=r.is_active, state=_state_ref(r),
                                 systems=[s.system_type for s in systems], ready=ready,
                                 applications=int(counts.get(r.id, 0))))
    return out


async def get_scheme(db: AsyncSession, code: str, on: dt.date | None = None) -> sch.SchemeDetail:
    r = (await db.execute(text(_SCHEME + " AND s.code = upper(:c)"), {"c": code})).one_or_none()
    if r is None:
        raise NotFoundError()
    day = on or today_ist()
    systems, stages, ready = await _readiness(db, str(r.id), day, r.is_active)
    return sch.SchemeDetail(code=r.code, name=r.name, is_active=r.is_active, state=_state_ref(r),
                            on=day.isoformat(), systems=systems, stages=stages, ready=ready)


async def create_scheme(db: AsyncSession, body: sch.SubsidySchemeCreate) -> sch.SchemeDetail:
    systems = body.systems
    if systems is None:
        systems = [y[0] for y in (await db.execute(text(
            "SELECT y.system_type::text FROM subsidy_system y JOIN subsidy_scheme s ON s.id = y.scheme_id "
            "WHERE s.code = upper(:t) AND s.is_active AND y.is_active"), {"t": body.template})).all()]
    await _call(db, "SELECT subsidy_scheme_create(:c, :n, CAST(:st AS uuid), :t, CAST(:sy AS text[]))",
                {"c": body.code, "n": body.name, "st": body.state_territory_id, "t": body.template,
                 "sy": systems})
    log.info("subsidy_scheme.created", code=body.code, template=body.template)
    return await get_scheme(db, body.code)


async def update_scheme(db: AsyncSession, code: str, body: sch.SchemeUpdate) -> sch.SchemeDetail:
    await _call(db, "SELECT subsidy_scheme_update(:c, :n, :a, CAST(:st AS uuid))",
                {"c": code, "n": body.name, "a": body.is_active, "st": body.state_territory_id})
    # this process's cached masters; other processes catch up within the TTL, and the
    # application definer checks the scheme is active under its own lock (rule 5)
    engine.clear_cache()
    log.info("subsidy_scheme.updated", code=code, is_active=body.is_active,
             linked=body.state_territory_id is not None)
    return await get_scheme(db, code)


async def rename_stage(db: AsyncSession, code: str, stage_code: str, body: sch.StageRename) -> sch.StageOut:
    stage_id = await _call(db, "SELECT subsidy_stage_rename(:s, :c, :n)",
                           {"s": code, "c": stage_code, "n": body.name})
    r = (await db.execute(text("SELECT seq, code, name, is_active FROM subsidy_stage_def WHERE id = :i"),
                          {"i": stage_id})).one()
    return sch.StageOut(seq=r.seq, code=r.code, name=r.name, is_active=r.is_active)


async def scheme_id_for_lead(db: AsyncSession, lead_id: str) -> str:
    """The id of the scheme an application on this lead takes, or the refusal."""
    try:
        async with db.begin_nested():
            sid: Any = (await db.execute(text("SELECT subsidy_scheme_for_lead(CAST(:l AS uuid))"),
                                    {"l": lead_id})).scalar_one()
    except DBAPIError as exc:
        state = _state(exc)
        if state == "SAPNF":
            raise NotFoundError() from exc
        if state == "SAPSC":
            raise ValidationFailed("The lead's area has no state above it.", code="territory_without_state_code",
                                   fields={"lead_id": "no state"}) from exc
        raise
    if sid is None:
        raise ValidationFailed("No subsidy scheme covers this lead's state.", code="no_scheme_for_state",
                               fields={"lead_id": "no scheme for the state"})
    return str(sid)


async def scheme_for_lead(db: AsyncSession, lead_id: str) -> sch.LeadScheme:
    sid = await scheme_id_for_lead(db, lead_id)
    r = (await db.execute(text("SELECT code::text AS code, name, is_active FROM subsidy_scheme WHERE id = :i"),
                          {"i": sid})).one()
    _, _, ready = await _readiness(db, sid, today_ist(), r.is_active)
    return sch.LeadScheme(code=r.code, name=r.name, ready=ready)
