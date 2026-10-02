"""Quotations (FS-005): every transaction.

The save, the freeze, the number, the link and the lifecycle around the pricing
preview FS-010 shipped. Every line is re-resolved through the one pricing
pipeline (`pricing.price_document`) at save and again at send, and a difference
from what the preview showed is `409 rate_changed`, never a silent repricing
(rule 4).

**Lock order: the lead first, then quotation rows lower version first, then the
counter.** `assign_lead`, `patch_lead` and `lead_merge()` lock the lead and then,
through the propagation trigger, its quotations; a send that locked the
quotation first would deadlock against a concurrent reassignment. So every
mutation, `create()` included, calls `lead_lock_for_quotation()` before touching
a quotation row. Every status change is a `text()` statement: the session has
`autoflush=False`, and `lead_stage_from_quotation()` reads the row.

The lead is never written here. `lead_stage_from_quotation()` (definer) moves it
after the quotation's own status has changed, bound to the document whose state
justifies the move, and writes the lead's event itself. This module writes only
quotation events.

Nothing here makes a network call. The render, the upload and the outbox row
are the worker's (`worker/jobs/quotations.py`); `send()` is database-only.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import sqlalchemy as sa
import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.config import Settings
from api.domain import leads as leads_domain
from api.domain import orders as order_domain
from api.domain import quotations as domain
from api.domain.identity import normalise_mobile
from api.domain.pricing.types import PricedLine
from api.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailed
from api.schemas import quotations as sch
from api.schemas.leads import (
    OrgUnitRef,
    PageMeta,
    PartnerRef,
    TerritoryRef,
    TimelineEvent,
    TimelinePage,
    UserRef,
)
from api.services import approval_view, people, pricing
from api.services.clock import IST, today_ist
from api.services.leads import _capped_total, _decode_cursor, _encode_cursor
from api.services.pricing import LineSpec, PricedContext, _rate, _s
from api.storage import Storage

_QUOTATIONS = SPECS["quotations"]
_MAX_LIMIT = 100

_UUID = sa.Uuid()
_TS = sa.DateTime(timezone=True)
quotation_t = sa.table(
    "quotation",
    sa.column("id", _UUID),
    sa.column("created_at", _TS),
    sa.column("status"),
    sa.column("sales_type"),
    sa.column("lead_id", _UUID),
    sa.column("owner_user_id", _UUID),
    sa.column("owner_org_unit_id", _UUID),
    sa.column("territory_id", _UUID),
    sa.column("partner_id", _UUID),
    sa.column("deleted_at", _TS),
    sa.column("party_name"),
    sa.column("party_mobile"),
    sa.column("quote_no"),
    sa.column("superseded_by_id", _UUID),
)

# The document, with the people and masters it names. The lead and the people
# are RLS-filtered LEFT JOINs and may come back null for a caller who can see the
# quotation but not the row (the lead block is nullable by contract, §4). The
# seller block is the master while draft and the row's own snapshot once sent, by
# status and not by COALESCE: a sent row's null address is null, not the master's
# current one (rule 3; code review F-5).
_Q_SELECT = """
SELECT q.id, q.quote_no, q.version, q.status, q.sales_type, q.source,
       q.lead_id, l.inquiry_no AS lead_inquiry_no, l.stage AS lead_stage,
       q.party_name, q.party_mobile, q.party_address, q.party_gstin,
       q.partner_id, cp.name AS partner_name, cp.partner_type AS partner_type,
       q.owner_user_id, ow.full_name AS owner_name,
       q.owner_org_unit_id, ou.name AS owner_org_unit_name,
       q.territory_id, t.name AS territory_name, t.level AS territory_level,
       q.seller_gstin_id,
       CASE WHEN q.status = 'draft' THEN sg.gstin ELSE q.seller_gstin_no END AS seller_gstin_no,
       CASE WHEN q.status = 'draft' THEN sg.legal_name ELSE q.seller_legal_name END
           AS seller_legal_name,
       CASE WHEN q.status = 'draft' THEN sg.address ELSE q.seller_address END AS seller_address,
       CASE WHEN q.status = 'draft' THEN sst.code ELSE q.seller_state_code END AS seller_state_code,
       q.place_of_supply_territory_id, pt.name AS pos_name, pt.level AS pos_level,
       ps.code AS pos_state_code,
       q.intra_state, q.price_effective_date,
       q.price_list_id, pl.name AS price_list_name,
       q.gross, q.discount, q.taxable, q.cgst, q.sgst, q.igst, q.total,
       q.is_provisional, q.terms, q.valid_until, q.sent_at, q.viewed_at, q.open_count,
       q.accepted_at, q.rejected_at, q.decided_by, dbu.full_name AS decided_by_name,
       q.decision_remark,
       q.supersedes_id, sv.version AS supersedes_version,
       q.superseded_by_id, sb.version AS superseded_by_version,
       q.share_token, q.pdf_state, q.pdf_key, q.pdf_error, q.notify_channel,
       q.created_at, q.created_by, cb.full_name AS created_by_name, q.updated_at,
       -- whoever sees the quotation sees its requests (017's policy): the list's
       -- "Awaiting approval" (the frontend walk, 29 Sep)
       EXISTS (SELECT 1 FROM approval_request ar WHERE ar.doc_type = 'quotation'
                  AND ar.entity_id = q.id AND ar.status = 'pending') AS awaiting_approval
  FROM quotation q
  JOIN org_unit ou ON ou.id = q.owner_org_unit_id
  JOIN territory t ON t.id = q.territory_id
  JOIN territory pt ON pt.id = q.place_of_supply_territory_id
  JOIN territory ps ON ps.id = q.place_of_supply_state_id
  LEFT JOIN lead l ON l.id = q.lead_id
  LEFT JOIN channel_partner cp ON cp.id = q.partner_id
  LEFT JOIN app_user ow ON ow.id = q.owner_user_id
  LEFT JOIN seller_gstin sg ON sg.id = q.seller_gstin_id
  LEFT JOIN territory sst ON sst.id = sg.state_territory_id
  LEFT JOIN price_list pl ON pl.id = q.price_list_id
  LEFT JOIN app_user dbu ON dbu.id = q.decided_by
  LEFT JOIN quotation sv ON sv.id = q.supersedes_id
  LEFT JOIN quotation sb ON sb.id = q.superseded_by_id
  LEFT JOIN app_user cb ON cb.id = q.created_by
"""

_LINE_SELECT = """
SELECT quotation_id, line_no, product_id, description, hsn_code, uom, qty, rate,
       price_list_id, price_list_item_id, gst_rate_id, gross,
       discount_pct, discount1_amt, after_discount1, discount2_pct, discount2_amt,
       after_discount2, discount3_pct, discount3_amt, discount, taxable,
       gst_slab, cgst_rate, sgst_rate, igst_rate, cgst, sgst, igst, total, provisional_fields
  FROM quotation_line WHERE quotation_id = ANY(CAST(:ids AS uuid[]))
 ORDER BY quotation_id, line_no
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def _iso(v: datetime | dt.date | None) -> str | None:
    return None if v is None else v.isoformat()


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)


def _pg_text(exc: DBAPIError) -> str:
    return str(getattr(exc.orig, "args", [""])[0] or exc.orig)


async def _actor_name(db: AsyncSession) -> str:
    return str((await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = (SELECT app_current_user_id())"))
    ).scalar_one())


async def _emit(db: AsyncSession, *, quotation_id: Any, lead_id: Any, kind: str,
                actor_id: str, actor_name: str, **payload: Any) -> None:
    """One quotation event. entity_id is the quotation and lead_id its lead, so the
    row is visible through the quotation and read by the lead's timeline. No
    payload carries a money figure (rule 17)."""
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('quotation', :q, :l, :kind, :me, CAST(:p AS jsonb))"),
        {"q": quotation_id, "l": lead_id, "kind": kind, "me": actor_id,
         "p": json.dumps({"actor_name": actor_name, **payload})})


async def _lock_lead(db: AsyncSession, lead_id: str, *, require_open: bool) -> str:
    """The first call of every mutation (lock order). Returns the lead's stage."""
    try:
        return str((await db.execute(
            text("SELECT lead_lock_for_quotation(CAST(:id AS uuid), :open)"),
            {"id": lead_id, "open": require_open})).scalar_one())
    except DBAPIError as exc:
        raise _map_lead_error(exc) from exc


