# ruff: noqa: E501  (embedded SQL)

"""Dealer applications (FS-051). Every write goes through a definer in migration
062; the staff side reads under `dealer_application_sel`, the applicant's side by
the token's hash and a session stored on the row."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.domain import complaints as files
from api.domain import gstin as gst
from api.domain.auth import generate_otp
from api.domain.identity import MobileError, mobile_for_user
from api.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationFailed,
)
from api.integrations import gst as gst_provider
from api.schemas import dealer_applications as sch
from api.services import people
from api.services.complaints import _safe_filename
from api.storage import Storage

log = structlog.get_logger()

LINK_DAYS = 30
SESSION_SECONDS = 2 * 60 * 60
CODE_SECONDS = 10 * 60
_PAN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_PIN = re.compile(r"^[1-9][0-9]{5}$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_ACCOUNT = re.compile(r"^[0-9]{6,20}$")


def _state(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _code_hash(token_hash: str, code: str) -> str:
    """An HMAC, not a bare hash: six digits hash in no time (FS-001 section 4)."""
    secret = get_settings().jwt_secret.get_secret_value().encode()
    return hmac.new(secret, f"{token_hash}:{code}".encode(), hashlib.sha256).hexdigest()


def _apply_url(token: str) -> str:
    return f"{get_settings().public_web_url.strip().rstrip('/')}/dealer-apply/{token}"


def _raise_for(exc: DBAPIError) -> None:
    code = _state(exc)
    msg = str(getattr(exc, "orig", exc))
    mapping: dict[str, Exception] = {
        "DAPNF": NotFoundError("No such application."),
        "DAPCL": ConflictError("This application is closed to changes.", code="application_closed"),
        "DAPDC": ConflictError("This application has already been decided.", code="already_decided"),
        "DAPMU": ConflictError("This mobile already signs someone in.", code="mobile_in_use"),
        "DAPOP": ConflictError("An open application already has this mobile.", code="application_open"),
        "DAPCD": ConflictError("That partner code is taken.", code="code_in_use"),
        "DAPFB": ForbiddenError("Only a State Manager or above, other than whoever started it, decides."),
        "DAPRM": ValidationFailed(fields={"remark": "required to reject or return"}),
        "DAPPR": ValidationFailed(fields={"parent_id": "not an active distributor"}),
        "DAPPN": ValidationFailed(fields={"pan": "not the PAN inside the GSTIN"}),
        "DAPTR": ValidationFailed(fields={"territory_id": "outside your scope"}),
        "DAPLD": ValidationFailed(fields={"lead_id": "not a lead you can see"}),
        "42501": ForbiddenError("Dealer applications are for staff who see partners."),
    }
    if code == "DAPMS":
        missing = msg.split("missing:", 1)[-1].split("\n")[0].strip()
        raise ValidationFailed("Something is still missing.", code="application_incomplete",
                               fields={m.strip(): "required" for m in missing.split(",") if m.strip()}) from exc
    if code in mapping:
        raise mapping[code] from exc


def _clean_fields(body: sch.DealerApplicationFields) -> dict[str, Any]:
    """The fields sent, upper-cased and checked against channel_partner's own shapes, so
    approval never fails on a CHECK weeks later (edge E-7)."""
    out: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name in body.model_fields_set:
        value = getattr(body, name)
        if isinstance(value, str):
            value = value.strip()
            if name in ("gstin", "pan", "bank_ifsc"):
                value = value.upper()
        if value in ("", None):
            out[name] = ""
            continue
        if name == "gstin":
            facts = gst.read(value)
            if not facts.valid:
                errors[name] = facts.reason or "not a valid GSTIN"
        elif name == "pan" and not _PAN.match(value):
            errors[name] = "10 characters: 5 letters, 4 digits, a letter"
        elif name == "pincode" and not _PIN.match(value):
            errors[name] = "6 digits"
        elif name == "bank_ifsc" and not _IFSC.match(value):
            errors[name] = "11 characters: 4 letters, 0, then 6 letters or digits"
        elif name == "bank_account_no" and not _ACCOUNT.match(value):
            errors[name] = "6 to 20 digits"
        out[name] = value
    if errors:
        raise ValidationFailed(fields=errors)
    return out


async def lookup(raw: str) -> sch.DealerGstLookup:
    """The GSTIN read from itself, then its details from the provider when one is
    configured (FS-053). An invalid GSTIN never spends a provider lookup."""
    facts = gst.read(raw)
    found: str = "unavailable"
    details: dict[str, Any] = {}
    if facts.valid:
        found, details = await gst_provider.fetch(facts.gstin, get_settings())
    return sch.DealerGstLookup(gstin=facts.gstin, valid=facts.valid, reason=facts.reason,
                               state_code=facts.state_code, pan=facts.pan, lookup=found,  # type: ignore[arg-type]
                               legal_name=details.get("legal_name"), trade_name=details.get("trade_name"),
                               address=details.get("address"), status=details.get("status"))


# ── staff ────────────────────────────────────────────────────────────────────

_SELECT = """SELECT a.*, t.name AS territory_name, cb.full_name AS created_by_name, db.full_name AS decided_by_name,
       dealer_application_missing(a.id) AS missing
  FROM dealer_application a JOIN territory t ON t.id = a.territory_id
  LEFT JOIN app_user cb ON cb.id = a.created_by LEFT JOIN app_user db ON db.id = a.decided_by """


async def _can_decide(db: AsyncSession, caller: Caller, row: Any) -> bool:
    if row.status != "submitted" or str(row.created_by) == caller.user_id:
        return False
    r = (await db.execute(text(
        "SELECT (NOT r.is_functional AND NOT r.is_portal AND r.level >= 3) "
        "OR (app_has_permission('partners', 'create') AND app_scope('partners') = 'global') "
        "FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = app_current_user_id()"))).scalar_one_or_none()
    return bool(r)


async def get(db: AsyncSession, caller: Caller, app_id: str, *, apply_url: str | None = None) -> sch.DealerApplication:
    row = (await db.execute(text(_SELECT + "WHERE a.id = CAST(:i AS uuid)"), {"i": app_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such application.")
    names = await people.resolve(db, [row], [("created_by", "created_by_name"), ("decided_by", "decided_by_name")])
    decide = await _can_decide(db, caller, row)
    sees_bank = decide or "partners" in caller.deletes or (await db.execute(
        text("SELECT app_has_permission('partners', 'edit')"))).scalar_one()
    acct = row.bank_account_no
    open_ = row.status in ("draft", "returned", "submitted")
    return sch.DealerApplication(
        id=str(row.id), status=row.status, firm_name=row.firm_name, contact_name=row.contact_name,
        mobile=row.mobile, territory={"id": str(row.territory_id), "name": row.territory_name},
        lead_id=str(row.lead_id) if row.lead_id else None, firm_type=row.firm_type,
        gst_registered=row.gst_registered, gstin=row.gstin, pan=row.pan, address=row.address,
        pincode=row.pincode, email=row.email, godown_address=row.godown_address,
        years_in_business=row.years_in_business, current_brands=row.current_brands, notes=row.notes,
        bank_account_name=row.bank_account_name,
        bank_account_no=acct if (sees_bank or acct is None) else "x" * max(len(acct) - 4, 0) + acct[-4:],
        bank_ifsc=row.bank_ifsc, gst_lookup=row.gst_lookup, gst_state_mismatch=row.gst_state_mismatch,
        missing=list(row.missing or []), partner_id=str(row.partner_id) if row.partner_id else None,
        user_id=str(row.user_id) if row.user_id else None,
        decided_by=names.user(row.decided_by, row.decided_by_name) if row.decided_by else None,
        decided_at=row.decided_at.isoformat() if row.decided_at else None,
        decision_remark=row.decision_remark, link_expires_at=row.link_expires_at.isoformat(),
        apply_url=apply_url, created_by=names.user(row.created_by, row.created_by_name),
        created_at=row.created_at.isoformat(),
        can={"edit": open_, "decide": decide, "withdraw": open_, "renew": row.status in ("draft", "returned")})


async def list_(db: AsyncSession, caller: Caller, *, status: str | None, q: str | None) -> list[sch.DealerApplicationRow]:
    if caller.partner_id is not None:
        raise ForbiddenError("Dealer applications are for staff.")
    where: list[str] = ["TRUE"]
    params: dict[str, Any] = {}
    if status:
        where.append("a.status = ANY(CAST(:s AS text[]))")
        params["s"] = [x.strip() for x in status.split(",") if x.strip()]
    if q:
        where.append("(a.firm_name ILIKE :q OR a.contact_name ILIKE :q OR a.mobile LIKE :q)")
        params["q"] = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = (await db.execute(text(
        "SELECT a.id, a.status, a.firm_name, a.contact_name, t.name AS territory_name, a.created_at, a.submitted_at "
        "FROM dealer_application a JOIN territory t ON t.id = a.territory_id WHERE " + " AND ".join(where) +
        " ORDER BY a.created_at DESC LIMIT 200"), params)).all()
    return [sch.DealerApplicationRow(id=str(r.id), status=r.status, firm_name=r.firm_name, contact_name=r.contact_name,
                               territory_name=r.territory_name, created_at=r.created_at.isoformat(),
                               submitted_at=r.submitted_at.isoformat() if r.submitted_at else None) for r in rows]


async def create(db: AsyncSession, caller: Caller, body: sch.DealerApplicationCreate) -> sch.DealerApplication:
    if caller.partner_id is not None:
        raise ForbiddenError("Dealer applications are for staff.")
    try:
        mobile = mobile_for_user(body.mobile)
    except MobileError as exc:
        raise ValidationFailed(fields={"mobile": "not an Indian mobile number"}) from exc
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=LINK_DAYS)
    try:
        async with db.begin_nested():
            app_id = (await db.execute(text(
                "SELECT dealer_application_create(:f, :c, :m, CAST(:t AS uuid), CAST(:l AS uuid), :h, :e)"),
                {"f": body.firm_name, "c": body.contact_name, "m": mobile, "t": body.territory_id,
                 "l": body.lead_id, "h": _hash(token), "e": expires})).scalar_one()
    except DBAPIError as exc:
        _raise_for(exc)
        raise
    return await get(db, caller, str(app_id), apply_url=_apply_url(token))


async def start_from_lead(db: AsyncSession, caller: Caller, *, lead_id: str, firm: str,
                          mobile: str, territory_id: str) -> Any:
    """FS-053: a dealership lead won starts its dealer application. The lead stays won
    when it cannot (the mobile signs someone in, or an application is open): the
    answer says why."""
    from api.schemas.leads import DealerApplicationStarted
    try:
        mobile_db = mobile_for_user(mobile)
    except MobileError:
        return DealerApplicationStarted(id=None, apply_url=None, not_started="mobile_invalid")
    token = secrets.token_urlsafe(32)
    try:
        async with db.begin_nested():
            app_id = (await db.execute(text(
                "SELECT dealer_application_create(:f, :c, :m, CAST(:t AS uuid), CAST(:l AS uuid), :h, :e)"),
                {"f": firm, "c": firm, "m": mobile_db, "t": territory_id, "l": lead_id,
                 "h": _hash(token), "e": datetime.now(UTC) + timedelta(days=LINK_DAYS)})).scalar_one()
    except DBAPIError as exc:
        reason = {"DAPMU": "mobile_in_use", "DAPOP": "application_open"}.get(_state(exc) or "")
        if reason is None:
            raise
        return DealerApplicationStarted(id=None, apply_url=None, not_started=reason)
    return DealerApplicationStarted(id=str(app_id), apply_url=_apply_url(token), not_started=None)


async def staff_action(db: AsyncSession, caller: Caller, app_id: str, action: str, *,
                       fields: dict[str, Any] | None = None, remark: str | None = None) -> sch.DealerApplication:
    if caller.partner_id is not None:
        raise ForbiddenError("Dealer applications are for staff.")
    token = expires = None
    if action == "renew":
        token = secrets.token_urlsafe(32)
        expires = datetime.now(UTC) + timedelta(days=LINK_DAYS)
    try:
        async with db.begin_nested():
            await db.execute(text(
                "SELECT dealer_application_staff(CAST(:i AS uuid), :a, CAST(:f AS jsonb), :r, :h, :e)"),
                {"i": app_id, "a": action, "f": json.dumps(fields or {}), "r": remark,
                 "h": _hash(token) if token else None, "e": expires})
    except DBAPIError as exc:
        _raise_for(exc)
        raise
    return await get(db, caller, app_id, apply_url=_apply_url(token) if token else None)


async def decide(db: AsyncSession, caller: Caller, app_id: str, body: sch.DealerApplicationDecision) -> sch.DealerApplication:
    if caller.partner_id is not None:
        raise ForbiddenError("Dealer applications are for staff.")
    try:
        async with db.begin_nested():
            await db.execute(text(
                "SELECT * FROM dealer_application_decide(CAST(:i AS uuid), :d, :r, CAST(:p AS uuid), :c)"),
                {"i": app_id, "d": body.decision, "r": body.remark, "p": body.parent_id, "c": body.code})
    except DBAPIError as exc:
        _raise_for(exc)
        raise
    return await get(db, caller, app_id)


# ── the applicant ────────────────────────────────────────────────────────────

async def view(db: AsyncSession, token: str, session: str | None) -> dict[str, Any]:
    got = (await db.execute(text("SELECT dealer_apply_view(:t, :s)"),
                            {"t": _hash(token), "s": _hash(session) if session else None})).scalar_one()
    if got is None:
        raise NotFoundError("This link is not valid.")
    return dict(got)


async def send_code(db: AsyncSession, token: str) -> None:
    code = generate_otp(get_settings().otp_length)
    th = _hash(token)
    outcome = (await db.execute(text("SELECT dealer_apply_issue_code(:t, :c, :h, :ttl)"),
                                {"t": th, "c": code, "h": _code_hash(th, code), "ttl": CODE_SECONDS})).scalar_one()
    if outcome == "not_found":
        raise NotFoundError("This link is not valid.")
    if outcome == "too_soon":
        raise ValidationFailed("Wait a minute before asking for another code.", code="rate_limited")
    if outcome == "rate_limited":
        raise ValidationFailed("Too many codes today. Try again tomorrow, or ask us for help.",
                               code="rate_limited")


async def check_code(db: AsyncSession, token: str, code: str) -> sch.DealerApplicantSession | None:
    """None for a wrong code. The router answers 422 without raising, so the attempt
    count written by the definer commits: raising rolls the transaction back, and the
    five-try burn would never happen (code review, critical)."""
    th = _hash(token)
    session = secrets.token_urlsafe(32)
    outcome = (await db.execute(text("SELECT dealer_apply_check_code(:t, :h, :s, :ttl)"),
                                {"t": th, "h": _code_hash(th, code.strip()), "s": _hash(session),
                                 "ttl": SESSION_SECONDS})).scalar_one()
    return sch.DealerApplicantSession(session=session) if outcome == "ok" else None


async def applicant_write(db: AsyncSession, token: str, session: str | None, action: str,
                          fields: dict[str, Any] | None = None) -> None:
    if not session:
        raise ForbiddenError("Verify your mobile first.", code="no_session")
    th = _hash(token)
    try:
        async with db.begin_nested():
            outcome = (await db.execute(text("SELECT dealer_apply_write(:t, :s, :a, CAST(:f AS jsonb))"),
                                        {"t": th, "s": _hash(session), "a": action,
                                         "f": json.dumps(fields or {})})).scalar_one()
    except DBAPIError as exc:
        _raise_for(exc)
        raise
    if outcome == "not_found":
        raise NotFoundError("This link is not valid.")
    if outcome == "no_session":
        raise ForbiddenError("Verify your mobile again.", code="no_session")
    if outcome == "closed":
        raise ConflictError("This application is closed to changes.", code="application_closed")
    if outcome.startswith("missing:"):
        raise ValidationFailed("Something is still missing.", code="application_incomplete",
                               fields={m: "required" for m in outcome[8:].split(",") if m})


async def applicant_document(db: AsyncSession, token: str, session: str | None, *, doc_type: str,
                             name: str | None, filename: str | None, data: bytes, storage: Storage) -> dict[str, Any]:
    if not session:
        raise ForbiddenError("Verify your mobile first.", code="no_session")
    if not data or len(data) > files.MAX_UPLOAD_BYTES:
        raise ValidationFailed(fields={"file": "1 byte to 10 MB"})
    sniffed = files.sniff(data[:16])
    if sniffed is None:
        raise ValidationFailed("JPEG, PNG, WebP, HEIC or PDF only.", code="attachment_type",
                               fields={"file": "not an allowed type"})
    th, sh = _hash(token), _hash(session)
    app_id = (await db.execute(text("SELECT dealer_apply_session(:t, :s)"), {"t": th, "s": sh})).scalar_one()
    if app_id is None:
        raise ForbiddenError("Verify your mobile again.", code="no_session")
    key = f"documents/dealer_application/{app_id}/{uuid.uuid4().hex}.{sniffed.extension}"
    try:
        await asyncio.to_thread(storage.put, key, data, sniffed.content_type)
    except Exception as exc:
        log.warning("dealer_apply.storage_unavailable", error=type(exc).__name__)
        raise ServiceUnavailableError("Files cannot be stored right now; try again later.",
                                      code="storage_unavailable") from exc
    try:
        async with db.begin_nested():
            row = (await db.execute(text(
                "SELECT * FROM dealer_apply_document(:t, :s, :k, :n, :key, :fn, :ct, :sz, :h)"),
                {"t": th, "s": sh, "k": doc_type, "n": name, "key": key,
                 "fn": _safe_filename(filename, sniffed.extension), "ct": sniffed.content_type,
                 "sz": len(data), "h": hashlib.sha256(data).hexdigest()})).one()
    except DBAPIError as exc:
        if _state(exc) == "DAPSS":
            raise ForbiddenError("Verify your mobile again.", code="no_session") from exc
        if _state(exc) == "DOCMX":
            raise ValidationFailed("Up to 50 documents.", code="too_many_documents") from exc
        raise
    return {"id": str(row.id), "created": bool(row.created)}


async def applicant_document_remove(db: AsyncSession, token: str, session: str | None, doc_id: str) -> None:
    if not session:
        raise ForbiddenError("Verify your mobile first.", code="no_session")
    outcome = (await db.execute(text("SELECT dealer_apply_document_remove(:t, :s, CAST(:d AS uuid))"),
                                {"t": _hash(token), "s": _hash(session), "d": doc_id})).scalar_one()
    if outcome == "no_session":
        raise ForbiddenError("Verify your mobile again.", code="no_session")
    if outcome == "not_found":
        raise NotFoundError("No such document of yours.")

