"""People: the transactions behind /users (FS-006 sections 4 and 5).

Enforcer 1 is the service predicate and the checks here; enforcer 2 is RLS and the
triggers migration 007 added. Nothing here commits (rule 3). Every write stamps
`updated_by` and emits its `activity_event` in the same transaction with the caller
as actor and the target as entity (rule 18). Every path that revokes sessions and
writes `app_user` revokes first (rule 6), inside a definer that takes the family
locks in id order.

What the service cannot see it asks a definer for: a target's lockout and live
session count (`session` is self-only), and the open-lead count of a person whose
leads are outside the caller's leads scope (a count, not a read, rule 12).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.config import get_settings
from api.domain import identity
from api.domain import leads as domain_leads
from api.errors import NotFoundError, ValidationFailed
from api.schemas.leads import OrgUnitRef, PageMeta, TerritoryRef, UserRef
from api.schemas.users import (
    HandoverRequest,
    HandoverResult,
    PartnerRef,
    PasswordSetResult,
    RevokeResult,
    RoleItem,
    RoleRef,
    UnlockResult,
    UserCreate,
    UserDetail,
    UserPage,
    UserPatch,
    UserRow,
)
from api.services import auth as auth_service
from api.services import leads as leads_service

_USERS = SPECS["users"]
_MAX_LIMIT = 100
HANDOVER_BATCH = 500

PRINCIPAL_REFUSED = "system accounts are not administrable"
LAST_ADMIN = "the last administrator cannot be deactivated, deleted or demoted"

# The columns the scope predicate, the list filters and the keyset order read.
_UUID = sa.Uuid()
_TS = sa.DateTime(timezone=True)
user_t = sa.table(
    "app_user",
    sa.column("id", _UUID),
    sa.column("created_at", _TS),
    sa.column("user_type"),
    sa.column("email"),
    sa.column("mobile"),
    sa.column("full_name"),
    sa.column("role_id", _UUID),
    sa.column("org_unit_id", _UUID),
    sa.column("partner_id", _UUID),
    sa.column("is_active"),
    sa.column("deleted_at", _TS),
)

# Everything a row needs. role and org_unit are readable by every authenticated
# caller; channel_partner is under the caller's partners policies, so its name can
# come back null for a caller who may see the person but not the partner.
_USER_SELECT = """
SELECT u.id, u.user_type::text AS user_type, u.full_name,
       u.email::text AS email, u.mobile,
       r.code::text AS role_code, r.name AS role_name,
       u.org_unit_id, ou.name AS org_unit_name,
       u.partner_id, cp.name AS partner_name,
       u.is_active, u.must_change_password, u.last_login_at, u.password_changed_at,
       u.created_at, u.deleted_at, u.created_by, cb.full_name AS created_by_name
  FROM app_user u
  LEFT JOIN role r ON r.id = u.role_id
  LEFT JOIN org_unit ou ON ou.id = u.org_unit_id
  LEFT JOIN channel_partner cp ON cp.id = u.partner_id
  LEFT JOIN app_user cb ON cb.id = u.created_by
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def _iso(v: datetime | None) -> str | None:
    return None if v is None else v.isoformat()


def _principals() -> tuple[str, str]:
    """The system principal and the website's intake account (FS-003a §5): neither
    is a person, and neither is ever listed or administered (code review F-3)."""
    settings = get_settings()
    return settings.system_user_id, settings.intake_user_id


def _refuse_principal(user_id: str, field: str = "id") -> None:
    """Rule 19: the principals are never administered. The database refuses them too."""
    if user_id in _principals():
        raise ValidationFailed(fields={field: PRINCIPAL_REFUSED})


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _pg_text(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "args", [""])[0] or exc.orig)


def _map_db_error(exc: DBAPIError) -> ValidationFailed | None:
    """The database refusals this feature turns into a field 422. Anything else
    stays a 500: an unmapped refusal is a bug to see, not to hide."""
    code = _sqlstate(exc)
    msg = _pg_text(exc)
    if code == "23505":
        if "uq_app_user_email" in msg:
            return ValidationFailed(fields={"email": "already in use"})
        if "uq_app_user_mobile" in msg:
            return ValidationFailed(fields={"mobile": "already in use"})
    if code == "23514":
        if "office is closed" in msg:
            return ValidationFailed(fields={"org_unit_id": "not found or closed"})
        if "partner is inactive or deleted" in msg:
            return ValidationFailed(fields={"partner_id": "not found or inactive"})
        if "does not match the partner type" in msg:
            return ValidationFailed(fields={"role": "does not match the partner's type"})
        if "last administrator" in msg:
            return ValidationFailed(fields={"id": LAST_ADMIN})
        if "ck_app_user_mobile_shape" in msg:
            return ValidationFailed(fields={"mobile": "not an Indian mobile"})
        if "ck_app_user_email_shape" in msg:
            return ValidationFailed(fields={"email": "not an email"})
        if "ck_app_user_name_shape" in msg:
            return ValidationFailed(fields={"full_name": "1 to 200 characters"})
    if code == "23503":
        if "org_unit" in msg:
            return ValidationFailed(fields={"org_unit_id": "not found or closed"})
        if "partner" in msg:
            return ValidationFailed(fields={"partner_id": "not found or inactive"})
    return None


