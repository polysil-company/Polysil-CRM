"""Lead creation and reads (FS-003 sections 4 and 5.3).

The transactions. Domain owns the rules (rule 1), get_db owns the boundary
(rule 3): nothing here commits. Every read runs under the caller's claim and
app_role, so RLS filters underneath the service predicate (FS-002 dual
enforcement). The service predicate is enforcer 1; the policies are enforcer 2.

Slice 1 is create, list and detail. Duplicate detection on create (rule 6),
PATCH, transition, reopen, assign, notes, timeline, merge and delete are later
slices; where one is deferred a GAP records it.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.config import get_settings
from api.domain import leads as domain
from api.errors import NotFoundError, ValidationFailed
from api.integrations.messages import TEMPLATE_LEAD_ACK
from api.schemas.leads import (
    DuplicateRef,
    Lead,
    LeadCreate,
    LeadPage,
    LookupItem,
    MergedRef,
    OrgUnitRef,
    PageMeta,
    PartnerRef,
    ReasonRef,
    TerritoryParent,
    TerritoryPick,
    TerritoryRef,
    UserRef,
)

_LEADS = SPECS["leads"]

# A light table clause the scope predicate and the list filters read. Only the
# columns those two touch, and the id/created_at the keyset page orders on. The id
# and the fk columns are typed uuid on purpose: an untyped column binds the
# caller id as varchar and Postgres refuses `uuid = character varying`, the trap
# api/authz/predicate.py already documents.
_UUID = sa.Uuid()
_TS = sa.DateTime(timezone=True)
lead_t = sa.table(
    "lead",
    sa.column("id", _UUID),
    sa.column("created_at", _TS),
    sa.column("stage"),
    sa.column("priority"),
    sa.column("owner_user_id", _UUID),
    sa.column("owner_org_unit_id", _UUID),
    sa.column("territory_id", _UUID),
    sa.column("assigned_partner_id", _UUID),
    sa.column("lead_source_id", _UUID),
    sa.column("inquiry_type"),
    sa.column("deleted_at", _TS),
    sa.column("farmer_name"),
    sa.column("mobile"),
    sa.column("inquiry_no"),
)

# Every field the Lead shape needs that is not a person. The masters (territory,
# org_unit, mis_system, lead_source, won_lost_reason) are readable by any
# authenticated caller or are the lead's own in-scope fks, so their names always
# resolve. The person joins (owner, created_by, partner, merged survivor) are RLS
# filtered and may come back null for a caller who can see the lead but not the
# referenced row; detail overrides them from lead_people(), which is the definer
# answer for a visible lead. GAP-060 covers the list, which keeps the join.
_LEAD_SELECT = """
SELECT l.id, l.inquiry_no, l.stage, l.inquiry_type,
       ms.code AS mis_code, src.code AS source_code,
       l.farmer_name, l.mobile, l.email, l.village,
       l.territory_id, t.name AS territory_name, t.level AS territory_level,
       l.owner_user_id, ow.full_name AS owner_name,
       l.owner_org_unit_id, ou.name AS owner_org_unit_name,
       l.assigned_partner_id, cp.name AS partner_name, cp.partner_type AS partner_type,
       l.score, l.priority, l.estimated_value,
       l.lost_reason_id, wlr.code AS lost_reason_code, wlr.name AS lost_reason_name,
       l.lost_note, l.reopen_count,
       l.merged_into_id, mi.inquiry_no AS merged_into_no,
       l.first_contacted_at, l.last_activity_at, l.created_at,
       l.created_by, cb.full_name AS created_by_name
  FROM lead l
  JOIN mis_system ms ON ms.id = l.mis_system_id
  JOIN lead_source src ON src.id = l.lead_source_id
  JOIN territory t ON t.id = l.territory_id
  JOIN org_unit ou ON ou.id = l.owner_org_unit_id
  LEFT JOIN app_user ow ON ow.id = l.owner_user_id
  LEFT JOIN channel_partner cp ON cp.id = l.assigned_partner_id
  LEFT JOIN won_lost_reason wlr ON wlr.id = l.lost_reason_id
  LEFT JOIN lead mi ON mi.id = l.merged_into_id
  LEFT JOIN app_user cb ON cb.id = l.created_by
