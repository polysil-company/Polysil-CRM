"""Field tracking (FS-021, ADR-044): duty, location batches, visits, the team map,
routes, consent, the policy and the view log.

Every by-id read of a person's own row filters on `user_id = caller` here as well
as in RLS: a manager may read a subordinate's session by id, and "return the open
one" must never return someone else's (review B-6). Services never commit.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import base64
import binascii
import datetime as dt
import hashlib
import json
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import complaints as uploads
from api.domain import tracking as domain
from api.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailed,
)
from api.schemas import tracking as sch
from api.schemas.complaints import AttachmentLink
from api.schemas.leads import PageMeta, UserRef
from api.services.leads import _decode_cursor, _encode_cursor
from api.storage import Storage

log = structlog.get_logger()

MAX_BATCH_POINTS = 500
MAX_PHOTOS = 3
PHOTO_WINDOW = dt.timedelta(hours=24)
SKEW_LIMIT = dt.timedelta(hours=24)

_SUBTREE = "(SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))"


def _sqlstate(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")


def _coord(v: float) -> Decimal:
    return Decimal(str(round(v, 6)))


def _num(v: float | None, places: int = 1) -> Decimal | None:
    return None if v is None else Decimal(str(round(v, places)))


def _iso(v: dt.datetime | None) -> str | None:
    return None if v is None else v.isoformat()


async def _emit(db: AsyncSession, caller: Caller, entity_type: str, entity_id: str, kind: str,
                payload: dict[str, Any], lead_id: str | None = None) -> None:
    """Rule 7. No payload here carries a position (review B-5, EC-9)."""
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES (:t, CAST(:e AS uuid), CAST(:l AS uuid), :k, CAST(:a AS uuid), CAST(:p AS jsonb))"),
        {"t": entity_type, "e": entity_id, "l": lead_id, "k": kind, "a": caller.user_id,
         "p": json.dumps(payload)})


# ── policy and consent ──────────────────────────────────────────────────────

async def _policy(db: AsyncSession) -> Any:
    row = (await db.execute(text(
        "SELECT * FROM tracking_policy WHERE effective_from <= now() "
        "ORDER BY effective_from DESC LIMIT 1"))).one_or_none()
    if row is None:
        raise ServiceUnavailableError("Tracking is not configured.", code="tracking_not_configured")
    return row


def _hours(p: Any) -> domain.Hours:
    return domain.Hours(p.work_start, p.work_end, frozenset(int(d) for d in p.work_days))


def _working_hours(p: Any) -> sch.WorkingHours:
    return sch.WorkingHours(start=p.work_start.strftime("%H:%M"), end=p.work_end.strftime("%H:%M"),
                            days=sorted(int(d) for d in p.work_days))


def _policy_out(p: Any) -> sch.Policy:
    return sch.Policy(effective_from=p.effective_from.isoformat(), interval_seconds=p.interval_seconds,
                      distance_filter_m=p.distance_filter_m, working_hours=_working_hours(p),
                      retention_days=p.retention_days, visit_photo_required=p.visit_photo_required,
                      consent_version=p.consent_version, consent_text=p.consent_text)


async def _accepted_version(db: AsyncSession, user_id: str) -> str | None:
    """The newest consent row decides: accepted gives its version, withdrawn gives none."""
    row = (await db.execute(text(
        "SELECT version, accepted FROM tracking_consent WHERE user_id = CAST(:u AS uuid) "
        "ORDER BY at DESC, id DESC LIMIT 1"), {"u": user_id})).one_or_none()
    return row.version if row is not None and row.accepted else None


async def _may_track(db: AsyncSession) -> bool:
    return bool((await db.execute(text("SELECT app_has_permission('tracking', 'create')"))).scalar_one())


async def _open_duty(db: AsyncSession, user_id: str, *, lock: bool = False) -> Any:
    return (await db.execute(text(
        "SELECT * FROM duty_session WHERE user_id = CAST(:u AS uuid) AND ended_at IS NULL"
        + (" FOR UPDATE" if lock else "")), {"u": user_id})).one_or_none()


def _duty_out(d: Any) -> sch.Duty:
    return sch.Duty(id=str(d.id), started_at=d.started_at.isoformat(), ended_at=_iso(d.ended_at),
                    end_reason=d.end_reason, outside_hours=d.outside_hours)


async def config(db: AsyncSession, caller: Caller) -> sch.TrackingConfig:
    if caller.partner_id is not None:
        raise ForbiddenError("Dealers do not track.")
    p = await _policy(db)
    duty = await _open_duty(db, caller.user_id)
    return sch.TrackingConfig(
        tracking_allowed=await _may_track(db),
        consent=sch.ConsentState(required_version=p.consent_version,
                                 accepted_version=await _accepted_version(db, caller.user_id),
                                 text=p.consent_text),
        interval_seconds=p.interval_seconds, distance_filter_m=p.distance_filter_m,
        working_hours=_working_hours(p), max_batch_points=MAX_BATCH_POINTS,
        visit_photo_required=p.visit_photo_required,
        on_duty=None if duty is None else sch.OnDuty(id=str(duty.id), started_at=duty.started_at.isoformat()))


async def _end_duty(db: AsyncSession, caller: Caller, duty: Any, at: dt.datetime, reason: str,
                    pos: tuple[float | None, float | None, float | None] = (None, None, None)) -> Any:
    lat, lng, acc = pos
    row = (await db.execute(text(
        "UPDATE duty_session SET ended_at = GREATEST(started_at, :at), end_reason = CAST(:r AS duty_end_reason), "
        "end_lat = :lat, end_lng = :lng, end_accuracy_m = :acc "
        "WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid) AND ended_at IS NULL RETURNING *"),
        {"at": at, "r": reason, "lat": None if lat is None else _coord(lat),
         "lng": None if lng is None else _coord(lng), "acc": _num(acc), "id": str(duty.id),
         "u": caller.user_id})).one()
    await _emit(db, caller, "duty_session", str(row.id), "duty.ended",
                {"end_reason": reason, "user_id": caller.user_id})
    return row


async def consent(db: AsyncSession, caller: Caller, body: sch.ConsentIn) -> sch.Consent:
    p = await _policy(db)
    if body.accepted and body.version != p.consent_version:
        raise ValidationFailed("Accept the current version.", code="consent_version",
                               fields={"version": f"the current version is {p.consent_version}"})
    row = (await db.execute(text(
        "INSERT INTO tracking_consent (user_id, org_unit_id, version, accepted) "
        "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :v, :a) RETURNING id, version, accepted, at"),
        {"u": caller.user_id, "o": caller.org_unit_id, "v": body.version, "a": body.accepted})).one()
    await _emit(db, caller, "tracking_consent", str(row.id),
                "tracking.consent_given" if body.accepted else "tracking.consent_withdrawn",
                {"version": body.version})
    if not body.accepted:
        duty = await _open_duty(db, caller.user_id, lock=True)
        if duty is not None:
            await _end_duty(db, caller, duty, dt.datetime.now(dt.UTC), "consent_withdrawn")
    return sch.Consent(id=str(row.id), version=row.version, accepted=row.accepted, at=row.at.isoformat())


async def policy(db: AsyncSession, caller: Caller) -> sch.Policy:
    if caller.partner_id is not None:
        raise ForbiddenError("Dealers do not track.")
    return _policy_out(await _policy(db))


async def set_policy(db: AsyncSession, caller: Caller, body: sch.PolicyIn) -> sch.Policy:
    """Masters are effective-dated (CLAUDE.md 4.1 rule 10): a save adds a version."""
    if body.work_end <= body.work_start:
        raise ValidationFailed(fields={"work_end": "must be after work_start"})
    if body.effective_from < dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5):
        raise ValidationFailed(fields={"effective_from": "must not be in the past"})
    try:
        async with db.begin_nested():
            await db.execute(text(
                "INSERT INTO tracking_policy (effective_from, interval_seconds, distance_filter_m, work_start, "
                "work_end, work_days, retention_days, visit_photo_required, consent_version, consent_text, created_by) "
                "VALUES (:ef, :iv, :df, :ws, :we, CAST(:wd AS smallint[]), :rd, :ph, :cv, :ct, CAST(:me AS uuid))"),
                {"ef": body.effective_from, "iv": body.interval_seconds, "df": body.distance_filter_m,
                 "ws": body.work_start, "we": body.work_end, "wd": sorted(set(body.work_days)),
                 "rd": body.retention_days, "ph": body.visit_photo_required, "cv": body.consent_version,
                 "ct": body.consent_text, "me": caller.user_id})
    except DBAPIError as exc:
        if _sqlstate(exc) == "23505":
            raise ConflictError("A version already starts then.", code="policy_exists",
                                fields={"effective_from": "taken"}) from exc
        raise
    row = (await db.execute(text("SELECT * FROM tracking_policy WHERE effective_from = :ef"),
                            {"ef": body.effective_from})).one()
    return _policy_out(row)


# ── duty ────────────────────────────────────────────────────────────────────

async def duty_start(db: AsyncSession, caller: Caller, body: sch.DutyStart) -> tuple[sch.Duty, bool]:
    """Returns the session and whether it is new. An open session is returned as it
    is, whatever id was sent (a reinstall adopts it, review EC-14)."""
    open_ = await _open_duty(db, caller.user_id)
    if open_ is not None:
        return _duty_out(open_), False
    mine = (await db.execute(text(
        "SELECT * FROM duty_session WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid)"),
        {"id": body.id, "u": caller.user_id})).one_or_none()
    if mine is not None:           # a retry after the session already ended
        return _duty_out(mine), False
    p = await _policy(db)
    if await _accepted_version(db, caller.user_id) != p.consent_version:
        raise ConflictError("Accept the tracking consent first.", code="consent_required")
    at = domain.corrected_at(body.at, body.sent_at, dt.datetime.now(dt.UTC))
    outside = domain.outside_hours(at, _hours(p))
    try:
        async with db.begin_nested():
            row = (await db.execute(text(
                "INSERT INTO duty_session (id, user_id, org_unit_id, device_id, started_at, start_lat, start_lng, "
                "start_accuracy_m, outside_hours) VALUES (CAST(:id AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), "
                ":dev, :at, :lat, :lng, :acc, :out) RETURNING *"),
                {"id": body.id, "u": caller.user_id, "o": caller.org_unit_id, "dev": body.device_id,
                 "at": at, "lat": _coord(body.lat), "lng": _coord(body.lng), "acc": _num(body.accuracy_m),
                 "out": outside})).one()
    except DBAPIError as exc:
        if _sqlstate(exc) != "23505":
            raise
        open_ = await _open_duty(db, caller.user_id)
        if open_ is not None:      # a concurrent start won
            return _duty_out(open_), False
        raise ConflictError("That id is in use.", code="id_in_use", fields={"id": "in use"}) from exc
    await _emit(db, caller, "duty_session", str(row.id), "duty.started", {"outside_hours": outside})
    return _duty_out(row), True


async def duty_end(db: AsyncSession, caller: Caller, body: sch.DutyEnd) -> sch.Duty:
    d = (await db.execute(text(
        "SELECT * FROM duty_session WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid) FOR UPDATE"),
        {"id": body.id, "u": caller.user_id})).one_or_none()
    if d is None:
        raise NotFoundError("No such duty session.", code="duty_not_found")
    if d.ended_at is not None:
        return _duty_out(d)
    at = domain.corrected_at(body.at, body.sent_at, dt.datetime.now(dt.UTC))
    return _duty_out(await _end_duty(db, caller, d, at, "user", (body.lat, body.lng, body.accuracy_m)))


# ── location batches ────────────────────────────────────────────────────────

async def batch(db: AsyncSession, caller: Caller, body: sch.BatchIn,
                now: dt.datetime | None = None) -> sch.BatchResult:
    now = now or dt.datetime.now(dt.UTC)
    if len(body.points) > MAX_BATCH_POINTS:
        raise ValidationFailed(f"Up to {MAX_BATCH_POINTS} points per batch.", code="batch_too_large",
                               fields={"points": f"over {MAX_BATCH_POINTS}"})
    skew = now - body.sent_at
    if abs(skew) > SKEW_LIMIT:
        raise ValidationFailed("The phone's clock is more than a day off.", code="bad_clock",
                               fields={"sent_at": "more than a day from the server's clock"})
    shift = skew if abs(skew) > domain.FUTURE_SKEW else dt.timedelta(0)
    duty_ids = sorted({pt.duty_id for pt in body.points})
    duties = {str(r.id): r for r in (await db.execute(text(
        "SELECT id, started_at, ended_at, end_reason::text AS end_reason, org_unit_id FROM duty_session "
        "WHERE user_id = CAST(:u AS uuid) AND id = ANY(CAST(:ids AS uuid[]))"),
        {"u": caller.user_id, "ids": duty_ids})).all()}
    newest = max(body.points, key=lambda pt: pt.recorded_at)
    newest_duty = duties.get(newest.duty_id)

    def duty_state() -> sch.BatchDuty | None:
        d = newest_duty
        return None if d is None else sch.BatchDuty(id=str(d.id), ended_at=_iso(d.ended_at),
                                                     end_reason=d.end_reason)

    rejected: list[sch.Rejected] = []
    if await _accepted_version(db, caller.user_id) is None:
        # consent withdrawn: a 200 that names every point, so the phone's queue drains (EC-2)
        return sch.BatchResult(accepted=0, duplicates=0, duty=duty_state(),
                               rejected=[sch.Rejected(id=pt.id, reason="consent_withdrawn") for pt in body.points])
    known = {str(r[0]) for r in (await db.execute(text(
        "SELECT id FROM location_point WHERE user_id = CAST(:u AS uuid) AND id = ANY(CAST(:ids AS uuid[]))"),
        {"u": caller.user_id, "ids": sorted({pt.id for pt in body.points})})).all()}
    retention = dt.timedelta(days=(await _policy(db)).retention_days)
    duplicates = 0
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for pt in body.points:
        if pt.id in known or pt.id in seen:
            duplicates += 1
            continue
        seen.add(pt.id)
        d = duties.get(pt.duty_id)
        if d is None:
            rejected.append(sch.Rejected(id=pt.id, reason="unknown_duty"))
            continue
        at = pt.recorded_at + shift
        window_end = d.started_at + domain.AUTO_END_MAX if d.end_reason == "auto" else d.ended_at
        problem = domain.point_problem(recorded_at=at, lat=pt.lat, lng=pt.lng, now=now,
                                       retention=retention, duty=[(d.started_at, window_end)])
        if problem is not None:
            rejected.append(sch.Rejected(id=pt.id, reason=problem))   # type: ignore[arg-type]
            continue
        rows.append({"id": pt.id, "u": caller.user_id, "o": str(d.org_unit_id) if d.org_unit_id else None,
                     "duty": pt.duty_id, "dev": body.device_id, "at": at, "skew": int(shift.total_seconds()),
                     "lat": _coord(pt.lat), "lng": _coord(pt.lng), "acc": _num(pt.accuracy_m),
                     "spd": _num(pt.speed_mps, 2), "hd": _num(pt.heading), "alt": _num(pt.altitude_m),
                     "bat": pt.battery_pct, "mock": pt.is_mock})
    insert = text(
        "INSERT INTO location_point (id, user_id, org_unit_id, duty_id, device_id, recorded_at, clock_skew_s, "
        "lat, lng, accuracy_m, speed_mps, heading, altitude_m, battery_pct, is_mock) VALUES (CAST(:id AS uuid), "
        "CAST(:u AS uuid), CAST(:o AS uuid), CAST(:duty AS uuid), :dev, :at, :skew, :lat, :lng, :acc, :spd, :hd, "
        ":alt, :bat, :mock)")
    stored = rows
    if rows:
        try:
            async with db.begin_nested():
                await db.execute(insert, rows)
        except DBAPIError as exc:
            if _sqlstate(exc) != "23505":
                raise
            # an id another user holds, or a concurrent copy of this batch: one by one
            stored = []
            for r in rows:
                try:
                    async with db.begin_nested():
                        await db.execute(insert, r)
                    stored.append(r)
                except DBAPIError as one:
                    if _sqlstate(one) != "23505":
                        raise
                    mine = (await db.execute(text(
                        "SELECT 1 FROM location_point WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid)"),
                        {"id": r["id"], "u": caller.user_id})).first()
                    if mine is not None:
                        duplicates += 1
                    else:
                        rejected.append(sch.Rejected(id=r["id"], reason="id_in_use"))
    if stored:
        for duty_id in sorted({r["duty"] for r in stored}):
            last = max(r["at"] for r in stored if r["duty"] == duty_id)
            await db.execute(text(
                "UPDATE duty_session SET last_point_at = GREATEST(COALESCE(last_point_at, :at), :at), "
                "ended_at = CASE WHEN end_reason = 'auto' THEN GREATEST(ended_at, :at) ELSE ended_at END "
                "WHERE id = CAST(:d AS uuid) AND user_id = CAST(:u AS uuid)"),
                {"at": last, "d": duty_id, "u": caller.user_id})
        top = max(stored, key=lambda r: r["at"])
        # forward only: an older batch arriving late never moves the marker back (EC-15)
        await db.execute(text(
            "INSERT INTO tracking_latest (user_id, org_unit_id, duty_id, recorded_at, lat, lng, accuracy_m, "
            "battery_pct, is_mock) VALUES (CAST(:u AS uuid), CAST(:o AS uuid), CAST(:duty AS uuid), :at, :lat, :lng, "
            ":acc, :bat, :mock) ON CONFLICT (user_id) DO UPDATE SET org_unit_id = excluded.org_unit_id, "
            "duty_id = excluded.duty_id, recorded_at = excluded.recorded_at, lat = excluded.lat, lng = excluded.lng, "
            "accuracy_m = excluded.accuracy_m, battery_pct = excluded.battery_pct, is_mock = excluded.is_mock "
            "WHERE excluded.recorded_at > tracking_latest.recorded_at"), top)
    return sch.BatchResult(accepted=len(stored), duplicates=duplicates, rejected=rejected, duty=duty_state())


# ── visits ──────────────────────────────────────────────────────────────────

_VISIT_SELECT = """SELECT v.*, u.full_name AS user_name, l.inquiry_no::text AS lead_label, cp.name AS partner_name,
       (SELECT count(*) FROM visit_photo ph WHERE ph.visit_id = v.id) AS photo_count
  FROM visit v
  LEFT JOIN app_user u ON u.id = v.user_id
  LEFT JOIN lead l ON l.id = v.lead_id
  LEFT JOIN channel_partner cp ON cp.id = v.partner_id"""


def _pos(lat: Any, lng: Any, acc: Any) -> sch.Position | None:
    if lat is None or lng is None:
        return None
    return sch.Position(lat=float(lat), lng=float(lng), accuracy_m=None if acc is None else float(acc))


def _visit_out(r: Any) -> sch.Visit:
    duration = None
    if r.checkout_at is not None:
        duration = int((r.checkout_at - r.checkin_at).total_seconds() // 60)
    checkin = _pos(r.checkin_lat, r.checkin_lng, r.checkin_accuracy_m)
    assert checkin is not None
    return sch.Visit(
        id=str(r.id), user=UserRef(id=str(r.user_id), full_name=r.user_name or ""),
        lead=None if r.lead_id is None else sch.DocRef(id=str(r.lead_id), label=r.lead_label or ""),
        partner=None if r.partner_id is None else sch.DocRef(id=str(r.partner_id), label=r.partner_name or ""),
        task_id=None if r.task_id is None else str(r.task_id), place_name=r.place_name,
        checkin_at=r.checkin_at.isoformat(), checkin=checkin, checkout_at=_iso(r.checkout_at),
        checkout=_pos(r.checkout_lat, r.checkout_lng, r.checkout_accuracy_m), duration_minutes=duration,
        outcome=r.outcome, note=r.note, auto_closed=r.auto_closed, photo_count=int(r.photo_count))


async def _visit(db: AsyncSession, visit_id: str) -> sch.Visit:
    r = (await db.execute(text(_VISIT_SELECT + " WHERE v.id = CAST(:id AS uuid)"), {"id": visit_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such visit.")
    return _visit_out(r)


async def _own_visit(db: AsyncSession, caller: Caller, visit_id: str, *, lock: bool = False) -> Any:
    r = (await db.execute(text(
        "SELECT * FROM visit WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid)"
        + (" FOR UPDATE" if lock else "")), {"id": visit_id, "u": caller.user_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such visit.")
    return r


async def check_in(db: AsyncSession, caller: Caller, body: sch.VisitIn) -> tuple[sch.Visit, bool]:
    if body.lead_id and body.partner_id:
        raise ValidationFailed(fields={"partner_id": "give a lead or a dealer, not both"})
    if not (body.lead_id or body.partner_id or body.place_name):
        raise ValidationFailed(fields={"place_name": "required without a lead or a dealer"})
    mine = (await db.execute(text(
        "SELECT id FROM visit WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid)"),
        {"id": body.id, "u": caller.user_id})).first()
    if mine is not None:
        return await _visit(db, body.id), False
    if await _accepted_version(db, caller.user_id) is None:
        raise ConflictError("Accept the tracking consent first.", code="consent_required")
    if body.lead_id and (await db.execute(text("SELECT 1 FROM lead WHERE id = CAST(:i AS uuid)"),
                                          {"i": body.lead_id})).first() is None:
        raise NotFoundError("No such lead.", code="not_found")
    if body.partner_id and (await db.execute(text(
            "SELECT 1 WHERE EXISTS (SELECT 1 FROM channel_partner WHERE id = CAST(:i AS uuid)) "
            "OR partner_on_visible_document(CAST(:i AS uuid))"), {"i": body.partner_id})).first() is None:
        raise NotFoundError("No such dealer.", code="not_found")
    if body.task_id:
        assignee = (await db.execute(text("SELECT assigned_to FROM task WHERE id = CAST(:i AS uuid)"),
                                     {"i": body.task_id})).scalar_one_or_none()
        if assignee is None or str(assignee) != caller.user_id:
            raise NotFoundError("No such task of yours.", code="not_found")
    open_ = (await db.execute(text(
        "SELECT id FROM visit WHERE user_id = CAST(:u AS uuid) AND checkout_at IS NULL"),
        {"u": caller.user_id})).scalar_one_or_none()
    if open_ is not None:
        raise ConflictError("Check out of your open visit first.", code="visit_open",
                            fields={"visit_id": str(open_)})
    duty = await _open_duty(db, caller.user_id)
    office = str(duty.org_unit_id) if duty is not None and duty.org_unit_id else caller.org_unit_id
    try:
        async with db.begin_nested():
            await db.execute(text(
                "INSERT INTO visit (id, user_id, org_unit_id, duty_id, lead_id, partner_id, task_id, place_name, "
                "checkin_at, checkin_lat, checkin_lng, checkin_accuracy_m) VALUES (CAST(:id AS uuid), "
                "CAST(:u AS uuid), CAST(:o AS uuid), CAST(:d AS uuid), CAST(:l AS uuid), CAST(:p AS uuid), "
                "CAST(:t AS uuid), :pl, :at, :lat, :lng, :acc)"),
                {"id": body.id, "u": caller.user_id, "o": office, "d": None if duty is None else str(duty.id),
                 "l": body.lead_id, "p": body.partner_id, "t": body.task_id, "pl": body.place_name,
                 "at": domain.corrected_at(body.at, body.sent_at, dt.datetime.now(dt.UTC)), "lat": _coord(body.lat), "lng": _coord(body.lng), "acc": _num(body.accuracy_m)})
    except DBAPIError as exc:
        if _sqlstate(exc) != "23505":
            raise
        open_ = (await db.execute(text(
            "SELECT id FROM visit WHERE user_id = CAST(:u AS uuid) AND checkout_at IS NULL"),
            {"u": caller.user_id})).scalar_one_or_none()
        if open_ is not None:
            raise ConflictError("Check out of your open visit first.", code="visit_open",
                                fields={"visit_id": str(open_)}) from exc
        raise ConflictError("That id is in use.", code="id_in_use", fields={"id": "in use"}) from exc
    await _emit(db, caller, "visit", body.id, "visit.checked_in",
                {"place_name": body.place_name, "partner_id": body.partner_id, "task_id": body.task_id},
                lead_id=body.lead_id)
    return await _visit(db, body.id), True


async def check_out(db: AsyncSession, caller: Caller, visit_id: str, body: sch.CheckOut) -> sch.Visit:
    v = await _own_visit(db, caller, visit_id, lock=True)
    if v.checkout_at is not None:
        raise ConflictError("This visit is closed.", code="visit_closed")
    at = domain.corrected_at(body.at, body.sent_at, dt.datetime.now(dt.UTC))
    if at < v.checkin_at:
        raise ValidationFailed(fields={"at": "before the check-in"})
    p = await _policy(db)
    if p.visit_photo_required and not (await db.execute(text(
            "SELECT 1 FROM visit_photo WHERE visit_id = CAST(:v AS uuid)"), {"v": visit_id})).first():
        raise ConflictError("Add a photo before checking out.", code="photo_required")
    await db.execute(text(
        "UPDATE visit SET checkout_at = :at, checkout_lat = :lat, checkout_lng = :lng, checkout_accuracy_m = :acc, "
        "outcome = CAST(:oc AS visit_outcome), note = :note WHERE id = CAST(:id AS uuid) AND user_id = CAST(:u AS uuid)"),
        {"at": at, "lat": _coord(body.lat), "lng": _coord(body.lng), "acc": _num(body.accuracy_m),
         "oc": body.outcome, "note": body.note, "id": visit_id, "u": caller.user_id})
    await _emit(db, caller, "visit", visit_id, "visit.checked_out", {"outcome": body.outcome},
                lead_id=None if v.lead_id is None else str(v.lead_id))
    return await _visit(db, visit_id)


async def add_photo(db: AsyncSession, caller: Caller, visit_id: str, *, filename: str | None, data: bytes,
                    storage: Storage, now: dt.datetime | None = None) -> tuple[sch.VisitPhoto, bool]:
    """ADR-041's path. Refused before storage when it cannot land (code review F-2 of FS-015)."""
    now = now or dt.datetime.now(dt.UTC)
    if not data:
        raise ValidationFailed(fields={"file": "empty"})
    if len(data) > uploads.MAX_UPLOAD_BYTES:
        raise ValidationFailed("Up to 10 MB.", code="attachment_too_large", fields={"file": "over 10 MB"})
    sniffed = uploads.sniff(data[:16])
    if sniffed is None or sniffed.content_type == "application/pdf":
        raise ValidationFailed("JPEG, PNG, WebP or HEIC only.", code="attachment_type",
                               fields={"file": "not an allowed type"})
    digest = hashlib.sha256(data).hexdigest()
    v = await _own_visit(db, caller, visit_id)
    existing = (await db.execute(text(
        "SELECT * FROM visit_photo WHERE visit_id = CAST(:v AS uuid) AND sha256 = :h"),
        {"v": visit_id, "h": digest})).one_or_none()
    if existing is not None:
        return _photo_out(existing), False
    if now - v.checkin_at > PHOTO_WINDOW:
        raise ConflictError("Photos are taken up to a day after check-in.", code="photo_window_closed")
    if (await db.execute(text("SELECT count(*) FROM visit_photo WHERE visit_id = CAST(:v AS uuid)"),
                         {"v": visit_id})).scalar_one() >= MAX_PHOTOS:
        raise ConflictError(f"Up to {MAX_PHOTOS} photos.", code="photo_limit")
    key = f"visits/{visit_id}/{digest[:32]}.{sniffed.extension}"
    try:
        await asyncio.to_thread(storage.put, key, data, sniffed.content_type)
    except Exception as exc:  # the unconfigured adapter's RuntimeError and every network error
        log.warning("visit.storage_unavailable", error=type(exc).__name__)
        raise ServiceUnavailableError("Files cannot be stored right now; try again later.",
                                      code="storage_unavailable") from exc
    await _own_visit(db, caller, visit_id, lock=True)    # two uploads at once count under one lock
    count = (await db.execute(text("SELECT count(*) FROM visit_photo WHERE visit_id = CAST(:v AS uuid)"),
                              {"v": visit_id})).scalar_one()
    if count >= MAX_PHOTOS:
        raise ConflictError(f"Up to {MAX_PHOTOS} photos.", code="photo_limit")
    try:
        async with db.begin_nested():
            row = (await db.execute(text(
                "INSERT INTO visit_photo (visit_id, storage_key, content_type, filename, size_bytes, sha256, "
                "uploaded_by) VALUES (CAST(:v AS uuid), :k, :ct, :fn, :sz, :h, CAST(:me AS uuid)) RETURNING *"),
                {"v": visit_id, "k": key, "ct": sniffed.content_type, "fn": (filename or "")[:255] or None,
                 "sz": len(data), "h": digest, "me": caller.user_id})).one()
    except DBAPIError as exc:
        if _sqlstate(exc) != "23505":
            raise
        again = (await db.execute(text(
            "SELECT * FROM visit_photo WHERE visit_id = CAST(:v AS uuid) AND sha256 = :h"),
            {"v": visit_id, "h": digest})).one()
        return _photo_out(again), False
    return _photo_out(row), True


