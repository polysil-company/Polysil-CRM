"""Complaints (FS-015): entry, the manager check, the quality check.

Reads run under the caller's RLS. Every transition goes through a definer in
migration 019 (`complaint_submit`, `complaint_check`, `complaint_qc`,
`complaint_cancel`), which locks the row, asks `complaint_refusal()` and writes the
status, the decision row, the event and the message; the service validates the
input and maps the refusals. Drafts are edited here, under the column grants.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import re
import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.domain import complaints as domain
from api.domain.identity import MobileError, normalise_mobile
from api.domain.orders import actor_hidden_from_partner
from api.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailed,
)
from api.schemas import complaints as sch
from api.schemas.leads import PageMeta, TimelineEvent, TimelinePage
from api.schemas.tasks import LeadLink, OrderLink, PartnerLink
from api.services import approval_view, people, pricing
from api.services.clock import today_ist
from api.services.leads import _covering_org_unit, _decode_cursor, _encode_cursor
from api.storage import Storage

log = structlog.get_logger()

_MAX_LIMIT = 100
_UNSAFE = re.compile(r"[\x00-\x1f\x7f]")


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _iso(v: Any) -> str | None:
    return v.isoformat() if v is not None else None


def _qty(value: Any) -> str:
    """340.000 as "340", 12.500 as "12.5": never the exponent normalize() gives."""
    return f"{value.normalize():f}"


def _portal(caller: Caller) -> bool:
    return caller.partner_id is not None


def _sqlstate(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None) or "")


def _message(exc: DBAPIError) -> str:
    text_ = str(exc.orig)
    return text_.split("\n")[0].split(": ", 1)[-1] if ": " in text_ else text_


def _refusal(exc: DBAPIError) -> Exception | None:
    """Migration 019's SQLSTATEs as API errors, or None for anything else."""
    state = _sqlstate(exc)
    if state == "CMPNF":
        return NotFoundError("No such complaint.")
    if state == "CMPSC":
        return ConflictError("The complaint moved on; reload it.", code="status_changed")
    if state == "CMPND":
        return ConflictError("The complaint is no longer a draft.", code="complaint_not_draft")
    if state in ("CMPRF", "42501"):
        return ForbiddenError("This is not yours to do on this complaint.")
    if state == "CMPMS":
        missing = [m for m in _message(exc).split(",") if m]
        return ValidationFailed("Fill these in before submitting.", code="missing_for_submit",
                                fields={m.strip(): "required to submit" for m in missing})
    if state == "CMPZD":
        return ValidationFailed("At least one product needs a defective quantity.",
                                code="nothing_defective", fields={"lines": "nothing defective"})
    if state == "CMPNC":
        return ValidationFailed("Nobody may check this complaint: ask the admin.", code="no_checker")
    if state == "CMPAS":
        return ValidationFailed(fields={"owner_user_id": "not someone you may assign"})
    if state == "CMPBD":
        return ValidationFailed(fields={"decision": _message(exc)})
    if state == "CMPSP":
        return ConflictError("A target already starts that day.", code="target_exists")
    if state == "CMPRV":
        field = _message(exc)
        if field == "lines":
            return ValidationFailed("The replacement lines no longer match the complaint; reload it.",
                                    code="replacement_unpriced", fields={"lines": "changed"})
        return ValidationFailed(fields={field: "not accepted"})
    if state == "ORDNA":
        return ValidationFailed("Nobody holds a role this approval needs: ask the admin.",
                                code="no_approver")
    if state == "ORDST":
        return ValidationFailed("The complaint's territory has no coded state.",
                                code="territory_without_state_code",
                                fields={"territory_id": "no coded state above it"})
    if state == "CMPRW":
        return ValidationFailed("The time to reopen this complaint has passed, or it was "
                                "reopened as often as allowed.", code="reopen_window_closed")
    if state == "CMPRK":
        return ValidationFailed(code="remark_required", fields={"reason": "required"})
    if state == "CMPPD":
        return ValidationFailed("A target cannot start in the past.", code="target_in_the_past",
                                fields={"effective_from": "today or later"})
    return None


async def _definer(db: AsyncSession, sql: str, params: dict[str, Any]) -> Any:
    try:
        async with db.begin_nested():
            return (await db.execute(text(sql), params)).scalar_one_or_none()
    except DBAPIError as exc:
        mapped = _refusal(exc)
        if mapped is not None:
            raise mapped from exc
        raise


# ── reading ──────────────────────────────────────────────────────────────────

_SELECT = """
SELECT c.*, c.status::text AS status_text, c.severity::text AS severity_text,
       ct.code::text AS type_code, ct.name AS type_name,
       t.name AS territory_name, ou.name AS office_name,
       l.id AS l_id, l.inquiry_no::text AS l_no, l.farmer_name AS l_name,
       o.id AS o_id, o.order_no::text AS o_no,
       cp.id AS p_id, cp.name AS p_name, cp.partner_type::text AS p_type,
       ow.full_name AS owner_name, rb.full_name AS raiser_name
  FROM complaint c
  JOIN complaint_type ct ON ct.id = c.complaint_type_id
  LEFT JOIN territory t ON t.id = c.territory_id
  LEFT JOIN org_unit ou ON ou.id = c.owner_org_unit_id
  LEFT JOIN lead l ON l.id = c.lead_id
  LEFT JOIN sales_order o ON o.id = c.sales_order_id
  LEFT JOIN channel_partner cp ON cp.id = c.partner_id
  LEFT JOIN app_user ow ON ow.id = c.owner_user_id
  LEFT JOIN app_user rb ON rb.id = c.raised_by"""


def _lead(r: Any) -> LeadLink | None:
    if r.lead_id is None:
        return None
    if r.l_id is None:
        return LeadLink(id=str(r.lead_id), hidden=True)
    return LeadLink(id=str(r.lead_id), inquiry_no=r.l_no, farmer_name=r.l_name)


def _order(r: Any) -> OrderLink | None:
    if r.sales_order_id is None:
        return None
    if r.o_id is None:
        return OrderLink(id=str(r.sales_order_id), hidden=True)
    return OrderLink(id=str(r.sales_order_id), order_no=r.o_no)


def _partner(r: Any) -> PartnerLink | None:
    if r.partner_id is None:
        return None
    if r.p_id is None:
        return PartnerLink(id=str(r.partner_id), hidden=True)
    return PartnerLink(id=str(r.partner_id), name=r.p_name, partner_type=r.p_type)


def _sla(r: Any, now: dt.datetime) -> sch.Sla | None:
    if r.first_submitted_at is None:
        return None
    return sch.Sla(
        policy="none" if r.response_due_at is None and r.resolution_due_at is None else "set",
        response_due_at=_iso(r.response_due_at), responded_at=_iso(r.responded_at),
        response_breached=domain.breached(r.response_due_at, r.responded_at, now),
        resolution_due_at=_iso(r.resolution_due_at), resolved_at=_iso(r.resolved_at),
        resolution_breached=domain.breached(r.resolution_due_at, r.resolved_at, now))


async def _perms(db: AsyncSession) -> dict[str, bool]:
    r = (await db.execute(text(
        "SELECT app_has_permission('complaints', 'create') AS create, "
        "app_has_permission('complaints', 'edit') AS edit, "
        "app_has_permission('complaints', 'delete') AS delete, "
        "app_has_permission('complaints', 'approve') AS approve"))).one()
    return {"create": bool(r.create), "edit": bool(r.edit), "delete": bool(r.delete),
            "approve": bool(r.approve)}