"""


# ── helpers: values off the row ──────────────────────────────────────────────

def _contains(q: str) -> str:
    """A case-insensitive contains pattern. The LIKE wildcards `%` `_` `\\` are
    escaped, not stripped, so a search term that contains one matches it literally
    (Postgres ILIKE uses backslash as its default escape)."""
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def _dec(v: Any) -> str | None:
    return None if v is None else str(v)


def _iso(v: datetime | None) -> str | None:
    return None if v is None else v.isoformat()


# ── create ───────────────────────────────────────────────────────────────────

async def create_lead(db: AsyncSession, caller: Caller, body: LeadCreate) -> Lead:
    """Enter one lead, in one transaction (rule 14). require('leads','create') has
    already run in the route, and the idempotency record is reserved around this
    call, so this is the work that commits or rolls back as a unit."""
    # 1. mobile to E.164 (rule 1). A non-Indian or malformed number is a field 422.
    try:
        mobile = domain.normalise_mobile(body.mobile)
    except domain.MobileError as exc:
        raise ValidationFailed(fields={"mobile": str(exc)}) from exc

    # 2. the source, and its quality factor for the score. Default by user type:
    # a partner user's leads are 'dealer', a staff user's 'employee'.
    source_code = body.source or ("dealer" if caller.partner_id else "employee")
    src = (await db.execute(text(
        "SELECT id, quality FROM lead_source "
        "WHERE code = :c AND is_active AND deleted_at IS NULL"),
        {"c": source_code})).one_or_none()
    if src is None:
        raise ValidationFailed(fields={"source": "not an active source"})

    mis = (await db.execute(text(
        "SELECT id FROM mis_system WHERE code = :c AND is_active AND deleted_at IS NULL"),
        {"c": body.mis_system})).one_or_none()
    if mis is None:
        raise ValidationFailed(fields={"mis_system": "not an active system"})

    # 3. the state code for the inquiry number (rule 3): the code of the state-level
    # ancestor of the territory. No coded state ancestor refuses creation rather
    # than allocating under a made-up code.
    state_code = (await db.execute(text(
        "SELECT t.code FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
        "WHERE tc.descendant_id = :tid AND t.level = 'state' "
        "ORDER BY tc.depth ASC LIMIT 1"), {"tid": str(body.territory_id)})).scalar_one_or_none()
    if not state_code:
        raise ValidationFailed(
            "This territory has no coded state, so an inquiry number cannot be allocated.",
            code="territory_without_state_code",
            fields={"territory_id": "no coded state ancestor"})

    # 4. route the owner and the org unit (rules 4 and 5).
    owner_user_id, owner_org_unit_id, assigned_partner_id = await _route(
        db, caller, str(body.territory_id))

    # 4b. the routed row must sit in the caller's own scope. The INSERT policy would
    # refuse it with 42501 (a 500); this turns the common misroute into a clean 422
    # (rule 4, plan review B-9).
    await _assert_insert_in_scope(
        db, caller, territory_id=str(body.territory_id),
        owner_user_id=owner_user_id, owner_org_unit_id=owner_org_unit_id,
        assigned_partner_id=assigned_partner_id)

    # 5. the inquiry number, allocated inside this transaction under a row lock
    # (definer function, rule 2). The financial year is the IST-local one (rule 2).
    fy = domain.financial_year(datetime.now(UTC))
    inquiry_no = (await db.execute(
        text("SELECT lead_allocate_inquiry_no(:sc, :fy)"),
        {"sc": state_code, "fy": fy})).scalar_one()

    # 6. the score (rule 7): domain maths over lead_score_rule rows. On create there
    # is no contact yet and no events, so speed and engagement are zero.
    config = {k: Decimal(v) for k, v in (await db.execute(
        text("SELECT key, value FROM lead_score_rule"))).all()}
    score, priority = domain.score(
        source_quality=Decimal(src.quality),
        estimated_value=body.estimated_value,
        created_at=datetime.now(UTC), first_contacted_at=None, event_count=0,
        config=config)

    # 7. the row (rule 14). RLS WITH CHECK re-verifies scope underneath 4b.
    lead_id = (await db.execute(text("""
        INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id,
            farmer_name, mobile, email, territory_id, village, owner_user_id,
            owner_org_unit_id, assigned_partner_id, score, priority, estimated_value,
            created_by)
        VALUES (:no, 'new', CAST(:it AS inquiry_type), :mis, :src, :name, :mob, :email,
            :tid, :village, :owner, :oou, :ap, :score, CAST(:prio AS lead_priority),
            :est, :me)
        RETURNING id"""), {
        "no": inquiry_no, "it": body.inquiry_type, "mis": mis.id, "src": src.id,
        "name": body.farmer_name, "mob": mobile, "email": body.email,
        "tid": str(body.territory_id), "village": body.village, "owner": owner_user_id,
        "oou": owner_org_unit_id, "ap": assigned_partner_id, "score": score,
        "prio": priority, "est": body.estimated_value, "me": caller.user_id,
    })).scalar_one()

    # 8. the event (CLAUDE.md rule 7, FS-003 rule 14). actor_id must be the caller:
    # the activity_event INSERT policy checks it.
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', :id, :id, 'lead.created', :me, CAST(:p AS jsonb))"),
        {"id": lead_id, "me": caller.user_id,
         "p": json.dumps({"stage": "new", "source": source_code, "inquiry_no": inquiry_no})})
    if body.note:
        await db.execute(text(
            "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
            "VALUES ('lead', :id, :id, 'lead.note', :me, CAST(:p AS jsonb))"),
            {"id": lead_id, "me": caller.user_id, "p": json.dumps({"note": body.note})})

    # 9. the acknowledgement, through the outbox (CLAUDE.md rule 6, FS-003 rule 17).
    # recipient is E.164 with the plus, the provider's form.
    await db.execute(text(
        "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
        "VALUES ('whatsapp', :tk, :to, CAST(:p AS jsonb))"),
        {"tk": TEMPLATE_LEAD_ACK, "to": mobile,
         "p": json.dumps({"farmer_name": body.farmer_name, "inquiry_no": inquiry_no})})

    # GAP-059: duplicate detection on create (rule 6, AC-LEAD-3) is the duplicates
    # slice. The response carries an empty list until then; the shape is final so
    # adding it is additive.
    return await get_lead(db, caller, str(lead_id))


async def _route(db: AsyncSession, caller: Caller, territory_id: str
                 ) -> tuple[str | None, str, str | None]:
    """owner_user_id, owner_org_unit_id, assigned_partner_id for a new lead (rules
    4 and 5). owner_org_unit_id is never user-supplied and is NOT NULL."""
    if caller.partner_id is not None:
        # A partner user's lead is anchored on the partner and auto-assigned to a
        # field officer of the covering sales unit (rule 5). lead_auto_owner is a
        # definer function because a partner's claim can read neither the officers
        # nor their lead counts. It may return null: no active officer covers the
        # territory, and the lead waits in the unassigned list.
        owner = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                                  {"t": territory_id})).scalar_one_or_none()
        oou = await _covering_org_unit(db, territory_id)
        return (str(owner) if owner else None, oou, caller.partner_id)

    # A staff user owns the lead they create. If their own org unit is a sales-line
    # unit (it has a territory) that is the owning unit (rule 4 path A); an HQ
    # functional unit with no territory routes by the lead's territory (path B).
    owner = caller.user_id
    own_unit_territory = None
    if caller.org_unit_id is not None:
        own_unit_territory = (await db.execute(
            text("SELECT territory_id FROM org_unit WHERE id = :id"),
            {"id": caller.org_unit_id})).scalar_one_or_none()
    if caller.org_unit_id is not None and own_unit_territory is not None:
        return (owner, caller.org_unit_id, None)
    return (owner, await _covering_org_unit(db, territory_id), None)


async def _covering_org_unit(db: AsyncSession, territory_id: str) -> str:
    """The sales-line org unit whose territory is the lead's territory or its
    nearest ancestor; the named anchor when none covers it (rule 4). org_unit and
    territory_closure are readable by any authenticated caller, so this is plain
    SQL for staff and partner alike."""
    covering = (await db.execute(text(
        "SELECT ou.id FROM org_unit ou "
        "JOIN territory_closure tc ON tc.ancestor_id = ou.territory_id "
        "                         AND tc.descendant_id = :tid "
        "WHERE ou.territory_id IS NOT NULL "
        "ORDER BY tc.depth ASC, ou.id ASC LIMIT 1"), {"tid": territory_id})).scalar_one_or_none()
    if covering is not None:
        return str(covering)
    root = get_settings().root_org_unit_id
    if root:
        return root
    # No covering unit and no anchor: refuse cleanly rather than violate NOT NULL
    # with a 500. On the dev box the seeded org tree always covers a seeded
    # territory, so this is the unconfigured-anchor path (GAP-046).
    raise ValidationFailed(
        "No sales org unit covers this territory, and no fallback unit is configured.",
        code="territory_without_org_unit",
        fields={"territory_id": "no org unit covers this territory"})


async def _assert_insert_in_scope(db: AsyncSession, caller: Caller, *, territory_id: str,
                                  owner_user_id: str | None, owner_org_unit_id: str,
                                  assigned_partner_id: str | None) -> None:
    """The routed row must satisfy the caller's own leads scope, the same branch the
    INSERT policy checks. This is the advisory pre-check (rule 4 B-9); RLS is the
    real enforcer. A miss is a 422 on territory_id, the field the caller can act on."""
    scope = caller.scopes.get("leads")
    ok = False
    if scope == "global":
        ok = True
    elif scope == "own":
        ok = owner_user_id == caller.user_id
    elif scope == "org_subtree" and caller.org_unit_id is not None:
        ok = bool((await db.execute(text(
            "SELECT 1 FROM org_closure WHERE ancestor_id = :a AND descendant_id = :d"),
            {"a": caller.org_unit_id, "d": owner_org_unit_id})).first())
    elif scope == "territory":
        ok = bool((await db.execute(text(
            "SELECT 1 FROM territory_closure tc JOIN user_territory ut "
            "ON ut.territory_id = tc.ancestor_id "
            "WHERE ut.user_id = :u AND tc.descendant_id = :d"),
            {"u": caller.user_id, "d": territory_id})).first())
    elif scope == "partner_subtree" and caller.partner_id is not None and assigned_partner_id:
        ok = bool((await db.execute(text(
            "SELECT 1 FROM partner_closure WHERE ancestor_id = :a AND descendant_id = :d"),
            {"a": caller.partner_id, "d": assigned_partner_id})).first())
    if not ok:
        raise ValidationFailed(
            fields={"territory_id": "no part of your scope covers this lead"})


# ── read one ─────────────────────────────────────────────────────────────────

async def get_lead(db: AsyncSession, caller: Caller, lead_id: str) -> Lead:
    """One lead, or 404. Out of scope and does-not-exist are one answer: RLS
    returns no row for either, and the two must not be distinguishable (FS-003 4)."""
    row = (await db.execute(text(_LEAD_SELECT + " WHERE l.id = :id"),
                            {"id": lead_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such lead.")

    lead = _row_to_lead(row, duplicates=await _duplicates(db, lead_id))

    # The people, authoritatively. lead_people() is a definer read that answers for
    # a visible lead, so a manager who can see the lead but not the owner's user row
    # still gets the owner's name. It overrides the RLS-filtered joins.
    people = (await db.execute(
        text("SELECT kind, id, name, detail FROM lead_people(:id)"), {"id": lead_id})).all()
    for p in people:
        if p.kind == "owner":
            lead.owner = UserRef(id=str(p.id), full_name=p.name)
        elif p.kind == "created_by":
            lead.created_by = UserRef(id=str(p.id), full_name=p.name)
        elif p.kind == "assigned_partner":
            lead.assigned_partner = PartnerRef(
                id=str(p.id), name=p.name, partner_type=p.detail)
        elif p.kind == "merged_into":
            lead.merged_into = MergedRef(id=str(p.id), inquiry_no=p.detail)
    return lead


async def _duplicates(db: AsyncSession, lead_id: str) -> list[DuplicateRef]:
    """Pending links whose other lead is also in the caller's scope. That is the
    link table's own rule (both leads visible), not a service filter, so a raw read
    cannot name an id the caller could not GET either."""
    rows = (await db.execute(text("""
        SELECT dl.id AS link_id, o.id AS other_id, o.inquiry_no, dl.signal, dl.score, dl.state
          FROM lead_duplicate_link dl
          JOIN lead o ON o.id = CASE WHEN dl.lead_a_id = :id THEN dl.lead_b_id
                                     ELSE dl.lead_a_id END
         WHERE (dl.lead_a_id = :id OR dl.lead_b_id = :id) AND dl.state = 'pending'
         ORDER BY dl.created_at DESC"""), {"id": lead_id})).all()
    return [DuplicateRef(link_id=str(r.link_id), lead_id=str(r.other_id),
                         inquiry_no=r.inquiry_no, signal=r.signal, score=_dec(r.score),
                         state=r.state) for r in rows]


def _row_to_lead(row: Any, *, duplicates: list[DuplicateRef]) -> Lead:
    """The non-person fields, plus the people from the RLS-filtered joins. get_lead
    overrides the people from lead_people(); the list keeps these (GAP-058)."""
    return Lead(
        id=str(row.id), inquiry_no=row.inquiry_no, stage=row.stage,
        inquiry_type=row.inquiry_type, mis_system=row.mis_code, source=row.source_code,
        farmer_name=row.farmer_name, mobile=row.mobile, email=row.email,
        territory=TerritoryRef(id=str(row.territory_id), name=row.territory_name,
                               level=row.territory_level),
        village=row.village,
        owner=UserRef(id=str(row.owner_user_id), full_name=row.owner_name)
        if row.owner_user_id and row.owner_name else None,
        owner_org_unit=OrgUnitRef(id=str(row.owner_org_unit_id),
                                  name=row.owner_org_unit_name),
        assigned_partner=PartnerRef(id=str(row.assigned_partner_id), name=row.partner_name,
                                    partner_type=row.partner_type)
        if row.assigned_partner_id and row.partner_name else None,
        score=_dec(row.score), priority=row.priority, estimated_value=_dec(row.estimated_value),
        lost_reason=ReasonRef(id=str(row.lost_reason_id), code=row.lost_reason_code,
                              name=row.lost_reason_name) if row.lost_reason_id else None,
        lost_note=row.lost_note, reopen_count=row.reopen_count,
        merged_into=MergedRef(id=str(row.merged_into_id), inquiry_no=row.merged_into_no)
        if row.merged_into_id and row.merged_into_no else None,
        first_contacted_at=_iso(row.first_contacted_at),
        last_activity_at=_iso(row.last_activity_at), created_at=_iso(row.created_at),
        created_by=UserRef(id=str(row.created_by), full_name=row.created_by_name)
        if row.created_by and row.created_by_name else None,
        duplicates=duplicates)


# ── list ─────────────────────────────────────────────────────────────────────

_MAX_LIMIT = 100


async def list_leads(db: AsyncSession, caller: Caller, *, stage: str | None = None,
                     priority: str | None = None, owner_user_id: str | None = None,
                     owner: str | None = None, territory_id: str | None = None,
                     source: str | None = None, inquiry_type: str | None = None,
                     created_from: str | None = None, created_to: str | None = None,
                     q: str | None = None, limit: int = 50,
                     cursor: str | None = None) -> LeadPage:
    """The lead list, scoped and filtered, keyset-paged by (created_at desc, id).

    Enforcer 1 is scope_predicate; RLS re-checks the same rows underneath. No total
    (ISS-014): counting a scoped table on every page is the cost this avoids.
    """
    limit = max(1, min(limit, _MAX_LIMIT))

    where = [scope_predicate(_LEADS, caller, lead_t)]

    if stage:
        wanted = [s.strip() for s in stage.split(",") if s.strip()]
        if wanted:
            where.append(sa.cast(lead_t.c.stage, sa.Text).in_(wanted))
    else:
        # The default list is every stage except the merge losers; ?stage=merged
        # lists them for an audit (round 3 Q-1).
        where.append(sa.cast(lead_t.c.stage, sa.Text) != "merged")
    if priority:
        where.append(sa.cast(lead_t.c.priority, sa.Text) == priority)
    if inquiry_type:
        where.append(sa.cast(lead_t.c.inquiry_type, sa.Text) == inquiry_type)
    if owner == "none":
        where.append(lead_t.c.owner_user_id.is_(None))
    elif owner_user_id:
        where.append(lead_t.c.owner_user_id == owner_user_id)
    if territory_id:
        where.append(lead_t.c.territory_id == territory_id)
    if source:
        src_id = (await db.execute(
            text("SELECT id FROM lead_source WHERE code = :c"),
            {"c": source})).scalar_one_or_none()
        # An unknown source matches nothing rather than every row.
        where.append(lead_t.c.lead_source_id == src_id if src_id is not None
                     else sa.false())
    if created_from:
        where.append(lead_t.c.created_at >= _parse_ts(created_from, "created_from"))
    if created_to:
        where.append(lead_t.c.created_at <= _parse_ts(created_to, "created_to"))
    if q:
        where.append(_search_clause(q))
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append(sa.or_(lead_t.c.created_at < c_ts,
                            sa.and_(lead_t.c.created_at == c_ts, lead_t.c.id < c_id)))

    page = (await db.execute(
        sa.select(lead_t.c.id, lead_t.c.created_at)
        .where(sa.and_(*where))
        .order_by(lead_t.c.created_at.desc(), lead_t.c.id.desc())
        .limit(limit + 1))).all()

    next_cursor = None
    if len(page) > limit:
        last = page[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        page = page[:limit]

    ids = [str(r.id) for r in page]
    if not ids:
        return LeadPage(data=[], meta=PageMeta(limit=limit, next_cursor=None))

    rows = (await db.execute(text(_LEAD_SELECT + " WHERE l.id = ANY(:ids)"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    data = [_row_to_lead(by_id[i], duplicates=[]) for i in ids if i in by_id]
    return LeadPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor))


def _search_clause(q: str) -> Any:
    """q matches farmer_name (contains), mobile (digits contains) and inquiry_no
    (exact). inquiry_no is citext, so the equality is case-insensitive."""
    clauses = [lead_t.c.farmer_name.ilike(_contains(q)), lead_t.c.inquiry_no == q]
    digits = "".join(ch for ch in q if ch.isdigit())
    if digits:
        clauses.append(lead_t.c.mobile.like("%" + digits + "%"))
    return sa.or_(*clauses)


def _parse_ts(value: str, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationFailed(fields={field: "not an ISO date"}) from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _encode_cursor(created_at: datetime, lead_id: str) -> str:
    raw = f"{created_at.isoformat()}|{lead_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, _, lead_id = raw.partition("|")
        return datetime.fromisoformat(ts), lead_id
    except (ValueError, binascii.Error) as exc:
        raise ValidationFailed(fields={"cursor": "malformed cursor"}) from exc


# ── lookups ──────────────────────────────────────────────────────────────────

async def list_lead_sources(db: AsyncSession) -> list[LookupItem]:
    rows = (await db.execute(text(
        "SELECT id, code, name, is_active FROM lead_source "
        "WHERE deleted_at IS NULL ORDER BY sort_order, name"))).all()
    return [LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)
            for r in rows]


async def list_mis_systems(db: AsyncSession) -> list[LookupItem]:
    rows = (await db.execute(text(
        "SELECT id, code, name, is_active FROM mis_system "
        "WHERE deleted_at IS NULL ORDER BY name"))).all()
    return [LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)
            for r in rows]


async def list_lost_reasons(db: AsyncSession) -> list[LookupItem]:
    rows = (await db.execute(text(
        "SELECT id, code, name, is_active FROM won_lost_reason "
        "WHERE kind = 'lost' AND deleted_at IS NULL ORDER BY sort_order, name"))).all()
    return [LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)
            for r in rows]


async def list_territories(db: AsyncSession, *, level: str | None = None,
                           parent_id: str | None = None, q: str | None = None,
                           limit: int = 50) -> list[TerritoryPick]:
    """The territory picker for the new-lead form. territory is readable by any
    authenticated caller; q is a name substring."""
    limit = max(1, min(limit, _MAX_LIMIT))
    like = _contains(q) if q else None
    # Each optional filter casts its bind explicitly: a bare `:p IS NULL` leaves
    # asyncpg unable to infer the parameter type (AmbiguousParameterError).
    rows = (await db.execute(text("""
        SELECT t.id, t.name, t.level, t.code,
               p.id AS parent_id, p.name AS parent_name, p.level AS parent_level
          FROM territory t
          LEFT JOIN territory p ON p.id = t.parent_id
         WHERE (CAST(:level AS text) IS NULL OR t.level::text = CAST(:level AS text))
           AND (CAST(:parent AS uuid) IS NULL OR t.parent_id = CAST(:parent AS uuid))
           AND (CAST(:like AS text) IS NULL OR t.name ILIKE CAST(:like AS text))
         ORDER BY t.name LIMIT :lim"""),
        {"level": level, "parent": parent_id, "like": like, "lim": limit})).all()
    return [TerritoryPick(
        id=str(r.id), name=r.name, level=r.level, code=r.code,
        parent=TerritoryParent(id=str(r.parent_id), name=r.parent_name,
                               level=r.parent_level) if r.parent_id else None)
        for r in rows]