async def _execute_mapped(db: AsyncSession, stmt: Any, params: dict[str, Any]) -> Any:
    try:
        return await db.execute(stmt, params)
    except DBAPIError as exc:
        mapped = _map_db_error(exc)
        if mapped is None:
            raise
        raise mapped from exc


async def _has_permission(db: AsyncSession, module: str, action: str) -> bool:
    return bool((await db.execute(text("SELECT app_has_permission(:m, :a)"),
                                  {"m": module, "a": action})).scalar_one())


async def _emit(db: AsyncSession, *, user_id: str, kind: str, actor_id: str,
                **payload: Any) -> None:
    """One app_user event: actor = the caller (the INSERT policy checks it), entity =
    the target. Never a hash, never a password (rule 5)."""
    assert "password" not in payload and "password_hash" not in payload
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
        "VALUES ('app_user', CAST(:id AS uuid), :kind, CAST(:me AS uuid), CAST(:p AS jsonb))"),
        {"id": user_id, "kind": kind, "me": actor_id, "p": json.dumps(payload)})


async def _force_admin_floor(db: AsyncSession) -> None:
    """Rule 16: the deferred constraint trigger fires at commit, where a raise is a
    500. Forcing it here makes the answer a 422 inside the request. Not a commit."""
    try:
        await db.execute(text("SET CONSTRAINTS trg_app_user_admin_floor IMMEDIATE"))
    except DBAPIError as exc:
        if _sqlstate(exc) == "23514":
            raise ValidationFailed(fields={"id": LAST_ADMIN}) from exc
        raise


async def _open_tasks(db: AsyncSession, user_id: str) -> int:
    """FS-014 rule 9b: counted by a definer, since the caller's own tasks scope
    need not reach the person."""
    n: int = (await db.execute(text("SELECT user_open_tasks(CAST(:u AS uuid))"),
                               {"u": user_id})).scalar_one()
    return n


async def _open_leads(db: AsyncSession, ids: list[str]) -> dict[str, int]:
    """Unscoped counts through the definer (rule 12); users.view is its guard."""
    if not ids:
        return {}
    rows = (await db.execute(text(
        "SELECT user_id, open_leads FROM user_open_leads_bulk(CAST(:ids AS uuid[]))"),
        {"ids": ids})).all()
    return {str(r.user_id): int(r.open_leads) for r in rows}


def _row(r: Any, open_leads: int | None) -> UserRow:
    return UserRow(
        id=str(r.id), user_type=r.user_type, full_name=r.full_name,
        email=r.email, mobile=r.mobile,
        role=RoleRef(code=r.role_code, name=r.role_name) if r.role_code else None,
        org_unit=OrgUnitRef(id=str(r.org_unit_id), name=r.org_unit_name)
        if r.org_unit_id else None,
        partner=PartnerRef(id=str(r.partner_id), name=r.partner_name)
        if r.partner_id else None,
        is_active=bool(r.is_active), must_change_password=bool(r.must_change_password),
        last_login_at=_iso(r.last_login_at), open_leads=open_leads)


# ── reads ────────────────────────────────────────────────────────────────────

