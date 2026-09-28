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
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, scope_predicate
from api.config import get_settings
from api.domain import leads as domain
from api.domain import tasks as task_domain
from api.domain.orders import actor_hidden_from_partner
from api.errors import ForbiddenError, NotFoundError, StageChangedError, ValidationFailed
from api.integrations.messages import TEMPLATE_LEAD_ACK
from api.schemas.leads import (
    Assignee,
    DismissResult,
    DuplicatePage,
    DuplicatePair,
    DuplicateRef,
    Lead,
    LeadAssign,
    LeadCreate,
    LeadMerge,
    LeadNote,
    LeadPage,
    LeadPatch,
    LeadReopen,
    LeadStats,
    LeadTransition,
    LookupCreate,
    LookupItem,
    LookupUpdate,
    MergedRef,
    OrgUnitRef,
    PageMeta,
    PartnerPick,
    PartnerRef,
    ReasonRef,
    ScoringItem,
    ScoringPatch,
    TerritoryParent,
    TerritoryPick,
    TerritoryRef,
    TimelineEvent,
    TimelinePage,
    UserRef,
)
from api.services import people
from api.services.clock import today_ist

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


def _iso_req(v: datetime) -> str:
    """For NOT NULL timestamp columns."""
    return v.isoformat()


async def _has_permission(db: AsyncSession, module: str, action: str) -> bool:
    return bool((await db.execute(text("SELECT app_has_permission(:m, :a)"),
                                  {"m": module, "a": action})).scalar_one())


async def _actor_name(db: AsyncSession) -> str:
    """The caller's display name, for `payload.actor_name`. Every lead event carries
    it at write time so the timeline needs no lookup a field officer may not make
    (FS-003 4, EC-4). The caller can always read their own app_user row."""
    return str((await db.execute(text(
        "SELECT full_name FROM app_user WHERE id = (SELECT app_current_user_id())"))
    ).scalar_one())


async def _emit(db: AsyncSession, *, lead_id: Any, kind: str, actor_id: str,
                actor_name: str, **payload: Any) -> Any:
    """Write one lead activity_event and return its (id, occurred_at) row. actor_id
    must be the caller (the INSERT policy checks it); actor_name goes in the payload."""
    return (await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
        "VALUES ('lead', :id, :id, :kind, :me, CAST(:p AS jsonb)) RETURNING id, occurred_at"),
        {"id": lead_id, "kind": kind, "me": actor_id,
         "p": json.dumps({"actor_name": actor_name, **payload})})).one()


async def _load_config(db: AsyncSession) -> dict[str, Decimal]:
    return {k: Decimal(v) for k, v in (await db.execute(
        text("SELECT key, value FROM lead_score_rule"))).all()}


async def _rescore(db: AsyncSession, lead_id: Any) -> None:
    """Recompute score and priority from the lead's current factors and its events
    (rule 7). Called after any mutation that changes a factor: contact, note, reopen.
    Runs under the leads UPDATE policy, which the caller already satisfies."""
    row = (await db.execute(text(
        "SELECT l.estimated_value, l.created_at, l.first_contacted_at, src.quality, "
        "(SELECT count(*) FROM activity_event ae WHERE ae.lead_id = l.id "
        " AND ae.kind <> 'lead.created') AS events "
        "FROM lead l JOIN lead_source src ON src.id = l.lead_source_id WHERE l.id = :id"),
        {"id": lead_id})).one()
    score, priority = domain.score(
        source_quality=Decimal(row.quality), estimated_value=row.estimated_value,
        created_at=row.created_at, first_contacted_at=row.first_contacted_at,
        event_count=int(row.events), config=await _load_config(db))
    await db.execute(text(
        "UPDATE lead SET score = :s, priority = CAST(:p AS lead_priority), "
        "last_activity_at = now() WHERE id = :id"),
        {"s": score, "p": priority, "id": lead_id})


# ── create ───────────────────────────────────────────────────────────────────

async def create_lead(db: AsyncSession, caller: Caller, body: LeadCreate, *,
                      intake: bool = False, intake_partner_id: str | None = None,
                      qr_code_id: str | None = None) -> Lead:
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
    # A definer read with a share lock on the state row (007), so a concurrent code
    # edit either waits for this transaction and is then refused by the counter it
    # finds, or commits first and this read returns the new code (FS-006 rule 15,
    # cross-vendor P2-3).
    state_code = (await db.execute(text("SELECT lead_state_code(CAST(:tid AS uuid))"),
                                   {"tid": str(body.territory_id)})).scalar_one_or_none()
    if not state_code:
        raise ValidationFailed(
            "This territory has no coded state, so an inquiry number cannot be allocated.",
            code="territory_without_state_code",
            fields={"territory_id": "no coded state ancestor"})

    # 4. route the owner and the org unit (rules 4 and 5). A public lead routes by
    # its territory and QR code, never by the intake principal's own office
    # (FS-003a EC-2).
    if intake:
        owner_user_id, owner_org_unit_id, assigned_partner_id = await _route_intake(
            db, str(body.territory_id), intake_partner_id)
    else:
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
    config = await _load_config(db)
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
            created_by, qr_code_id)
        VALUES (:no, 'new', CAST(:it AS inquiry_type), :mis, :src, :name, :mob, :email,
            :tid, :village, :owner, :oou, :ap, :score, CAST(:prio AS lead_priority),
            :est, :me, :qr)
        RETURNING id"""), {
        "no": inquiry_no, "it": body.inquiry_type, "mis": mis.id, "src": src.id,
        "name": body.farmer_name, "mob": mobile, "email": body.email,
        "tid": str(body.territory_id), "village": body.village, "owner": owner_user_id,
        "oou": owner_org_unit_id, "ap": assigned_partner_id, "score": score,
        "prio": priority, "est": body.estimated_value, "me": caller.user_id, "qr": qr_code_id,
    })).scalar_one()

    # 8. the event (CLAUDE.md rule 7, FS-003 rule 14). actor_id must be the caller:
    # the activity_event INSERT policy checks it. actor_name rides in the payload so
    # the timeline needs no user lookup (rule 16, EC-4).
    actor = await _actor_name(db)
    await _emit(db, lead_id=lead_id, kind="lead.created", actor_id=caller.user_id,
                actor_name=actor, stage="new", source=source_code, inquiry_no=inquiry_no)
    if body.note:
        await _emit(db, lead_id=lead_id, kind="lead.note_added", actor_id=caller.user_id,
                    actor_name=actor, note=body.note)

    # 9. the acknowledgement, through the outbox (CLAUDE.md rule 6, FS-003 rule 17).
    # recipient is E.164 with the plus, the provider's form.
    await db.execute(text(
        "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
        "VALUES ('whatsapp', :tk, :to, CAST(:p AS jsonb))"),
        {"tk": TEMPLATE_LEAD_ACK, "to": mobile,
         "p": json.dumps({"farmer_name": body.farmer_name, "inquiry_no": inquiry_no})})

    # 10. duplicates (rule 6, AC-LEAD-3): flag, never block. The response lists the
    # pending links whose other lead the caller can see.
    await _detect_duplicates(db, caller, str(lead_id), mobile=mobile, email=body.email,
                             farmer_name=body.farmer_name, village=body.village,
                             territory_id=str(body.territory_id))
    # 11. score again now that every contributing event is written: the create-time
    # note and a duplicate flag count toward engagement (cross-vendor P2). The
    # rescore is an UPDATE under the leads edit policy, so a create-only caller
    # keeps the pre-event score rather than failing the whole create.
    if await _has_permission(db, "leads", "edit"):
        await _rescore(db, str(lead_id))
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


async def _route_intake(db: AsyncSession, territory_id: str, partner_id: str | None
                        ) -> tuple[str | None, str, str | None]:
    """A public lead (FS-003a §5): the covering unit, the auto-assigned officer or
    nobody (the unassigned list), and the QR code's partner."""
    owner = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                              {"t": territory_id})).scalar_one_or_none()
    return (str(owner) if owner else None, await _covering_org_unit(db, territory_id),
            partner_id)


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


