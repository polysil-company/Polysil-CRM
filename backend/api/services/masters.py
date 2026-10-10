"""Offices, territories and partners: the transactions behind /org-units,
/territories and /partners (FS-006 sections 4 and 5).

Offices and territories are readable by every authenticated caller and written
under `masters.edit` (no scope). Partners are scoped by the partners ScopeSpec in
both enforcers: the service predicate here, the policies underneath. A partner
editing its own subtree may change contact details and nothing that prices,
credits or closes it (rule 14), refused here by field name and by the
`channel_partner_guarded_columns()` trigger underneath.

Nothing here commits (rule 3). Every write stamps `updated_by` and emits its event
in the same transaction (rule 18); a close is recorded by the cascade's own
`org_unit.deactivated` / `partner.deactivated`, so the service adds none.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.domain import identity
from api.errors import ForbiddenError, NotFoundError, ValidationFailed
from api.schemas.leads import PageMeta, TerritoryRef
from api.schemas.masters import (
    OrgUnit,
    OrgUnitCreate,
    OrgUnitPage,
    OrgUnitParent,
    OrgUnitPatch,
    Partner,
    PartnerCreate,
    PartnerPage,
    PartnerParent,
    PartnerPatch,
    PartnerStateChange,
    Territory,
    TerritoryCreate,
    TerritoryPage,
    TerritoryPatch,
)
from api.services.users import _decode_cursor, _encode_cursor, _pg_text, _sqlstate

_PARTNERS = SPECS["partners"]
_MAX_LIMIT = 100
LEVEL_ORDER = ("state", "district", "taluka", "village")
TYPE_ORDER = ("distributor", "dealer", "sub_dealer")
WRONG_TYPE = "wrong type for this parent: the order is distributor > dealer > sub_dealer"
# Migration 004's shapes, checked here first so the answer names the field.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
# What a partner-subtree caller may change on its own rows (rule 14).
PARTNER_SELF_FIELDS = frozenset({"name", "contact_name", "mobile", "email", "address",
                                 "gstin", "pan"})

_UUID = sa.Uuid()
_TS = sa.DateTime(timezone=True)
partner_t = sa.table(
    "channel_partner",
    sa.column("id", _UUID),
    sa.column("created_at", _TS),
    sa.column("parent_id", _UUID),
    sa.column("partner_type"),
    sa.column("code"),
    sa.column("name"),
    sa.column("contact_name"),
    sa.column("territory_id", _UUID),
    sa.column("is_active"),
    sa.column("deleted_at", _TS),
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _iso(v: datetime | None) -> str | None:
    return None if v is None else v.isoformat()


def _dec(v: Any) -> str | None:
    return None if v is None else str(v)


def _contains(q: str) -> str:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


async def _emit(db: AsyncSession, *, entity_type: str, entity_id: str, kind: str,
                actor_id: str, partner_id: str | None = None, **payload: Any) -> None:
    """One event. A channel_partner event must carry partner_id
    (ck_activity_event_reference); an office or territory event is read through
    entity_id (api/authz/activity.py, ENTITY_BY_ID)."""
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, partner_id, kind, actor_id, payload) "
        "VALUES (:t, CAST(:id AS uuid), CAST(:p AS uuid), :kind, CAST(:me AS uuid), "
        "CAST(:payload AS jsonb))"),
        {"t": entity_type, "id": entity_id, "p": partner_id, "kind": kind, "me": actor_id,
         "payload": json.dumps(payload)})


def _map_db_error(exc: DBAPIError) -> ValidationFailed | None:
    code = _sqlstate(exc)
    msg = _pg_text(exc)
    if code == "23505":
        if "uq_org_unit_parent_name" in msg or "uq_territory_parent_name" in msg:
            return ValidationFailed(fields={"name": "already used under this parent"})
        if "uq_territory_level_code" in msg:
            return ValidationFailed(fields={"code": "already used at this level"})
        if "uq_channel_partner_code" in msg:
            return ValidationFailed(fields={"code": "already in use"})
    if code == "23514":
        if "cannot be moved under its own descendant" in msg:
            return ValidationFailed(
                fields={"parent_id": "cannot move an office under one of its own"})
        if "active users are anchored here" in msg:
            return ValidationFailed(fields={"id": "active users are anchored here"})
        if "numbered under this code" in msg:
            return ValidationFailed(fields={"code": "cannot change: leads are numbered under it"})
        if "cannot sit under" in msg:
            return ValidationFailed(fields={"partner_type": WRONG_TYPE})
        if "soft-deleted; nothing may attach" in msg:
            return ValidationFailed(fields={"parent_id": "not found or closed"})
        if "users are anchored here; the type cannot change" in msg:
            return ValidationFailed(fields={"partner_type": "users are anchored here"})
        for constraint, field, reason in (
            ("ck_channel_partner_gstin_format", "gstin", "not a GSTIN"),
            ("ck_channel_partner_pan_format", "pan", "not a PAN"),
            ("ck_channel_partner_gstin_when_registered", "gstin", "required when GST registered"),
            ("ck_channel_partner_mobile_format", "mobile", "not an Indian mobile"),
            ("ck_channel_partner_code_shape", "code", "1 to 32 characters"),
            ("ck_channel_partner_name_shape", "name", "1 to 200 characters"),
            ("ck_channel_partner_credit_limit", "credit_limit", "must not be negative"),
        ):
            if constraint in msg:
                return ValidationFailed(fields={field: reason})
    if code == "42501" and "row-level security" in msg:
        return ValidationFailed(fields={"parent_id": "outside your scope"})
    if code == "23503":
        if "territory" in msg:
            return ValidationFailed(fields={"territory_id": "not found"})
        if "parent" in msg:
            return ValidationFailed(fields={"parent_id": "not found"})
    return None


async def _execute_mapped(db: AsyncSession, stmt: Any, params: dict[str, Any]) -> Any:
    try:
        return await db.execute(stmt, params)
    except DBAPIError as exc:
        mapped = _map_db_error(exc)
        if mapped is None:
            raise
        raise mapped from exc


async def _territory_exists(db: AsyncSession, territory_id: str) -> None:
    ok = (await db.execute(text(
        "SELECT 1 FROM territory WHERE id = CAST(:t AS uuid) AND deleted_at IS NULL"),
        {"t": territory_id})).first()
    if ok is None:
        raise ValidationFailed(fields={"territory_id": "not found"})


def _page(rows: Sequence[Any], limit: int) -> tuple[list[Any], str | None]:
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
    return list(rows[:limit]), next_cursor


# ── offices ──────────────────────────────────────────────────────────────────

_OU_SELECT = """
SELECT ou.id, ou.name, ou.role_level, ou.parent_id, p.name AS parent_name,
       ou.territory_id, t.name AS territory_name, t.level::text AS territory_level,
       ou.deleted_at, ou.created_at
  FROM org_unit ou
  LEFT JOIN org_unit p ON p.id = ou.parent_id
  LEFT JOIN territory t ON t.id = ou.territory_id