async def list_users(db: AsyncSession, caller: Caller, *, q: str | None = None,
                     user_type: str | None = None, role: str | None = None,
                     org_unit_id: str | None = None, partner_id: str | None = None,
                     is_active: bool | None = None, limit: int = 50,
                     cursor: str | None = None) -> UserPage:
    """The people list, scoped, filtered, keyset-paged by (created_at desc, id).
    Live rows only, and never the principal (rule 19)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    where = [scope_predicate(_USERS, caller, user_t),
             user_t.c.deleted_at.is_(None),
             user_t.c.id.notin_(_principals())]
    if user_type:
        where.append(sa.cast(user_t.c.user_type, sa.Text) == user_type)
    if role:
        where.append(user_t.c.role_id.in_(
            sa.select(sa.column("id", _UUID)).select_from(sa.table("role"))
            .where(sa.cast(sa.column("code"), sa.Text) == role)))
    if org_unit_id:
        where.append(user_t.c.org_unit_id == org_unit_id)
    if partner_id:
        where.append(user_t.c.partner_id == partner_id)
    if is_active is not None:
        where.append(user_t.c.is_active.is_(is_active))
    if q:
        like = leads_service._contains(q)
        clauses = [user_t.c.full_name.ilike(like), sa.cast(user_t.c.email, sa.Text).ilike(like)]
        digits = "".join(ch for ch in q if ch.isdigit())
        # A number query: digits with the usual separators. An email or a name is
        # never matched against mobiles by the digits it happens to contain.
        if digits and len(digits) >= 4 and not any(ch.isalpha() or ch == "@" for ch in q):
            clauses.append(user_t.c.mobile.like("%" + digits + "%"))
        where.append(sa.or_(*clauses))
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append(sa.or_(user_t.c.created_at < c_ts,
                            sa.and_(user_t.c.created_at == c_ts, user_t.c.id < c_id)))

    page = (await db.execute(
        sa.select(user_t.c.id, user_t.c.created_at)
        .where(sa.and_(*where))
        .order_by(user_t.c.created_at.desc(), user_t.c.id.desc())
        .limit(limit + 1))).all()
    next_cursor = None
    if len(page) > limit:
        last = page[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        page = page[:limit]
    ids = [str(r.id) for r in page]
    if not ids:
        return UserPage(data=[], meta=PageMeta(limit=limit, next_cursor=None))

    rows = (await db.execute(text(_USER_SELECT + " WHERE u.id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    staff_ids = [i for i in ids if i in by_id and by_id[i].user_type == "staff"]
    counts = await _open_leads(db, staff_ids)
    data = [_row(by_id[i], counts.get(i, 0) if by_id[i].user_type == "staff" else None)
            for i in ids if i in by_id]
    return UserPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def _visible(db: AsyncSession, caller: Caller, user_id: str) -> bool:
    """Enforcer 1 for one row: the predicate over the caller's claim. The principal
    is never visible here."""
    if user_id in _principals():
        return False
    return (await db.execute(
        sa.select(user_t.c.id).where(sa.and_(scope_predicate(_USERS, caller, user_t),
                                             user_t.c.id == user_id)))).first() is not None


async def get_user(db: AsyncSession, caller: Caller, user_id: str) -> UserDetail:
    """One person, with the territories and, for users.edit holders, the lockout and
    the live session count (both definer reads; `session` is self-only)."""
    if not await _visible(db, caller, user_id):
        raise NotFoundError("No such person.")
    row = (await db.execute(text(_USER_SELECT + " WHERE u.id = CAST(:id AS uuid)"),
                            {"id": user_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such person.")
    territories = (await db.execute(text(
        "SELECT t.id, t.name, t.level::text AS level FROM user_territory ut "
        "JOIN territory t ON t.id = ut.territory_id "
        "WHERE ut.user_id = CAST(:id AS uuid) ORDER BY t.name"), {"id": user_id})).all()
    counts = await _open_leads(db, [user_id]) if row.user_type == "staff" else {}
    locked_until = None
    active_sessions = None
    if await _has_permission(db, "users", "edit"):
        settings = get_settings()
        if row.user_type == "staff":
            locked_until = _iso((await db.execute(text(
                "SELECT auth_user_lockout(CAST(:id AS uuid), :n, :l)"),
                {"id": user_id, "n": settings.login_max_failures,
                 "l": settings.login_lockout})).scalar_one())
        active_sessions = int((await db.execute(text(
            "SELECT auth_user_session_count(CAST(:id AS uuid))"), {"id": user_id})).scalar_one())
    base = _row(row, counts.get(user_id, 0) if row.user_type == "staff" else None)
    return UserDetail(
        **base.model_dump(),
        territories=[TerritoryRef(id=str(t.id), name=t.name, level=t.level) for t in territories],
        locked_until=locked_until, active_sessions=active_sessions,
        password_changed_at=_iso(row.password_changed_at),
        created_at=row.created_at.isoformat(), deleted_at=_iso(row.deleted_at),
        created_by=UserRef(id=str(row.created_by), full_name=row.created_by_name)
        if row.created_by and row.created_by_name else None)


# ── create ───────────────────────────────────────────────────────────────────

async def _role_for_staff(db: AsyncSession, code: str | None) -> str:
    if not code or code not in identity.ASSIGNABLE_ROLES:
        raise ValidationFailed(fields={"role": "unknown"})
    row = (await db.execute(text(
        "SELECT id, is_portal FROM role WHERE code = CAST(:c AS citext) AND deleted_at IS NULL"),
        {"c": code})).one_or_none()
    if row is None:
        raise ValidationFailed(fields={"role": "unknown"})
    if row.is_portal:
        raise ValidationFailed(fields={"role": "portal roles are for partner users"})
    return str(row.id)


async def _role_for_partner(db: AsyncSession, partner_id: str) -> str:
    """Rule 2: the partner's type decides the role. The partner must be active and
    in the caller's partners scope (the policies filter it underneath)."""
    ptype = (await db.execute(text(
        "SELECT partner_type::text FROM channel_partner "
        "WHERE id = CAST(:p AS uuid) AND is_active AND deleted_at IS NULL"),
        {"p": partner_id})).scalar_one_or_none()
    if ptype is None:
        raise ValidationFailed(fields={"partner_id": "not found or inactive"})
    code = identity.PORTAL_ROLE_BY_TYPE[ptype]
    role_id = (await db.execute(text(
        "SELECT id FROM role WHERE code = CAST(:c AS citext) AND deleted_at IS NULL"),
        {"c": code})).scalar_one_or_none()
    if role_id is None:
        raise ValidationFailed(fields={"partner_id": f"the {code} role is not seeded"})
    return str(role_id)


async def _open_office(db: AsyncSession, org_unit_id: str) -> None:
    ok = (await db.execute(text(
        "SELECT 1 FROM org_unit WHERE id = CAST(:o AS uuid) AND deleted_at IS NULL"),
        {"o": org_unit_id})).first()
    if ok is None:
        raise ValidationFailed(fields={"org_unit_id": "not found or closed"})