async def _can(db: AsyncSession, caller: Caller, r: Any) -> sch.Can:
    refusals = (await db.execute(text(
        "SELECT complaint_refusal(CAST(:c AS uuid), 'submit') AS submit, "
        "complaint_refusal(CAST(:c AS uuid), 'check') AS check_, "
        "complaint_refusal(CAST(:c AS uuid), 'qc') AS qc, "
        "complaint_refusal(CAST(:c AS uuid), 'cancel') AS cancel, "
        "complaint_refusal(CAST(:c AS uuid), 'remedy') AS remedy, "
        "complaint_refusal(CAST(:c AS uuid), 'withdraw') AS withdraw, "
        "complaint_reopen_refusal(CAST(:c AS uuid)) AS reopen"), {"c": str(r.id)})).one()
    perms = await _perms(db)
    draft = r.status_text == "draft"
    mine = caller.user_id in (str(r.raised_by), str(r.owner_user_id) if r.owner_user_id else "")
    edit = draft and (perms["edit"] or mine)
    upload = ((r.status_text in ("draft", "submitted") and (perms["edit"] or perms["create"]))
              or (r.status_text == "under_qc" and refusals.qc is None))
    return sch.Can(edit=edit, submit=refusals.submit is None, check=refusals.check_ is None,
                   qc=refusals.qc is None, cancel=refusals.cancel is None,
                   delete=draft and r.submit_count == 0 and perms["delete"], upload=upload,
                   remedy=refusals.remedy is None, withdraw=refusals.withdraw is None,
                   reopen=refusals.reopen is None)


async def _rows(db: AsyncSession, where: str, params: dict[str, Any]) -> list[Any]:
    return list((await db.execute(text(f"{_SELECT} WHERE c.deleted_at IS NULL AND {where}"),
                                  params)).all())


async def get_complaint(db: AsyncSession, caller: Caller, complaint_id: str) -> sch.Complaint:
    rows = await _rows(db, "c.id = CAST(:id AS uuid)", {"id": complaint_id})
    if not rows:
        raise NotFoundError("No such complaint.")
    r = rows[0]
    portal = _portal(caller)
    lines = (await db.execute(text(
        "SELECT cl.id, cl.product_id, p.description::text AS description, cl.uom, cl.supplied_qty, "
        "cl.defective_qty, cl.failure_frequency, cl.remark FROM complaint_line cl "
        "LEFT JOIN product p ON p.id = cl.product_id WHERE cl.complaint_id = CAST(:c AS uuid) "
        "ORDER BY cl.line_no"), {"c": complaint_id})).all()
    files = (await db.execute(text(
        "SELECT a.*, u.full_name FROM complaint_attachment a LEFT JOIN app_user u ON u.id = a.uploaded_by "
        "WHERE a.complaint_id = CAST(:c AS uuid) AND a.deleted_at IS NULL ORDER BY a.uploaded_at, a.id"),
        {"c": complaint_id})).all()
    decisions = (await db.execute(text(
        "SELECT d.*, u.full_name, n.internal_note FROM complaint_decision d "
        "LEFT JOIN app_user u ON u.id = d.decided_by "
        "LEFT JOIN complaint_decision_note n ON n.decision_id = d.id "
        "WHERE d.complaint_id = CAST(:c AS uuid) "
        "ORDER BY d.decided_at DESC, d.id DESC"), {"c": complaint_id})).all()
    # names beyond the joins come through people_names(), which never names a
    # decider to a partner; a partner's request does not ask for them at all
    user_ids = {str(x) for x in (r.owner_user_id, r.raised_by) if x}
    user_ids |= {str(f.uploaded_by) for f in files}
    if not portal:
        user_ids |= {str(d.decided_by) for d in decisions}
    else:
        # whoever cancelled is the raiser or the owner, both names a dealer already sees
        user_ids |= {str(d.decided_by) for d in decisions if d.stage == "cancel"}
    names = await people.resolve_ids(db, user_ids)

    check = next((d for d in decisions if d.stage == "check" and d.submit_no == r.submit_count), None)
    quality = next((d for d in decisions if d.stage == "qc"), None)
    cancelled = next((d for d in decisions if d.stage == "cancel"), None)
    now = _now()
    return sch.Complaint(
        id=str(r.id), complaint_no=r.complaint_no, status=r.status_text,
        complaint_type=sch.TypeRef(id=str(r.complaint_type_id), code=r.type_code, name=r.type_name),
        severity=r.severity_text, description=r.description, contact_name=r.contact_name,
        contact_mobile=r.contact_mobile,
        territory=sch.Ref(id=str(r.territory_id), name=r.territory_name or ""),
        partner=_partner(r), lead=_lead(r), sales_order=_order(r),
        dc_no=r.dc_no, supply_date=_iso(r.supply_date), reg_no=r.reg_no, pims_no=r.pims_no,
        sample_courier_date=_iso(r.sample_courier_date), sample_courier_detail=r.sample_courier_detail,
        lines=[sch.Line(id=str(x.id), product=sch.ProductRef(id=str(x.product_id), description=x.description),
                        uom=x.uom, supplied_qty=_qty(x.supplied_qty), defective_qty=_qty(x.defective_qty),
                        failure_frequency=x.failure_frequency, remark=x.remark) for x in lines],
        attachments=[sch.Attachment(
            id=str(f.id), kind=f.kind, filename=f.filename, content_type=f.content_type,
            size_bytes=f.size_bytes, preview=f.content_type != "image/heic",
            uploaded_by=names.user(f.uploaded_by, f.full_name), uploaded_at=f.uploaded_at.isoformat())
            for f in files],
        check=(sch.Check(decision=check.decision, remark=check.remark,
                         by=None if portal else names.user(check.decided_by, check.full_name),
                         at=check.decided_at.isoformat(),
                         internal_note=None if portal else check.internal_note)
               if check else None),
        quality=(sch.Quality(verdict=quality.decision, remark=quality.remark,
                             sample_received_on=_iso(quality.sample_received_on),
                             tested_on=_iso(quality.tested_on), field_visit_on=_iso(quality.field_visit_on),
                             by=None if portal else names.user(quality.decided_by, quality.full_name),
                             at=quality.decided_at.isoformat(),
                             internal_note=None if portal else quality.internal_note)
                 if quality else None),
        cancellation=(sch.Cancellation(reason=cancelled.remark,
                                       by=names.user(cancelled.decided_by, cancelled.full_name),
                                       at=cancelled.decided_at.isoformat())
                      if cancelled else None),
        sla=_sla(r, now), submit_count=r.submit_count,
        owner=names.user(r.owner_user_id, r.owner_name),
        owner_org_unit=sch.Ref(id=str(r.owner_org_unit_id), name=r.office_name or ""),
        raised_by=names.user(r.raised_by, r.raiser_name),
        remedy=await _remedy(db, complaint_id, portal),
        closed_at=_iso(r.closed_at),
        reopen_count=r.reopen_count, reopened_at=_iso(r.reopened_at),
        reopen_reason=None if portal else r.reopen_reason,
        can=await _can(db, caller, r),
        created_at=r.created_at.isoformat(), updated_at=r.updated_at.isoformat(),
        submitted_at=_iso(r.submitted_at))