"""


async def _ou_counts(db: AsyncSession, ids: list[str]) -> dict[str, int]:
    if not ids:
        return {}
    rows = (await db.execute(text(
        "SELECT org_unit_id, active_users FROM org_unit_user_counts(CAST(:ids AS uuid[]))"),
        {"ids": ids})).all()
    return {str(r.org_unit_id): int(r.active_users) for r in rows}


def _ou(r: Any, active_users: int) -> OrgUnit:
    return OrgUnit(
        id=str(r.id), name=r.name, role_level=int(r.role_level),
        parent=OrgUnitParent(id=str(r.parent_id), name=r.parent_name) if r.parent_id else None,
        territory=TerritoryRef(id=str(r.territory_id), name=r.territory_name,
                               level=r.territory_level) if r.territory_id else None,
        is_open=r.deleted_at is None, closed_at=_iso(r.deleted_at),
        active_users=active_users, created_at=r.created_at.isoformat())


async def _ou_rows(db: AsyncSession, ids: list[str]) -> list[OrgUnit]:
    if not ids:
        return []
    rows = (await db.execute(text(_OU_SELECT + " WHERE ou.id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    counts = await _ou_counts(db, [i for i in ids if i in by_id])
    return [_ou(by_id[i], counts.get(i, 0)) for i in ids if i in by_id]


async def list_org_units(db: AsyncSession, *, q: str | None = None, parent_id: str | None = None,
                         is_open: bool | None = None, limit: int = 50,
                         cursor: str | None = None) -> OrgUnitPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    c_ts, c_id = _decode_cursor(cursor) if cursor else (None, None)
    rows = (await db.execute(text("""
        SELECT id, created_at FROM org_unit
         WHERE (CAST(:like AS text) IS NULL OR name ILIKE CAST(:like AS text))
           AND (CAST(:parent AS uuid) IS NULL OR parent_id = CAST(:parent AS uuid))
           AND (CAST(:open AS boolean) IS NULL
                OR (deleted_at IS NULL) = CAST(:open AS boolean))
           AND (CAST(:c_ts AS timestamptz) IS NULL
                OR (created_at, id) < (CAST(:c_ts AS timestamptz), CAST(:c_id AS uuid)))
         ORDER BY created_at DESC, id DESC LIMIT :lim"""),
        {"like": _contains(q) if q else None, "parent": parent_id, "open": is_open,
         "c_ts": c_ts, "c_id": c_id, "lim": limit + 1})).all()
    rows, next_cursor = _page(rows, limit)
    data = await _ou_rows(db, [str(r.id) for r in rows])
    return OrgUnitPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def get_org_unit(db: AsyncSession, org_unit_id: str) -> OrgUnit:
    rows = await _ou_rows(db, [org_unit_id])
    if not rows:
        raise NotFoundError("No such office.")
    return rows[0]


async def _open_office(db: AsyncSession, org_unit_id: str, field: str = "parent_id") -> None:
    ok = (await db.execute(text(
        "SELECT 1 FROM org_unit WHERE id = CAST(:o AS uuid) AND deleted_at IS NULL"),
        {"o": org_unit_id})).first()
    if ok is None:
        raise ValidationFailed(fields={field: "not found or closed"})


async def create_org_unit(db: AsyncSession, caller: Caller, body: OrgUnitCreate) -> OrgUnit:
    if body.parent_id is not None:
        await _open_office(db, body.parent_id)
    if body.territory_id is not None:
        await _territory_exists(db, body.territory_id)
    new_id = str((await _execute_mapped(db, text(
        "INSERT INTO org_unit (name, role_level, parent_id, territory_id, created_by) "
        "VALUES (:n, :l, CAST(:p AS uuid), CAST(:t AS uuid), CAST(:me AS uuid)) RETURNING id"),
        {"n": body.name, "l": body.role_level, "p": body.parent_id, "t": body.territory_id,
         "me": caller.user_id})).scalar_one())
    await _emit(db, entity_type="org_unit", entity_id=new_id, kind="org_unit.created",
                actor_id=caller.user_id, name=body.name, parent_id=body.parent_id,
                territory_id=body.territory_id, role_level=body.role_level)
    return await get_org_unit(db, new_id)


async def patch_org_unit(db: AsyncSession, caller: Caller, org_unit_id: str,
                         body: OrgUnitPatch) -> OrgUnit:
    """Rename, move, or change the territory. A move rebuilds the closure in the
    same transaction (002); a cycle is 422 on parent_id (rule 8)."""
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    row = (await db.execute(text(
        "SELECT id, name, parent_id, territory_id, deleted_at FROM org_unit "
        "WHERE id = CAST(:id AS uuid) FOR UPDATE"), {"id": org_unit_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such office.")
    sets: list[str] = []
    params: dict[str, Any] = {"id": org_unit_id, "me": caller.user_id}
    changed: dict[str, Any] = {}
    if "name" in fields:
        if body.name is None:
            raise ValidationFailed(fields={"name": "cannot be cleared"})
        sets.append("name = :name")
        params["name"] = body.name
        changed["name"] = body.name
    if "parent_id" in fields:
        if body.parent_id == org_unit_id:
            raise ValidationFailed(
                fields={"parent_id": "cannot move an office under one of its own"})
        if body.parent_id is not None:
            await _open_office(db, body.parent_id)
        sets.append("parent_id = CAST(:parent AS uuid)")
        params["parent"] = body.parent_id
        changed["parent_id"] = body.parent_id
    if "territory_id" in fields:
        if body.territory_id is not None:
            await _territory_exists(db, body.territory_id)
        sets.append("territory_id = CAST(:territory AS uuid)")
        params["territory"] = body.territory_id
        changed["territory_id"] = body.territory_id
    sets.append("updated_by = CAST(:me AS uuid)")
    r = await _execute_mapped(db, text(
        f"UPDATE org_unit SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)"), params)
    if r.rowcount == 0:
        raise NotFoundError("No such office.")
    await _emit(db, entity_type="org_unit", entity_id=org_unit_id, kind="org_unit.updated",
                actor_id=caller.user_id, fields=sorted(changed), **changed)
    return await get_org_unit(db, org_unit_id)


async def close_org_unit(db: AsyncSession, caller: Caller, org_unit_id: str) -> OrgUnit:
    """Rule 9: refused while active users are anchored; the trigger says so and the
    service turns it into `422 fields.id`. Already closed is a no-op."""
    current = await get_org_unit(db, org_unit_id)
    if not current.is_open:
        return current
    try:
        await db.execute(text("SELECT authz_deactivate_anchor('org_unit', CAST(:id AS uuid))"),
                         {"id": org_unit_id})
    except DBAPIError as exc:
        mapped = _map_db_error(exc)
        if mapped is not None:
            raise mapped from exc
        if _sqlstate(exc) == "42501":
            raise ForbiddenError() from exc
        raise
    return await get_org_unit(db, org_unit_id)


async def reopen_org_unit(db: AsyncSession, caller: Caller, org_unit_id: str) -> OrgUnit:
    """Restores the anchor only (rule 10): it had no active people when it closed."""
    reopened = (await db.execute(text(
        "UPDATE org_unit SET deleted_at = NULL, updated_by = CAST(:me AS uuid) "
        "WHERE id = CAST(:id AS uuid) AND deleted_at IS NOT NULL RETURNING id"),
        {"id": org_unit_id, "me": caller.user_id})).first() is not None
    current = await get_org_unit(db, org_unit_id)
    if reopened:
        await _emit(db, entity_type="org_unit", entity_id=org_unit_id, kind="org_unit.reopened",
                    actor_id=caller.user_id)
    return current


# ── territories ──────────────────────────────────────────────────────────────

_T_SELECT = """
SELECT t.id, t.name, t.level::text AS level, t.code::text AS code, t.parent_id,
       p.name AS parent_name, p.level::text AS parent_level, t.created_at
  FROM territory t
  LEFT JOIN territory p ON p.id = t.parent_id