async def _territories_exist(db: AsyncSession, ids: list[str]) -> None:
    if not ids:
        return
    if len(set(ids)) != len(ids):
        raise ValidationFailed(fields={"territory_ids": "repeated"})
    n: int = (await db.execute(text(
        "SELECT count(*) FROM territory WHERE id = ANY(CAST(:ids AS uuid[])) "
        "AND deleted_at IS NULL"), {"ids": ids})).scalar_one()
    if int(n) != len(ids):
        raise ValidationFailed(fields={"territory_ids": "not found"})


async def _role_needs_territory(db: AsyncSession, role_id: str) -> bool:
    """A role with any view row at territory scope sees nothing there without a
    territory (RBAC section 3). role_permission is readable by every caller."""
    return (await db.execute(text(
        "SELECT 1 FROM role_permission WHERE role_id = CAST(:r AS uuid) "
        "AND action = 'view' AND scope = 'territory' LIMIT 1"), {"r": role_id})).first() is not None


async def _assert_anchor_in_scope(db: AsyncSession, caller: Caller, *,
                                  org_unit_id: str | None, partner_id: str | None) -> None:
    """Enforcer 1 for the INSERT (and a re-anchoring PATCH): the row must sit in the
    caller's users scope, the branch the WITH CHECK re-verifies underneath."""
    scope = caller.scopes.get("users")
    if scope == "global":
        return
    if scope == "org_subtree" and caller.org_unit_id and org_unit_id and (await db.execute(
            text("SELECT 1 FROM org_closure WHERE ancestor_id = CAST(:a AS uuid) "
                 "AND descendant_id = CAST(:d AS uuid)"),
            {"a": caller.org_unit_id, "d": org_unit_id})).first():
        return
    if scope == "partner_subtree" and caller.partner_id and partner_id and (await db.execute(
            text("SELECT 1 FROM partner_closure WHERE ancestor_id = CAST(:a AS uuid) "
                 "AND descendant_id = CAST(:d AS uuid)"),
            {"a": caller.partner_id, "d": partner_id})).first():
        return
    field = "org_unit_id" if org_unit_id else "partner_id"
    raise ValidationFailed(fields={field: "outside your scope"})


async def _identifier_free(db: AsyncSession, column: str, value: str) -> None:
    """The pre-check among live rows; the partial unique index is the enforcer, and
    a 23505 the caller's scope hid from this read is mapped to the same field."""
    taken = (await db.execute(text(
        f"SELECT 1 FROM app_user WHERE {column} = :v AND deleted_at IS NULL"),
        {"v": value})).first()
    if taken is not None:
        raise ValidationFailed(fields={column: "already in use"})


def _normalised_email(raw: str | None, *, required: bool) -> str | None:
    if raw is None:
        if required:
            raise ValidationFailed(fields={"email": "required for staff"})
        return None
    try:
        return identity.normalise_email(raw)
    except identity.EmailError as exc:
        raise ValidationFailed(fields={"email": str(exc)}) from exc


def _normalised_mobile(raw: str | None, *, required: bool) -> str | None:
    if raw is None:
        if required:
            raise ValidationFailed(fields={"mobile": "required for a partner user"})
        return None
    try:
        return identity.mobile_for_user(raw)
    except identity.MobileError as exc:
        raise ValidationFailed(fields={"mobile": "not an Indian mobile"}) from exc


async def create_user(db: AsyncSession, caller: Caller, body: UserCreate) -> UserDetail:
    """A staff member or a partner user, in one transaction with its event. The
    route has passed require('users', 'create') and reserved the idempotency record."""
    staff = body.user_type == "staff"
    email = _normalised_email(body.email, required=staff)
    mobile = _normalised_mobile(body.mobile, required=not staff)
    password_hash: str | None = None

    if staff:
        if body.partner_id is not None:
            raise ValidationFailed(fields={"partner_id": "staff are anchored on an office"})
        if body.org_unit_id is None:
            raise ValidationFailed(fields={"org_unit_id": "not found or closed"})
        if body.password is None:
            raise ValidationFailed(
                fields={"password": f"at least {identity.PASSWORD_MIN} characters"})
        problem = identity.password_problem(body.password)
        if problem:
            raise ValidationFailed(fields={"password": problem})
        role_id = await _role_for_staff(db, body.role)
        await _open_office(db, body.org_unit_id)
        await _territories_exist(db, body.territory_ids)
        if not body.territory_ids and await _role_needs_territory(db, role_id):
            raise ValidationFailed(
                fields={"territory_ids": "this role needs at least one territory"})
        password_hash = await asyncio.to_thread(auth_service.hash_password, body.password)
    else:
        if body.role is not None:
            raise ValidationFailed(fields={"role": "a partner user's role is its partner's type"})
        if body.org_unit_id is not None:
            raise ValidationFailed(
                fields={"org_unit_id": "partner users are anchored on a partner"})
        if body.partner_id is None:
            raise ValidationFailed(fields={"partner_id": "not found or inactive"})
        if body.territory_ids:
            raise ValidationFailed(fields={"territory_ids": "partner users hold no territories"})
        if body.password is not None:
            raise ValidationFailed(
                fields={"password": "a partner user signs in by OTP and has no password"})
        role_id = await _role_for_partner(db, body.partner_id)

    await _assert_anchor_in_scope(db, caller, org_unit_id=body.org_unit_id,
                                  partner_id=body.partner_id)
    if email is not None:
        await _identifier_free(db, "email", email)
    if mobile is not None:
        await _identifier_free(db, "mobile", mobile)

    new_id = str((await _execute_mapped(db, text("""
        INSERT INTO app_user (user_type, email, mobile, password_hash, full_name, role_id,
                              org_unit_id, partner_id, must_change_password, created_by)
        VALUES (CAST(:ut AS user_type), CAST(:email AS citext), :mobile, :hash, :name,
                CAST(:role AS uuid), CAST(:ou AS uuid), CAST(:partner AS uuid), :mcp,
                CAST(:me AS uuid))
        RETURNING id"""), {
        "ut": body.user_type, "email": email, "mobile": mobile, "hash": password_hash,
        "name": body.full_name.strip(), "role": role_id, "ou": body.org_unit_id,
        "partner": body.partner_id, "mcp": staff, "me": caller.user_id,
    })).scalar_one())
    for tid in body.territory_ids:
        await db.execute(text(
            "INSERT INTO user_territory (user_id, territory_id) "
            "VALUES (CAST(:u AS uuid), CAST(:t AS uuid))"), {"u": new_id, "t": tid})
    await _emit(db, user_id=new_id, kind="user.created", actor_id=caller.user_id,
                user_type=body.user_type, role_id=role_id, org_unit_id=body.org_unit_id,
                partner_id=body.partner_id, territory_ids=list(body.territory_ids))
    return await get_user(db, caller, new_id)