def _map_lead_error(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc)
    if code == "LEADN":
        return NotFoundError("No such lead.")
    if code == "QLNOP":
        stage = _pg_text(exc).split("lead is ", 1)[-1].split("\n")[0].strip() or "closed"
        return ValidationFailed(
            f"The lead is {stage}, so this quotation cannot move. Reopen the lead first.",
            code="lead_not_open", fields={"lead_stage": stage})
    if code == "QLBND":
        return ConflictError("The quotation is not in a state that moves the lead.",
                             code="status_changed")
    if code == "42501":
        return ForbiddenError("Not permitted on this lead.")
    return exc


async def _stage_lead(db: AsyncSession, quotation_id: str, to: str) -> str:
    try:
        return str((await db.execute(
            text("SELECT lead_stage_from_quotation(CAST(:id AS uuid), :to)"),
            {"id": quotation_id, "to": to})).scalar_one())
    except DBAPIError as exc:
        raise _map_lead_error(exc) from exc


async def _lock_quotation(db: AsyncSession, quotation_id: str) -> Any:
    """SELECT ... FOR UPDATE under the quotation UPDATE policy: a row the caller
    may see but not edit locks nothing and reads as 404."""
    row = (await db.execute(text(
        "SELECT id, lead_id, quote_no, version, status::text AS status, sales_type::text AS "
        "sales_type, supersedes_id, superseded_by_id, valid_until, partner_id, "
        "place_of_supply_territory_id, seller_gstin_id, price_effective_date, party_name, "
        "party_mobile, party_address, party_gstin, terms, deleted_at, pdf_state, pdf_key "
        "FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL FOR UPDATE"),
        {"id": quotation_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such quotation.")
    return row


def _expect(row: Any, expected: str | None) -> None:
    if expected and expected != row.status:
        raise ConflictError(f"The quotation is now {row.status}.", code="status_changed",
                            fields={"status": row.status})


def _must_be_draft(row: Any) -> None:
    if row.status != "draft":
        raise ConflictError("Only a draft can be changed. Revise the quotation instead.",
                            code="quotation_not_draft", fields={"status": row.status})


def _check_sales_type(sales_type: str) -> None:
    if sales_type not in domain.SALES_TYPES_ACCEPTED:
        why = domain.SALES_TYPE_BLOCKED_ON[sales_type]
        raise ValidationFailed(f"{sales_type} quotations are not built yet: {why}.",
                               code="sales_type_unsupported", fields={"sales_type": sales_type})


def _party_from(lead: Any) -> dict[str, Any]:
    address = ", ".join(x for x in (lead.village, lead.territory_name) if x)
    return {"name": lead.farmer_name, "mobile": lead.mobile, "address": address or None,
            "gstin": None}


def _party_values(party: sch.Party | dict[str, Any]) -> dict[str, Any]:
    p = party.model_dump() if isinstance(party, sch.Party) else dict(party)
    mobile = normalise_mobile(p["mobile"])
    if mobile is None:
        raise ValidationFailed(fields={"party.mobile": "not an Indian mobile number"})
    return {"party_name": p["name"], "party_mobile": mobile, "party_address": p.get("address"),
            "party_gstin": p["gstin"].upper() if p.get("gstin") else None}


async def _lead_defaults(db: AsyncSession, lead_id: str) -> Any:
    """The lead as the caller sees it. The lock already proved visibility."""
    row = (await db.execute(text(
        "SELECT l.id, l.stage::text AS stage, l.inquiry_type::text AS inquiry_type, "
        "l.farmer_name, l.mobile, l.village, l.territory_id, t.name AS territory_name, "
        "l.assigned_partner_id, l.owner_user_id, l.owner_org_unit_id, l.merged_into_id "
        "FROM lead l JOIN territory t ON t.id = l.territory_id "
        "WHERE l.id = CAST(:id AS uuid)"), {"id": lead_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such lead.")
    return row


# ── pricing: the one pipeline, the comparison, the write ─────────────────────

async def _price(db: AsyncSession, *, partner_id: str | None, pos_territory_id: str,
                 seller_gstin_id: str | None, as_of: dt.date | None,
                 specs: list[LineSpec], existing: bool) -> PricedContext:
    try:
        return await pricing.price_document(
            db, partner_id=partner_id, place_of_supply_territory_id=pos_territory_id,
            seller_gstin_id=seller_gstin_id, as_of=as_of, lines=specs, existing=existing)
    except ValidationFailed as exc:
        # the pipeline speaks the preview's field name; a quotation's is
        # price_effective_date, and a screen attaches errors by field (PR #10 review)
        if exc.fields and "as_of" in exc.fields:
            exc.fields = {("price_effective_date" if k == "as_of" else k): v
                          for k, v in exc.fields.items()}
        raise


def _compare(lines: list[sch.QuotationLineIn], ctx: PricedContext) -> None:
    """Rule 4: what the preview showed against what resolves now. A difference is
    the whole request refused, naming the lines and the new figures."""
    fields: dict[str, str] = {}
    for i, (ln, priced) in enumerate(zip(lines, ctx.document.lines, strict=True)):
        if ln.price_list_item_id and ln.price_list_item_id != priced.rate.price_list_item_id:
            fields[f"lines[{i}].rate"] = f"now {_s(priced.rate.rate)}"
        if ln.gst_rate_id and ln.gst_rate_id != priced.tax.gst_rate_id:
            fields[f"lines[{i}].gst_slab"] = f"now {_rate(priced.tax.slab)}"
    if fields:
        raise ConflictError("Prices or tax changed since the preview. Review the new figures "
                            "and save again.", code="rate_changed", fields=fields)


_MONEY = ("gross", "discount", "taxable", "cgst", "sgst", "igst", "total")


def _compare_stored(stored: list[Any], ctx: PricedContext) -> None:
    """At send: the stored lines against a fresh resolution (a master moved under
    the draft). The two ids are not enough: a seller registration whose state
    changed flips CGST and SGST into IGST with neither id moving (cross-vendor
    A-1, reproduced). So every printed figure is compared as well."""
    fields: dict[str, str] = {}
    for i, (row, priced) in enumerate(zip(stored, ctx.document.lines, strict=True)):
        if str(row.price_list_item_id) != priced.rate.price_list_item_id:
            fields[f"lines[{i}].rate"] = f"{_s(row.rate)} -> {_s(priced.rate.rate)}"
        if str(row.gst_rate_id) != priced.tax.gst_rate_id:
            fields[f"lines[{i}].gst_slab"] = f"{_rate(row.gst_slab)} -> {_rate(priced.tax.slab)}"
        moved = [f for f in _MONEY if Decimal(getattr(row, f)) != getattr(priced.money, f)]
        if moved:
            fields[f"lines[{i}].tax"] = ", ".join(
                f"{f} {_s(getattr(row, f))} -> {_s(getattr(priced.money, f))}" for f in moved)
    if fields:
        raise ConflictError("Prices or tax changed since this draft was saved. Review the new "
                            "figures and save again.", code="rate_changed", fields=fields)


def _line_values(quotation_id: Any, line_no: int, p: PricedLine,
                 snapshot: Any | None) -> dict[str, Any]:
    """A line row. `snapshot` is the stored line when re-pricing an existing
    document: its printed description, unit and tariff heading stay the line's own
    (rule 5); only the rate, the tax ids and the figures come from the resolution."""
    steps = list(p.money.steps) + [None] * (3 - len(p.money.steps))
    s1, s2, s3 = steps[:3]
    zero = Decimal("0")
    return {
        "q": quotation_id, "n": line_no, "product": p.product.id,
        "desc": snapshot.description if snapshot is not None else p.product.description,
        "hsn": snapshot.hsn_code if snapshot is not None else p.tax.hsn_code,
        "uom": snapshot.uom if snapshot is not None else p.product.uom_code,
        "qty": p.qty, "rate": p.rate.rate,
        "pl": p.rate.price_list.id, "pli": p.rate.price_list_item_id, "gr": p.tax.gst_rate_id,
        "gross": p.money.gross,
        "d1p": s1.pct if s1 else zero, "d1a": s1.amount if s1 else zero,
        "a1": s1.after if s1 else p.money.gross,
        "d2p": s2.pct if s2 else zero, "d2a": s2.amount if s2 else zero,
        "a2": s2.after if s2 else (s1.after if s1 else p.money.gross),
        "d3p": s3.pct if s3 else zero, "d3a": s3.amount if s3 else zero,
        "disc": p.money.discount, "taxable": p.money.taxable, "slab": p.tax.slab,
        "cr": p.money.cgst_rate, "sr": p.money.sgst_rate, "ir": p.money.igst_rate,
        "cgst": p.money.cgst, "sgst": p.money.sgst, "igst": p.money.igst, "total": p.money.total,
        "prov": list(p.provisional_fields),
    }


_LINE_INSERT = text("""
    INSERT INTO quotation_line (quotation_id, line_no, product_id, description, hsn_code, uom,
        qty, rate, price_list_id, price_list_item_id, gst_rate_id, gross,
        discount_pct, discount1_amt, after_discount1, discount2_pct, discount2_amt,
        after_discount2, discount3_pct, discount3_amt, discount, taxable, gst_slab,
        cgst_rate, sgst_rate, igst_rate, cgst, sgst, igst, total, provisional_fields)
    VALUES (CAST(:q AS uuid), :n, CAST(:product AS uuid), :desc, :hsn, :uom, :qty, :rate,
        CAST(:pl AS uuid), CAST(:pli AS uuid), CAST(:gr AS uuid), :gross,
        :d1p, :d1a, :a1, :d2p, :d2a, :a2, :d3p, :d3a, :disc, :taxable, :slab,
        :cr, :sr, :ir, :cgst, :sgst, :igst, :total, CAST(:prov AS text[]))
""")


async def _write_lines(db: AsyncSession, quotation_id: Any, ctx: PricedContext,
                       snapshots: list[Any] | None = None) -> None:
    await db.execute(text("DELETE FROM quotation_line WHERE quotation_id = CAST(:q AS uuid)"),
                     {"q": quotation_id})
    for i, p in enumerate(ctx.document.lines):
        snap = snapshots[i] if snapshots is not None else None
        await db.execute(_LINE_INSERT, _line_values(quotation_id, i + 1, p, snap))


async def _write_header_figures(db: AsyncSession, quotation_id: Any, ctx: PricedContext) -> None:
    t = ctx.document.totals
    lists = {p.rate.price_list.id for p in ctx.document.lines}
    await db.execute(text("""
        UPDATE quotation SET
            seller_gstin_id = CAST(:sg AS uuid), place_of_supply_state_id = CAST(:ps AS uuid),
            intra_state = :intra, price_effective_date = :day,
            price_list_id = CAST(:pl AS uuid),
            gross = :gross, discount = :disc, taxable = :taxable,
            cgst = :cgst, sgst = :sgst, igst = :igst, total = :total,
            is_provisional = :prov
        WHERE id = CAST(:q AS uuid)"""),
        {"sg": ctx.seller_gstin_id, "ps": ctx.place_of_supply_state_id,
         "intra": ctx.intra_state, "day": ctx.as_of,
         "pl": next(iter(lists)) if len(lists) == 1 else None,
         "gross": t.gross, "disc": t.discount, "taxable": t.taxable, "cgst": t.cgst,
         "sgst": t.sgst, "igst": t.igst, "total": t.total,
         "prov": any(p.provisional_fields for p in ctx.document.lines), "q": quotation_id})


def _specs_from_rows(rows: list[Any]) -> list[LineSpec]:
    return [LineSpec(product_id=str(r.product_id), qty=Decimal(r.qty),
                     discounts=(Decimal(r.discount_pct), Decimal(r.discount2_pct),
                                Decimal(r.discount3_pct))) for r in rows]


def _specs_from_body(lines: list[sch.QuotationLineIn]) -> list[LineSpec]:
    return [LineSpec(product_id=ln.product_id, qty=ln.qty, discounts=ln.discounts)
            for ln in lines]


async def _stored_lines(db: AsyncSession, quotation_id: Any) -> list[Any]:
    return list((await db.execute(text(_LINE_SELECT), {"ids": [str(quotation_id)]})).all())


# ── reads ────────────────────────────────────────────────────────────────────

def _lead_ref(row: Any) -> sch.LeadRef | None:
    if row.lead_inquiry_no is None:
        return None
    return sch.LeadRef(id=str(row.lead_id), inquiry_no=row.lead_inquiry_no, stage=row.lead_stage)


_Q_PEOPLE = [("owner_user_id", "owner_name"), ("created_by", "created_by_name"),
             ("decided_by", "decided_by_name")]
_Q_PARTNERS = [("partner_id", "partner_name")]


async def _names(db: AsyncSession, rows: Sequence[Any]) -> people.Names:
    return await people.resolve(db, rows, _Q_PEOPLE, _Q_PARTNERS)


def _people(row: Any, names: people.Names) -> tuple[PartnerRef | None, UserRef | None]:
    return (names.partner(row.partner_id, row.partner_name, row.partner_type),
            names.user(row.owner_user_id, row.owner_name))


def _totals(row: Any) -> sch.Totals:
    return sch.Totals(gross=_s(row.gross), discount=_s(row.discount), taxable=_s(row.taxable),
                      cgst=_s(row.cgst), sgst=_s(row.sgst), igst=_s(row.igst),
                      total=_s(row.total))


def _pdf_state(row: Any) -> sch.PdfState | None:
    """The worker's own `rendering` reads as `pending` on the API (round 4 B-5)."""
    if not row.pdf_state:
        return None
    return cast(sch.PdfState, domain.PDF_STATE_PUBLIC.get(row.pdf_state, row.pdf_state))


def _line_out(r: Any) -> sch.QuotationLine:
    return sch.QuotationLine(
        line_no=r.line_no, product_id=str(r.product_id), description=r.description,
        hsn_code=r.hsn_code, uom=r.uom, qty=f"{Decimal(r.qty):f}", rate=_s(r.rate),
        gross=_s(r.gross), discount_pct=_rate(r.discount_pct), discount1_amt=_s(r.discount1_amt),
        after_discount1=_s(r.after_discount1), discount2_pct=_rate(r.discount2_pct),
        discount2_amt=_s(r.discount2_amt), after_discount2=_s(r.after_discount2),
        discount3_pct=_rate(r.discount3_pct), discount3_amt=_s(r.discount3_amt),
        discount=_s(r.discount), taxable=_s(r.taxable), gst_slab=_rate(r.gst_slab),
        cgst_rate=_rate(r.cgst_rate), sgst_rate=_rate(r.sgst_rate), igst_rate=_rate(r.igst_rate),
        cgst=_s(r.cgst), sgst=_s(r.sgst), igst=_s(r.igst), total=_s(r.total),
        price_list_id=str(r.price_list_id), price_list_item_id=str(r.price_list_item_id),
        gst_rate_id=str(r.gst_rate_id), provisional_fields=list(r.provisional_fields or []))


def _warnings(row: Any, lines: list[sch.QuotationLine]) -> list[str]:
    out: list[str] = []
    provisional = sum(1 for ln in lines if ln.provisional_fields)
    if provisional:
        out.append(f"provisional_pricing: {provisional} of {len(lines)} lines use a stand-in "
                   f"rate or tax slab that the client has not confirmed.")
    lists = {ln.price_list_id for ln in lines}
    if len(lists) > 1:
        out.append(f"mixed_price_lists: the lines draw from {len(lists)} price lists.")
    return out


def _with_pricing_warnings(out: sch.Quotation, ctx: PricedContext) -> sch.Quotation:
    """A write's response carries what the pipeline said and the stored row cannot
    reproduce (`discontinued_products`, `future_price_date`; edge case 8). The two
    the row does reproduce are already on it, so codes are not repeated."""
    have = {w.split(":", 1)[0] for w in out.warnings}
    for warning in ctx.document.warnings:
        if warning.split(":", 1)[0] not in have:
            out.warnings.append(warning)
    return out


log = structlog.get_logger()

_STORAGE_DOWN = "The document cannot be opened right now. Try again later."


def _to_quotation(row: Any, line_rows: list[Any], settings: Settings,
                  names: people.Names | None = None, portal: bool = False) -> sch.Quotation:
    """`portal`: a partner caller gets no staff decision remark and no render error
    (question 15.14, API review L1 and L4)."""
    names = names or people.Names()
    partner, owner = _people(row, names)
    lines = [_line_out(r) for r in line_rows]
    return sch.Quotation(
        id=str(row.id), quote_no=row.quote_no, version=row.version, status=row.status,
        sales_type=row.sales_type, source=row.source, lead=_lead_ref(row),
        party=sch.Party(name=row.party_name, mobile=row.party_mobile,
                        address=row.party_address, gstin=row.party_gstin),
        partner=partner, owner=owner,
        owner_org_unit=OrgUnitRef(id=str(row.owner_org_unit_id), name=row.owner_org_unit_name),
        territory=TerritoryRef(id=str(row.territory_id), name=row.territory_name,
                               level=row.territory_level),
        seller_gstin=sch.SellerRef(id=str(row.seller_gstin_id), gstin=row.seller_gstin_no,
                                   legal_name=row.seller_legal_name, address=row.seller_address,
                                   state=row.seller_state_code),
        place_of_supply=sch.PlaceOfSupply(
            territory=TerritoryRef(id=str(row.place_of_supply_territory_id), name=row.pos_name,
                                   level=row.pos_level),
            state=row.pos_state_code),
        intra_state=row.intra_state, price_effective_date=row.price_effective_date.isoformat(),
        price_list=(sch.PriceListRef(id=str(row.price_list_id), name=row.price_list_name)
                    if row.price_list_id and row.price_list_name else None),
        price_list_ids=sorted({ln.price_list_id for ln in lines}),
        lines=lines, totals=_totals(row), is_provisional=row.is_provisional,
        warnings=_warnings(row, lines), terms=row.terms,
        valid_until=_iso(row.valid_until), sent_at=_iso(row.sent_at),
        viewed_at=_iso(row.viewed_at), open_count=row.open_count,
        accepted_at=_iso(row.accepted_at), rejected_at=_iso(row.rejected_at),
        decided_by=names.user(row.decided_by, row.decided_by_name),
        decision_remark=None if portal else row.decision_remark,
        supersedes=(sch.VersionRef(id=str(row.supersedes_id), version=row.supersedes_version)
                    if row.supersedes_id and row.supersedes_version else None),
        superseded_by=(sch.VersionRef(id=str(row.superseded_by_id),
                                      version=row.superseded_by_version)
                       if row.superseded_by_id and row.superseded_by_version else None),
        share_url=(domain.share_url(settings.public_web_url, row.share_token)
                   if row.share_token else None),
        pdf_state=_pdf_state(row), pdf_error=None if portal else row.pdf_error,
        created_at=row.created_at.isoformat(),
        created_by=names.user(row.created_by, row.created_by_name),
        updated_at=row.updated_at.isoformat())


def _to_summary(row: Any, names: people.Names) -> sch.QuotationSummary:
    partner, owner = _people(row, names)
    return sch.QuotationSummary(
        id=str(row.id), quote_no=row.quote_no, version=row.version, status=row.status,
        sales_type=row.sales_type, lead=_lead_ref(row), party_name=row.party_name,
        party_mobile=row.party_mobile, partner=partner, owner=owner, totals=_totals(row),
        is_provisional=row.is_provisional, valid_until=_iso(row.valid_until),
        sent_at=_iso(row.sent_at), viewed_at=_iso(row.viewed_at), pdf_state=_pdf_state(row),
        superseded_by=(sch.VersionRef(id=str(row.superseded_by_id),
                                      version=row.superseded_by_version)
                       if row.superseded_by_id and row.superseded_by_version else None),
        created_at=row.created_at.isoformat(), awaiting_approval=row.awaiting_approval)


async def get_quotation(db: AsyncSession, quotation_id: str, settings: Settings,
                        portal: bool = False) -> sch.Quotation:
    row = (await db.execute(text(_Q_SELECT + " WHERE q.id = CAST(:id AS uuid)"),
                            {"id": quotation_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such quotation.")
    out = _to_quotation(row, await _stored_lines(db, row.id), settings,
                        await _names(db, [row]), portal)
    out.approval, _ = await approval_view.load(db, "quotation", quotation_id, portal)
    if row.status == "draft" and not portal:
        # a dealer does not learn the officer's discount limit (OCR review)
        out.discount = await _discount(db, quotation_id)
    return out


async def _discount(db: AsyncSession, quotation_id: str) -> sch.DiscountInfo:
    """FS-013: the owner's limit and the gate, from the definers (officers cannot read
    the threshold rows, EC-7)."""
    # one round trip: every read of a draft pays for this (code review)
    lim = (await db.execute(text(
        "SELECT l.owner_limit_pct, l.effective_pct, l.approval_required, "
        "quotation_send_gate(CAST(:q AS uuid)) AS gate "
        "FROM quotation_discount_limit(CAST(:q AS uuid)) l"), {"q": quotation_id})).one()
    gate = lim.gate
    return sch.DiscountInfo(
        effective_pct=f"{lim.effective_pct:.2f}",
        owner_limit_pct=None if lim.owner_limit_pct is None else f"{lim.owner_limit_pct:.2f}",
        approval_required=bool(lim.approval_required), send_gate=gate)


async def _cancel_approval(db: AsyncSession, quotation_id: str) -> None:
    """Plan review B-2: an edit or a delete cancels a pending request, so an approval
    is never for other figures (EC-1). After the lead and quotation locks."""
    await db.execute(text("SELECT quotation_approval_cancel(CAST(:q AS uuid))"),
                     {"q": quotation_id})


async def list_quotations(db: AsyncSession, caller: Caller, *, lead_id: str | None = None,
                          status: str | None = None, sales_type: str | None = None,
                          owner: str | None = None, partner_id: str | None = None,
                          q: str | None = None, created_from: str | None = None,
                          created_to: str | None = None, current_only: bool = True,
                          limit: int = 25, cursor: str | None = None,
                          include_total: bool = False) -> sch.QuotationPage:
    """The list, keyset-paged by (created_at desc, id). A lead_id filter also
    returns quotations on leads merged into it, one level (AC-LEAD-8)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    where: list[Any] = [scope_predicate(_QUOTATIONS, caller, quotation_t)]
    if lead_id:
        where.append(sa.or_(
            quotation_t.c.lead_id == lead_id,
            quotation_t.c.lead_id.in_(sa.select(sa.column("id", _UUID)).select_from(
                sa.table("lead", sa.column("id", _UUID), sa.column("merged_into_id", _UUID))
            ).where(sa.column("merged_into_id", _UUID) == lead_id))))
    if status:
        # a comma list, like the lead list's stage: "open" is several statuses
        wanted = [x.strip() for x in status.split(",") if x.strip()]
        where.append(sa.cast(quotation_t.c.status, sa.Text).in_(wanted) if wanted else sa.true())
    if sales_type:
        where.append(sa.cast(quotation_t.c.sales_type, sa.Text) == sales_type)
    if owner == "me":
        where.append(quotation_t.c.owner_user_id == caller.user_id)
    elif owner:
        where.append(quotation_t.c.owner_user_id == owner)
    if partner_id:
        where.append(quotation_t.c.partner_id == partner_id)
    if current_only:
        where.append(quotation_t.c.superseded_by_id.is_(None))
    if created_from:
        where.append(quotation_t.c.created_at >= _parse_date(created_from, "from"))
    if created_to:
        where.append(quotation_t.c.created_at < _parse_date(created_to, "to")
                     + dt.timedelta(days=1))
    if q:
        where.append(_search_clause(q))
    filters = list(where)
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append(sa.or_(quotation_t.c.created_at < c_ts,
                            sa.and_(quotation_t.c.created_at == c_ts, quotation_t.c.id < c_id)))
    total, total_capped = (await _capped_total(db, quotation_t, filters)
                           if include_total else (None, False))
    page = (await db.execute(
        sa.select(quotation_t.c.id, quotation_t.c.created_at).where(sa.and_(*where))
        .order_by(quotation_t.c.created_at.desc(), quotation_t.c.id.desc())
        .limit(limit + 1))).all()
    next_cursor = None
    if len(page) > limit:
        last = page[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        page = page[:limit]
    ids = [str(r.id) for r in page]
    if not ids:
        return sch.QuotationPage(data=[], meta=PageMeta(limit=limit, next_cursor=None,
                                                        total=total, total_capped=total_capped))
    rows = (await db.execute(text(_Q_SELECT + " WHERE q.id = ANY(CAST(:ids AS uuid[]))"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    names = await _names(db, rows)
    return sch.QuotationPage(
        data=[_to_summary(by_id[i], names) for i in ids if i in by_id],
        meta=PageMeta(limit=limit, next_cursor=next_cursor, total=total,
                      total_capped=total_capped))


def _parse_date(value: str, field: str) -> datetime:
    """The start of that day on the IST calendar. A UTC midnight put the list's
    date filter five and a half hours off the day the user means (PR #10 review)."""
    try:
        return datetime.combine(dt.date.fromisoformat(value), dt.time.min, tzinfo=IST)
    except ValueError as exc:
        raise ValidationFailed(fields={field: "not an ISO date"}) from exc


def _search_clause(q: str) -> Any:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clauses = [quotation_t.c.party_name.ilike(f"%{esc}%"),
               sa.cast(quotation_t.c.quote_no, sa.Text).ilike(f"%{esc}%")]
    digits = "".join(ch for ch in q if ch.isdigit())
    if digits:
        clauses.append(quotation_t.c.party_mobile.like(f"%{digits}%"))
    return sa.or_(*clauses)


async def versions(db: AsyncSession, quotation_id: str) -> list[sch.QuotationSummary]:
    anchor = (await db.execute(text(
        "SELECT quote_no, id FROM quotation WHERE id = CAST(:id AS uuid)"),
        {"id": quotation_id})).one_or_none()
    if anchor is None:
        raise NotFoundError("No such quotation.")
    if anchor.quote_no is None:
        rows = (await db.execute(text(_Q_SELECT + " WHERE q.id = CAST(:id AS uuid)"),
                                 {"id": quotation_id})).all()
    else:
        rows = (await db.execute(text(_Q_SELECT + " WHERE q.quote_no = :no ORDER BY q.version"),
                                 {"no": anchor.quote_no})).all()
    names = await _names(db, rows)
    return [_to_summary(r, names) for r in rows]


# what a dealer's quotation timeline never carries: staff remarks (question 15.14)
_PORTAL_HIDDEN_KEYS = frozenset({"remark", "decision_remark", "owner_limit_pct"})


async def timeline(db: AsyncSession, quotation_id: str, *, limit: int = 100,
                   cursor: str | None = None, portal: bool = False) -> TimelinePage:
    limit = max(1, min(limit, _MAX_LIMIT))
    visible: bool = (await db.execute(text("SELECT quotation_visible(CAST(:id AS uuid))"),
                                {"id": quotation_id})).scalar_one()
    if not visible:
        raise NotFoundError("No such quotation.")
    before_at, before_id = (None, None)
    if cursor:
        before_at, before_id = _decode_cursor(cursor)
    rows = (await db.execute(text(
        "SELECT id, kind, occurred_at, actor_id, payload FROM activity_event "
        "WHERE entity_type = 'quotation' AND entity_id = CAST(:id AS uuid) "
        "AND (CAST(:bat AS timestamptz) IS NULL OR (occurred_at, id) < "
        "(CAST(:bat AS timestamptz), CAST(:bid AS uuid))) "
        "ORDER BY occurred_at DESC, id DESC LIMIT :lim"),
        {"id": quotation_id, "bat": before_at, "bid": before_id, "lim": limit + 1})).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.occurred_at, str(last.id))
        rows = rows[:limit]
    remarks = {} if portal else await _request_remarks(db, quotation_id)
    events = []
    for r in rows:
        payload = json.loads(r.payload) if isinstance(r.payload, str) else dict(r.payload or {})
        if portal:
            # a dealer sees that the discount was decided, never by whom or why
            # (cross-vendor review of FS-013)
            payload = {k: v for k, v in payload.items() if k not in _PORTAL_HIDDEN_KEYS}
        elif r.kind == "quotation.approval_requested":
            remark = remarks.get(str(payload.get("request_id")))
            if remark:
                payload["remark"] = remark
        hidden = portal and order_domain.actor_hidden_from_partner(r.kind)
        if hidden:
            # the decider's name rides in the payload too (FS-015 code review F-1)
            payload = {k: v for k, v in payload.items() if k != "actor_name"}
        actor = (UserRef(id=str(r.actor_id), full_name=payload.get("actor_name") or "")
                 if r.actor_id is not None and not hidden else None)
        events.append(TimelineEvent(id=str(r.id), kind=r.kind,
                                    occurred_at=r.occurred_at.isoformat(),
                                    actor=actor, payload=payload))
    return TimelinePage(data=events, meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def _request_remarks(db: AsyncSession, quotation_id: str) -> dict[str, str]:
    """Why each discount approval was asked for, for staff: kept on the request, never
    in an event payload."""
    rows = (await db.execute(text(
        "SELECT id::text AS id, remark FROM approval_request "
        "WHERE doc_type = 'quotation' AND entity_id = CAST(:q AS uuid) AND remark IS NOT NULL"),
        {"q": quotation_id})).all()
    return {r.id: r.remark for r in rows}


# ── create ───────────────────────────────────────────────────────────────────

async def create_quotation(db: AsyncSession, caller: Caller, body: sch.QuotationCreate,
                           settings: Settings) -> sch.Quotation:
    if caller.partner_id is not None:
        raise ForbiddenError("Partner users do not raise quotations.")
    stage = await _lock_lead(db, body.lead_id, require_open=True)
    if stage not in domain.CREATABLE_ON:
        raise ValidationFailed(
            "Qualify the lead first: a quotation needs its name, mobile, territory and system.",
            code="lead_not_qualified", fields={"lead_stage": stage})
    lead = await _lead_defaults(db, body.lead_id)

    sales_type = body.sales_type or domain.INQUIRY_TO_SALES_TYPE[lead.inquiry_type]
    _check_sales_type(sales_type)
    partner_id = body.partner_id if body.partner_given else (
        str(lead.assigned_partner_id) if lead.assigned_partner_id else None)
    pos_territory = body.place_of_supply_territory_id or str(lead.territory_id)
    party = _party_values(body.party or _party_from(lead))

    ctx = await _price(db, partner_id=partner_id, pos_territory_id=pos_territory,
                       seller_gstin_id=body.seller_gstin_id, as_of=body.price_effective_date,
                       specs=_specs_from_body(body.lines), existing=False)
    _compare(body.lines, ctx)

    try:
        quotation_id: Any = (await db.execute(text("""
            INSERT INTO quotation (lead_id, sales_type, partner_id, owner_user_id,
                owner_org_unit_id, territory_id, party_name, party_mobile, party_address,
                party_gstin, seller_gstin_id, place_of_supply_territory_id,
                place_of_supply_state_id, intra_state, price_effective_date, terms,
                created_by, updated_by)
            VALUES (CAST(:lead AS uuid), CAST(:st AS quotation_sales_type), CAST(:p AS uuid),
                CAST(:ou AS uuid), CAST(:oou AS uuid), CAST(:terr AS uuid),
                :party_name, :party_mobile, :party_address, :party_gstin,
                CAST(:sg AS uuid), CAST(:pos AS uuid), CAST(:ps AS uuid), :intra, :day, :terms,
                CAST(:me AS uuid), CAST(:me AS uuid))
            RETURNING id"""),
            {"lead": body.lead_id, "st": sales_type, "p": ctx.partner_id,
             "ou": str(lead.owner_user_id) if lead.owner_user_id else None,
             "oou": str(lead.owner_org_unit_id), "terr": str(lead.territory_id),
             **party, "sg": ctx.seller_gstin_id, "pos": pos_territory,
             "ps": ctx.place_of_supply_state_id, "intra": ctx.intra_state, "day": ctx.as_of,
             "terms": body.terms, "me": caller.user_id})).scalar_one()
    except DBAPIError as exc:
        raise _map_write_error(exc) from exc
    await _write_lines(db, quotation_id, ctx)
    await _write_header_figures(db, quotation_id, ctx)
    await _emit(db, quotation_id=quotation_id, lead_id=body.lead_id, kind="quotation.created",
                actor_id=caller.user_id, actor_name=await _actor_name(db),
                sales_type=sales_type, lines=len(body.lines))
    return _with_pricing_warnings(await get_quotation(db, str(quotation_id), settings), ctx)


# the messages refuse_sent_quotation_edit() and its line twin raise (migration 012)
_FROZEN_REFUSALS = ("a sent quotation cannot change", "the lines of a sent quotation",
                    "cannot become", "an accepted quotation cannot be superseded")


def _map_write_error(exc: DBAPIError) -> Exception:
    code = _sqlstate(exc)
    msg = _pg_text(exc)
    if code == "23505" and ("uq_quotation_open_draft" in msg or "uq_quotation_no_version" in msg):
        return ConflictError("A revision of this quotation is already open. Send or delete it.",
                             code="revision_exists")
    if code == "23514":
        # by what raised it, never by SQLSTATE alone: the table's own CHECKs failing
        # is a server bug and must surface as a 500 (PR #10 review)
        if "party_gstin" in msg:
            return ValidationFailed(fields={"party.gstin": "not a valid GSTIN"})
        if any(m in msg for m in _FROZEN_REFUSALS):
            return ConflictError("The quotation cannot change in that way.",
                                 code="quotation_not_draft")
    if code == "42501":
        return ForbiddenError("Not permitted on this quotation.")
    return exc


# ── draft edits ──────────────────────────────────────────────────────────────

async def patch_quotation(db: AsyncSession, caller: Caller, quotation_id: str,
                          body: sch.QuotationPatch, settings: Settings) -> sch.Quotation:
    head = (await db.execute(text(
        "SELECT lead_id FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if head is None:
        raise NotFoundError("No such quotation.")
    await _lock_lead(db, str(head.lead_id), require_open=False)
    row = await _lock_quotation(db, quotation_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)

    sales_type = body.sales_type or row.sales_type
    _check_sales_type(sales_type)
    partner_id = body.partner_id if body.partner_given else (
        str(row.partner_id) if row.partner_id else None)
    pos_territory = body.place_of_supply_territory_id or str(row.place_of_supply_territory_id)
    seller = body.seller_gstin_id or str(row.seller_gstin_id)
    day = body.price_effective_date or row.price_effective_date
    party = _party_values(body.party) if body.party else None
    terms = body.terms if "terms" in body.model_fields_set else row.terms

    stored = await _stored_lines(db, row.id)
    ctx = await _price(db, partner_id=partner_id, pos_territory_id=pos_territory,
                       seller_gstin_id=seller, as_of=day, specs=_specs_from_rows(stored),
                       existing=True)
    try:
        await db.execute(text("""
            UPDATE quotation SET sales_type = CAST(:st AS quotation_sales_type),
                partner_id = CAST(:p AS uuid), place_of_supply_territory_id = CAST(:pos AS uuid),
                terms = :terms, updated_by = CAST(:me AS uuid),
                party_name = COALESCE(:party_name, party_name),
                party_mobile = COALESCE(:party_mobile, party_mobile),
                party_address = CASE WHEN :party_given THEN :party_address ELSE party_address END,
                party_gstin = CASE WHEN :party_given THEN :party_gstin ELSE party_gstin END
            WHERE id = CAST(:q AS uuid)"""),
            {"st": sales_type, "p": ctx.partner_id, "pos": pos_territory, "terms": terms,
             "me": caller.user_id, "party_given": party is not None,
             "party_name": party["party_name"] if party else None,
             "party_mobile": party["party_mobile"] if party else None,
             "party_address": party["party_address"] if party else None,
             "party_gstin": party["party_gstin"] if party else None, "q": quotation_id})
    except DBAPIError as exc:
        raise _map_write_error(exc) from exc
    await _write_lines(db, row.id, ctx, snapshots=stored)
    await _write_header_figures(db, row.id, ctx)
    await _cancel_approval(db, quotation_id)
    await _emit(db, quotation_id=row.id, lead_id=row.lead_id, kind="quotation.updated",
                actor_id=caller.user_id, actor_name=await _actor_name(db),
                fields=sorted(body.model_fields_set - {"expected_status"}))
    return _with_pricing_warnings(await get_quotation(db, quotation_id, settings), ctx)


async def replace_lines(db: AsyncSession, caller: Caller, quotation_id: str,
                        body: sch.LinesReplace, settings: Settings) -> sch.Quotation:
    head = (await db.execute(text(
        "SELECT lead_id FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if head is None:
        raise NotFoundError("No such quotation.")
    await _lock_lead(db, str(head.lead_id), require_open=False)
    row = await _lock_quotation(db, quotation_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)
    ctx = await _price(db, partner_id=str(row.partner_id) if row.partner_id else None,
                       pos_territory_id=str(row.place_of_supply_territory_id),
                       seller_gstin_id=str(row.seller_gstin_id), as_of=row.price_effective_date,
                       specs=_specs_from_body(body.lines), existing=False)
    _compare(body.lines, ctx)
    await _write_lines(db, row.id, ctx)
    await _write_header_figures(db, row.id, ctx)
    await _cancel_approval(db, quotation_id)
    await _emit(db, quotation_id=row.id, lead_id=row.lead_id, kind="quotation.lines_replaced",
                actor_id=caller.user_id, actor_name=await _actor_name(db), lines=len(body.lines))
    return _with_pricing_warnings(await get_quotation(db, quotation_id, settings), ctx)


async def delete_quotation(db: AsyncSession, caller: Caller, quotation_id: str,
                           body: sch.DeleteRequest) -> None:
    head = (await db.execute(text(
        "SELECT lead_id FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if head is None:
        raise NotFoundError("No such quotation.")
    await _lock_lead(db, str(head.lead_id), require_open=False)
    row = await _lock_quotation(db, quotation_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)
    await _cancel_approval(db, quotation_id)
    await _emit(db, quotation_id=row.id, lead_id=row.lead_id, kind="quotation.deleted",
                actor_id=caller.user_id, actor_name=await _actor_name(db))
    await db.execute(text("UPDATE quotation SET deleted_at = now(), updated_by = CAST(:me AS uuid) "
                          "WHERE id = CAST(:q AS uuid)"), {"me": caller.user_id, "q": quotation_id})


# ── send ─────────────────────────────────────────────────────────────────────

async def send_quotation(db: AsyncSession, caller: Caller, quotation_id: str,
                         body: sch.SendRequest, settings: Settings) -> sch.Quotation:
    """Freeze the draft, number it, mint the link, hand the PDF to the worker.
    Database only (rule 21)."""
    head = (await db.execute(text(
        "SELECT lead_id, supersedes_id FROM quotation "
        "WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"), {"id": quotation_id})).one_or_none()
    if head is None:
        raise NotFoundError("No such quotation.")
    await _lock_lead(db, str(head.lead_id), require_open=True)
    predecessor = None
    if head.supersedes_id is not None:
        # lower version first
        predecessor = (await db.execute(text(
            "SELECT id, status::text AS status, quote_no FROM quotation "
            "WHERE id = CAST(:id AS uuid) FOR UPDATE"), {"id": str(head.supersedes_id)})).one()
    row = await _lock_quotation(db, quotation_id)
    _expect(row, body.expected_status)
    _must_be_draft(row)
    stored = await _stored_lines(db, row.id)
    if not stored:
        raise ValidationFailed("Add at least one line before sending.", code="no_lines",
                               fields={"lines": "empty"})
    if predecessor is not None and predecessor.status == "accepted":
        raise ConflictError("The version this revises was accepted meanwhile.",
                            code="predecessor_accepted")

    ctx = await _price(db, partner_id=str(row.partner_id) if row.partner_id else None,
                       pos_territory_id=str(row.place_of_supply_territory_id),
                       seller_gstin_id=str(row.seller_gstin_id), as_of=row.price_effective_date,
                       specs=_specs_from_rows(stored), existing=True)
    _compare_stored(stored, ctx)
    gate: str = (await db.execute(text("SELECT quotation_send_gate(CAST(:q AS uuid))"),
                             {"q": quotation_id})).scalar_one()
    if gate == "pending":
        raise ConflictError("The discount is waiting for approval.", code="approval_pending")
    if gate not in ("none_needed", "approved"):
        raise ConflictError("The discount is above your limit. Request approval first.",
                            code="discount_approval_required", fields={"send_gate": gate})
    if gate == "none_needed":
        # a limit raised while a request waited: the request is moot, and must not
        # sit in the approver's inbox for a sent document (code review)
        await _cancel_approval(db, quotation_id)

    lead = await _lead_defaults(db, str(row.lead_id))
    if predecessor is not None and predecessor.quote_no:
        quote_no = predecessor.quote_no
    else:
        state_code = (await db.execute(
            text("SELECT lead_state_code(CAST(:tid AS uuid))"),
            {"tid": str(lead.territory_id)})).scalar_one_or_none()
        if not state_code:
            raise ValidationFailed(
                "The lead's territory has no coded state, so a number cannot be allocated.",
                code="territory_without_state_code", fields={"territory_id": "no coded state"})
        fy = leads_domain.financial_year(datetime.now(UTC))
        quote_no = (await db.execute(
            text("SELECT quotation_allocate_no(:sc, :fy)"),
            {"sc": state_code, "fy": fy})).scalar_one()

    seller = (await db.execute(text(
        "SELECT sg.gstin, sg.legal_name, sg.address, st.code AS state_code "
        "FROM seller_gstin sg JOIN territory st ON st.id = sg.state_territory_id "
        "WHERE sg.id = CAST(:id AS uuid)"), {"id": str(row.seller_gstin_id)})).one()
    today = today_ist()
    token = domain.share_token()
    try:
        await db.execute(text("""
            UPDATE quotation SET status = 'sent', sent_at = now(), quote_no = :no,
                valid_until = :until, share_token = :token, notify_channel = :channel,
                seller_gstin_no = :sg_no, seller_legal_name = :sg_name,
                seller_address = :sg_addr, seller_state_code = :sg_state,
                pdf_state = 'pending', pdf_next_attempt_at = now(), pdf_attempts = 0,
                updated_by = CAST(:me AS uuid)
            WHERE id = CAST(:q AS uuid)"""),
            {"no": quote_no, "until": domain.valid_until(today), "token": token,
             "channel": body.channel, "sg_no": seller.gstin, "sg_name": seller.legal_name,
             "sg_addr": seller.address, "sg_state": seller.state_code,
             "me": caller.user_id, "q": quotation_id})
        if predecessor is not None:
            await db.execute(text(
                "UPDATE quotation SET superseded_by_id = CAST(:q AS uuid) "
                "WHERE id = CAST(:p AS uuid)"), {"q": quotation_id, "p": str(predecessor.id)})
    except DBAPIError as exc:
        raise _map_write_error(exc) from exc

    previous = await _stage_lead(db, quotation_id, "quoted")
    await _emit(db, quotation_id=row.id, lead_id=row.lead_id, kind="quotation.sent",
                actor_id=caller.user_id, actor_name=await _actor_name(db),
                quote_no=quote_no, version=row.version, channel=body.channel,
                lead_stage_before=previous, provisional=any(r.provisional_fields for r in stored))
    return _with_pricing_warnings(await get_quotation(db, quotation_id, settings), ctx)


# ── discount approval (FS-013) ──────────────────────────────────────────────

_APPROVAL_ERRORS = {
    "APRNR": (409, "approval_not_required", "The discount is within the owner's limit; send it."),
    "APRPD": (409, "approval_pending", "An approval is already waiting."),
    "APRNA": (422, "no_approver", "Nobody's limit covers this discount. Lower it or ask an "
                                  "administrator to raise a limit."),
    "QTNDR": (409, "quotation_not_draft", "Only a draft needs a discount approval."),
    "QTNF0": (404, "not_found", "No such quotation."),
}


async def request_approval(db: AsyncSession, caller: Caller, quotation_id: str,
                           body: sch.ApprovalRequestIn, settings: Settings) -> sch.Quotation:
    head = (await db.execute(text(
        "SELECT lead_id FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if head is None:
        raise NotFoundError("No such quotation.")
    await _lock_lead(db, str(head.lead_id), require_open=False)
    try:
        await db.execute(text("SELECT quotation_request_approval(CAST(:q AS uuid), :r)"),
                         {"q": quotation_id, "r": body.remark})
    except DBAPIError as exc:
        code = _sqlstate(exc) or ""
        if code == "42501":
            raise ForbiddenError("Not permitted on this quotation.") from exc
        if code in _APPROVAL_ERRORS:
            status, api_code, sentence = _APPROVAL_ERRORS[code]
            if status == 404:
                raise NotFoundError(sentence) from exc
            if status == 409:
                raise ConflictError(sentence, code=api_code) from exc
            raise ValidationFailed(sentence, code=api_code) from exc
        raise
    return await get_quotation(db, quotation_id, settings)


# ── the answer ───────────────────────────────────────────────────────────────

async def transition_quotation(db: AsyncSession, caller: Caller, quotation_id: str,
                               body: sch.TransitionRequest, settings: Settings) -> sch.Quotation:
    head = (await db.execute(text(
        "SELECT lead_id FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if head is None:
        raise NotFoundError("No such quotation.")
    await _lock_lead(db, str(head.lead_id), require_open=True)
    row = await _lock_quotation(db, quotation_id)
    _expect(row, body.expected_status)
    if row.superseded_by_id is not None:
        raise ConflictError("A newer version of this quotation was sent; answer that one.",
                            code="quotation_superseded")
    if not domain.can_transition(row.status, body.to):
        raise ValidationFailed(f"A {row.status} quotation cannot become {body.to}.",
                               code="invalid_transition", fields={"to": body.to})
    if domain.is_expired(row.valid_until, today_ist()):
        raise ValidationFailed("This quotation has expired. Revise it to make a new offer.",
                               code="quotation_expired",
                               fields={"valid_until": str(row.valid_until)})
    try:
        await db.execute(text("""
            UPDATE quotation SET status = CAST(:to AS quotation_status),
                accepted_at = CASE WHEN :to = 'accepted' THEN now() ELSE accepted_at END,
                rejected_at = CASE WHEN :to = 'rejected' THEN now() ELSE rejected_at END,
                decided_by = CAST(:me AS uuid), decision_remark = :remark,
                updated_by = CAST(:me AS uuid)
            WHERE id = CAST(:q AS uuid)"""),
            {"to": body.to, "me": caller.user_id, "remark": body.remark, "q": quotation_id})
    except DBAPIError as exc:
        raise _map_write_error(exc) from exc
    lead_before = None
    if body.to == "accepted":
        lead_before = await _stage_lead(db, quotation_id, "won")
    elif body.to == "negotiation":
        lead_before = await _stage_lead(db, quotation_id, "negotiation")
    await _emit(db, quotation_id=row.id, lead_id=row.lead_id, kind=f"quotation.{body.to}",
                actor_id=caller.user_id, actor_name=await _actor_name(db),
                **{"from": row.status, "to": body.to, "remark": body.remark,
                   "lead_stage_before": lead_before})
    return await get_quotation(db, quotation_id, settings)


# ── revise ───────────────────────────────────────────────────────────────────

async def revise_quotation(db: AsyncSession, caller: Caller, quotation_id: str,
                           body: sch.ReviseRequest, settings: Settings) -> sch.Quotation:
    head = (await db.execute(text(
        "SELECT q.lead_id, COALESCE(l.merged_into_id, l.id) AS live_lead "
        "FROM quotation q LEFT JOIN lead l ON l.id = q.lead_id "
        "WHERE q.id = CAST(:id AS uuid) AND q.deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if head is None or head.live_lead is None:
        raise NotFoundError("No such quotation.")
    # a merged loser's quotation is revised on the survivor (rule 12)
    lead_id = str(head.live_lead)
    await _lock_lead(db, lead_id, require_open=True)
    src = await _lock_quotation(db, quotation_id)
    _expect(src, body.expected_status)
    if src.superseded_by_id is not None:
        raise ConflictError("A newer version exists; revise the current one.",
                            code="quotation_superseded")
    if src.status not in domain.REVISABLE:
        raise ValidationFailed(f"A {src.status} quotation cannot be revised.",
                               code="invalid_transition", fields={"status": src.status})
    open_draft = (await db.execute(text("SELECT quotation_open_draft(CAST(:no AS citext))"),
                                   {"no": src.quote_no})).scalar_one_or_none()
    if open_draft is not None:
        raise ConflictError("A revision of this quotation is already open. Send or delete it.",
                            code="revision_exists", fields={"draft_id": str(open_draft)})
    # counted as the owner: a soft-deleted draft is invisible to a caller without
    # quotations.delete, and its version is still taken (round 2 B-6, review F-1)
    next_version = int((await db.execute(text(
        "SELECT quotation_next_version(CAST(:id AS uuid))"),
        {"id": quotation_id})).scalar_one())

    lead = await _lead_defaults(db, lead_id)
    stored = await _stored_lines(db, src.id)
    ctx = await _price(db, partner_id=str(src.partner_id) if src.partner_id else None,
                       pos_territory_id=str(src.place_of_supply_territory_id),
                       seller_gstin_id=str(src.seller_gstin_id), as_of=body.price_effective_date,
                       specs=_specs_from_rows(stored), existing=True)
    try:
        new_id: Any = (await db.execute(text("""
            INSERT INTO quotation (quote_no, version, supersedes_id, lead_id, sales_type,
                partner_id, owner_user_id, owner_org_unit_id, territory_id, party_name,
                party_mobile, party_address, party_gstin, seller_gstin_id,
                place_of_supply_territory_id, place_of_supply_state_id, intra_state,
                price_effective_date, terms, created_by, updated_by)
            VALUES (:no, :ver, CAST(:src AS uuid), CAST(:lead AS uuid),
                CAST(:st AS quotation_sales_type), CAST(:p AS uuid), CAST(:ou AS uuid),
                CAST(:oou AS uuid), CAST(:terr AS uuid), :pn, :pm, :pa, :pg, CAST(:sg AS uuid),
                CAST(:pos AS uuid), CAST(:ps AS uuid), :intra, :day, :terms,
                CAST(:me AS uuid), CAST(:me AS uuid))
            RETURNING id"""),
            {"no": src.quote_no, "ver": next_version, "src": quotation_id, "lead": lead_id,
             "st": src.sales_type, "p": ctx.partner_id,
             "ou": str(lead.owner_user_id) if lead.owner_user_id else None,
             "oou": str(lead.owner_org_unit_id), "terr": str(lead.territory_id),
             "pn": src.party_name, "pm": src.party_mobile, "pa": src.party_address,
             "pg": src.party_gstin, "sg": ctx.seller_gstin_id,
             "pos": str(src.place_of_supply_territory_id), "ps": ctx.place_of_supply_state_id,
             "intra": ctx.intra_state, "day": ctx.as_of, "terms": src.terms,
             "me": caller.user_id})).scalar_one()
    except DBAPIError as exc:
        raise _map_write_error(exc) from exc
    await _write_lines(db, new_id, ctx, snapshots=stored)
    await _write_header_figures(db, new_id, ctx)
    repriced = sum(1 for r, p in zip(stored, ctx.document.lines, strict=True)
                   if Decimal(r.rate) != p.rate.rate or Decimal(r.gst_slab) != p.tax.slab)
    actor = await _actor_name(db)
    await _emit(db, quotation_id=new_id, lead_id=lead_id, kind="quotation.revised",
                actor_id=caller.user_id, actor_name=actor, supersedes=str(src.id),
                version=next_version, repriced_lines=repriced)
    await _emit(db, quotation_id=src.id, lead_id=src.lead_id, kind="quotation.revised",
                actor_id=caller.user_id, actor_name=actor, revision=str(new_id),
                version=next_version)
    out = _with_pricing_warnings(await get_quotation(db, str(new_id), settings), ctx)
    if repriced:
        out.warnings.append(f"repriced: {repriced} lines changed since version {src.version}.")
    return out


# ── the PDF and the public link ──────────────────────────────────────────────

async def pdf_link(db: AsyncSession, quotation_id: str, storage: Storage) -> sch.PdfLink:
    row = (await db.execute(text(
        "SELECT quote_no, version, status::text AS status, pdf_state, pdf_key, pdf_error "
        "FROM quotation WHERE id = CAST(:id AS uuid) AND deleted_at IS NULL"),
        {"id": quotation_id})).one_or_none()
    if row is None or row.status == "draft":
        raise NotFoundError("No PDF: the quotation has not been sent.")
    _pdf_ready_or_raise(row.pdf_state, row.pdf_error)
    filename = domain.pdf_filename(row.quote_no, row.version)
    try:
        url, expires = storage.presign_get(row.pdf_key, filename=filename)
    except RuntimeError as exc:
        # the reason names configuration; it goes to the log, never to a caller
        # (API review L4: the public link reached it)
        log.warning("quotation.storage_unavailable", reason=str(exc))
        raise ConflictError(_STORAGE_DOWN, code="storage_unavailable") from exc
    return sch.PdfLink(url=url, expires_at=expires.isoformat(), filename=filename)


def _pdf_ready_or_raise(state: str | None, error: str | None) -> None:
    if state == "failed":
        raise ConflictError("The PDF could not be produced.", code="pdf_failed",
                            fields={"pdf_error": error or ""})
    if state != "ready":
        raise ConflictError("The PDF is being prepared; try again in a few seconds.",
                            code="pdf_pending")


def _public(doc: dict[str, Any], token: str) -> sch.PublicQuotation:
    valid_until = dt.date.fromisoformat(doc["valid_until"]) if doc.get("valid_until") else None
    t = doc["totals"]
    return sch.PublicQuotation(
        quote_no=doc["quote_no"], version=doc["version"], status=doc["status"],
        sales_type=doc["sales_type"],
        seller=sch.PublicSeller(legal_name=doc["seller"]["legal_name"] or "",
                                gstin=doc["seller"]["gstin"] or ""),
        sent_at=doc.get("sent_at"), valid_until=doc.get("valid_until"),
        expired=domain.is_expired(valid_until, today_ist()), superseded=bool(doc["superseded"]),
        totals=sch.Totals(**{k: _s(Decimal(str(t[k]))) for k in
                             ("gross", "discount", "taxable", "cgst", "sgst", "igst", "total")}),
        line_count=int(doc["line_count"]), pdf_ready=doc.get("pdf_state") == "ready",
        pdf_url=f"/api/v1/public/q/{token}/pdf")


async def public_view(db: AsyncSession, token: str) -> sch.PublicQuotation:
    doc: Any = (await db.execute(text("SELECT quotation_public_view(:t)"),
                                 {"t": token})).scalar_one()
    if doc is None:
        raise NotFoundError("No such quotation.")
    if isinstance(doc, str):
        doc = json.loads(doc)
    return _public(doc, token)


async def public_open(db: AsyncSession, token: str, user_agent: str | None,
                      storage: Storage) -> str:
    """Records the view (once), then the ten-minute URL to redirect to."""
    doc: Any = (await db.execute(text("SELECT quotation_public_open(:t, :ua)"),
                            {"t": token, "ua": (user_agent or "")[:200]})).scalar_one()
    if doc is None:
        raise NotFoundError("No such quotation.")
    if isinstance(doc, str):
        doc = json.loads(doc)
    _pdf_ready_or_raise(doc.get("pdf_state"), None)
    filename = domain.pdf_filename(doc["quote_no"], int(doc["version"]))
    try:
        url, _ = storage.presign_get(str(doc["pdf_key"]), filename=filename)
    except RuntimeError as exc:
        # the reason names configuration; it goes to the log, never to a caller
        # (API review L4: the public link reached it)
        log.warning("quotation.storage_unavailable", reason=str(exc))
        raise ConflictError(_STORAGE_DOWN, code="storage_unavailable") from exc
    return url
