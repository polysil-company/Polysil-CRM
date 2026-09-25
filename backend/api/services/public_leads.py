"""Public lead capture: the website form and QR codes (FS-003a).

The public half runs without a sign-in. The form's lists and the code request go
through definers as `app_anon`; the lead itself is created inside
`deps.intake_session`, which sets the intake principal's claim only after the
WhatsApp code matched. Nothing here returns existing data beyond the caller's own
inquiry number (rule 6).

The staff half manages the printed codes under the caller's leads scope.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.deps import intake_session
from api.domain import leads as lead_domain
from api.domain.auth import generate_otp, hash_otp
from api.errors import NotFoundError, RateLimitedError, ValidationFailed
from api.schemas import public_leads as sch
from api.schemas.leads import LeadCreate, PartnerRef, TerritoryRef
from api.services import leads as lead_service
from api.services.clock import IST, today_ist

log = structlog.get_logger()

# FS-003a §4: six characters, no 0/O or 1/I, so a code read aloud or retyped from
# a poster is not mistaken
QR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
QR_LENGTH = 6
RESEND_AFTER = 60


def _mobile(raw: str) -> str:
    try:
        return lead_domain.normalise_mobile(raw)
    except lead_domain.MobileError as exc:
        raise ValidationFailed(fields={"mobile": str(exc)}) from exc


# ── the form ──────────────────────────────────────────────────────────────────

async def form(db: AsyncSession, qr: str | None) -> sch.PublicLeadForm:
    code = None
    if qr:
        row = (await db.execute(text(
            "SELECT code, label, campaign, territory_id FROM lead_qr_public(:c)"),
            {"c": qr.strip().upper()})).one_or_none()
        if row is None:
            raise NotFoundError("This QR code is not in use.")
        code = sch.PublicQr(code=row.code, label=row.label, campaign=row.campaign,
                            territory_id=str(row.territory_id) if row.territory_id else None)
    lists: dict[str, Any] = (await db.execute(text("SELECT lead_public_form()"))).scalar_one()
    return sch.PublicLeadForm(
        qr=code, states=[sch.PublicState(id=str(x["id"]), name=x["name"]) for x in lists["states"]],
        mis_systems=[sch.PublicSystem(code=x["code"], name=x["name"])
                     for x in lists["mis_systems"]],
        inquiry_types=list(lists["inquiry_types"]))


async def territories(db: AsyncSession, parent_id: str) -> list[sch.PublicTerritory]:
    rows = (await db.execute(text(
        "SELECT id, name, level FROM lead_public_territories(CAST(:p AS uuid))"),
        {"p": parent_id})).all()
    return [sch.PublicTerritory(id=str(r.id), name=r.name, level=r.level) for r in rows]


# ── the code ──────────────────────────────────────────────────────────────────

async def request_code(db: AsyncSession, raw_mobile: str, ip: str | None) -> sch.VerifySent:
    """Rule 5 and 9. Over a per-number or per-address limit is a 429 (the form
    looks nobody up, so it reveals nothing); over the global ceiling answers like
    success and writes nothing, with an error-level log."""
    settings = get_settings()
    mobile = _mobile(raw_mobile)
    code = generate_otp(6)
    outcome: str = (await db.execute(text(
        "SELECT lead_intake_issue(:m, CAST(:ip AS inet), :c, :h, :ttl, :per_ip, :per_hour)"),
        {"m": mobile, "ip": ip, "c": code, "h": hash_otp(code),
         "ttl": settings.public_lead_code_ttl_seconds,
         "per_ip": settings.public_lead_codes_per_ip_per_hour,
         "per_hour": settings.public_lead_codes_per_hour})).scalar_one()
    if outcome == "rate_limited":
        raise RateLimitedError()
    if outcome == "suppressed":
        log.error("public_lead.code_ceiling_reached", per_hour=settings.public_lead_codes_per_hour)
    return sch.VerifySent(expires_in=settings.public_lead_code_ttl_seconds,
                          resend_after=RESEND_AFTER)


# ── the lead ──────────────────────────────────────────────────────────────────

async def submit(body: sch.PublicLeadCreate) -> tuple[int, sch.PublicLeadResult]:
    """201 with a new number, or 200 with the earlier one (a replay, or a second
    enquiry from this mobile today). A wrong code leaves the session normally, so
    its attempt count commits; a failure while creating raises inside it, so the
    code's consumption rolls back and the farmer can submit again (EC-3)."""
    mobile = _mobile(body.mobile)
    refused = None
    result: tuple[int, sch.PublicLeadResult] | None = None
    async with intake_session(mobile, hash_otp(body.code)) as it:
        if it.outcome != "ok" or it.session is None:
            refused = it
        else:
            result = await _create(it.session, it.challenge_id, body, mobile)
    if refused is not None:
        if refused.outcome == "replay" and refused.inquiry_no:
            return 200, sch.PublicLeadResult(inquiry_no=refused.inquiry_no, created=False)
        raise ValidationFailed("The code is wrong or has expired. Ask for a new one.",
                               code="invalid_code", fields={"code": "wrong or expired"})
    assert result is not None
    return result