# ── edit ─────────────────────────────────────────────────────────────────────

_LOCK = text(
    "SELECT id, user_type::text AS user_type, email::text AS email, mobile, full_name, "
    "role_id, org_unit_id, partner_id, is_active, deleted_at "
    "FROM app_user WHERE id = CAST(:id AS uuid) FOR UPDATE")


async def _lock(db: AsyncSession, user_id: str) -> Any:
    """SELECT ... FOR UPDATE under the users UPDATE policy: a caller who may see the
    row but not edit it gets zero rows, which is a 404 after require() has passed.
    Rule 20: the person's row is held before any lead row is touched."""
    return (await db.execute(_LOCK, {"id": user_id})).one_or_none()


_SELF_LABELS = {
    "role": "you cannot change your own role",
    "org_unit_id": "you cannot move yourself",
    "partner_id": "you cannot move yourself",
    "territory_ids": "you cannot change your own territories",
    "is_active": "you cannot deactivate yourself",
}


async def _revoke(db: AsyncSession, user_id: str) -> int:
    return int((await db.execute(text(
        "SELECT auth_revoke_user_sessions(CAST(:id AS uuid))"), {"id": user_id})).scalar_one())


async def patch_user(db: AsyncSession, caller: Caller, user_id: str,
                     body: UserPatch) -> UserDetail:
    """Correct a person (FS-006 4). user_type never changes; a partner user's role
    follows its partner; territory_ids replaces the set; deactivation revokes
    first; the last administrator is protected at the floor (rule 16)."""
    _refuse_principal(user_id)
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    if user_id == caller.user_id:
        for f in ("role", "org_unit_id", "partner_id", "territory_ids", "is_active"):
            if f in fields:
                raise ValidationFailed(fields={f: _SELF_LABELS[f]})
    if not await _visible(db, caller, user_id):
        raise NotFoundError("No such person.")
    # Rule 6 before rule 20: a deactivation revokes BEFORE this row is locked. The
    # definer takes the family locks first, and a concurrent refresh holds a family
    # lock while it waits for a share of this row, so the other order deadlocks
    # (cross-vendor P1, executed: 40P01). A 4xx below rolls the revoke back.
    pre = (await db.execute(text(
        "SELECT is_active FROM app_user WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": user_id})).one_or_none()
    if pre is None:
        raise NotFoundError("No such person.")
    revoked_early = 0
    if "is_active" in fields and body.is_active is False and pre.is_active:
        revoked_early = await _revoke(db, user_id)
    row = await _lock(db, user_id)
    if row is None:
        raise NotFoundError("No such person.")
    if row.deleted_at is not None:
        raise ValidationFailed(fields={"id": "this person is deleted"})
    staff = row.user_type == "staff"

    sets: list[str] = []
    params: dict[str, Any] = {"id": user_id, "me": caller.user_id}
    changed: dict[str, Any] = {}
    role_id = str(row.role_id) if row.role_id else None
    role_changed = False

    if "full_name" in fields:
        if body.full_name is None:
            raise ValidationFailed(fields={"full_name": "cannot be cleared"})
        sets.append("full_name = :name")
        params["name"] = body.full_name
        changed["full_name"] = body.full_name
    if "email" in fields:
        if not staff and body.email is None:
            sets.append("email = NULL")
            changed["email"] = None
        else:
            email = _normalised_email(body.email, required=staff)
            if email != row.email:
                await _identifier_free(db, "email", email or "")
            sets.append("email = CAST(:email AS citext)")
            params["email"] = email
            changed["email"] = email
    if "mobile" in fields:
        if staff and body.mobile is None:
            sets.append("mobile = NULL")
            changed["mobile"] = None
        else:
            mobile = _normalised_mobile(body.mobile, required=not staff)
            if mobile != row.mobile:
                await _identifier_free(db, "mobile", mobile or "")
            sets.append("mobile = :mobile")
            params["mobile"] = mobile
            changed["mobile"] = mobile
    if "role" in fields:
        if not staff:
            raise ValidationFailed(fields={"role": "a partner user's role is its partner's type"})
        role_id = await _role_for_staff(db, body.role)
        role_changed = role_id != str(row.role_id)
        sets.append("role_id = CAST(:role AS uuid)")
        params["role"] = role_id
        changed["role"] = body.role
    if "org_unit_id" in fields:
        if not staff:
            raise ValidationFailed(
                fields={"org_unit_id": "partner users are anchored on a partner"})
        if body.org_unit_id is None:
            raise ValidationFailed(fields={"org_unit_id": "not found or closed"})
        await _open_office(db, body.org_unit_id)
        await _assert_anchor_in_scope(db, caller, org_unit_id=body.org_unit_id, partner_id=None)
        sets.append("org_unit_id = CAST(:ou AS uuid)")
        params["ou"] = body.org_unit_id
        changed["org_unit_id"] = body.org_unit_id
    if "partner_id" in fields:
        if staff:
            raise ValidationFailed(fields={"partner_id": "staff are anchored on an office"})
        if body.partner_id is None:
            raise ValidationFailed(fields={"partner_id": "not found or inactive"})
        role_id = await _role_for_partner(db, body.partner_id)
        await _assert_anchor_in_scope(db, caller, org_unit_id=None, partner_id=body.partner_id)
        sets.append("partner_id = CAST(:partner AS uuid)")
        params["partner"] = body.partner_id
        sets.append("role_id = CAST(:role AS uuid)")
        params["role"] = role_id
        role_changed = role_id != str(row.role_id)
        changed["partner_id"] = body.partner_id
    if "territory_ids" in fields:
        if not staff:
            raise ValidationFailed(fields={"territory_ids": "partner users hold no territories"})
        ids = list(body.territory_ids or [])
        await _territories_exist(db, ids)
        if not ids and role_id and await _role_needs_territory(db, role_id):
            raise ValidationFailed(
                fields={"territory_ids": "this role needs at least one territory"})
        await db.execute(text("DELETE FROM user_territory WHERE user_id = CAST(:u AS uuid)"),
                         {"u": user_id})
        for tid in ids:
            await db.execute(text(
                "INSERT INTO user_territory (user_id, territory_id) "
                "VALUES (CAST(:u AS uuid), CAST(:t AS uuid))"), {"u": user_id, "t": tid})
        changed["territory_ids"] = ids

    if (role_changed and "territory_ids" not in fields and staff and role_id
            and await _role_needs_territory(db, role_id)):
        held: int = (await db.execute(text(
            "SELECT count(*) FROM user_territory WHERE user_id = CAST(:u AS uuid)"),
            {"u": user_id})).scalar_one()
        if not held:
            raise ValidationFailed(
                fields={"territory_ids": "this role needs at least one territory"})

    active_change: str | None = None
    if "is_active" in fields and body.is_active is not None and body.is_active != row.is_active:
        if not body.is_active:
            if staff and await _open_tasks(db, user_id):
                raise ValidationFailed(
                    fields={"is_active": "hand over their open tasks first"})
            changed["sessions_revoked"] = revoked_early   # revoked above, before the lock
            active_change = "user.deactivated"
        else:
            active_change = "user.reactivated"
        sets.append("is_active = :active")
        params["active"] = body.is_active
        changed["is_active"] = body.is_active

    if sets:
        sets.append("updated_by = CAST(:me AS uuid)")
        r = await _execute_mapped(db, text(
            f"UPDATE app_user SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)"), params)
        if r.rowcount == 0:
            raise NotFoundError("No such person.")
    if changed:
        payload = {k: v for k, v in changed.items() if k not in ("is_active", "sessions_revoked")}
        if payload:
            await _emit(db, user_id=user_id, kind="user.updated", actor_id=caller.user_id,
                        fields=sorted(payload), **payload)
        if active_change:
            await _emit(db, user_id=user_id, kind=active_change, actor_id=caller.user_id,
                        sessions_revoked=changed.get("sessions_revoked", 0))
    if role_changed or active_change:
        await _force_admin_floor(db)
    return await get_user(db, caller, user_id)