"""


async def _codes_locked(db: AsyncSession, state_ids: list[str]) -> set[str]:
    if not state_ids:
        return set()
    rows = (await db.execute(text(
        "SELECT id FROM territory_codes_locked(CAST(:ids AS uuid[]))"), {"ids": state_ids})).all()
    return {str(r.id) for r in rows}


def _territory(r: Any, locked: bool) -> Territory:
    return Territory(
        id=str(r.id), name=r.name, level=r.level, code=r.code,
        parent=TerritoryRef(id=str(r.parent_id), name=r.parent_name, level=r.parent_level)
        if r.parent_id else None,
        code_locked=locked, created_at=r.created_at.isoformat())


async def _t_rows(db: AsyncSession, ids: list[str]) -> list[Territory]:
    if not ids:
        return []
    rows = (await db.execute(text(_T_SELECT + " WHERE t.id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    locked = await _codes_locked(db, [i for i in ids if i in by_id and by_id[i].level == "state"
                                      and by_id[i].code])
    return [_territory(by_id[i], i in locked) for i in ids if i in by_id]


async def list_territories(db: AsyncSession, *, level: str | None = None,
                           parent_id: str | None = None, q: str | None = None,
                           limit: int = 50, cursor: str | None = None) -> TerritoryPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    c_ts, c_id = _decode_cursor(cursor) if cursor else (None, None)
    rows = (await db.execute(text("""
        SELECT id, created_at FROM territory
         WHERE deleted_at IS NULL
           AND (CAST(:level AS text) IS NULL OR level::text = CAST(:level AS text))
           AND (CAST(:parent AS uuid) IS NULL OR parent_id = CAST(:parent AS uuid))
           AND (CAST(:like AS text) IS NULL OR name ILIKE CAST(:like AS text)
                OR code::text ILIKE CAST(:like AS text))
           AND (CAST(:c_ts AS timestamptz) IS NULL
                OR (created_at, id) < (CAST(:c_ts AS timestamptz), CAST(:c_id AS uuid)))
         ORDER BY created_at DESC, id DESC LIMIT :lim"""),
        {"level": level, "parent": parent_id, "like": _contains(q) if q else None,
         "c_ts": c_ts, "c_id": c_id, "lim": limit + 1})).all()
    rows, next_cursor = _page(rows, limit)
    data = await _t_rows(db, [str(r.id) for r in rows])
    return TerritoryPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def get_territory(db: AsyncSession, territory_id: str) -> Territory:
    rows = await _t_rows(db, [territory_id])
    if not rows:
        raise NotFoundError("No such territory.")
    return rows[0]


def _code(raw: str | None) -> str | None:
    return raw.strip().upper() if raw else None


async def create_territory(db: AsyncSession, caller: Caller, body: TerritoryCreate) -> Territory:
    """A state at the root, then one level down under a parent of the level above."""
    depth = LEVEL_ORDER.index(body.level)
    if depth == 0:
        if body.parent_id is not None:
            raise ValidationFailed(fields={"parent_id": "a state has no parent"})
    else:
        expected = LEVEL_ORDER[depth - 1]
        if body.parent_id is None:
            raise ValidationFailed(fields={"parent_id": f"a {body.level} sits under a {expected}"})
        parent_level = (await db.execute(text(
            "SELECT level::text FROM territory WHERE id = CAST(:p AS uuid) AND deleted_at IS NULL"),
            {"p": body.parent_id})).scalar_one_or_none()
        if parent_level is None:
            raise ValidationFailed(fields={"parent_id": "not found"})
        if parent_level != expected:
            raise ValidationFailed(fields={"parent_id": f"a {body.level} sits under a {expected}"})
    new_id = str((await _execute_mapped(db, text(
        "INSERT INTO territory (name, level, parent_id, code, created_by) "
        "VALUES (:n, CAST(:l AS territory_level), CAST(:p AS uuid), CAST(:c AS citext), "
        "CAST(:me AS uuid)) RETURNING id"),
        {"n": body.name, "l": body.level, "p": body.parent_id, "c": _code(body.code),
         "me": caller.user_id})).scalar_one())
    await _emit(db, entity_type="territory", entity_id=new_id, kind="territory.created",
                actor_id=caller.user_id, name=body.name, level=body.level,
                parent_id=body.parent_id, code=_code(body.code))
    return await get_territory(db, new_id)


async def patch_territory(db: AsyncSession, caller: Caller, territory_id: str,
                          body: TerritoryPatch) -> Territory:
    """Rename or set the code. A state's code is immutable once a lead is numbered
    under it (rule 15): the trigger refuses and the answer names `code`."""
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    row = (await db.execute(text(
        "SELECT id FROM territory WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL FOR UPDATE"),
        {"id": territory_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such territory.")
    sets: list[str] = []
    params: dict[str, Any] = {"id": territory_id, "me": caller.user_id}
    changed: dict[str, Any] = {}
    if "name" in fields:
        if body.name is None:
            raise ValidationFailed(fields={"name": "cannot be cleared"})
        sets.append("name = :name")
        params["name"] = body.name
        changed["name"] = body.name
    if "code" in fields:
        sets.append("code = CAST(:code AS citext)")
        params["code"] = _code(body.code)
        changed["code"] = _code(body.code)
    sets.append("updated_by = CAST(:me AS uuid)")
    await _execute_mapped(db, text(
        f"UPDATE territory SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)"), params)
    await _emit(db, entity_type="territory", entity_id=territory_id, kind="territory.updated",
                actor_id=caller.user_id, fields=sorted(changed), **changed)
    return await get_territory(db, territory_id)


# ── partners ─────────────────────────────────────────────────────────────────

_P_SELECT = """
SELECT cp.id, cp.code::text AS code, cp.name, cp.partner_type::text AS partner_type,
       cp.price_tier::text AS price_tier,
       cp.parent_id, pp.name AS parent_name, pp.partner_type::text AS parent_type,
       cp.territory_id, t.name AS territory_name, t.level::text AS territory_level,
       cp.contact_name, cp.mobile, cp.email::text AS email, cp.address, cp.gstin, cp.pan,
       cp.is_gst_registered, cp.credit_limit, cp.payment_terms_days, cp.is_active,
       cp.deleted_at, cp.created_at
  FROM channel_partner cp
  LEFT JOIN channel_partner pp ON pp.id = cp.parent_id
  LEFT JOIN territory t ON t.id = cp.territory_id