_LEAD_PEOPLE = [("owner_user_id", "owner_name"), ("created_by", "created_by_name")]
_LEAD_PARTNERS = [("assigned_partner_id", "partner_name")]


def _row_to_lead(row: Any, *, duplicates: list[DuplicateRef],
                 names: people.Names | None = None) -> Lead:
    """The non-person fields, plus the people: from the RLS-filtered joins, and
    from people_names() where the caller's scope did not reach (GAP-060). get_lead
    overrides the people from lead_people()."""
    names = names or people.Names()
    return Lead(
        id=str(row.id), inquiry_no=row.inquiry_no, stage=row.stage,
        inquiry_type=row.inquiry_type, mis_system=row.mis_code, source=row.source_code,
        farmer_name=row.farmer_name, mobile=row.mobile, email=row.email,
        territory=TerritoryRef(id=str(row.territory_id), name=row.territory_name,
                               level=row.territory_level),
        village=row.village,
        owner=names.user(row.owner_user_id, row.owner_name),
        owner_org_unit=OrgUnitRef(id=str(row.owner_org_unit_id),
                                  name=row.owner_org_unit_name),
        assigned_partner=names.partner(row.assigned_partner_id, row.partner_name,
                                       row.partner_type),
        score=_dec(row.score), priority=row.priority, estimated_value=_dec(row.estimated_value),
        lost_reason=ReasonRef(id=str(row.lost_reason_id), code=row.lost_reason_code,
                              name=row.lost_reason_name) if row.lost_reason_id else None,
        lost_note=row.lost_note, reopen_count=row.reopen_count,
        merged_into=MergedRef(id=str(row.merged_into_id), inquiry_no=row.merged_into_no)
        if row.merged_into_id and row.merged_into_no else None,
        first_contacted_at=_iso(row.first_contacted_at),
        last_activity_at=_iso_req(row.last_activity_at), created_at=_iso_req(row.created_at),
        created_by=names.user(row.created_by, row.created_by_name),
        duplicates=duplicates)


# ── lifecycle: transition, reopen, notes, timeline ───────────────────────────

async def _lock(db: AsyncSession, lead_id: str) -> Any:
    """SELECT ... FOR UPDATE under the leads UPDATE policy (rule 19). A caller who
    may see the row but not edit it gets zero rows, which the caller treats as 404
    after require('leads','edit') has already passed. Returns the locked row."""
    return (await db.execute(text(
        "SELECT stage::text AS stage, first_contacted_at, lost_from_stage::text AS lost_from, "
        "lost_reason_id, lost_note, territory_id, owner_user_id, owner_org_unit_id, "
        "assigned_partner_id, deleted_at FROM lead WHERE id = :id FOR UPDATE"),
        {"id": lead_id})).one_or_none()


async def transition_lead(db: AsyncSession, caller: Caller, lead_id: str,
                          body: LeadTransition) -> Lead:
    """Move a lead along the lifecycle (rules 8-10). Validated against the stage the
    row holds under the lock, not the one the caller saw."""
    row = await _lock(db, lead_id)
    if row is None:
        raise NotFoundError("No such lead.")
    current = row.stage
    if body.expected_stage and body.expected_stage != current:
        raise StageChangedError(f"The lead is now {current}.", fields={"stage": current})
    if current in domain.TERMINAL:
        raise ValidationFailed("This lead is closed and cannot change stage.",
                               code="stage_terminal", fields={"stage": current})
    if not domain.can_transition(current, body.to_stage):
        raise ValidationFailed(f"A {current} lead cannot move to {body.to_stage}.",
                               code="invalid_transition", fields={"to_stage": body.to_stage})
    if body.to_stage in domain.VIA_QUOTATION:
        raise ValidationFailed(
            "This stage is reached by sending a quotation, not from here.",
            code="quotation_required", fields={"to_stage": body.to_stage})
    if body.to_stage in domain.REQUIRES_QUOTATION:
        # Counted as the owner: an EXISTS under the caller's quotation policies would
        # say no to an officer whose colleague raised the accepted quotation
        # (FS-005 edge case 9).
        accepted: bool = (await db.execute(
            text("SELECT quotation_accepted_for_lead(CAST(:id AS uuid))"),
            {"id": lead_id})).scalar_one()
        if not accepted:
            raise ValidationFailed(
                "This stage needs an accepted quotation on the lead.",
                code="quotation_required", fields={"to_stage": body.to_stage})

    payload: dict[str, Any] = {"from": current, "to": body.to_stage}
    if body.to_stage == "lost":
        if not body.lost_reason_id:
            raise ValidationFailed(fields={"lost_reason_id": "a lost reason is required"})
        ok = (await db.execute(text(
            "SELECT 1 FROM won_lost_reason WHERE id = :r AND kind = 'lost' "
            "AND is_active AND deleted_at IS NULL"), {"r": body.lost_reason_id})).first()
        if not ok:
            raise ValidationFailed(fields={"lost_reason_id": "not an active lost reason"})
        payload.update(lost_reason_id=body.lost_reason_id, lost_note=body.lost_note)

    actor = await _actor_name(db)
    await _emit(db, lead_id=lead_id, kind="lead.stage_changed", actor_id=caller.user_id,
                actor_name=actor, **payload)
    await db.execute(text("""
        UPDATE lead SET
            stage = CAST(:to AS lead_stage),
            first_contacted_at = COALESCE(first_contacted_at,
                CASE WHEN :to = 'contacted' THEN now() END),
            lost_reason_id = CASE WHEN :to = 'lost' THEN CAST(:lr AS uuid) ELSE lost_reason_id END,
            lost_note = CASE WHEN :to = 'lost' THEN :ln ELSE lost_note END,
            lost_from_stage = CASE WHEN :to = 'lost' THEN CAST(:frm AS lead_stage)
                                   ELSE lost_from_stage END
         WHERE id = :id"""),
        {"to": body.to_stage, "lr": body.lost_reason_id, "ln": body.lost_note,
         "frm": current, "id": lead_id})
    await _rescore(db, lead_id)
    return await get_lead(db, caller, lead_id)