# ── the admin actions ────────────────────────────────────────────────────────

async def _target(db: AsyncSession, caller: Caller, user_id: str) -> Any:
    """A visible, live target for the definer-backed actions; 404 otherwise, and
    the principal is refused by name (rule 19)."""
    _refuse_principal(user_id)
    if not await _visible(db, caller, user_id):
        raise NotFoundError("No such person.")
    row = (await db.execute(text(
        "SELECT user_type::text AS user_type, is_active, deleted_at FROM app_user "
        "WHERE id = CAST(:id AS uuid)"), {"id": user_id})).one_or_none()
    if row is None or row.deleted_at is not None:
        raise NotFoundError("No such person.")
    return row


async def set_password(db: AsyncSession, caller: Caller, user_id: str,
                       password: str) -> PasswordSetResult:
    """An admin's temporary password for a staff member: every session revoked
    first (rule 6), then the hash and the forced-change flag."""
    row = await _target(db, caller, user_id)
    if row.user_type != "staff":
        raise ValidationFailed(
            fields={"user_type": "a partner user signs in by OTP and has no password"})
    problem = identity.password_problem(password)
    if problem:
        raise ValidationFailed(fields={"password": problem})
    revoked = await _revoke(db, user_id)
    password_hash = await asyncio.to_thread(auth_service.hash_password, password)
    r = await _execute_mapped(db, text(
        "UPDATE app_user SET password_hash = :h, must_change_password = true, "
        "updated_by = CAST(:me AS uuid) WHERE id = CAST(:id AS uuid)"),
        {"h": password_hash, "me": caller.user_id, "id": user_id})
    if r.rowcount == 0:
        raise NotFoundError("No such person.")
    await _emit(db, user_id=user_id, kind="auth.password_set_by_admin", actor_id=caller.user_id,
                sessions_revoked=revoked)
    return PasswordSetResult(id=user_id, sessions_revoked=revoked)