def _photo_out(r: Any) -> sch.VisitPhoto:
    return sch.VisitPhoto(id=str(r.id), content_type=r.content_type, size_bytes=r.size_bytes,
                          uploaded_at=r.created_at.isoformat())


async def photo_link(db: AsyncSession, visit_id: str, photo_id: str, storage: Storage) -> AttachmentLink:
    r = (await db.execute(text(
        "SELECT ph.storage_key, ph.content_type FROM visit_photo ph WHERE ph.id = CAST(:p AS uuid) "
        "AND ph.visit_id = CAST(:v AS uuid)"), {"p": photo_id, "v": visit_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such photo.")
    try:
        url, expires = storage.presign_get(
            r.storage_key, filename=f"visit-photo.{r.storage_key.rsplit('.', 1)[-1]}",
            disposition="attachment" if r.content_type == "image/heic" else "inline")
    except RuntimeError as exc:
        raise ServiceUnavailableError("Files cannot be opened right now.", code="storage_unavailable") from exc
    return AttachmentLink(url=url, expires_at=expires.isoformat())


async def _log_view(db: AsyncSession, caller: Caller, what: str, subject: str | None,
                    day: dt.date | None = None) -> None:
    """Rule 11: every look at someone else's whereabouts. One's own is not logged."""
    if subject is not None and subject == caller.user_id:
        return
    await db.execute(text(
        "INSERT INTO tracking_view_log (viewer_id, subject_user_id, what, viewed_date) "
        "VALUES (CAST(:me AS uuid), CAST(:s AS uuid), :w, :d)"),
        {"me": caller.user_id, "s": subject, "w": what, "d": day})


async def get_visit(db: AsyncSession, caller: Caller, visit_id: str) -> sch.Visit:
    v = await _visit(db, visit_id)
    await _log_view(db, caller, "visits", v.user.id)
    return v


async def list_visits(db: AsyncSession, caller: Caller, *, user_id: str | None, day: dt.date | None,
                      lead_id: str | None, limit: int, cursor: str | None) -> sch.VisitPage:
    where: list[str] = ["TRUE"]
    params: dict[str, Any] = {"lim": limit + 1}
    if user_id:
        where.append("v.user_id = CAST(:u AS uuid)")
        params["u"] = caller.user_id if user_id == "me" else user_id
    if day:
        start, end = domain.day_bounds(day)
        where.append("v.checkin_at >= :s AND v.checkin_at < :e")
        params |= {"s": start, "e": end}
    if lead_id:
        where.append("v.lead_id = CAST(:l AS uuid)")
        params["l"] = lead_id
    if cursor:
        at, vid = _decode_cursor(cursor)
        where.append("(v.checkin_at, v.id) < (:cat, CAST(:cid AS uuid))")
        params |= {"cat": at, "cid": vid}
    rows = (await db.execute(text(
        _VISIT_SELECT + " WHERE " + " AND ".join(where) + " ORDER BY v.checkin_at DESC, v.id DESC LIMIT :lim"),
        params)).all()
    page = rows[:limit]
    for subject in sorted({str(r.user_id) for r in page}):
        await _log_view(db, caller, "visits", subject, day)
    next_cursor = _encode_cursor(page[-1].checkin_at, str(page[-1].id)) if len(rows) > limit else None
    return sch.VisitPage(data=[_visit_out(r) for r in page], meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── team map and routes ─────────────────────────────────────────────────────

def _people_in_scope(caller: Caller) -> str:
    """The people the caller may track: holders of tracking.create, active staff,
    narrowed to the caller's tracking scope. The tables' own RLS still decides
    which positions come back."""
    scope = caller.scopes.get("tracking")
    # org: today's office. A person transferred mid-duty leaves the old manager's
    # view: app_user's own policy hides them there (GAP-202)
    reach = {"own": "u.id = (SELECT app_current_user_id())",
             "org_subtree": f"u.org_unit_id IN {_SUBTREE}",
             "global": "TRUE"}.get(scope or "", "FALSE")
    return f"""u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL AND ({reach})
   AND EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = u.role_id AND rp.module = 'tracking'
                AND rp.action = 'create' AND rp.deleted_at IS NULL)"""


async def team_latest(db: AsyncSession, caller: Caller, now: dt.datetime | None = None) -> list[sch.TeamMember]:
    now = now or dt.datetime.now(dt.UTC)
    rows = (await db.execute(text(f"""
SELECT u.id, u.full_name, r.code AS role, d.id AS duty_id, t.recorded_at, t.lat, t.lng, t.accuracy_m,
       t.battery_pct, t.is_mock, v.id AS visit_id, v.checkin_at, l.inquiry_no::text AS lead_label,
       cp.name AS partner_name, v.place_name
  FROM app_user u
  LEFT JOIN role r ON r.id = u.role_id
  LEFT JOIN duty_session d ON d.user_id = u.id AND d.ended_at IS NULL
  LEFT JOIN tracking_latest t ON t.user_id = u.id
  LEFT JOIN visit v ON v.user_id = u.id AND v.checkout_at IS NULL
  LEFT JOIN lead l ON l.id = v.lead_id
  LEFT JOIN channel_partner cp ON cp.id = v.partner_id
 WHERE {_people_in_scope(caller)}
 ORDER BY u.full_name, u.id"""))).all()
    await _log_view(db, caller, "team", None)
    out = []
    for r in rows:
        on_duty = r.duty_id is not None
        show = on_duty and r.recorded_at is not None
        open_visit = None
        if r.visit_id is not None:
            open_visit = sch.OpenVisit(id=str(r.visit_id), label=r.lead_label or r.partner_name or r.place_name or "",
                                       since=r.checkin_at.isoformat())
        out.append(sch.TeamMember(
            user=UserRef(id=str(r.id), full_name=r.full_name), role=r.role, on_duty=on_duty,
            last_seen_at=_iso(r.recorded_at), lat=float(r.lat) if show else None,
            lng=float(r.lng) if show else None,
            accuracy_m=float(r.accuracy_m) if show and r.accuracy_m is not None else None,
            battery_pct=r.battery_pct if show else None, is_mock=bool(r.is_mock) if show else False,
            stale=domain.stale(r.recorded_at, on_duty, now), open_visit=open_visit))
    return out


async def route(db: AsyncSession, caller: Caller, user_id: str, day: dt.date) -> sch.Route:
    subject = (await db.execute(text(
        f"SELECT u.id, u.full_name FROM app_user u WHERE u.id = CAST(:s AS uuid) AND {_people_in_scope(caller)}"),
        {"s": user_id})).one_or_none()
    if subject is None:
        raise NotFoundError("No such person in your team.")
    start, end = domain.day_bounds(day)
    params = {"s": user_id, "a": start, "b": end}
    pts = (await db.execute(text(
        "SELECT recorded_at, lat, lng, accuracy_m, is_mock FROM location_point WHERE user_id = CAST(:s AS uuid) "
        "AND recorded_at >= :a AND recorded_at < :b ORDER BY recorded_at, id"), params)).all()
    duty = (await db.execute(text(
        "SELECT * FROM duty_session WHERE user_id = CAST(:s AS uuid) AND started_at < :b "
        "AND (ended_at IS NULL OR ended_at >= :a) ORDER BY started_at"), params)).all()
    visits = [_visit_out(r) for r in (await db.execute(text(
        _VISIT_SELECT + " WHERE v.user_id = CAST(:s AS uuid) AND v.checkin_at >= :a AND v.checkin_at < :b "
        "ORDER BY v.checkin_at"), params)).all()]
    fixes = [domain.Fix(r.recorded_at, float(r.lat), float(r.lng),
                        None if r.accuracy_m is None else float(r.accuracy_m)) for r in pts]
    mock = {r.recorded_at for r in pts if r.is_mock}
    kept, dropped = domain.route_fixes(fixes)
    stops = []
    for s in domain.stops(kept):
        hit = next((v.id for v in visits
                    if dt.datetime.fromisoformat(v.checkin_at) <= s.end
                    and (v.checkout_at is None or dt.datetime.fromisoformat(v.checkout_at) >= s.start)), None)
        stops.append(sch.Stop.model_validate({"from": s.start.isoformat(), "to": s.end.isoformat(),
                                              "minutes": s.minutes, "lat": round(s.lat, 6),
                                              "lng": round(s.lng, 6), "visit_id": hit}))
    km = Decimal(str(domain.distance_m(kept) / 1000)).quantize(Decimal("0.1"))
    await _log_view(db, caller, "route", user_id, day)
    return sch.Route(
        user=UserRef(id=str(subject.id), full_name=subject.full_name), date=day.isoformat(),
        duty=[_duty_out(d) for d in duty],
        points=[sch.RoutePoint(at=f.at.isoformat(), lat=f.lat, lng=f.lng, accuracy_m=f.accuracy_m,
                               is_mock=f.at in mock) for f in domain.thin(kept)],
        stops=stops, visits=visits, distance_km=str(km), point_count=len(pts), dropped_points=dropped,
        mock_points=sum(1 for r in pts if r.is_mock))


def _decode_log_cursor(cursor: str) -> tuple[dt.datetime, int]:
    """The log's ids are a sequence, not uuids, so leads' decoder does not fit."""
    try:
        ts, _, gid = base64.urlsafe_b64decode(cursor.encode()).decode().partition("|")
        return dt.datetime.fromisoformat(ts), int(gid)
    except (ValueError, binascii.Error) as exc:
        raise ValidationFailed(fields={"cursor": "malformed cursor"}) from exc


async def view_log(db: AsyncSession, *, subject_user_id: str | None, limit: int,
                   cursor: str | None) -> sch.ViewLogPage:
    where: list[str] = ["TRUE"]
    params: dict[str, Any] = {"lim": limit + 1}
    if subject_user_id:
        where.append("g.subject_user_id = CAST(:s AS uuid)")
        params["s"] = subject_user_id
    if cursor:
        at, gid = _decode_log_cursor(cursor)
        where.append("(g.viewed_at, g.id) < (:cat, :cid)")
        params |= {"cat": at, "cid": gid}
    rows = (await db.execute(text(
        "SELECT g.*, vw.full_name AS viewer_name, sj.full_name AS subject_name FROM tracking_view_log g "
        "LEFT JOIN app_user vw ON vw.id = g.viewer_id LEFT JOIN app_user sj ON sj.id = g.subject_user_id "
        "WHERE " + " AND ".join(where) + " ORDER BY g.viewed_at DESC, g.id DESC LIMIT :lim"), params)).all()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        next_cursor = base64.urlsafe_b64encode(f"{page[-1].viewed_at.isoformat()}|{page[-1].id}".encode()).decode()
    return sch.ViewLogPage(
        data=[sch.ViewLogRow(
            viewer=UserRef(id=str(r.viewer_id), full_name=r.viewer_name or ""),
            subject=None if r.subject_user_id is None else UserRef(id=str(r.subject_user_id),
                                                                   full_name=r.subject_name or ""),
            what=r.what, viewed_date=None if r.viewed_date is None else r.viewed_date.isoformat(),
            viewed_at=r.viewed_at.isoformat()) for r in page],
        meta=PageMeta(limit=limit, next_cursor=next_cursor))