async def _remedy(db: AsyncSession, complaint_id: str, portal: bool) -> sch.Remedy | None:
    """The live remedy, else the latest. A dealer sees the kind, status, amount and
    the replacement order, never the payee, the approvers or the remark (rule 10)."""
    m = (await db.execute(text(
        "SELECT m.*, cp.name AS partner_name FROM complaint_remedy m "
        "LEFT JOIN channel_partner cp ON cp.id = m.paid_through_partner_id "
        "WHERE m.complaint_id = CAST(:c AS uuid) "
        "ORDER BY (m.status = 'pending') DESC, m.chosen_at DESC, m.id DESC LIMIT 1"),
        {"c": complaint_id})).one_or_none()
    if m is None:
        return None
    refund = replacement = None
    if m.kind == "refund":
        approval = None
        if not portal:
            approval, _raw = await approval_view.load(db, "complaint", complaint_id, portal,
                                                      request_id=str(m.approval_request_id))
        refund = sch.Refund(
            amount=f"{m.amount:.2f}", payee_name=None if portal else m.payee_name,
            paid_through=(None if portal or m.paid_through_partner_id is None
                          else sch.Ref(id=str(m.paid_through_partner_id), name=m.partner_name or "")),
            approval=approval, payment_reference=None if portal else m.payment_reference)
    elif m.kind == "replacement":
        o = (await db.execute(text("SELECT * FROM complaint_remedy_order(CAST(:m AS uuid))"),
                              {"m": str(m.id)})).one_or_none()
        replacement = sch.Replacement(order=sch.RemedyOrder(id=str(o.id), order_no=o.order_no,
                                                            status=o.status) if o else None)
    chosen_by = None
    if not portal:
        chosen_by = (await people.resolve_ids(db, {str(m.chosen_by)})).user(m.chosen_by, None)
    return sch.Remedy(id=str(m.id), kind=m.kind, status=m.status,
                      remark=None if portal else m.remark, refund=refund, replacement=replacement,
                      chosen_by=chosen_by, chosen_at=m.chosen_at.isoformat(),
                      completed_at=_iso(m.completed_at))


_BREACHED = ("((c.response_due_at IS NOT NULL AND COALESCE(c.responded_at, now()) > c.response_due_at) "
             "OR (c.resolution_due_at IS NOT NULL AND COALESCE(c.resolved_at, now()) > c.resolution_due_at))")


