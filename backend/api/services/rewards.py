# ruff: noqa: E501  (embedded SQL)

"""Reward points (FS-032): the masters, balances, the ledger and redemptions.

Earning happens in migration 036's triggers and spending in its definers; this
service owns the masters and the reads, and maps the definers' refusals. Balances and
the ledger are read under the caller's own policies, never through a definer, so a
field officer sums only their own points (plan review B3).

Services never commit (rule 3).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import rewards as domain
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import rewards as sch
from api.schemas.leads import PageMeta
from api.services.clock import today_ist
from api.services.leads import _decode_cursor, _encode_cursor
from api.services.orders import _pg_text, _sqlstate, map_db_error

_LIMIT = 100


def _db_error(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc) or ""
    msg = _pg_text(exc).split("\n", 1)[0]
    if code in domain.SQLSTATE_TO_ERROR:
        status, api_code = domain.SQLSTATE_TO_ERROR[code]
        if status == 404:
            return NotFoundError("No such request.")
        if status == 409:
            return ConflictError(msg, code=api_code)
        return ValidationFailed(msg, code=api_code)
    if code == "42501" and "not your points" in msg:
        return ForbiddenError("These are not your points to spend.", code="not_your_points")
    return map_db_error(exc)


async def _call(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        raise _db_error(exc) from exc


async def _event(db: AsyncSession, caller: Caller, entity: str, entity_id: str, kind: str,
                 **payload: Any) -> None:
    """Rule 7 for the reward masters (code review F-3): a point value or a rule is a
    money-affecting change, so it lands on a timeline, not only in the audit log."""
    import json
    name = (await db.execute(text("SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"),
                             {"u": caller.user_id})).scalar_one_or_none()
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
        "VALUES (:t, CAST(:i AS uuid), :k, CAST(:u AS uuid), CAST(:p AS jsonb))"),
        {"t": entity, "i": entity_id, "k": kind, "u": caller.user_id,
         "p": json.dumps({"actor_name": name or "", **payload}, default=str)})


def _money(v: Any) -> str:
    return format(Decimal(v).quantize(Decimal("0.01")), "f")


# ── rules ────────────────────────────────────────────────────────────────────

_RULE_SELECT = ("SELECT r.*, r.code::text AS code_text, reward_rule_used(r.id) AS used FROM reward_rule r")


def _rule(r: Any) -> sch.Rule:
    return sch.Rule(id=str(r.id), code=r.code_text, name=r.name, holder=r.holder, basis=r.basis,
                    points=r.points, per_amount=_money(r.per_amount) if r.per_amount is not None else None,
                    valid_from=r.valid_from.isoformat(),
                    valid_to=r.valid_to.isoformat() if r.valid_to else None,
                    expiry_days=r.expiry_days, is_active=r.is_active, used=bool(r.used))


def _rule_problems(holder: str, basis: str, per_amount: Decimal | None, valid_from: Any,
                   valid_to: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if basis == "order_value" and per_amount is None:
        out["per_amount"] = "An order-value rule needs the rupees per block."
    if basis == "lead_won":
        if holder != "staff":
            out["holder"] = "Lead points go to staff."
        if per_amount is not None:
            out["per_amount"] = "A lead rule gives a flat number of points."
    if valid_to is not None and valid_to < valid_from:
        out["valid_to"] = "Must be on or after the start date."
    return out


async def get_rule(db: AsyncSession, rule_id: str) -> sch.Rule:
    r = (await db.execute(text(_RULE_SELECT + " WHERE r.id = CAST(:i AS uuid)"), {"i": rule_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such rule.")
    return _rule(r)


async def list_rules(db: AsyncSession) -> list[sch.Rule]:
    rows = (await db.execute(text(_RULE_SELECT + " ORDER BY r.is_active DESC, r.created_at DESC"))).all()
    return [_rule(r) for r in rows]


async def create_rule(db: AsyncSession, caller: Caller, body: sch.RuleCreate) -> sch.Rule:
    problems = _rule_problems(body.holder, body.basis, body.per_amount, body.valid_from, body.valid_to)
    if problems:
        raise ValidationFailed(fields=problems)
    try:
        async with db.begin_nested():
            rid: Any = (await db.execute(text(
                "INSERT INTO reward_rule (code, name, holder, basis, points, per_amount, valid_from, valid_to, "
                "expiry_days, created_by, updated_by) VALUES (:c, :n, :h, :b, :p, :pa, :vf, :vt, :e, "
                "CAST(:u AS uuid), CAST(:u AS uuid)) RETURNING id"),
                {"c": body.code, "n": body.name.strip(), "h": body.holder, "b": body.basis, "p": body.points,
                 "pa": body.per_amount, "vf": body.valid_from, "vt": body.valid_to, "e": body.expiry_days,
                 "u": caller.user_id})).scalar_one()
    except IntegrityError as exc:
        if "reward_rule_code_key" in str(exc.orig):
            raise ConflictError("A rule with this code exists.", code="code_taken",
                                fields={"code": "Already used."}) from exc
        raise
    await _event(db, caller, "reward_rule", str(rid), "rewards.rule_created", code=body.code)
    return await get_rule(db, str(rid))


async def patch_rule(db: AsyncSession, caller: Caller, rule_id: str, body: sch.RulePatch) -> sch.Rule:
    current = await get_rule(db, rule_id)
    sent = body.model_dump(exclude_unset=True)
    if current.used and set(sent) - {"valid_to", "is_active"}:
        raise ConflictError("This rule has awarded points. Only its end date and active flag "
                            "can change; end it and create a new one.", code="rule_in_use")
    merged = {**current.model_dump(), **sent}
    pa = merged["per_amount"]
    import datetime as dt
    vf = merged["valid_from"] if isinstance(merged["valid_from"], dt.date) else dt.date.fromisoformat(merged["valid_from"])
    vt = merged["valid_to"]
    vt = vt if vt is None or isinstance(vt, dt.date) else dt.date.fromisoformat(vt)
    problems = _rule_problems(current.holder, current.basis, Decimal(pa) if pa is not None else None, vf, vt)
    if problems:
        raise ValidationFailed(fields=problems)
    try:
        async with db.begin_nested():
            await db.execute(text(
                "UPDATE reward_rule SET name = :n, points = :p, per_amount = :pa, valid_from = :vf, "
                "valid_to = :vt, expiry_days = :e, is_active = :a, updated_by = CAST(:u AS uuid) "
                "WHERE id = CAST(:i AS uuid)"),
                {"n": merged["name"].strip(), "p": merged["points"], "pa": pa, "vf": vf, "vt": vt,
                 "e": merged["expiry_days"], "a": merged["is_active"], "u": caller.user_id, "i": rule_id})
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    await _event(db, caller, "reward_rule", rule_id, "rewards.rule_updated", fields=sorted(sent))
    return await get_rule(db, rule_id)


# ── settings and gifts ───────────────────────────────────────────────────────

async def get_settings(db: AsyncSession) -> sch.SettingsOut:
    r = (await db.execute(text(
        "SELECT point_value, max_redeem_pct, effective_from FROM reward_setting "
        "WHERE effective_from <= :d ORDER BY effective_from DESC LIMIT 1"), {"d": today_ist()})).one_or_none()
    if r is None:
        raise NotFoundError("No reward settings yet.")
    return sch.SettingsOut(point_value=_money(r.point_value), max_redeem_pct=_money(r.max_redeem_pct),
                           effective_from=r.effective_from.isoformat())


async def put_settings(db: AsyncSession, caller: Caller, body: sch.Settings) -> sch.SettingsOut:
    """A new row from today; a second change on the same day replaces today's row
    (an edit of the day's own value, never of a past one)."""
    await db.execute(text(
        "INSERT INTO reward_setting (point_value, max_redeem_pct, effective_from, created_by, updated_by) "
        "VALUES (:v, :m, :d, CAST(:u AS uuid), CAST(:u AS uuid)) "
        "ON CONFLICT (effective_from) DO NOTHING"),
        {"v": body.point_value, "m": body.max_redeem_pct, "d": today_ist(), "u": caller.user_id})
    current = await get_settings(db)
    if (Decimal(current.point_value), Decimal(current.max_redeem_pct)) != (body.point_value, body.max_redeem_pct):
        raise ConflictError("The settings were already changed today; change them again tomorrow.",
                            code="settings_changed_today")
    sid: Any = (await db.execute(text("SELECT id FROM reward_setting WHERE effective_from = :d"),
                            {"d": today_ist()})).scalar_one()
    await _event(db, caller, "reward_setting", str(sid), "rewards.settings_changed",
                 point_value=current.point_value, max_redeem_pct=current.max_redeem_pct)
    return current


def _gift(r: Any) -> sch.Gift:
    return sch.Gift(id=str(r.id), name=r.name, description=r.description, points_cost=r.points_cost,
                    is_active=r.is_active)


async def list_gifts(db: AsyncSession, active: bool | None) -> list[sch.Gift]:
    where = "" if active is None else " WHERE is_active = :a"
    rows = (await db.execute(text("SELECT * FROM gift" + where + " ORDER BY points_cost, name"),
                             {"a": active})).all()
    return [_gift(r) for r in rows]


async def create_gift(db: AsyncSession, caller: Caller, body: sch.GiftCreate) -> sch.Gift:
    r = (await db.execute(text(
        "INSERT INTO gift (name, description, points_cost, created_by, updated_by) "
        "VALUES (:n, :d, :p, CAST(:u AS uuid), CAST(:u AS uuid)) RETURNING *"),
        {"n": body.name.strip(), "d": body.description, "p": body.points_cost, "u": caller.user_id})).one()
    await _event(db, caller, "gift", str(r.id), "rewards.gift_created", points_cost=body.points_cost)
    return _gift(r)


async def patch_gift(db: AsyncSession, caller: Caller, gift_id: str, body: sch.GiftPatch) -> sch.Gift:
    sent = body.model_dump(exclude_unset=True)
    if not sent:
        r = (await db.execute(text("SELECT * FROM gift WHERE id = CAST(:i AS uuid)"), {"i": gift_id})).one_or_none()
    else:
        sets = ", ".join(f"{k} = :{k}" for k in sent)
        r = (await db.execute(text(
            f"UPDATE gift SET {sets}, updated_by = CAST(:u AS uuid) WHERE id = CAST(:i AS uuid) RETURNING *"),
            {**sent, "u": caller.user_id, "i": gift_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such gift.")
    if sent:
        await _event(db, caller, "gift", gift_id, "rewards.gift_updated", fields=sorted(sent))
    return _gift(r)


# ── balances and the ledger, under the caller's policies ─────────────────────

async def _holder(db: AsyncSession, caller: Caller, partner_id: str | None,
                  user_id: str | None) -> sch.Holder:
    if caller.partner_id:
        partner_id, user_id = caller.partner_id, None
    elif user_id == "me" or (not partner_id and not user_id):
        user_id = caller.user_id
    if partner_id and user_id:
        raise ValidationFailed(fields={"partner_id": "Send a partner or a user, not both."})
    if partner_id:
        name = (await db.execute(text("SELECT name FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                                 {"p": partner_id})).scalar_one_or_none()
        if name is None:
            raise NotFoundError("No such partner.")
        return sch.Holder(type="partner", id=partner_id, name=name)
    assert user_id is not None
    name = (await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = CAST(:u AS uuid)"), {"u": user_id})).scalar_one_or_none()
    if name is None and user_id != caller.user_id:
        raise NotFoundError("No such user.")
    return sch.Holder(type="user", id=user_id, name=name)


_WHERE_HOLDER = ("holder_type = :ht AND CASE :ht WHEN 'partner' THEN partner_id ELSE user_id END "
                 "= CAST(:h AS uuid)")


async def balance(db: AsyncSession, caller: Caller, partner_id: str | None,
                  user_id: str | None) -> sch.Balance:
    h = await _holder(db, caller, partner_id, user_id)
    total: Any = (await db.execute(text(f"SELECT coalesce(sum(points), 0) FROM reward_ledger WHERE {_WHERE_HOLDER}"),
                              {"ht": h.type, "h": h.id})).scalar_one()
    settings = await get_settings(db)
    return sch.Balance(holder=h, balance=int(total), point_value=settings.point_value)


async def ledger(db: AsyncSession, caller: Caller, partner_id: str | None, user_id: str | None,
                 cursor: str | None, limit: int) -> sch.LedgerPage:
    h = await _holder(db, caller, partner_id, user_id)
    limit = max(1, min(limit, _LIMIT))
    params: dict[str, Any] = {"ht": h.type, "h": h.id, "lim": limit + 1}
    where = _WHERE_HOLDER
    if cursor:
        at, lid = _decode_cursor(cursor)
        where += " AND (created_at, id) < (:at, CAST(:lid AS uuid))"
        params.update(at=at, lid=lid)
    rows = (await db.execute(text(
        f"SELECT * FROM reward_ledger WHERE {where} ORDER BY created_at DESC, id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    return sch.LedgerPage(data=[sch.LedgerRow(
        id=str(r.id), points=r.points, kind=r.kind, reason=r.reason, at=r.created_at.isoformat(),
        expires_at=r.expires_at.isoformat() if r.expires_at else None) for r in rows],
        meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def adjust(db: AsyncSession, body: sch.Adjustment) -> sch.LedgerRow:
    if bool(body.partner_id) == bool(body.user_id):
        raise ValidationFailed(fields={"partner_id": "Send a partner or a user."})
    if body.points == 0:
        raise ValidationFailed(fields={"points": "Not zero."})
    ht = "partner" if body.partner_id else "user"
    rid = await _call(db, "SELECT reward_adjust(:ht, CAST(:h AS uuid), :p, :r)",
                      {"ht": ht, "h": body.partner_id or body.user_id, "p": body.points, "r": body.reason})
    r = (await db.execute(text("SELECT * FROM reward_ledger WHERE id = CAST(:i AS uuid)"), {"i": str(rid)})).one()
    return sch.LedgerRow(id=str(r.id), points=r.points, kind=r.kind, reason=r.reason,
                         at=r.created_at.isoformat(), expires_at=None)


# ── redemptions ──────────────────────────────────────────────────────────────

_RED_SELECT = """
SELECT x.*, g.name AS gift_name, g.description AS gift_description, g.points_cost AS gift_cost,
       g.is_active AS gift_active, o.order_no::text AS order_no,
       coalesce(c.name, u.full_name) AS holder_name
  FROM reward_redemption x
  LEFT JOIN gift g ON g.id = x.gift_id
  LEFT JOIN sales_order o ON o.id = x.sales_order_id
  LEFT JOIN channel_partner c ON c.id = x.partner_id
  LEFT JOIN app_user u ON u.id = x.user_id"""


def _redemption(r: Any) -> sch.Redemption:
    gift = (sch.Gift(id=str(r.gift_id), name=r.gift_name, description=r.gift_description,
                     points_cost=r.gift_cost, is_active=r.gift_active) if r.gift_id else None)
    return sch.Redemption(
        id=str(r.id), kind=r.kind,
        holder=sch.Holder(type=r.holder_type, id=str(r.partner_id or r.user_id), name=r.holder_name),
        points=r.points, amount=_money(r.amount) if r.amount is not None else None, status=r.status,
        gift=gift,
        sales_order={"id": str(r.sales_order_id), "order_no": r.order_no} if r.sales_order_id else None,
        remark=r.remark, decided_at=r.decided_at.isoformat() if r.decided_at else None,
        created_at=r.created_at.isoformat())


async def get_redemption(db: AsyncSession, rid: str) -> sch.Redemption:
    r = (await db.execute(text(_RED_SELECT + " WHERE x.id = CAST(:i AS uuid)"), {"i": rid})).one_or_none()
    if r is None:
        raise NotFoundError("No such request.")
    return _redemption(r)


async def redeem_on_order(db: AsyncSession, caller: Caller, order_id: str, points: int) -> sch.Redemption:
    if not caller.partner_id:
        raise ForbiddenError("Points are spent on an order by the dealer's own user.",
                             code="not_your_points")
    rid = await _call(db, "SELECT reward_spend('order', 'partner', CAST(:h AS uuid), :p, CAST(:o AS uuid), NULL)",
                      {"h": caller.partner_id, "p": points, "o": order_id})
    return await get_redemption(db, str(rid))


async def remove_from_order(db: AsyncSession, caller: Caller, order_id: str) -> None:
    rid = (await db.execute(text(
        "SELECT id FROM reward_redemption WHERE sales_order_id = CAST(:o AS uuid) AND kind = 'order' "
        "AND status = 'pending'"), {"o": order_id})).scalar_one_or_none()
    if rid is None:
        raise NotFoundError("No points on this draft.")
    await _call(db, "SELECT reward_redemption_close(CAST(:i AS uuid), 'released', NULL)", {"i": str(rid)})


async def request_gift(db: AsyncSession, caller: Caller, gift_id: str) -> sch.Redemption:
    ht, holder = ("partner", caller.partner_id) if caller.partner_id else ("user", caller.user_id)
    rid = await _call(db, "SELECT reward_spend('gift', :ht, CAST(:h AS uuid), 1, NULL, CAST(:g AS uuid))",
                      {"ht": ht, "h": holder, "g": gift_id})
    return await get_redemption(db, str(rid))


async def decide(db: AsyncSession, rid: str, to: str, remark: str | None) -> sch.Redemption:
    await get_redemption(db, rid)
    await _call(db, "SELECT reward_redemption_close(CAST(:i AS uuid), :t, :r)", {"i": rid, "t": to, "r": remark})
    return await get_redemption(db, rid)


async def list_redemptions(db: AsyncSession, *, status: str | None, kind: str | None,
                           cursor: str | None, limit: int) -> sch.RedemptionPage:
    limit = max(1, min(limit, _LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if status:
        where.append("x.status = :st")
        params["st"] = status
    if kind:
        where.append("x.kind = :k")
        params["k"] = kind
    if cursor:
        at, xid = _decode_cursor(cursor)
        where.append("(x.created_at, x.id) < (:at, CAST(:xid AS uuid))")
        params.update(at=at, xid=xid)
    rows = (await db.execute(text(_RED_SELECT + " WHERE " + " AND ".join(where)
                                  + " ORDER BY x.created_at DESC, x.id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    return sch.RedemptionPage(data=[_redemption(r) for r in rows],
                              meta=PageMeta(limit=limit, next_cursor=next_cursor))