"""


def _is_partner_caller(caller: Caller) -> bool:
    return caller.scopes.get("partners") == "partner_subtree"


async def _p_counts(db: AsyncSession, ids: list[str]) -> dict[str, tuple[int, int]]:
    if not ids:
        return {}
    rows = (await db.execute(text(
        "SELECT partner_id, users, users_inactive "
        "FROM channel_partner_user_counts(CAST(:ids AS uuid[]))"), {"ids": ids})).all()
    return {str(r.partner_id): (int(r.users), int(r.users_inactive)) for r in rows}


def _partner(r: Any, counts: tuple[int, int], terms: bool) -> Partner:
    return Partner(
        id=str(r.id), code=r.code, name=r.name, partner_type=r.partner_type,
        price_tier=r.price_tier,
        parent=PartnerParent(id=str(r.parent_id), name=r.parent_name, partner_type=r.parent_type)
        if r.parent_id and r.parent_name else None,
        territory=TerritoryRef(id=str(r.territory_id), name=r.territory_name,
                               level=r.territory_level) if r.territory_id else None,
        contact_name=r.contact_name, mobile=r.mobile, email=r.email, address=r.address,
        gstin=r.gstin, pan=r.pan, is_gst_registered=bool(r.is_gst_registered),
        credit_limit=_dec(r.credit_limit) if terms else None,
        payment_terms_days=int(r.payment_terms_days)
        if terms and r.payment_terms_days is not None else None,
        is_active=bool(r.is_active), users=counts[0], created_at=r.created_at.isoformat())


async def _p_rows(db: AsyncSession, caller: Caller, ids: list[str]
                  ) -> list[tuple[Partner, int]]:
    if not ids:
        return []
    rows = (await db.execute(text(_P_SELECT + " WHERE cp.id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    counts = await _p_counts(db, [i for i in ids if i in by_id])
    # Credit terms are for those who set them: staff with partners.edit. A field
    # officer sees the dealers serving his area, not their credit (FS-020 rule 6).
    terms = not _is_partner_caller(caller) and bool((await db.execute(
        text("SELECT app_has_permission('partners', 'edit')"))).scalar_one())
    return [(_partner(by_id[i], counts.get(i, (0, 0)), terms), counts.get(i, (0, 0))[1])
            for i in ids if i in by_id]


async def list_partners(db: AsyncSession, caller: Caller, *, q: str | None = None,
                        partner_type: str | None = None, parent_id: str | None = None,
                        is_active: bool | None = None, limit: int = 50,
                        cursor: str | None = None) -> PartnerPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    where = [scope_predicate(_PARTNERS, caller, partner_t)]
    if partner_type:
        where.append(sa.cast(partner_t.c.partner_type, sa.Text) == partner_type)
    if parent_id:
        where.append(partner_t.c.parent_id == parent_id)
    if is_active is not None:
        where.append(partner_t.c.is_active.is_(is_active))
    if q:
        like = _contains(q)
        where.append(sa.or_(partner_t.c.name.ilike(like),
                            sa.cast(partner_t.c.code, sa.Text).ilike(like),
                            partner_t.c.contact_name.ilike(like)))
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append(sa.or_(partner_t.c.created_at < c_ts,
                            sa.and_(partner_t.c.created_at == c_ts, partner_t.c.id < c_id)))
    rows = (await db.execute(
        sa.select(partner_t.c.id, partner_t.c.created_at)
        .where(sa.and_(*where))
        .order_by(partner_t.c.created_at.desc(), partner_t.c.id.desc())
        .limit(limit + 1))).all()
    rows, next_cursor = _page(rows, limit)
    data = [p for p, _ in await _p_rows(db, caller, [str(r.id) for r in rows])]
    return PartnerPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def _visible_partner(db: AsyncSession, caller: Caller, partner_id: str) -> bool:
    return (await db.execute(
        sa.select(partner_t.c.id).where(sa.and_(scope_predicate(_PARTNERS, caller, partner_t),
                                                partner_t.c.id == partner_id)))).first() is not None


async def _get_partner_state(db: AsyncSession, caller: Caller, partner_id: str
                             ) -> tuple[Partner, int]:
    if not await _visible_partner(db, caller, partner_id):
        raise NotFoundError("No such partner.")
    rows = await _p_rows(db, caller, [partner_id])
    if not rows:
        raise NotFoundError("No such partner.")
    return rows[0]


async def get_partner(db: AsyncSession, caller: Caller, partner_id: str) -> Partner:
    return (await _get_partner_state(db, caller, partner_id))[0]


def _gstin(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().upper()
    if not GSTIN_RE.match(value):
        raise ValidationFailed(fields={"gstin": "not a GSTIN"})
    return value


def _pan(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().upper()
    if not PAN_RE.match(value):
        raise ValidationFailed(fields={"pan": "not a PAN"})
    return value


def _mobile(raw: str | None) -> str | None:
    if raw is None:
        return None
    try:
        return identity.mobile_for_user(raw)
    except identity.MobileError as exc:
        raise ValidationFailed(fields={"mobile": "not an Indian mobile"}) from exc


def _email(raw: str | None) -> str | None:
    if raw is None:
        return None
    try:
        return identity.normalise_email(raw)
    except identity.EmailError as exc:
        raise ValidationFailed(fields={"email": str(exc)}) from exc


async def create_partner(db: AsyncSession, caller: Caller, body: PartnerCreate) -> Partner:
    """Staff create anywhere in their partners scope; a distributor or dealer creates
    the next type down under itself (ISS-058). price_tier is the type (ADR-030)."""
    partner_caller = _is_partner_caller(caller)
    if partner_caller:
        if body.credit_limit is not None or body.payment_terms_days is not None:
            field = "credit_limit" if body.credit_limit is not None else "payment_terms_days"
            raise ValidationFailed(fields={field: "set by staff only"})
        if body.parent_id is None:
            raise ValidationFailed(fields={"parent_id": "name yourself or a partner under you"})
    if body.parent_id is not None:
        parent = (await db.execute(text(
            "SELECT partner_type::text AS partner_type, is_active, deleted_at "
            "FROM channel_partner WHERE id = CAST(:p AS uuid)"),
            {"p": body.parent_id})).one_or_none()
        if parent is None or parent.deleted_at is not None:
            raise ValidationFailed(fields={"parent_id": "not found or closed"})
        expected = TYPE_ORDER.index(parent.partner_type) + 1
        if expected >= len(TYPE_ORDER) or TYPE_ORDER[expected] != body.partner_type:
            raise ValidationFailed(fields={"partner_type": WRONG_TYPE})
    await _territory_exists(db, body.territory_id)
    gstin = _gstin(body.gstin)
    if body.is_gst_registered and gstin is None:
        raise ValidationFailed(fields={"gstin": "required when GST registered"})
    new_id = str((await _execute_mapped(db, text("""
        INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id,
            contact_name, mobile, email, address, gstin, pan, is_gst_registered, price_tier,
            credit_limit, payment_terms_days, created_by)
        VALUES (CAST(:p AS uuid), CAST(:type AS partner_type), CAST(:code AS citext), :name,
            CAST(:t AS uuid), :contact, :mobile, CAST(:email AS citext), :address, :gstin,
            :pan, :gst, CAST(:tier AS channel_tier), :credit, :terms, CAST(:me AS uuid))
        RETURNING id"""), {
        "p": body.parent_id, "type": body.partner_type, "tier": body.partner_type,
        "code": body.code.strip(),
        "name": body.name, "t": body.territory_id, "contact": body.contact_name,
        "mobile": _mobile(body.mobile), "email": _email(body.email), "address": body.address,
        "gstin": gstin, "pan": _pan(body.pan), "gst": body.is_gst_registered,
        "credit": body.credit_limit, "terms": body.payment_terms_days, "me": caller.user_id,
    })).scalar_one())
    await _emit(db, entity_type="channel_partner", entity_id=new_id, kind="partner.created",
                actor_id=caller.user_id, partner_id=new_id, code=body.code.strip(),
                partner_type=body.partner_type, parent_id=body.parent_id)
    return await get_partner(db, caller, new_id)


async def patch_partner(db: AsyncSession, caller: Caller, partner_id: str,
                        body: PartnerPatch) -> Partner:
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    if _is_partner_caller(caller):
        for f in sorted(fields - PARTNER_SELF_FIELDS):
            raise ValidationFailed(fields={f: "a partner may edit its contact details only"})
    row = (await db.execute(text(
        "SELECT id, deleted_at FROM channel_partner WHERE id = CAST(:id AS uuid) FOR UPDATE"),
        {"id": partner_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such partner.")
    sets: list[str] = []
    params: dict[str, Any] = {"id": partner_id, "me": caller.user_id}
    changed: dict[str, Any] = {}
    plain = {"name": "name = :name", "contact_name": "contact_name = :contact_name",
             "address": "address = :address"}
    for f, clause in plain.items():
        if f in fields:
            value = getattr(body, f)
            if f == "name" and value is None:
                raise ValidationFailed(fields={"name": "cannot be cleared"})
            sets.append(clause)
            params[f] = value
            changed[f] = value
    if "mobile" in fields:
        sets.append("mobile = :mobile")
        params["mobile"] = _mobile(body.mobile)
        changed["mobile"] = params["mobile"]
    if "email" in fields:
        sets.append("email = CAST(:email AS citext)")
        params["email"] = _email(body.email)
        changed["email"] = params["email"]
    if "gstin" in fields:
        sets.append("gstin = :gstin")
        params["gstin"] = _gstin(body.gstin)
        changed["gstin"] = params["gstin"]
    if "pan" in fields:
        sets.append("pan = :pan")
        params["pan"] = _pan(body.pan)
        changed["pan"] = params["pan"]
    if "is_gst_registered" in fields and body.is_gst_registered is not None:
        sets.append("is_gst_registered = :gst")
        params["gst"] = body.is_gst_registered
        changed["is_gst_registered"] = body.is_gst_registered
    if "territory_id" in fields:
        if body.territory_id is None:
            raise ValidationFailed(fields={"territory_id": "cannot be cleared"})
        await _territory_exists(db, body.territory_id)
        sets.append("territory_id = CAST(:territory AS uuid)")
        params["territory"] = body.territory_id
        changed["territory_id"] = body.territory_id
    if "credit_limit" in fields:
        sets.append("credit_limit = :credit")
        params["credit"] = body.credit_limit
        changed["credit_limit"] = _dec(body.credit_limit)
    if "payment_terms_days" in fields:
        sets.append("payment_terms_days = :terms")
        params["terms"] = body.payment_terms_days
        changed["payment_terms_days"] = body.payment_terms_days
    if not sets:
        raise ValidationFailed(fields={"body": "nothing to change"})
    sets.append("updated_by = CAST(:me AS uuid)")
    r = await _execute_mapped(db, text(
        f"UPDATE channel_partner SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)"), params)
    if r.rowcount == 0:
        raise NotFoundError("No such partner.")
    await _emit(db, entity_type="channel_partner", entity_id=partner_id, kind="partner.updated",
                actor_id=caller.user_id, partner_id=partner_id, fields=sorted(changed), **changed)
    return await get_partner(db, caller, partner_id)


def _state(partner: Partner, inactive: int) -> PartnerStateChange:
    return PartnerStateChange(**partner.model_dump(), users_inactive=inactive)


async def close_partner(db: AsyncSession, caller: Caller, partner_id: str) -> PartnerStateChange:
    """The cascade signs the partner's users out and records partner.deactivated.
    A partner never closes itself (rule 14). Already inactive is a no-op."""
    if _is_partner_caller(caller):
        raise ForbiddenError()
    current, inactive = await _get_partner_state(db, caller, partner_id)
    if not current.is_active:
        return _state(current, inactive)
    try:
        await db.execute(text(
            "SELECT authz_deactivate_anchor('channel_partner', CAST(:id AS uuid))"),
            {"id": partner_id})
    except DBAPIError as exc:
        if _sqlstate(exc) == "42501":
            raise ForbiddenError() from exc
        raise
    return _state(*await _get_partner_state(db, caller, partner_id))


async def reopen_partner(db: AsyncSession, caller: Caller, partner_id: str) -> PartnerStateChange:
    """Restores the anchor only; the people stay inactive and the answer says how
    many (rule 10, GAP-069)."""
    if _is_partner_caller(caller):
        raise ForbiddenError()
    if not await _visible_partner(db, caller, partner_id):
        raise NotFoundError("No such partner.")
    r = await _execute_mapped(db, text(
        "UPDATE channel_partner SET is_active = true, updated_by = CAST(:me AS uuid) "
        "WHERE id = CAST(:id AS uuid) AND NOT is_active AND deleted_at IS NULL"),
        {"id": partner_id, "me": caller.user_id})
    if r.rowcount:
        await _emit(db, entity_type="channel_partner", entity_id=partner_id,
                    kind="partner.reopened", actor_id=caller.user_id, partner_id=partner_id)
    return _state(*await _get_partner_state(db, caller, partner_id))