async def reopen_lead(db: AsyncSession, caller: Caller, lead_id: str,
                      body: LeadReopen) -> Lead:
    """Bring a lost lead back to the stage it was lost from (rule 11). The reason and
    note move to the timeline and are cleared on the row; reopen_count goes up."""
    row = await _lock(db, lead_id)
    if row is None:
        raise NotFoundError("No such lead.")
    if row.stage != "lost":
        raise ValidationFailed("Only a lost lead can be reopened.", code="stage_terminal",
                               fields={"stage": row.stage})
    target = row.lost_from or "new"
    actor = await _actor_name(db)
    await _emit(db, lead_id=lead_id, kind="lead.reopened", actor_id=caller.user_id,
                actor_name=actor, **{"from": "lost", "to": target,
                                     "lost_reason_id": str(row.lost_reason_id)
                                     if row.lost_reason_id else None,
                                     "lost_note": row.lost_note, "note": body.note})
    await db.execute(text(
        "UPDATE lead SET stage = CAST(:t AS lead_stage), lost_reason_id = NULL, "
        "lost_note = NULL, reopen_count = reopen_count + 1 WHERE id = :id"),
        {"t": target, "id": lead_id})
    await _rescore(db, lead_id)
    return await get_lead(db, caller, lead_id)


async def add_note(db: AsyncSession, caller: Caller, lead_id: str,
                   body: LeadNote) -> TimelineEvent:
    """Append a note to a lead's timeline (rule 16). It bumps last_activity_at and
    counts toward engagement, so the score is recomputed."""
    if await _lock(db, lead_id) is None:
        raise NotFoundError("No such lead.")
    actor = await _actor_name(db)
    ev = await _emit(db, lead_id=lead_id, kind="lead.note_added", actor_id=caller.user_id,
                     actor_name=actor, note=body.note)
    await _rescore(db, lead_id)
    return TimelineEvent(id=str(ev.id), kind="lead.note_added",
                         occurred_at=_iso_req(ev.occurred_at),
                         actor=UserRef(id=caller.user_id, full_name=actor),
                         payload={"actor_name": actor, "note": body.note})