async def _create(db: AsyncSession, challenge_id: str | None, body: sch.PublicLeadCreate,
                  mobile: str) -> tuple[int, sch.PublicLeadResult]:
    """Under the intake claim, after the code matched."""
    settings = get_settings()
    level = (await db.execute(text(
        "SELECT level::text FROM territory WHERE id = CAST(:t AS uuid) AND deleted_at IS NULL"),
        {"t": body.territory_id})).scalar_one_or_none()
    if level not in ("district", "taluka"):
        raise ValidationFailed(fields={"territory_id": "choose a district or taluka"})

    # rule 4: one public lead per mobile per IST day
    day_start = datetime.combine(today_ist(), datetime.min.time(), tzinfo=IST)
    earlier = (await db.execute(text(
        "SELECT id, inquiry_no::text AS inquiry_no FROM lead WHERE mobile = :m "
        "AND created_by = CAST(:i AS uuid) AND created_at >= :d AND deleted_at IS NULL "
        "ORDER BY created_at LIMIT 1"),
        {"m": mobile, "i": settings.intake_user_id, "d": day_start})).one_or_none()
    if earlier is not None:
        await _record(db, challenge_id, str(earlier.id))
        return 200, sch.PublicLeadResult(inquiry_no=earlier.inquiry_no, created=False)

    qr = await _qr(db, body.qr)
    caller = Caller(settings.intake_user_id, None, None, scopes={"leads": "global"})
    lead = await lead_service.create_lead(
        db, caller,
        LeadCreate(farmer_name=body.farmer_name, mobile=mobile,
                   territory_id=body.territory_id, village=body.village,
                   mis_system=body.mis_system, inquiry_type=body.inquiry_type,
                   note=body.note, source="qr_code" if qr else "website",
                   email=None, estimated_value=None),
        intake=True, intake_partner_id=qr[1] if qr else None,
        qr_code_id=qr[0] if qr else None)
    await _record(db, challenge_id, lead.id)
    return 201, sch.PublicLeadResult(inquiry_no=lead.inquiry_no, created=True)


async def _record(db: AsyncSession, challenge_id: str | None, lead_id: str) -> None:
    await db.execute(text("SELECT lead_intake_record(CAST(:c AS uuid), CAST(:l AS uuid))"),
                     {"c": challenge_id, "l": lead_id})


async def _qr(db: AsyncSession, code: str | None) -> tuple[str, str | None] | None:
    """The code's id and partner. An unknown or inactive code, or one whose
    partner closed, is ignored: the lead is still captured, as `website` (rule 2)."""
    if not code:
        return None
    row = (await db.execute(text(
        "SELECT q.id, q.partner_id FROM lead_qr_code q "
        "LEFT JOIN channel_partner cp ON cp.id = q.partner_id "
        "WHERE q.code = CAST(:c AS citext) AND q.is_active "
        "AND (q.partner_id IS NULL OR (cp.is_active AND cp.deleted_at IS NULL))"),
        {"c": code.strip().upper()})).one_or_none()
    if row is None:
        return None
    return str(row.id), str(row.partner_id) if row.partner_id else None


# ── staff: the printed codes ──────────────────────────────────────────────────