async def revoke_sessions(db: AsyncSession, caller: Caller, user_id: str) -> RevokeResult:
    """Sign a person out everywhere, now (GAP-045). The definer writes the event."""
    await _target(db, caller, user_id)
    return RevokeResult(id=user_id, sessions_revoked=await _revoke(db, user_id))


async def unlock(db: AsyncSession, caller: Caller, user_id: str) -> UnlockResult:
    """Clear a staff member's lockout (GAP-017, the in-band half). The definer
    appends an `unlock` row and writes the event; nothing is deleted (rule 13)."""
    row = await _target(db, caller, user_id)
    if row.user_type != "staff":
        raise ValidationFailed(fields={"user_type": "OTP sign-in has no lockout to clear"})
    settings = get_settings()
    was_locked: Any = (await db.execute(text(
        "SELECT auth_unlock_user(CAST(:id AS uuid), :n, :l)"),
        {"id": user_id, "n": settings.login_max_failures,
         "l": settings.login_lockout})).scalar_one()
    return UnlockResult(id=user_id, was_locked=bool(was_locked))


async def handover(db: AsyncSession, caller: Caller, user_id: str,
                   body: HandoverRequest) -> HandoverResult:
    """Move the leaver's open leads to someone who can work them (rule 11), at most
    500 per call, one `lead.assigned` event each, and all their open tasks (FS-014
    rule 9b); optionally deactivate the leaver once nothing remains. Both people are
    locked first, in id order (rule 20)."""
    _refuse_principal(user_id)
    _refuse_principal(body.to_user_id, "to_user_id")
    if body.to_user_id == user_id:
        raise ValidationFailed(fields={"to_user_id": "choose a different person"})
    if body.deactivate and user_id == caller.user_id:
        raise ValidationFailed(fields={"id": _SELF_LABELS["is_active"]})

    # One handover at a time (namespace 4, its own key). Two reciprocal deactivating
    # handovers would otherwise each hold one person through the revoke below and
    # wait for the other. Taken before any row lock; a refresh never takes it, so
    # it cannot cycle with rule 6's family locks (cross-vendor P1).
    await db.execute(text("SELECT pg_advisory_xact_lock(4, hashtext('handover'))"))
    revoked = 0
    if body.deactivate:
        if not await _visible(db, caller, user_id):
            raise NotFoundError("No such person.")
        # rule 6 before rule 20: the leaver's sessions go before the row locks; a
        # 422 below rolls the revoke back
        revoked = await _revoke(db, user_id)

    rows = (await db.execute(text(
        "SELECT id, user_type::text AS user_type, is_active, deleted_at FROM app_user "
        "WHERE id IN (CAST(:a AS uuid), CAST(:b AS uuid)) ORDER BY id FOR UPDATE"),
        {"a": user_id, "b": body.to_user_id})).all()
    by_id = {str(r.id): r for r in rows}
    leaver = by_id.get(user_id)
    if leaver is None or leaver.deleted_at is not None or body.to_user_id not in by_id:
        raise NotFoundError("No such person.")
    ok: bool = (await db.execute(text("SELECT authz_user_assignable('leads', CAST(:u AS uuid))"),
                           {"u": body.to_user_id})).scalar_one()
    if not ok:
        raise ValidationFailed(fields={"to_user_id": "not assignable by you"})

    lead_ids = [str(r.id) for r in (await db.execute(text(
        "SELECT id FROM lead WHERE owner_user_id = CAST(:u AS uuid) AND deleted_at IS NULL "
        "AND NOT (stage::text = ANY(CAST(:closed AS text[]))) ORDER BY id FOR UPDATE LIMIT :n"),
        {"u": user_id, "closed": sorted(domain_leads.TERMINAL), "n": HANDOVER_BATCH})).all()]
    actor_name = await leads_service._actor_name(db) if lead_ids else ""
    for lid in lead_ids:
        await db.execute(text(
            "UPDATE lead SET owner_user_id = CAST(:to AS uuid), updated_by = CAST(:me AS uuid) "
            "WHERE id = CAST(:id AS uuid)"),
            {"to": body.to_user_id, "me": caller.user_id, "id": lid})
        await leads_service._emit(db, lead_id=lid, kind="lead.assigned", actor_id=caller.user_id,
                                  actor_name=actor_name, owner_user_id=body.to_user_id,
                                  previous_owner_user_id=user_id, handover=True)
        await leads_service._rescore(db, lid)

    # FS-014 rule 9b: every open task goes with this call, one task.reassigned each
    tasks_moved = 0
    if leaver.user_type == "staff":
        tasks_moved = (await db.execute(text(
            "SELECT user_tasks_handover(CAST(:f AS uuid), CAST(:t AS uuid))"),
            {"f": user_id, "t": body.to_user_id})).scalar_one()

    remaining = (await _open_leads(db, [user_id])).get(user_id, 0)
    deactivated = False
    if body.deactivate:
        if remaining > 0:
            raise ValidationFailed(
                fields={"deactivate": "open leads remain; repeat the handover first"})
        if leaver.is_active:
            await _execute_mapped(db, text(
                "UPDATE app_user SET is_active = false, updated_by = CAST(:me AS uuid) "
                "WHERE id = CAST(:id AS uuid)"), {"me": caller.user_id, "id": user_id})
            await _emit(db, user_id=user_id, kind="user.deactivated", actor_id=caller.user_id,
                        sessions_revoked=revoked, handover_to=body.to_user_id)
            await _force_admin_floor(db)
        deactivated = True
    await _emit(db, user_id=user_id, kind="user.handover", actor_id=caller.user_id,
                to_user_id=body.to_user_id, leads_moved=len(lead_ids), remaining=remaining,
                tasks_moved=tasks_moved)
    return HandoverResult(leads_moved=len(lead_ids), remaining=remaining,
                          tasks_moved=tasks_moved, deactivated=deactivated)