async def list_complaints(db: AsyncSession, caller: Caller, *, status: list[str] | None = None,
                          complaint_type_id: str | None = None, severity: str | None = None,
                          partner_id: str | None = None, lead_id: str | None = None,
                          sales_order_id: str | None = None, owner: str | None = None,
                          breached: bool = False, awaiting: str | None = None, q: str | None = None,
                          limit: int = 50, cursor: str | None = None) -> sch.ComplaintPage:
    limit = max(1, min(limit, _MAX_LIMIT))
    where = ["true"]
    params: dict[str, Any] = {"lim": limit + 1}
    if status:
        where.append("c.status::text = ANY(CAST(:st AS text[]))")
        params["st"] = status
    for col, val in (("complaint_type_id", complaint_type_id), ("partner_id", partner_id),
                     ("lead_id", lead_id), ("sales_order_id", sales_order_id)):
        if val:
            where.append(f"c.{col} = CAST(:{col} AS uuid)")
            params[col] = val
    if severity:
        where.append("c.severity::text = :sev")
        params["sev"] = severity
    if owner == "none":
        where.append("c.owner_user_id IS NULL")
    if breached:
        where.append(_BREACHED)
    if q:
        digits = re.sub(r"[^0-9]", "", q)
        params["q"] = f"%{q.strip()}%"
        if digits:
            where.append("(c.complaint_no ILIKE :q OR c.contact_name ILIKE :q OR c.contact_mobile LIKE :qm)")
            params["qm"] = f"%{digits}%"
        else:
            # no digits, no mobile clause: a NUL stand-in made PostgreSQL refuse the
            # statement and every name search a 500 (astra, reproduced)
            where.append("(c.complaint_no ILIKE :q OR c.contact_name ILIKE :q)")
    if awaiting == "me":
        where.append("((c.status IN ('submitted', 'under_qc') AND "
                     "(complaint_refusal(c.id, 'check') IS NULL OR complaint_refusal(c.id, 'qc') IS NULL)) "
                     # FS-015b: an approved complaint waits on QC for its remedy (code review F-4)
                     "OR (c.status = 'qc_approved' AND complaint_refusal(c.id, 'remedy') IS NULL))")
        order = "c.first_submitted_at, c.id"
        if cursor:
            raise ValidationFailed(fields={"cursor": "the queue is one page"})
    else:
        order = "c.created_at DESC, c.id DESC"
        if cursor:
            at, cid = _decode_cursor(cursor)
            where.append("(c.created_at, c.id) < (CAST(:cat AS timestamptz), CAST(:cid AS uuid))")
            params.update(cat=at, cid=cid)
    rows = list((await db.execute(text(
        f"{_SELECT} WHERE c.deleted_at IS NULL AND {' AND '.join(where)} ORDER BY {order} LIMIT :lim"),
        params)).all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        if awaiting != "me":
            next_cursor = _encode_cursor(rows[-1].created_at, str(rows[-1].id))
    names = await people.resolve(db, rows, [("owner_user_id", "owner_name")])
    now = _now()
    return sch.ComplaintPage(data=[sch.ComplaintSummary(
        id=str(r.id), complaint_no=r.complaint_no, status=r.status_text,
        complaint_type=sch.TypeRef(id=str(r.complaint_type_id), code=r.type_code, name=r.type_name),
        severity=r.severity_text, contact_name=r.contact_name, partner=_partner(r),
        owner=names.user(r.owner_user_id, r.owner_name), first_submitted_at=_iso(r.first_submitted_at),
        breached=(domain.breached(r.response_due_at, r.responded_at, now)
                  or domain.breached(r.resolution_due_at, r.resolved_at, now)),
        created_at=r.created_at.isoformat()) for r in rows],
        meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def stats(db: AsyncSession, storage: Storage) -> sch.Stats:
    rows = (await db.execute(text(
        "SELECT c.status::text AS status, count(*) AS n FROM complaint c WHERE c.deleted_at IS NULL "
        "GROUP BY c.status"))).all()
    extra = (await db.execute(text(
        f"SELECT count(*) FILTER (WHERE {_BREACHED}) AS breached, "
        "count(*) FILTER (WHERE c.submit_count > 0 AND c.response_due_at IS NULL "
        "                 AND c.resolution_due_at IS NULL) AS no_target "
        "FROM complaint c WHERE c.deleted_at IS NULL"))).one()
    return sch.Stats(by_status={r.status: int(r.n) for r in rows}, breached=int(extra.breached),
                     no_target=int(extra.no_target), storage_available=storage.name != "unconfigured")


# ── writing a draft ──────────────────────────────────────────────────────────

def _mobile(raw: str) -> str:
    try:
        return normalise_mobile(raw)
    except MobileError as exc:
        raise ValidationFailed(fields={"contact_mobile": str(exc)}) from exc


async def _state_code(db: AsyncSession, territory_id: str) -> str:
    """Resolved at create and on a territory change (EC-16), so an uncoded
    territory is refused before the form is filled."""
    code = (await db.execute(text(
        "SELECT t.code FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
        "WHERE tc.descendant_id = CAST(:t AS uuid) AND t.level = 'state' AND t.code IS NOT NULL "
        "ORDER BY tc.depth LIMIT 1"), {"t": territory_id})).scalar_one_or_none()
    if code is None:
        exists = (await db.execute(text("SELECT 1 FROM territory WHERE id = CAST(:t AS uuid)"),
                                   {"t": territory_id})).first()
        if exists is None:
            raise ValidationFailed(fields={"territory_id": "not found"})
        raise ValidationFailed("That territory has no state code yet.",
                               code="territory_without_state_code",
                               fields={"territory_id": "no state code above it"})
    return str(code)


async def _route(db: AsyncSession, caller: Caller, territory_id: str) -> tuple[str | None, str]:
    """Rule 3: the owner and the owning office, set at create and following nothing."""
    if _portal(caller):
        owner = (await db.execute(text("SELECT lead_auto_owner(CAST(:t AS uuid))"),
                                  {"t": territory_id})).scalar_one_or_none()
        return (str(owner) if owner else None), await _covering_org_unit(db, territory_id)
    if caller.org_unit_id is not None:
        has_territory = (await db.execute(text(
            "SELECT territory_id IS NOT NULL FROM org_unit WHERE id = CAST(:o AS uuid)"),
            {"o": caller.org_unit_id})).scalar_one_or_none()
        if has_territory:
            return caller.user_id, caller.org_unit_id
    return caller.user_id, await _covering_org_unit(db, territory_id)


async def _check_links(db: AsyncSession, partner_id: str | None, lead_id: str | None,
                       order_id: str | None, *, partner_for_order: str | None = None) -> None:
    """Rule 4: every link visible to the raiser; a linked order's dealer is the
    complaint's (GAP-148)."""
    for table, value, field in (("channel_partner", partner_id, "partner_id"), ("lead", lead_id, "lead_id"),
                                ("sales_order", order_id, "sales_order_id")):
        if value and (await db.execute(text(f"SELECT 1 FROM {table} WHERE id = CAST(:i AS uuid)"),
                                       {"i": value})).first() is None:
            raise ValidationFailed(fields={field: "not found or not yours"})
    if order_id:
        order_partner: Any = (await db.execute(text(
            "SELECT partner_id FROM sales_order WHERE id = CAST(:o AS uuid)"), {"o": order_id})).scalar_one()
        expected = partner_for_order if partner_for_order is not None else partner_id
        if order_partner is not None and str(order_partner) != (expected or ""):
            raise ValidationFailed(fields={"sales_order_id": "an order of another dealer"})


async def _from_dispatch(db: AsyncSession, order_id: str) -> tuple[str | None, dt.date | None]:
    """The challan and supply date of the order's latest dispatch, when the caller
    can read it."""
    row = (await db.execute(text(
        # the IST day: the session runs in UTC (PR 25 review)
        "SELECT dc_no, COALESCE(dc_date, (dispatched_at AT TIME ZONE 'Asia/Kolkata')::date) "
        "AS day FROM dispatch "
        "WHERE sales_order_id = CAST(:o AS uuid) AND dc_no IS NOT NULL "
        "ORDER BY dispatched_at DESC NULLS LAST LIMIT 1"), {"o": order_id})).one_or_none()
    return (row.dc_no, row.day) if row else (None, None)


def _check_dates(values: dict[str, dt.date | None]) -> None:
    problems = domain.date_problems(today=domain.ist_today(_now()), **values)
    if problems:
        raise ValidationFailed(fields=problems)


def _check_lines(lines: list[sch.LineIn]) -> None:
    problems = domain.line_problems([domain.Line(ln.product_id, ln.supplied_qty, ln.defective_qty)
                                     for ln in lines])
    if problems:
        raise ValidationFailed(fields=problems)


async def _write_lines(db: AsyncSession, complaint_id: str, lines: list[sch.LineIn]) -> None:
    for i, ln in enumerate(lines, start=1):
        try:
            async with db.begin_nested():
                await db.execute(text(
                    "INSERT INTO complaint_line (complaint_id, line_no, product_id, uom, supplied_qty, "
                    "defective_qty, failure_frequency, remark) SELECT CAST(:c AS uuid), :n, p.id, "
                    "u.code::text, :s, :d, :f, :r FROM product p LEFT JOIN uom u ON u.id = p.uom_id "
                    "WHERE p.id = CAST(:p AS uuid)"),
                    {"c": complaint_id, "n": i, "p": ln.product_id, "s": ln.supplied_qty,
                     "d": ln.defective_qty, "f": domain.clean_text(ln.failure_frequency),
                     "r": domain.clean_text(ln.remark)})
        except DBAPIError as exc:
            mapped = _refusal(exc)
            if mapped is not None:
                raise mapped from exc
            raise
    found: int = (await db.execute(text("SELECT count(*) FROM complaint_line WHERE complaint_id = CAST(:c AS uuid)"),
                              {"c": complaint_id})).scalar_one()
    if found != len(lines):
        raise ValidationFailed(fields={"lines": "a product was not found"})


async def _event(db: AsyncSession, complaint_id: str, lead_id: Any, kind: str, caller: Caller,
                 **payload: Any) -> None:
    name = (await db.execute(text("SELECT full_name FROM app_user WHERE id = (SELECT app_current_user_id())"))
            ).scalar_one_or_none()
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('complaint', CAST(:e AS uuid), CAST(:l AS uuid), :k, CAST(:me AS uuid), CAST(:p AS jsonb))"),
        {"e": complaint_id, "l": str(lead_id) if lead_id else None, "k": kind, "me": caller.user_id,
         "p": json.dumps({"actor_name": name or "", **payload})})


async def create_complaint(db: AsyncSession, caller: Caller, body: sch.ComplaintCreate) -> sch.Complaint:
    if _portal(caller):
        if body.partner_id not in (None, caller.partner_id):
            raise ValidationFailed(fields={"partner_id": "a dealer raises for themselves"})
        partner_id: str | None = caller.partner_id
    else:
        if caller.org_unit_id is None:
            raise ForbiddenError("Complaints are raised by staff or a dealer.")
        partner_id = body.partner_id
    _check_lines(body.lines)
    mobile = _mobile(body.contact_mobile)
    dc_no, supply = domain.clean_text(body.dc_no), body.supply_date
    await _check_links(db, partner_id, body.lead_id, body.sales_order_id)
    if body.sales_order_id and (dc_no is None or supply is None):
        found_dc, found_day = await _from_dispatch(db, body.sales_order_id)
        dc_no, supply = dc_no or found_dc, supply or found_day
    _check_dates({"supply_date": supply, "sample_courier_date": body.sample_courier_date})
    state_code = await _state_code(db, body.territory_id)
    owner, office = await _route(db, caller, body.territory_id)
    try:
        async with db.begin_nested():
            complaint_id = str((await db.execute(text(
                "INSERT INTO complaint (complaint_type_id, severity, description, contact_name, contact_mobile, "
                "territory_id, state_code, partner_id, lead_id, sales_order_id, owner_user_id, owner_org_unit_id, "
                "raised_by, dc_no, supply_date, reg_no, pims_no, sample_courier_date, sample_courier_detail, "
                "created_by, updated_by) VALUES (CAST(:ty AS uuid), CAST(:sev AS complaint_severity), :d, :cn, :cm, "
                "CAST(:t AS uuid), :sc, CAST(:p AS uuid), CAST(:l AS uuid), CAST(:o AS uuid), CAST(:ow AS uuid), "
                "CAST(:ou AS uuid), CAST(:me AS uuid), :dc, :sd, :rn, :pn, :scd, :scx, CAST(:me AS uuid), "
                "CAST(:me AS uuid)) RETURNING id"),
                {"ty": body.complaint_type_id, "sev": body.severity, "d": body.description.strip(),
                 "cn": body.contact_name.strip(), "cm": mobile, "t": body.territory_id, "sc": state_code,
                 "p": partner_id, "l": body.lead_id, "o": body.sales_order_id, "ow": owner, "ou": office,
                 "me": caller.user_id, "dc": dc_no, "sd": supply, "rn": domain.clean_text(body.reg_no),
                 "pn": domain.clean_text(body.pims_no), "scd": body.sample_courier_date,
                 "scx": domain.clean_text(body.sample_courier_detail)})).scalar_one())
    except DBAPIError as exc:
        if _sqlstate(exc) in ("23503", "42501"):
            raise ValidationFailed(fields={"complaint_type_id": "not found, or not yours to raise"}) from exc
        raise
    await _write_lines(db, complaint_id, body.lines)
    await _event(db, complaint_id, body.lead_id, "complaint.created", caller)
    return await get_complaint(db, caller, complaint_id)


async def _draft_row(db: AsyncSession, complaint_id: str) -> Any:
    """The draft, locked. 404 out of scope; 409 once it moved on (EC-19)."""
    try:
        row = (await db.execute(text(
            "SELECT * FROM complaint WHERE id = CAST(:c AS uuid) AND deleted_at IS NULL FOR UPDATE"),
            {"c": complaint_id})).one_or_none()
    except DBAPIError as exc:
        if _sqlstate(exc) == "42501":
            raise ForbiddenError("You may not edit this complaint.") from exc
        raise
    if row is None:
        raise NotFoundError("No such complaint.")
    if row.status != "draft":
        raise ConflictError("The complaint is no longer a draft.", code="complaint_not_draft")
    return row


async def patch_complaint(db: AsyncSession, caller: Caller, complaint_id: str,
                          body: sch.ComplaintPatch) -> sch.Complaint:
    given = body.model_fields_set
    if not given:
        raise ValidationFailed(fields={"body": "nothing to change"})
    if "partner_id" in given and _portal(caller):
        raise ValidationFailed(fields={"partner_id": "a dealer raises for themselves"})
    row = await _draft_row(db, complaint_id)
    sets: list[str] = []
    params: dict[str, Any] = {"c": complaint_id, "me": caller.user_id}
    text_fields = {"description", "contact_name", "dc_no", "reg_no", "pims_no", "sample_courier_detail"}
    for f in sorted(given):
        value = getattr(body, f)
        if f in ("description", "contact_name", "complaint_type_id", "severity", "territory_id",
                 "contact_mobile") and value is None:
            raise ValidationFailed(fields={f: "cannot be cleared"})
        if f in text_fields:
            value = domain.clean_text(value)
        if f == "contact_mobile":
            value = _mobile(value)
        cast = {"complaint_type_id": "uuid", "territory_id": "uuid", "partner_id": "uuid", "lead_id": "uuid",
                "sales_order_id": "uuid", "severity": "complaint_severity"}.get(f)
        sets.append(f"{f} = CAST(:{f} AS {cast})" if cast else f"{f} = :{f}")
        params[f] = value
    partner = body.partner_id if "partner_id" in given else (str(row.partner_id) if row.partner_id else None)
    order = (body.sales_order_id if "sales_order_id" in given
             else (str(row.sales_order_id) if row.sales_order_id else None))
    # a partner change re-checks the order already on it (code review F-3)
    await _check_links(db, body.partner_id if "partner_id" in given else None,
                       body.lead_id if "lead_id" in given else None,
                       order if "partner_id" in given or "sales_order_id" in given else None,
                       partner_for_order=partner)
    if "territory_id" in given:
        sets.append("state_code = :state_code")
        params["state_code"] = await _state_code(db, body.territory_id or "")
    _check_dates({"supply_date": body.supply_date if "supply_date" in given else row.supply_date,
                  "sample_courier_date": (body.sample_courier_date if "sample_courier_date" in given
                                          else row.sample_courier_date)})
    sets.append("updated_by = CAST(:me AS uuid)")
    try:
        async with db.begin_nested():
            done: Any = await db.execute(text(
                f"UPDATE complaint SET {', '.join(sets)} WHERE id = CAST(:c AS uuid) AND status = 'draft'"),
                params)
    except DBAPIError as exc:
        if _sqlstate(exc) in ("23503", "42501"):
            raise ValidationFailed(fields={f: "not found or not yours" for f in given
                                           if f.endswith("_id")} or {"body": "refused"}) from exc
        raise
    if done.rowcount == 0:
        raise ConflictError("The complaint is no longer a draft.", code="complaint_not_draft")
    await _event(db, complaint_id, row.lead_id, "complaint.updated", caller, fields=sorted(given))
    return await get_complaint(db, caller, complaint_id)


async def replace_lines(db: AsyncSession, caller: Caller, complaint_id: str,
                        body: sch.LinesReplace) -> sch.Complaint:
    _check_lines(body.lines)
    row = await _draft_row(db, complaint_id)
    await db.execute(text("DELETE FROM complaint_line WHERE complaint_id = CAST(:c AS uuid)"), {"c": complaint_id})
    await _write_lines(db, complaint_id, body.lines)
    await _event(db, complaint_id, row.lead_id, "complaint.updated", caller, fields=["lines"])
    return await get_complaint(db, caller, complaint_id)


async def delete_complaint(db: AsyncSession, caller: Caller, complaint_id: str) -> None:
    row = await _draft_row(db, complaint_id)
    if row.submit_count:
        raise ConflictError("A submitted complaint is cancelled, not deleted.", code="complaint_not_draft")
    if not (await _perms(db))["delete"]:
        raise ForbiddenError("Deleting a complaint needs complaints.delete.")
    await db.execute(text(
        "UPDATE complaint SET deleted_at = now(), updated_by = CAST(:me AS uuid) WHERE id = CAST(:c AS uuid)"),
        {"c": complaint_id, "me": caller.user_id})
    await _event(db, complaint_id, row.lead_id, "complaint.deleted", caller)


# ── the transitions ──────────────────────────────────────────────────────────

async def submit(db: AsyncSession, caller: Caller, complaint_id: str) -> sch.Complaint:
    await _definer(db, "SELECT complaint_submit(CAST(:c AS uuid))", {"c": complaint_id})
    return await get_complaint(db, caller, complaint_id)


async def check(db: AsyncSession, caller: Caller, complaint_id: str, body: sch.CheckIn) -> sch.Complaint:
    if body.decision == "return" and (body.severity or body.owner_user_id):
        raise ValidationFailed(fields={"decision": "severity and owner only with approve"})
    await _definer(db,
                   "SELECT complaint_check(CAST(:c AS uuid), :d, :r, CAST(:s AS complaint_severity), "
                   "CAST(:o AS uuid), :n)",
                   {"c": complaint_id, "d": body.decision, "r": body.remark, "s": body.severity,
                    "o": body.owner_user_id, "n": domain.clean_text(body.internal_note)})
    return await get_complaint(db, caller, complaint_id)


async def qc(db: AsyncSession, caller: Caller, complaint_id: str, body: sch.QcIn) -> sch.Complaint:
    supply = (await db.execute(text(
        "SELECT supply_date FROM complaint WHERE id = CAST(:c AS uuid) AND deleted_at IS NULL"),
        {"c": complaint_id})).scalar_one_or_none()
    _check_dates({"supply_date": supply, "sample_received_on": body.sample_received_on,
                  "tested_on": body.tested_on, "field_visit_on": body.field_visit_on})
    await _definer(db,
                   "SELECT complaint_qc(CAST(:c AS uuid), :v, :r, :rec, :tst, :vis, :n)",
                   {"c": complaint_id, "v": body.verdict, "r": body.remark, "rec": body.sample_received_on,
                    "tst": body.tested_on, "vis": body.field_visit_on,
                    "n": domain.clean_text(body.internal_note)})
    return await get_complaint(db, caller, complaint_id)


async def choose_remedy(db: AsyncSession, caller: Caller, complaint_id: str,
                        body: sch.RemedyIn) -> sch.Complaint:
    """FS-015b: a refund into the engine, a free replacement order, or no action."""
    if body.kind == "refund":
        missing = {f: "required for a refund" for f, v in
                   (("amount", body.amount), ("payee_name", body.payee_name)) if v is None}
        if missing:
            raise ValidationFailed(fields=missing)
    elif body.amount is not None or body.payee_name or body.paid_through_partner_id:
        raise ValidationFailed(fields={"kind": "amount and payee belong to a refund"})
    if body.kind == "replacement":
        # 403 and 409 before any pricing 422 (PR 38 review); the definer checks again
        refusal: str | None = (await db.execute(text("SELECT complaint_refusal(CAST(:c AS uuid), 'remedy')"),
                                    {"c": complaint_id})).scalar_one()
        if refusal == "not_visible":
            raise NotFoundError("No such complaint.")
        if refusal == "not_qc_approved":
            raise ConflictError("The complaint moved on; reload it.", code="status_changed")
        if refusal is not None:
            raise ForbiddenError("This is not yours to do on this complaint.")
        order, lines = await _replacement_rows(db, complaint_id)
        await _definer(db, "SELECT complaint_remedy_replacement(CAST(:c AS uuid), CAST(:o AS jsonb), "
                           "CAST(:l AS jsonb), :r)",
                       {"c": complaint_id, "o": json.dumps(order, default=str),
                        "l": json.dumps(lines, default=str), "r": body.remark})
    else:
        await _definer(db, "SELECT complaint_remedy_choose(CAST(:c AS uuid), :k, :a, :p, "
                           "CAST(:pt AS uuid), :r)",
                       {"c": complaint_id, "k": body.kind, "a": body.amount, "p": body.payee_name,
                        "pt": body.paid_through_partner_id, "r": body.remark})
    return await get_complaint(db, caller, complaint_id)


# order_line's columns, from the orders service's row (its keys are bind names)
_LINE_COLUMNS = {"n": "line_no", "product": "product_id", "desc": "description", "hsn": "hsn_code",
                 "uom": "uom", "dec": "uom_decimals", "qty": "qty", "rate": "rate",
                 "pl": "price_list_id", "pli": "price_list_item_id", "gr": "gst_rate_id",
                 "gross": "gross", "d1p": "discount_pct", "d1a": "discount1_amt",
                 "a1": "after_discount1", "d2p": "discount2_pct", "d2a": "discount2_amt",
                 "a2": "after_discount2", "d3p": "discount3_pct", "d3a": "discount3_amt",
                 "disc": "discount", "taxable": "taxable", "slab": "gst_slab",
                 "cr": "cgst_rate", "sr": "sgst_rate", "ir": "igst_rate", "cgst": "cgst",
                 "sgst": "sgst", "igst": "igst", "total": "total", "prov": "provisional_fields"}


async def _replacement_rows(db: AsyncSession, complaint_id: str
                            ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The defective lines priced today with a 100 % first-tier discount, under the
    caller's own claim (plan review B3). The definer checks them against the
    complaint again under its lock."""
    from decimal import Decimal

    from api.services import orders as order_service  # the order row's shape, one source

    c = (await db.execute(text(
        "SELECT territory_id FROM complaint WHERE id = CAST(:c AS uuid) AND deleted_at IS NULL"),
        {"c": complaint_id})).one_or_none()
    if c is None:
        raise NotFoundError("No such complaint.")
    defective = (await db.execute(text(
        "SELECT product_id, defective_qty FROM complaint_line WHERE complaint_id = CAST(:c AS uuid) "
        "AND defective_qty > 0 ORDER BY line_no"), {"c": complaint_id})).all()
    if not defective:
        raise ValidationFailed("At least one product needs a defective quantity.",
                               code="nothing_defective", fields={"lines": "nothing defective"})
    specs = [pricing.LineSpec(product_id=str(d.product_id), qty=Decimal(d.defective_qty),
                              discounts=(Decimal(100), Decimal(0), Decimal(0))) for d in defective]
    try:
        ctx = await pricing.price_document(
            db, partner_id=None, place_of_supply_territory_id=str(c.territory_id), seller_gstin_id=None,
            as_of=today_ist(), lines=specs, existing=False, tax_as_of=today_ist())
    except (ValidationFailed, NotFoundError) as exc:
        fields = getattr(exc, "fields", None) or {"lines": exc.message}
        raise ValidationFailed("A defective product cannot be priced today.",
                               code="replacement_unpriced", fields=fields) from exc
    lines = []
    for i, line in enumerate(ctx.document.lines):
        row = order_service._line_row("", i + 1, line, None, None)
        lines.append({col: row[key] for key, col in _LINE_COLUMNS.items()})
    t = ctx.document.totals
    price_lists = {line.rate.price_list.id for line in ctx.document.lines}
    order = {"seller_gstin_id": ctx.seller_gstin_id, "place_of_supply_territory_id": str(c.territory_id),
             "place_of_supply_state_id": ctx.place_of_supply_state_id, "intra_state": ctx.intra_state,
             "price_effective_date": ctx.as_of,
             "price_list_id": next(iter(price_lists)) if len(price_lists) == 1 else None,
             "gross": t.gross, "discount": t.discount, "taxable": t.taxable, "cgst": t.cgst,
             "sgst": t.sgst, "igst": t.igst, "total": t.total,
             "is_provisional": any(line.provisional_fields for line in ctx.document.lines)}
    return order, lines


async def withdraw_remedy(db: AsyncSession, caller: Caller, complaint_id: str,
                          body: sch.WithdrawIn) -> sch.Complaint:
    await _definer(db, "SELECT complaint_remedy_withdraw(CAST(:c AS uuid), :r)",
                   {"c": complaint_id, "r": body.remark})
    return await get_complaint(db, caller, complaint_id)


async def cancel(db: AsyncSession, caller: Caller, complaint_id: str, body: sch.CancelIn) -> sch.Complaint:
    await _definer(db, "SELECT complaint_cancel(CAST(:c AS uuid), :r)", {"c": complaint_id, "r": body.reason})
    return await get_complaint(db, caller, complaint_id)


async def reopen(db: AsyncSession, caller: Caller, complaint_id: str, body: sch.ReopenIn) -> sch.Complaint:
    """FS-036: a closed or rejected complaint starts a new round. The rules are
    complaint_reopen_refusal()'s, in migration 041."""
    await _definer(db, "SELECT complaint_reopen(CAST(:c AS uuid), :r)", {"c": complaint_id, "r": body.reason})
    return await get_complaint(db, caller, complaint_id)


async def assignees(db: AsyncSession, complaint_id: str) -> list[sch.Assignee]:
    try:
        async with db.begin_nested():
            rows = (await db.execute(text(
                "SELECT id, full_name, org_unit_id FROM complaint_assignees(CAST(:c AS uuid))"),
                {"c": complaint_id})).all()
    except DBAPIError as exc:
        if _sqlstate(exc) == "42501":
            raise ForbiddenError("Only whoever may check this complaint assigns its owner.") from exc
        raise
    return [sch.Assignee(id=str(r.id), full_name=r.full_name,
                         org_unit_id=str(r.org_unit_id) if r.org_unit_id else None) for r in rows]


async def timeline(db: AsyncSession, caller: Caller, complaint_id: str, *, limit: int = 100,
                   cursor: str | None = None) -> TimelinePage:
    if not (await _rows(db, "c.id = CAST(:id AS uuid)", {"id": complaint_id})):
        raise NotFoundError("No such complaint.")
    limit = max(1, min(limit, _MAX_LIMIT))
    portal = _portal(caller)
    before_at, before_id = _decode_cursor(cursor) if cursor else (None, None)
    rows = (await db.execute(text(
        "SELECT e.id, e.kind, e.occurred_at, e.actor_id, e.payload, u.full_name FROM activity_event e "
        "LEFT JOIN app_user u ON u.id = e.actor_id "
        "WHERE e.entity_type = 'complaint' AND e.entity_id = CAST(:c AS uuid) "
        "AND (CAST(:bat AS timestamptz) IS NULL OR (e.occurred_at, e.id) < (CAST(:bat AS timestamptz), CAST(:bid AS uuid))) "
        "ORDER BY e.occurred_at DESC, e.id DESC LIMIT :lim"),
        {"c": complaint_id, "bat": before_at, "bid": before_id, "lim": limit + 1})).all()
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].occurred_at, str(rows[-1].id))
    names = await people.resolve(db, rows, [("actor_id", "full_name")])
    events = []
    for r in rows:
        payload = json.loads(r.payload) if isinstance(r.payload, str) else dict(r.payload or {})
        name = payload.pop("actor_name", None) or r.full_name
        hidden = portal and actor_hidden_from_partner(r.kind)
        events.append(TimelineEvent(
            id=str(r.id), kind=r.kind, occurred_at=r.occurred_at.isoformat(),
            actor=None if hidden else names.user(r.actor_id, name), payload=payload))
    return TimelinePage(data=events, meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── attachments (ADR-041) ────────────────────────────────────────────────────

def _safe_filename(name: str | None, extension: str) -> str:
    """The name as given, without control characters; blank or dots only is
    `attachment.<ext>`. Stored as is; the header gets `_download_name`."""
    base = _UNSAFE.sub("", (name or "").strip())[:255]
    return base if base.strip(". ") else f"attachment.{extension}"


_HEADER_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _download_name(stored: str, content_type: str) -> str:
    """Header-safe, keeping the real extension: a Gujarati name or `...` becomes
    `attachment.jpg`, never `quotation.pdf` (code review F-5)."""
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
                 "image/heic": "heic", "application/pdf": "pdf"}.get(content_type, "bin")
    stem = stored.rsplit(".", 1)[0] if "." in stored else stored
    cleaned = _HEADER_UNSAFE.sub("-", stem).strip("-.")[:100]
    return f"{cleaned or 'attachment'}.{extension}"