_QR_SELECT = """
SELECT q.id, q.code::text AS code, q.label, q.campaign, q.is_active, q.created_at,
       q.partner_id, cp.name AS partner_name, cp.partner_type::text AS partner_type,
       q.territory_id, t.name AS territory_name, t.level::text AS territory_level,
       (SELECT count(*) FROM lead l WHERE l.qr_code_id = q.id) AS lead_count
  FROM lead_qr_code q
  LEFT JOIN channel_partner cp ON cp.id = q.partner_id
  LEFT JOIN territory t ON t.id = q.territory_id"""


def _qr_out(r: Any) -> sch.QrCode:
    base = get_settings().public_web_url.rstrip("/")
    return sch.QrCode(
        id=str(r.id), code=r.code, url=f"{base}/enquiry?qr={r.code}", label=r.label,
        campaign=r.campaign, is_active=r.is_active, lead_count=int(r.lead_count),
        partner=(PartnerRef(id=str(r.partner_id), name=r.partner_name,
                            partner_type=r.partner_type) if r.partner_id and r.partner_name
                 else None),
        territory=(TerritoryRef(id=str(r.territory_id), name=r.territory_name,
                                level=r.territory_level) if r.territory_id else None),
        created_at=r.created_at.isoformat())


async def create_qr(db: AsyncSession, caller: Caller, body: sch.QrCodeCreate) -> sch.QrCode:
    unit = caller.org_unit_id
    if unit is None:
        raise ValidationFailed("Only staff create QR codes.", fields={"partner_id": "staff only"})
    if body.partner_id is not None:
        # read under the caller's own policies: the insert policy checks the owning
        # office only, and the foreign key sees every dealer. Without this a manager
        # could credit a code, and every farmer it brings, to a dealer outside their
        # area (code review F-2).
        seen = (await db.execute(text(
            "SELECT 1 FROM channel_partner WHERE id = CAST(:p AS uuid) AND is_active "
            "AND deleted_at IS NULL"), {"p": body.partner_id})).one_or_none()
        if seen is None:
            raise ValidationFailed(fields={"partner_id": "not found"})
    for _ in range(5):
        code = "".join(secrets.choice(QR_ALPHABET) for _ in range(QR_LENGTH))
        try:
            async with db.begin_nested():
                new_id: Any = (await db.execute(text(
                    "INSERT INTO lead_qr_code (code, label, campaign, partner_id, territory_id, "
                    "owner_org_unit_id, created_by, updated_by) VALUES (:c, :l, :cmp, "
                    "CAST(:p AS uuid), CAST(:t AS uuid), CAST(:u AS uuid), CAST(:me AS uuid), "
                    "CAST(:me AS uuid)) RETURNING id"),
                    {"c": code, "l": body.label, "cmp": body.campaign, "p": body.partner_id,
                     "t": body.territory_id, "u": unit, "me": caller.user_id})).scalar_one()
        except IntegrityError as exc:
            if "uq_lead_qr_code_code" in str(exc.orig):
                continue       # a collision in 32^6; try another
            raise ValidationFailed(fields={"partner_id": "not found",
                                           "territory_id": "not found"}) from exc
        except DBAPIError as exc:
            # the row policy's WITH CHECK: a territory-scoped caller must name a
            # territory of theirs (code review F-4); anything else is not ours to map
            if getattr(exc.orig, "sqlstate", None) != "42501":
                raise
            raise ValidationFailed(
                fields={"territory_id": "choose a territory in your area"}) from exc
        # CLAUDE.md 4.1 rule 7, in the same transaction (cross-vendor review); read
        # through the code's own visibility (activity.py ENTITY_BY_ID)
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
            "VALUES ('lead_qr_code', :i, 'lead_qr_code.created', CAST(:me AS uuid), "
            "jsonb_build_object('code', CAST(:c AS text), 'label', CAST(:l AS text), "
            "'partner_id', CAST(:p AS text), 'territory_id', CAST(:t AS text)))"),
            {"i": new_id, "me": caller.user_id, "c": code, "l": body.label,
             "p": body.partner_id, "t": body.territory_id})
        row = (await db.execute(text(_QR_SELECT + " WHERE q.id = :i"), {"i": new_id})).one()
        return _qr_out(row)
    raise RuntimeError("no free QR code after five tries")


async def list_qr(db: AsyncSession) -> sch.QrCodeList:
    rows = (await db.execute(text(_QR_SELECT + " ORDER BY q.created_at DESC LIMIT 500"))).all()
    return sch.QrCodeList(data=[_qr_out(r) for r in rows])