async def timeline(db: AsyncSession, caller: Caller, lead_id: str, *, limit: int = 100,
                   cursor: str | None = None) -> TimelinePage:
    """A lead's history, newest first, keyset-paged by (occurred_at, id). Reads
    through lead_timeline(), a definer function that answers only for a visible lead
    and folds in the events of any lead merged into this one (rule 16)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    if not (await db.execute(text("SELECT lead_visible(:id)"), {"id": lead_id})).scalar_one():
        raise NotFoundError("No such lead.")
    before_at, before_id = (None, None)
    if cursor:
        before_at, before_id = _decode_cursor(cursor)
    rows = (await db.execute(text(
        "SELECT id, kind, occurred_at, actor_id, payload "
        "FROM lead_timeline(:id, :bat, :bid, :lim)"),
        {"id": lead_id, "bat": before_at, "bid": before_id, "lim": limit + 1})).all()

    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_cursor(last.occurred_at, str(last.id))
        rows = rows[:limit]

    events: list[TimelineEvent] = []
    for r in rows:
        payload = r.payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        actor = None
        # question 15.14: a partner never learns which approver decided an order
        hidden = caller.partner_id is not None and actor_hidden_from_partner(r.kind)
        if hidden and isinstance(payload, dict):
            # the name travels in the payload too; hiding `actor` alone left it there
            # (FS-015 code review F-1, executed)
            payload = {k: v for k, v in payload.items() if k != "actor_name"}
        if r.actor_id is not None and not hidden:
            actor = UserRef(id=str(r.actor_id), full_name=payload.get("actor_name") or "")
        events.append(TimelineEvent(id=str(r.id), kind=r.kind, occurred_at=_iso_req(r.occurred_at),
                                    actor=actor, payload=payload or {}))
    return TimelinePage(data=events, meta=PageMeta(limit=limit, next_cursor=next_cursor))


# ── assignment (rule 12) ─────────────────────────────────────────────────────

async def assign_lead(db: AsyncSession, caller: Caller, lead_id: str,
                      body: LeadAssign) -> Lead:
    """Set the owner and/or the partner. A field left out is unchanged; a field sent
    null is cleared. The owner check is authz_user_assignable() (the service cannot
    read the target's app_user row); the partner is checked by authz_visible(), the
    same function the parent-guard trigger enforces underneath (rule 12).

    GAP-061: owner_org_unit_id is not re-routed to the new owner's own sales unit
    (rule 4 path A), because reading that unit needs users.view the assigner lacks.
    The lead keeps its current unit, which stays in the assigner's scope; the new
    owner sees it by owner_user_id. A definer that returns the owner's unit closes
    this later."""
    fields = body.model_fields_set
    if not ({"owner_user_id", "assigned_partner_id"} & fields):
        raise ValidationFailed(fields={"owner_user_id": "provide an owner or a partner"})
    # FS-006 rule 20: the candidate's app_user row is shared BEFORE the lead is
    # locked, app_user then lead always, so an assign holding the lead can never
    # wait on a handover that holds the person and wants the lead. An unassignable
    # owner on a missing or closed lead therefore answers 422 before the 404 or
    # stage_terminal would, which leaks nothing about the lead.
    if "owner_user_id" in fields and body.owner_user_id is not None:
        if caller.scopes.get("leads") not in ("global", "org_subtree"):
            raise ValidationFailed(fields={"owner_user_id": "not assignable by you"})
        ok: bool = (await db.execute(
            text("SELECT authz_user_assignable('leads', CAST(:u AS uuid))"),
            {"u": body.owner_user_id})).scalar_one()
        if not ok:
            raise ValidationFailed(fields={"owner_user_id": "not assignable by you"})

    row = await _lock(db, lead_id)
    if row is None:
        raise NotFoundError("No such lead.")
    if row.stage in domain.TERMINAL:
        raise ValidationFailed("This lead is closed and cannot be reassigned.",
                               code="stage_terminal", fields={"stage": row.stage})

    sets: list[str] = []
    params: dict[str, Any] = {"id": lead_id}
    payload: dict[str, Any] = {}
    if "owner_user_id" in fields:
        sets.append("owner_user_id = CAST(:owner AS uuid)")
        params["owner"] = body.owner_user_id
        payload["owner_user_id"] = body.owner_user_id
    if "assigned_partner_id" in fields:
        if body.assigned_partner_id is not None:
            vis: bool = (await db.execute(
                text("SELECT authz_visible('channel_partner', CAST(:p AS uuid))"),
                {"p": body.assigned_partner_id})).scalar_one()
            if not vis:
                raise ValidationFailed(fields={"assigned_partner_id": "not in your scope"})
        sets.append("assigned_partner_id = CAST(:partner AS uuid)")
        params["partner"] = body.assigned_partner_id
        payload["assigned_partner_id"] = body.assigned_partner_id

    await _emit(db, lead_id=lead_id, kind="lead.assigned", actor_id=caller.user_id,
                actor_name=await _actor_name(db), **payload)
    await db.execute(text(f"UPDATE lead SET {', '.join(sets)} WHERE id = :id"), params)
    await _rescore(db, lead_id)
    return await get_lead(db, caller, lead_id)


async def assignees(db: AsyncSession, caller: Caller) -> list[Assignee]:
    """The staff the caller may assign a lead to (rule 12). staff_directory() is a
    definer read: all active staff for a global caller, the org subtree for
    org_subtree, nobody otherwise. Names and org units only."""
    rows = (await db.execute(text(
        "SELECT sd.id, sd.full_name, sd.org_unit_id, ou.name AS org_name "
        "FROM staff_directory('leads') sd LEFT JOIN org_unit ou ON ou.id = sd.org_unit_id "
        "ORDER BY sd.full_name"))).all()
    return [Assignee(id=str(r.id), full_name=r.full_name,
                     org_unit=OrgUnitRef(id=str(r.org_unit_id), name=r.org_name)
                     if r.org_unit_id else None) for r in rows]


# ── edit and delete ──────────────────────────────────────────────────────────

_PATCH_REQUIRED = frozenset({"farmer_name", "mobile", "territory_id", "inquiry_type",
                             "mis_system", "source"})


async def patch_lead(db: AsyncSession, caller: Caller, lead_id: str, body: LeadPatch) -> Lead:
    """Correct the lead's own fields (FS-003 4). Not the stage, owner or partner.
    Required fields cannot be cleared, which is also the qualification gate: a
    qualified lead can never lose one. A territory move re-routes the owning unit
    (rule 4) and must keep the row in the caller's scope (stage 4)."""
    row = await _lock(db, lead_id)
    if row is None:
        raise NotFoundError("No such lead.")
    if row.stage in domain.TERMINAL:
        raise ValidationFailed("This lead is closed and cannot be edited.",
                               code="stage_terminal", fields={"stage": row.stage})
    fields = body.model_fields_set
    if not fields:
        raise ValidationFailed(fields={"body": "nothing to change"})
    for f in fields & _PATCH_REQUIRED:
        if getattr(body, f) is None:
            raise ValidationFailed(fields={f: "cannot be cleared"})

    sets: list[str] = []
    params: dict[str, Any] = {"id": lead_id}
    changed: dict[str, Any] = {}

    if "farmer_name" in fields:
        sets.append("farmer_name = :farmer_name")
        params["farmer_name"] = body.farmer_name
        changed["farmer_name"] = body.farmer_name
    if "mobile" in fields:
        try:
            mobile = domain.normalise_mobile(body.mobile or "")
        except domain.MobileError as exc:
            raise ValidationFailed(fields={"mobile": str(exc)}) from exc
        sets.append("mobile = :mobile")
        params["mobile"] = mobile
        changed["mobile"] = mobile
    if "email" in fields:
        sets.append("email = :email")
        params["email"] = body.email
        changed["email"] = body.email
    if "village" in fields:
        sets.append("village = :village")
        params["village"] = body.village
        changed["village"] = body.village
    if "inquiry_type" in fields:
        sets.append("inquiry_type = CAST(:it AS inquiry_type)")
        params["it"] = body.inquiry_type
        changed["inquiry_type"] = body.inquiry_type
    if "mis_system" in fields:
        mis = (await db.execute(text(
            "SELECT id FROM mis_system WHERE code = :c AND is_active AND deleted_at IS NULL"),
            {"c": body.mis_system})).scalar_one_or_none()
        if mis is None:
            raise ValidationFailed(fields={"mis_system": "not an active system"})
        sets.append("mis_system_id = :mis")
        params["mis"] = mis
        changed["mis_system"] = body.mis_system
    if "source" in fields:
        src = (await db.execute(text(
            "SELECT id FROM lead_source WHERE code = :c AND is_active AND deleted_at IS NULL"),
            {"c": body.source})).scalar_one_or_none()
        if src is None:
            raise ValidationFailed(fields={"source": "not an active source"})
        sets.append("lead_source_id = :src")
        params["src"] = src
        changed["source"] = body.source
    if "estimated_value" in fields:
        sets.append("estimated_value = :est")
        params["est"] = body.estimated_value
        changed["estimated_value"] = _dec(body.estimated_value)

    territory_id = body.territory_id  # None only when unsent: it is in _PATCH_REQUIRED
    if territory_id is not None and territory_id != str(row.territory_id):
        # Rule 4: with an owner the unit is the owner's (path A, kept as-is, GAP-061);
        # with no owner it is routed by the new territory (path B).
        new_oou = str(row.owner_org_unit_id)
        if row.owner_user_id is None:
            new_oou = await _covering_org_unit(db, territory_id)
        await _assert_insert_in_scope(
            db, caller, territory_id=territory_id,
            owner_user_id=str(row.owner_user_id) if row.owner_user_id else None,
            owner_org_unit_id=new_oou,
            assigned_partner_id=str(row.assigned_partner_id) if row.assigned_partner_id else None)
        sets.append("territory_id = CAST(:territory AS uuid)")
        params["territory"] = body.territory_id
        changed["territory_id"] = body.territory_id
        if new_oou != str(row.owner_org_unit_id):
            sets.append("owner_org_unit_id = CAST(:oou AS uuid)")
            params["oou"] = new_oou

    if not sets:
        return await get_lead(db, caller, lead_id)   # nothing actually changed

    await _emit(db, lead_id=lead_id, kind="lead.updated", actor_id=caller.user_id,
                actor_name=await _actor_name(db), changed=changed)
    await db.execute(text(f"UPDATE lead SET {', '.join(sets)} WHERE id = :id"), params)
    # Rule 6: an identity change re-runs duplicate detection on the row as it now is.
    if changed.keys() & {"mobile", "farmer_name", "village", "email", "territory_id"}:
        cur = (await db.execute(text(
            "SELECT mobile, email, farmer_name, village, territory_id FROM lead WHERE id = :id"),
            {"id": lead_id})).one()
        await _detect_duplicates(db, caller, lead_id, mobile=cur.mobile, email=cur.email,
                                 farmer_name=cur.farmer_name, village=cur.village,
                                 territory_id=str(cur.territory_id))
    # Score after every contributing event, a duplicate flag included (cross-vendor P2).
    await _rescore(db, lead_id)
    return await get_lead(db, caller, lead_id)


async def delete_lead(db: AsyncSession, caller: Caller, lead_id: str) -> None:
    """Soft delete (rule 18, 21). Needs leads.delete: the restrictive soft-delete
    policy is checked against the updated row, so an edit-only caller gets 42501
    (ISS-065). Its pending duplicate links, hidden ones included, are closed by
    lead_close_links() so nobody's queue holds a pair they cannot act on (EC-15).
    Already deleted is a no-op."""
    row = await _lock(db, lead_id)
    if row is None:
        raise NotFoundError("No such lead.")
    if row.deleted_at is not None:
        return
    await db.execute(text("SELECT lead_close_links(CAST(:id AS uuid), 'dismissed')"),
                     {"id": lead_id})
    await _emit(db, lead_id=lead_id, kind="lead.deleted", actor_id=caller.user_id,
                actor_name=await _actor_name(db))
    await db.execute(text("UPDATE lead SET deleted_at = now() WHERE id = :id"), {"id": lead_id})


# ── duplicates (rules 6 and 13) ──────────────────────────────────────────────

_NAME_GEO_THRESHOLD = 0.6   # GAP-047: an assumption until the client tunes it


async def _detect_duplicates(db: AsyncSession, caller: Caller, lead_id: str, *, mobile: str,
                             email: str | None, farmer_name: str, village: str | None,
                             territory_id: str) -> None:
    """Flag pending links to leads that look like this one (rule 6): exact mobile,
    exact email, or name plus village by trigram within the same district, among
    leads neither merged nor deleted. Runs under the caller's read scope, so only
    visible candidates are found, which is exactly what the link policy admits.
    Never blocks the write. Writing a link needs leads.edit; without it nothing is
    flagged rather than the whole request failing with 42501."""
    if not await _has_permission(db, "leads", "edit"):
        return
    matches: dict[str, tuple[str, Decimal]] = {}
    for r in (await db.execute(text(
            "SELECT id FROM lead WHERE id <> CAST(:me AS uuid) AND mobile = :m "
            "AND stage <> 'merged' AND deleted_at IS NULL"),
            {"me": lead_id, "m": mobile})).all():
        matches.setdefault(str(r.id), ("mobile", Decimal("1.00")))
    if email:
        for r in (await db.execute(text(
                "SELECT id FROM lead WHERE id <> CAST(:me AS uuid) AND email = :e "
                "AND stage <> 'merged' AND deleted_at IS NULL"),
                {"me": lead_id, "e": email})).all():
            matches.setdefault(str(r.id), ("email", Decimal("1.00")))
    district = (await db.execute(text(
        "SELECT t.id FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id "
        "WHERE tc.descendant_id = CAST(:tid AS uuid) AND t.level = 'district' "
        "ORDER BY tc.depth LIMIT 1"), {"tid": territory_id})).scalar_one_or_none()
    if district is not None:
        nv = f"{farmer_name} {village or ''}".strip()
        for r in (await db.execute(text(
                "SELECT id, similarity(farmer_name || ' ' || coalesce(village, ''), :nv) AS sim "
                "FROM lead WHERE id <> CAST(:me AS uuid) AND stage <> 'merged' "
                "AND deleted_at IS NULL "
                "AND territory_id IN (SELECT descendant_id FROM territory_closure "
                "                     WHERE ancestor_id = :d) "
                "AND similarity(farmer_name || ' ' || coalesce(village, ''), :nv) >= :th"),
                {"nv": nv, "me": lead_id, "d": district, "th": _NAME_GEO_THRESHOLD})).all():
            matches.setdefault(str(r.id), ("name_geo", Decimal(str(round(float(r.sim), 2)))))
    if not matches:
        return
    for other, (signal, score) in matches.items():
        await db.execute(text(
            "INSERT INTO lead_duplicate_link "
            "(lead_a_id, lead_b_id, signal, score, state, created_by) "
            "VALUES (least(CAST(:x AS uuid), CAST(:y AS uuid)), "
            "        greatest(CAST(:x AS uuid), CAST(:y AS uuid)), "
            "        CAST(:s AS lead_dup_signal), :sc, 'pending', CAST(:me AS uuid)) "
            "ON CONFLICT (lead_a_id, lead_b_id) DO NOTHING"),
            {"x": lead_id, "y": other, "s": signal, "sc": score, "me": caller.user_id})
    await _emit(db, lead_id=lead_id, kind="lead.duplicate_flagged", actor_id=caller.user_id,
                actor_name=await _actor_name(db),
                matches=[{"lead_id": o, "signal": s, "score": str(sc)}
                         for o, (s, sc) in matches.items()])


async def duplicates(db: AsyncSession, caller: Caller, *, limit: int = 50,
                     cursor: str | None = None) -> DuplicatePage:
    """The review queue: pending pairs where both leads are in scope (the link
    policy), newest first, keyset-paged by (created_at, id)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    where = ["dl.state = 'pending'"]
    params: dict[str, Any] = {"lim": limit + 1}
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append("(dl.created_at, dl.id) < (CAST(:cts AS timestamptz), CAST(:cid AS uuid))")
        params.update(cts=c_ts, cid=c_id)
    links = (await db.execute(text(
        "SELECT dl.id, dl.signal, dl.score, dl.state, dl.created_at, dl.lead_a_id, dl.lead_b_id "
        f"FROM lead_duplicate_link dl WHERE {' AND '.join(where)} "
        "ORDER BY dl.created_at DESC, dl.id DESC LIMIT :lim"), params)).all()
    next_cursor = None
    if len(links) > limit:
        last = links[limit - 1]
        next_cursor = _encode_cursor(last.created_at, str(last.id))
        links = links[:limit]
    if not links:
        return DuplicatePage(data=[], meta=PageMeta(limit=limit, next_cursor=None))
    ids = list({str(x) for r in links for x in (r.lead_a_id, r.lead_b_id)})
    rows = (await db.execute(text(_LEAD_SELECT + " WHERE l.id = ANY(:ids)"), {"ids": ids})).all()
    names = await people.resolve(db, rows, _LEAD_PEOPLE, _LEAD_PARTNERS)
    by_id = {str(r.id): _row_to_lead(r, duplicates=[], names=names) for r in rows}
    pairs = [DuplicatePair(link_id=str(r.id), signal=r.signal, score=_dec(r.score), state=r.state,
                           created_at=_iso(r.created_at) or "",
                           lead_a=by_id[str(r.lead_a_id)], lead_b=by_id[str(r.lead_b_id)])
             for r in links if str(r.lead_a_id) in by_id and str(r.lead_b_id) in by_id]
    return DuplicatePage(data=pairs, meta=PageMeta(limit=limit, next_cursor=next_cursor))


async def dismiss_duplicate(db: AsyncSession, caller: Caller, link_id: str) -> DismissResult:
    """Mark a pending pair as not a duplicate. The link's UPDATE policy needs both
    leads visible and leads.edit; zero rows is 404."""
    row = (await db.execute(text(
        "UPDATE lead_duplicate_link SET state = 'dismissed', resolved_by = CAST(:me AS uuid), "
        "resolved_at = now() WHERE id = CAST(:id AS uuid) AND state = 'pending' "
        "RETURNING lead_a_id, lead_b_id"), {"me": caller.user_id, "id": link_id})).one_or_none()
    if row is None:
        raise NotFoundError("No such pending duplicate pair.")
    actor = await _actor_name(db)
    for lid in (row.lead_a_id, row.lead_b_id):
        await _emit(db, lead_id=lid, kind="lead.duplicate_dismissed", actor_id=caller.user_id,
                    actor_name=actor, link_id=link_id)
    return DismissResult(link_id=link_id)


async def merge_lead(db: AsyncSession, caller: Caller, lead_id: str, body: LeadMerge) -> Lead:
    """Merge this lead (the loser) into the survivor (rule 13). Staff only. The work
    is lead_merge(), one guarded definer step, because it must touch links and
    merged leads the caller cannot see; its own errors carry custom SQLSTATEs that
    are mapped here."""
    if caller.partner_id is not None:
        raise ForbiddenError("Only staff can merge leads.")
    if body.into_lead_id == lead_id:
        raise ValidationFailed("A lead cannot merge into itself.", code="merge_self",
                               fields={"into_lead_id": "same lead"})
    if await _lock(db, lead_id) is None:
        raise NotFoundError("No such lead.")
    try:
        await db.execute(text("SELECT lead_merge(CAST(:loser AS uuid), CAST(:surv AS uuid))"),
                         {"loser": lead_id, "surv": body.into_lead_id})
    except DBAPIError as exc:
        code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        if code == "LEADN":
            raise NotFoundError("No such lead.") from exc
        if code == "LEADT":
            raise ValidationFailed("A won, lost or merged lead cannot be merged.",
                                   code="merge_terminal", fields={"stage": "terminal"}) from exc
        if code == "LEADM":
            raise ValidationFailed("A lead cannot merge into itself.", code="merge_self") from exc
        raise
    return await get_lead(db, caller, body.into_lead_id)


# ── lookup admin (rule 23; masters.edit) ─────────────────────────────────────
#
# The table name is one of these three constants chosen by the route, never
# caller input, so it is safe to interpolate. Every write is audited by the
# audit_row() trigger; rows are added and switched off, never renamed or deleted.
_LOOKUP_COLS: dict[str, frozenset[str]] = {
    "lead_source": frozenset({"sort_order", "quality"}),
    "mis_system": frozenset(),
    "won_lost_reason": frozenset({"sort_order", "kind"}),
    "meeting_type": frozenset({"sort_order"}),  # FS-014
    "complaint_type": frozenset({"sort_order"}),  # FS-015
}


async def create_lookup(db: AsyncSession, table: str, body: LookupCreate) -> LookupItem:
    extra = _LOOKUP_COLS[table]
    # created_by from the claim, as on every business row. The seed leaves it null.
    cols = ["code", "name", "created_by"]
    vals = [":code", ":name", "app_current_user_id()"]
    params: dict[str, Any] = {"code": body.code, "name": body.name}
    if "sort_order" in extra and body.sort_order is not None:
        cols.append("sort_order")
        vals.append(":so")
        params["so"] = body.sort_order
    if "quality" in extra and body.quality is not None:
        cols.append("quality")
        vals.append(":q")
        params["q"] = body.quality
    if "kind" in extra:
        cols.append("kind")
        vals.append("CAST(:kind AS won_lost_kind)")
        params["kind"] = body.kind or "lost"
    try:
        r = (await db.execute(text(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
            "RETURNING id, code, name, is_active"), params)).one()
    except DBAPIError as exc:
        if (getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)) == "23505":
            raise ValidationFailed(fields={"code": "already exists"}) from exc
        raise
    return LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)


async def update_lookup(db: AsyncSession, table: str, item_id: str,
                        body: LookupUpdate) -> LookupItem:
    extra = _LOOKUP_COLS[table]
    fields = body.model_fields_set
    sets: list[str] = []
    params: dict[str, Any] = {"id": item_id}
    if "is_active" in fields and body.is_active is not None:
        sets.append("is_active = :active")
        params["active"] = body.is_active
    if "sort_order" in fields and "sort_order" in extra and body.sort_order is not None:
        sets.append("sort_order = :so")
        params["so"] = body.sort_order
    if "quality" in fields and "quality" in extra and body.quality is not None:
        sets.append("quality = :q")
        params["q"] = body.quality
    if not sets:
        raise ValidationFailed(fields={"body": "nothing to change"})
    sets.append("updated_by = app_current_user_id()")
    r = (await db.execute(text(
        f"UPDATE {table} SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) "
        "RETURNING id, code, name, is_active"), params)).one_or_none()
    if r is None:
        raise NotFoundError("No such row.")
    return LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)


# Caps and hour bands must stay positive or the score divides by zero (rule 7).
_SCORING_POSITIVE = frozenset({"value_cap", "engagement_cap", "speed_fast_hours",
                               "speed_slow_hours"})


async def get_scoring(db: AsyncSession) -> list[ScoringItem]:
    rows = (await db.execute(text("SELECT key, value FROM lead_score_rule ORDER BY key"))).all()
    return [ScoringItem(key=r.key, value=str(r.value)) for r in rows]


async def patch_scoring(db: AsyncSession, body: ScoringPatch) -> list[ScoringItem]:
    known = {r.key for r in (await db.execute(text("SELECT key FROM lead_score_rule"))).all()}
    # Validate what will be stored, not what was sent: the column is numeric(12,2),
    # so "0.001" passes a raw positive check and lands as 0.00, after which every
    # score divides by zero (cross-vendor P2). Half-up matches Postgres rounding.
    stored = {k: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
              for k, v in body.values.items()}
    bad = {k: "unknown key" for k in stored if k not in known}
    for k, v in stored.items():
        if k in known and (v <= 0 if k in _SCORING_POSITIVE else v < 0):
            bad[k] = ("must be positive (at two decimal places)" if k in _SCORING_POSITIVE
                      else "must not be negative")
    if bad:
        raise ValidationFailed(fields=bad)
    for k, v in stored.items():
        await db.execute(text("UPDATE lead_score_rule SET value = :v WHERE key = :k"),
                         {"v": v, "k": k})
    return await get_scoring(db)


# ── list ─────────────────────────────────────────────────────────────────────

_MAX_LIMIT = 100

# The ceiling on `?include_total=true`. A count over a scoped table is a scan, and
# its cost grows with the rows the caller can see: measured at 3 ms server-side
# over 111 leads, which says nothing about a global administrator two years in
# (ISS-014). Counting one row past the ceiling and stopping bounds that forever,
# and the response says when it stopped so the screen can render "1000+".
#
# A thousand is chosen for the screen rather than the database: past forty pages
# nobody is paging, they are filtering.
TOTAL_CEILING = 1000


async def _capped_total(db: AsyncSession, table: Any, filters: list[Any]) -> tuple[int, bool]:
    """How many rows match, up to the ceiling, and whether there are more.

    The LIMIT is inside the subquery on purpose: it stops the scan, which is the
    whole point. `SELECT count(*) ... LIMIT 1001` would count everything and then
    return one row. The FROM is explicit because a global caller who also holds
    the delete permission has a predicate of `true`, which names no column, and
    `SELECT 1 WHERE true` is one row however many exist (code review F-6).
    """
    inner = (sa.select(sa.literal(1))
             .select_from(table)
             .where(sa.and_(*filters))
             .limit(TOTAL_CEILING + 1)
             .subquery())
    counted = await db.scalar(sa.select(sa.func.count()).select_from(inner)) or 0
    return (TOTAL_CEILING, True) if counted > TOTAL_CEILING else (int(counted), False)


async def _lead_filters(db: AsyncSession, caller: Caller, *, stage: str | None = None,
                        priority: str | None = None, owner_user_id: str | None = None,
                        owner: str | None = None, territory_id: str | None = None,
                        owner_org_unit_id: str | None = None,
                        assigned_partner_id: str | None = None,
                        source: str | None = None, inquiry_type: str | None = None,
                        created_from: str | None = None, created_to: str | None = None,
                        q: str | None = None) -> list[Any]:
    """The scope and every filter of the lead list, shared with the counts so the
    two can never disagree about which leads a filter means."""
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
    # Each filter takes its whole subtree: a state selects its districts and
    # talukas, an office the offices under it, a distributor its dealers. The
    # closures hold every node as its own descendant.
    if territory_id:
        where.append(lead_t.c.territory_id.in_(_under("territory_closure", territory_id)))
    if owner_org_unit_id:
        where.append(lead_t.c.owner_org_unit_id.in_(_under("org_closure", owner_org_unit_id)))
    if assigned_partner_id:
        where.append(lead_t.c.assigned_partner_id.in_(
            _under("partner_closure", assigned_partner_id)))
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
    # Everything above narrows the set the caller asked for. The cursor below
    # narrows it to one page, so the total is counted from `filters` and not from
    # `where`: a total that shrank as the user paged would be worse than none.
    return where


async def list_leads(db: AsyncSession, caller: Caller, *, stage: str | None = None,
                     priority: str | None = None, owner_user_id: str | None = None,
                     owner: str | None = None, territory_id: str | None = None,
                     owner_org_unit_id: str | None = None,
                     assigned_partner_id: str | None = None,
                     source: str | None = None, inquiry_type: str | None = None,
                     created_from: str | None = None, created_to: str | None = None,
                     q: str | None = None, limit: int = 50,
                     cursor: str | None = None,
                     include_total: bool = False) -> LeadPage:
    """The lead list, scoped and filtered, keyset-paged by (created_at desc, id).

    Enforcer 1 is scope_predicate; RLS re-checks the same rows underneath. No total
    (ISS-014): counting a scoped table on every page is the cost this avoids.
    """
    limit = max(1, min(limit, _MAX_LIMIT))

    where = await _lead_filters(
        db, caller, stage=stage, priority=priority, owner_user_id=owner_user_id, owner=owner,
        territory_id=territory_id, owner_org_unit_id=owner_org_unit_id,
        assigned_partner_id=assigned_partner_id, source=source, inquiry_type=inquiry_type,
        created_from=created_from, created_to=created_to, q=q)
    filters = list(where)
    if cursor:
        c_ts, c_id = _decode_cursor(cursor)
        where.append(sa.or_(lead_t.c.created_at < c_ts,
                            sa.and_(lead_t.c.created_at == c_ts, lead_t.c.id < c_id)))

    total, total_capped = (await _capped_total(db, lead_t, filters)
                           if include_total else (None, False))

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
        return LeadPage(data=[], meta=PageMeta(limit=limit, next_cursor=None,
                                              total=total, total_capped=total_capped))

    rows = (await db.execute(text(_LEAD_SELECT + " WHERE l.id = ANY(:ids)"),
                             {"ids": ids})).all()
    by_id = {str(r.id): r for r in rows}
    names = await people.resolve(db, rows, _LEAD_PEOPLE, _LEAD_PARTNERS)
    data = [_row_to_lead(by_id[i], duplicates=[], names=names) for i in ids if i in by_id]
    return LeadPage(data=data, meta=PageMeta(limit=limit, next_cursor=next_cursor,
                                            total=total, total_capped=total_capped))


_PRIORITIES = ("hot", "warm", "cold")


async def lead_stats(db: AsyncSession, caller: Caller, **filters: str | None) -> LeadStats:
    """Counts under the list's own scope and filters (API review B2). One pass
    over the matching rows; no ceiling, because a count per stage is the point."""
    where = await _lead_filters(db, caller, **filters)
    stage = sa.cast(lead_t.c.stage, sa.Text)
    priority = sa.cast(lead_t.c.priority, sa.Text)
    inquiry = sa.cast(lead_t.c.inquiry_type, sa.Text)
    rows = (await db.execute(
        sa.select(stage.label("stage"), priority.label("priority"),
                  (lead_t.c.owner_user_id.is_(None)).label("unassigned"),
                  lead_t.c.lead_source_id.label("source_id"), inquiry.label("inquiry"),
                  sa.func.count().label("n"))
        .select_from(lead_t).where(sa.and_(*where))
        .group_by(stage, priority, lead_t.c.owner_user_id.is_(None),
                  lead_t.c.lead_source_id, inquiry))).all()
    sources = {str(r.id): r.code for r in (await db.execute(text(
        "SELECT id, code::text AS code FROM lead_source WHERE deleted_at IS NULL "
        "ORDER BY sort_order, code"))).all()}
    by_stage = dict.fromkeys(domain.STAGES, 0)
    by_priority = dict.fromkeys(_PRIORITIES, 0)
    by_source = dict.fromkeys(sources.values(), 0)
    by_inquiry_type = dict.fromkeys(_INQUIRY_TYPES, 0)
    unassigned = total = 0
    for r in rows:
        total += r.n
        by_stage[r.stage] = by_stage.get(r.stage, 0) + r.n
        if r.priority:
            by_priority[r.priority] = by_priority.get(r.priority, 0) + r.n
        if r.unassigned:
            unassigned += r.n
        code = sources.get(str(r.source_id))
        if code is not None:
            by_source[code] += r.n
        if r.inquiry:
            by_inquiry_type[r.inquiry] = by_inquiry_type.get(r.inquiry, 0) + r.n
    due_today, overdue = await _follow_ups(db, caller, where)
    return LeadStats(total=total, by_stage=by_stage, by_priority=by_priority,
                     unassigned=unassigned, by_source=by_source,
                     by_inquiry_type=by_inquiry_type, follow_ups_due_today=due_today,
                     follow_ups_overdue=overdue)


_INQUIRY_TYPES = ("commercial", "subsidised", "industrial")


async def _follow_ups(db: AsyncSession, caller: Caller, where: list[Any]
                      ) -> tuple[int | None, int | None]:
    """Open tasks on the filtered leads (FS-014), under the tasks policies: due today
    and overdue by the planner's own IST windows. None without a tasks scope, so a
    dealer's dashboard shows no figure rather than a false zero (BE-002, BE-007)."""
    if "tasks" not in caller.scopes:
        return None, None
    today = today_ist()
    start, end = task_domain.day_bounds(today)
    window = task_domain.overdue_window(today, today)
    assert window is not None
    leads = sa.select(lead_t.c.id).where(sa.and_(*where))
    task_t = sa.table("task", sa.column("lead_id", _UUID), sa.column("status"),
                      sa.column("due_at", sa.DateTime(timezone=True)))
    open_ = sa.cast(task_t.c.status, sa.Text) == "open"
    row = (await db.execute(sa.select(
        sa.func.count().filter(sa.and_(task_t.c.due_at >= start, task_t.c.due_at < end)),
        sa.func.count().filter(sa.and_(task_t.c.due_at >= window[0],
                                       task_t.c.due_at < window[1])))
        .select_from(task_t)
        .where(open_, task_t.c.lead_id.in_(leads.scalar_subquery())))).one()
    return int(row[0]), int(row[1])


def _under(closure: str, ancestor: str) -> Any:
    """The ids at and below `ancestor` in one of the three trees. The closures are
    readable by any authenticated caller; scope is applied by the list itself."""
    t = sa.table(closure, sa.column("ancestor_id", _UUID), sa.column("descendant_id", _UUID))
    return sa.select(t.c.descendant_id).where(t.c.ancestor_id == ancestor).scalar_subquery()


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


async def list_meeting_types(db: AsyncSession) -> list[LookupItem]:
    """FS-014: switched-off types included with `is_active` false, as for lost reasons."""
    rows = (await db.execute(text(
        "SELECT id, code, name, is_active FROM meeting_type "
        "WHERE deleted_at IS NULL ORDER BY sort_order, name"))).all()
    return [LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)
            for r in rows]