async def add_attachment(db: AsyncSession, caller: Caller, complaint_id: str, *, kind: str,
                         filename: str | None, data: bytes, storage: Storage) -> tuple[sch.Attachment, bool]:
    """Sniff and hash, write to storage outside any lock, then lock the complaint,
    check its status and the count, and insert (rule 10, recommendation 6). Returns
    the attachment and whether it is new."""
    if not data:
        raise ValidationFailed(fields={"file": "empty"})
    if len(data) > domain.MAX_UPLOAD_BYTES:
        raise ValidationFailed("Up to 10 MB.", code="attachment_too_large", fields={"file": "over 10 MB"})
    sniffed = domain.sniff(data[:16])
    if sniffed is None:
        raise ValidationFailed("JPEG, PNG, WebP, HEIC or PDF only.", code="attachment_type",
                               fields={"file": "not an allowed type"})
    digest = hashlib.sha256(data).hexdigest()
    # a duplicate on the same complaint returns the existing one (EC-9)
    existing = (await db.execute(text(
        "SELECT id FROM complaint_attachment WHERE complaint_id = CAST(:c AS uuid) AND sha256 = :h "
        "AND deleted_at IS NULL"), {"c": complaint_id, "h": digest})).scalar_one_or_none()
    if existing is not None:
        return await _attachment(db, str(existing)), False
    # refuse before anything reaches storage (code review F-2): a caller who may not
    # upload, or a closed complaint, costs no object
    await _may_upload(db, complaint_id)
    key = f"complaints/{complaint_id}/{uuid.uuid4().hex}.{sniffed.extension}"
    try:
        await asyncio.to_thread(storage.put, key, data, sniffed.content_type)
    except Exception as exc:  # the unconfigured adapter's RuntimeError and every network error
        log.warning("complaint.storage_unavailable", error=type(exc).__name__)
        # a 5xx: the idempotency record keeps nothing, so a retry retries (EC-10)
        raise ServiceUnavailableError("Files cannot be stored right now; try again later.",
                                      code="storage_unavailable") from exc
    # FOR UPDATE, not FOR SHARE: two uploads at once must not both count nine
    # (code review F-4); the definers take the same lock, so a decision waits too
    locked = (await db.execute(text(
        "SELECT status::text FROM complaint WHERE id = CAST(:c AS uuid) AND deleted_at IS NULL FOR UPDATE"),
        {"c": complaint_id})).scalar_one_or_none()
    if locked is None:
        raise ForbiddenError("You may not add files to this complaint.")
    await _may_upload(db, complaint_id)
    count = (await db.execute(text(
        "SELECT count(*) FROM complaint_attachment WHERE complaint_id = CAST(:c AS uuid) AND deleted_at IS NULL"),
        {"c": complaint_id})).scalar_one()
    if count >= domain.MAX_ATTACHMENTS:
        raise ValidationFailed(f"Up to {domain.MAX_ATTACHMENTS} files.", code="too_many_attachments")
    try:
        async with db.begin_nested():
            attachment_id = str((await db.execute(text(
                "INSERT INTO complaint_attachment (complaint_id, kind, storage_key, filename, content_type, "
                "size_bytes, sha256, uploaded_by) VALUES (CAST(:c AS uuid), :k, :key, :fn, :ct, :sz, :h, "
                "CAST(:me AS uuid)) RETURNING id"),
                {"c": complaint_id, "k": kind, "key": key, "fn": _safe_filename(filename, sniffed.extension),
                 "ct": sniffed.content_type, "sz": len(data), "h": digest, "me": caller.user_id})).scalar_one())
    except DBAPIError as exc:
        if _sqlstate(exc) == "23505":      # the same file won a race
            again = (await db.execute(text(
                "SELECT id FROM complaint_attachment WHERE complaint_id = CAST(:c AS uuid) AND sha256 = :h "
                "AND deleted_at IS NULL"), {"c": complaint_id, "h": digest})).scalar_one()
            return await _attachment(db, str(again)), False
        if _sqlstate(exc) == "42501":
            raise ForbiddenError("You may not add files to this complaint.") from exc
        raise
    lead = (await db.execute(text("SELECT lead_id FROM complaint WHERE id = CAST(:c AS uuid)"),
                             {"c": complaint_id})).scalar_one_or_none()
    await _event(db, complaint_id, lead, "complaint.attachment_added", caller, attachment_id=attachment_id,
                 attachment_kind=kind)
    return await _attachment(db, attachment_id), True