async def delete_user(db: AsyncSession, caller: Caller, user_id: str) -> None:
    """Soft delete (users.delete). Refused while they own an open lead or hold an
    open task, for the caller's own row, the last administrator and the principal.
    A repeat is a no-op."""
    _refuse_principal(user_id)
    if user_id == caller.user_id:
        raise ValidationFailed(fields={"id": "you cannot delete yourself"})
    if not await _visible(db, caller, user_id):
        raise NotFoundError("No such person.")
    pre = (await db.execute(text(
        "SELECT deleted_at FROM app_user WHERE id = CAST(:id AS uuid)"),
        {"id": user_id})).one_or_none()
    if pre is None:
        raise NotFoundError("No such person.")
    if pre.deleted_at is not None:
        return
    # rule 6 before the row lock (cross-vendor P1); a 422 below rolls it back
    revoked = await _revoke(db, user_id)
    row = await _lock(db, user_id)
    if row is None:
        raise NotFoundError("No such person.")
    if row.deleted_at is not None:
        return
    open_leads = (await _open_leads(db, [user_id])).get(user_id, 0) \
        if row.user_type == "staff" else 0
    if open_leads > 0:
        raise ValidationFailed(fields={"open_leads": "hand over their open leads first"})
    if row.user_type == "staff" and await _open_tasks(db, user_id):
        raise ValidationFailed(fields={"open_tasks": "hand over their open tasks first"})
    await _execute_mapped(db, text(
        "UPDATE app_user SET deleted_at = now(), is_active = false, "
        "updated_by = CAST(:me AS uuid) WHERE id = CAST(:id AS uuid)"),
        {"me": caller.user_id, "id": user_id})
    await _emit(db, user_id=user_id, kind="user.deleted", actor_id=caller.user_id,
                sessions_revoked=revoked)
    await _force_admin_floor(db)


# ── roles ────────────────────────────────────────────────────────────────────

async def list_roles(db: AsyncSession) -> list[RoleItem]:
    """The sixteen assignable roles (rule 1): never `system`, never a test leftover."""
    rows = (await db.execute(text(
        "SELECT code::text AS code, name, level, is_functional, is_portal FROM role "
        "WHERE deleted_at IS NULL AND code::text = ANY(CAST(:codes AS text[])) "
        "ORDER BY is_portal, level DESC, name"),
        {"codes": list(identity.ASSIGNABLE_ROLES)})).all()
    return [RoleItem(code=r.code, name=r.name, level=int(r.level),
                     is_functional=bool(r.is_functional), is_portal=bool(r.is_portal))
            for r in rows]


# ── cursor ───────────────────────────────────────────────────────────────────

def _encode_cursor(created_at: datetime, user_id: str) -> str:
    raw = f"{created_at.isoformat()}|{user_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, _, user_id = raw.partition("|")
        return datetime.fromisoformat(ts), user_id
    except (ValueError, binascii.Error) as exc:
        raise ValidationFailed(fields={"cursor": "malformed cursor"}) from exc