async def list_complaint_types(db: AsyncSession) -> list[LookupItem]:
    """FS-015: switched-off types included with `is_active` false."""
    rows = (await db.execute(text(
        "SELECT id, code, name, is_active FROM complaint_type "
        "WHERE deleted_at IS NULL ORDER BY sort_order, name"))).all()
    return [LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)
            for r in rows]


async def list_lost_reasons(db: AsyncSession) -> list[LookupItem]:
    rows = (await db.execute(text(
        "SELECT id, code, name, is_active FROM won_lost_reason "
        "WHERE kind = 'lost' AND deleted_at IS NULL ORDER BY sort_order, name"))).all()
    return [LookupItem(id=str(r.id), code=r.code, name=r.name, is_active=r.is_active)
            for r in rows]


async def list_partners(db: AsyncSession, *, q: str | None = None,
                        limit: int = 50) -> list[PartnerPick]:
    """The partner picker for assignment (FS-003 4). channel_partner's own policies
    scope it: a dealer sees its subtree, a manager the partners in its territories,
    an admin all. q matches the name or the code."""
    limit = max(1, min(limit, _MAX_LIMIT))
    like = _contains(q) if q else None
    rows = (await db.execute(text("""
        SELECT cp.id, cp.code, cp.name, cp.partner_type::text AS ptype,
               t.id AS tid, t.name AS tname, t.level::text AS tlevel
          FROM channel_partner cp
          LEFT JOIN territory t ON t.id = cp.territory_id
         WHERE cp.is_active AND cp.deleted_at IS NULL
           AND (CAST(:like AS text) IS NULL
                OR cp.name ILIKE CAST(:like AS text) OR cp.code ILIKE CAST(:like AS text))
         ORDER BY cp.name LIMIT :lim"""), {"like": like, "lim": limit})).all()
    return [PartnerPick(
        id=str(r.id), code=r.code, name=r.name, partner_type=r.ptype,
        territory=TerritoryParent(id=str(r.tid), name=r.tname, level=r.tlevel) if r.tid else None)
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