async def _may_upload(db: AsyncSession, complaint_id: str) -> None:
    """Rule 10: a draft or submitted complaint takes files from whoever may write
    complaints; one under QC, from QC alone. 404 out of scope, 409 once closed, 403
    otherwise. Read without a lock; the caller re-checks under one."""
    status = (await db.execute(text(
        "SELECT status::text FROM complaint WHERE id = CAST(:c AS uuid) AND deleted_at IS NULL"),
        {"c": complaint_id})).scalar_one_or_none()
    if status is None:
        raise NotFoundError("No such complaint.")
    if status in ("draft", "submitted"):
        perms = await _perms(db)
        if perms["edit"] or perms["create"]:
            return
        raise ForbiddenError("You may not add files to this complaint.")
    if status == "under_qc":
        if (await db.execute(text("SELECT complaint_refusal(CAST(:c AS uuid), 'qc') IS NULL"),
                             {"c": complaint_id})).scalar_one():
            return
        raise ForbiddenError("While QC has it, only QC adds files.")
    raise ConflictError("Files can no longer be added to this complaint.",
                        code="complaint_closed_for_upload")


async def _attachment(db: AsyncSession, attachment_id: str) -> sch.Attachment:
    r = (await db.execute(text(
        "SELECT a.*, u.full_name FROM complaint_attachment a LEFT JOIN app_user u ON u.id = a.uploaded_by "
        "WHERE a.id = CAST(:a AS uuid)"), {"a": attachment_id})).one()
    names = await people.resolve(db, [r], [("uploaded_by", "full_name")])
    return sch.Attachment(id=str(r.id), kind=r.kind, filename=r.filename, content_type=r.content_type,
                          size_bytes=r.size_bytes, preview=r.content_type != "image/heic",
                          uploaded_by=names.user(r.uploaded_by, r.full_name), uploaded_at=r.uploaded_at.isoformat())


async def attachment_link(db: AsyncSession, complaint_id: str, attachment_id: str,
                          storage: Storage) -> sch.AttachmentLink:
    r = (await db.execute(text(
        "SELECT storage_key, filename, content_type FROM complaint_attachment WHERE id = CAST(:a AS uuid) "
        "AND complaint_id = CAST(:c AS uuid) AND deleted_at IS NULL"),
        {"a": attachment_id, "c": complaint_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such file.")
    try:
        url, expires = storage.presign_get(
            r.storage_key, filename=_download_name(r.filename, r.content_type),
            disposition="attachment" if r.content_type == "image/heic" else "inline")
    except RuntimeError as exc:
        raise ServiceUnavailableError("Files cannot be opened right now.",
                                      code="storage_unavailable") from exc
    return sch.AttachmentLink(url=url, expires_at=expires.isoformat())


async def remove_attachment(db: AsyncSession, caller: Caller, complaint_id: str, attachment_id: str) -> None:
    """In a draft: the uploader or an editor. After submit, until a final state: the
    uploader only (EC-18)."""
    status = (await db.execute(text(
        "SELECT status::text FROM complaint WHERE id = CAST(:c AS uuid) AND deleted_at IS NULL FOR SHARE"),
        {"c": complaint_id})).scalar_one_or_none()
    if status is None:
        raise NotFoundError("No such complaint.")
    r = (await db.execute(text(
        "SELECT uploaded_by FROM complaint_attachment WHERE id = CAST(:a AS uuid) "
        "AND complaint_id = CAST(:c AS uuid) AND deleted_at IS NULL"),
        {"a": attachment_id, "c": complaint_id})).one_or_none()
    if r is None:
        raise NotFoundError("No such file.")
    mine = str(r.uploaded_by) == caller.user_id
    if status in ("qc_approved", "qc_rejected", "cancelled", "remedy_pending", "closed"):
        raise ConflictError("The complaint is closed.", code="complaint_closed_for_upload")
    if status != "draft" and not mine:
        raise ForbiddenError("After submit, only whoever added a file removes it.")
    if status == "draft" and not mine and not (await _perms(db))["edit"]:
        raise ForbiddenError("You may not remove this file.")
    done: Any = await db.execute(text(
        "UPDATE complaint_attachment SET deleted_at = now(), deleted_by = CAST(:me AS uuid) "
        "WHERE id = CAST(:a AS uuid) AND deleted_at IS NULL"), {"a": attachment_id, "me": caller.user_id})
    if done.rowcount == 0:
        raise NotFoundError("No such file.")
    lead = (await db.execute(text("SELECT lead_id FROM complaint WHERE id = CAST(:c AS uuid)"),
                             {"c": complaint_id})).scalar_one_or_none()
    await _event(db, complaint_id, lead, "complaint.attachment_removed", caller, attachment_id=attachment_id)


# ── the targets ──────────────────────────────────────────────────────────────

async def sla_policies(db: AsyncSession) -> list[sch.SlaPolicy]:
    rows = (await db.execute(text(
        "SELECT *, severity::text AS sev FROM complaint_sla_policy "
        "ORDER BY severity, complaint_type_id NULLS FIRST, effective_from"))).all()
    return [sch.SlaPolicy(id=str(r.id), severity=r.sev,
                          complaint_type_id=str(r.complaint_type_id) if r.complaint_type_id else None,
                          response_hours=r.response_hours, resolution_hours=r.resolution_hours,
                          business_hours_only=r.business_hours_only, effective_from=r.effective_from.isoformat(),
                          effective_to=_iso(r.effective_to)) for r in rows]


async def set_sla_policy(db: AsyncSession, body: sch.SlaPolicyIn) -> list[sch.SlaPolicy]:
    if body.resolution_hours < body.response_hours:
        raise ValidationFailed(fields={"resolution_hours": "not less than the response target"})
    await _definer(db,
                   "SELECT complaint_sla_policy_set(CAST(:s AS complaint_severity), CAST(:t AS uuid), :rh, :sh, "
                   ":bh, :f)",
                   {"s": body.severity, "t": body.complaint_type_id, "rh": body.response_hours,
                    "sh": body.resolution_hours, "bh": body.business_hours_only, "f": body.effective_from})
    return await sla_policies(db)
