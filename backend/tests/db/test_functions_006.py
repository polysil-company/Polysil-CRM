"""The nine definer functions migration 006 adds (FS-003 5.1), executed as app_role.

These are the security-critical core: each reads or writes rows the caller cannot
reach directly, so each guards itself. The endpoint tests exercise them end to end;
this proves the guards, the grants, and the merge flatten.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

SIGS = [
    "lead_allocate_inquiry_no(text, text)", "lead_visible(uuid)", "lead_people(uuid)",
    "lead_timeline(uuid, timestamptz, uuid, integer)", "lead_merge(uuid, uuid)",
    "lead_close_links(uuid, text)", "authz_user_assignable(text, uuid)",
    "staff_directory(text)", "lead_auto_owner(uuid)",
]


async def _grant(db: AsyncSession, role_id: str, module: str, actions: list[str],
                 scope: str) -> None:
    for action in actions:
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) "
            "VALUES (:r, :m, CAST(:a AS permission_action), CAST(:s AS permission_scope))"),
            {"r": role_id, "m": module, "a": action, "s": scope})


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _lead(db: AsyncSession, ids: Fixtures, *, owner_user_id: str | None = None,
                owner_org_unit_id: str | None = None, assigned_partner_id: str | None = None,
                territory_id: str | None = None, stage: str = "new") -> str:
    return str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, stage, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id, "
        "assigned_partner_id) VALUES (:no, CAST(:st AS lead_stage), 'commercial', "
        "(SELECT id FROM mis_system WHERE code='drip'), "
        "(SELECT id FROM lead_source WHERE code='employee'), 'Farmer', :mob, :terr, "
        ":ou, :oou, :ap) RETURNING id"),
        {"no": "POL-" + uuid.uuid4().hex[:12], "st": stage,
         "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "terr": territory_id or ids.territory_id, "ou": owner_user_id,
         "oou": owner_org_unit_id or ids.org_unit_id, "ap": assigned_partner_id})).scalar_one())


# ── grants ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig", SIGS)
async def test_app_role_may_execute_and_public_may_not(db: AsyncSession, sig: str) -> None:
    role_ok = (await db.execute(text(
        "SELECT has_function_privilege('app_role', :s, 'EXECUTE')"), {"s": sig})).scalar_one()
    pub = (await db.execute(text(
        "SELECT has_function_privilege('public', :s, 'EXECUTE')"), {"s": sig})).scalar_one()
    anon = (await db.execute(text(
        "SELECT has_function_privilege('app_anon', :s, 'EXECUTE')"), {"s": sig})).scalar_one()
    assert role_ok is True and pub is False and anon is False, sig


# ── lead_allocate_inquiry_no ─────────────────────────────────────────────────

async def test_the_inquiry_number_is_sequential_and_formatted(db: AsyncSession,
                                                              ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["create"], "global")
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    await _as(db, me)
    fy = uuid.uuid4().hex[:6]
    first = (await db.execute(text("SELECT lead_allocate_inquiry_no('GJ', :fy)"),
                              {"fy": fy})).scalar_one()
    second = (await db.execute(text("SELECT lead_allocate_inquiry_no('GJ', :fy)"),
                               {"fy": fy})).scalar_one()
    assert first == f"POL/GJ/{fy}/00001"
    assert second == f"POL/GJ/{fy}/00002"


async def test_the_allocator_needs_create_permission(db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")   # no leads.create
    await _as(db, me)
    with pytest.raises(Exception, match="permitted"):
        async with db.begin_nested():
            await db.execute(text("SELECT lead_allocate_inquiry_no('GJ', '2026-27')"))


# ── lead_visible / lead_people ───────────────────────────────────────────────

async def test_lead_visible_answers_the_policy(db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view"], "own")
    me = await make_staff(db, ids, email=ids.unique("v") + "@polysil.in")
    other = await make_staff(db, ids, email=ids.unique("o") + "@polysil.in")
    mine = await _lead(db, ids, owner_user_id=me)
    theirs = await _lead(db, ids, owner_user_id=other)
    await _as(db, me)
    assert (await db.execute(text("SELECT lead_visible(:i)"), {"i": mine})).scalar_one() is True
    assert (await db.execute(text("SELECT lead_visible(:i)"), {"i": theirs})).scalar_one() is False
    unrelated = str(uuid.uuid4())
    assert (await db.execute(text("SELECT lead_visible(:i)"),
                             {"i": unrelated})).scalar_one() is False


async def test_lead_people_answers_only_for_a_visible_lead(db: AsyncSession,
                                                           ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view"], "own")
    me = await make_staff(db, ids, email=ids.unique("v") + "@polysil.in")
    other = await make_staff(db, ids, email=ids.unique("o") + "@polysil.in")
    mine = await _lead(db, ids, owner_user_id=me)
    theirs = await _lead(db, ids, owner_user_id=other)
    await _as(db, me)
    n_mine = (await db.execute(text("SELECT count(*) FROM lead_people(:i)"),
                               {"i": mine})).scalar_one()
    n_theirs = (await db.execute(text("SELECT count(*) FROM lead_people(:i)"),
                                 {"i": theirs})).scalar_one()
    assert n_mine >= 1 and n_theirs == 0


# ── authz_user_assignable / staff_directory ──────────────────────────────────

async def test_assignable_needs_the_module_allow_list_and_edit(db: AsyncSession,
                                                               ids: Fixtures) -> None:
    # products is a module where a global caller has view, but assignment is not
    # allow-listed there: the directory must stay shut (cross-vendor B-1).
    await _grant(db, ids.staff_role_id, "products", ["view"], "global")
    await _grant(db, ids.staff_role_id, "leads", ["view"], "global")   # view, not edit
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    target = await make_staff(db, ids, email=ids.unique("t") + "@polysil.in")
    await _as(db, me)
    # not allow-listed
    assert (await db.execute(text("SELECT authz_user_assignable('products', :u)"),
                             {"u": target})).scalar_one() is False
    # allow-listed but caller lacks leads.edit
    assert (await db.execute(text("SELECT authz_user_assignable('leads', :u)"),
                             {"u": target})).scalar_one() is False
    assert (await db.execute(text("SELECT count(*) FROM staff_directory('leads')"))
            ).scalar_one() == 0


async def test_assignable_with_edit_sees_the_subtree(db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "org_subtree")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    inside = await make_staff(db, ids, email=ids.unique("i") + "@polysil.in")   # same org unit
    await _as(db, me)
    assert (await db.execute(text("SELECT authz_user_assignable('leads', :u)"),
                             {"u": inside})).scalar_one() is True
    names = (await db.execute(text("SELECT count(*) FROM staff_directory('leads')"))).scalar_one()
    assert names >= 2   # at least me and inside


# ── lead_auto_owner ──────────────────────────────────────────────────────────

async def _field_officer(db: AsyncSession, ids: Fixtures, email: str, role_id: Any) -> str:
    return str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Officer', :r, :o) RETURNING id"),
        {"e": email, "r": role_id, "o": ids.org_unit_id})).scalar_one())


async def test_auto_owner_picks_the_field_officer_with_the_fewest_open_leads(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 5: only field officers (role level 1) are candidates, then the one with
    the fewest open leads. A district manager in the same covering unit, even with
    no leads at all, is never picked (ISS-069)."""
    await _grant(db, ids.portal_role_id, "leads", ["create"], "partner_subtree")
    fo_role = (await db.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Field Officer', 1) RETURNING id"),
        {"c": ids.unique("field_officer")})).scalar_one()
    await _grant(db, fo_role, "leads", ["view", "edit"], "own")
    manager = await make_staff(db, ids, email=ids.unique("dm") + "@polysil.in")  # level 2
    busy = await _field_officer(db, ids, ids.unique("busy") + "@polysil.in", fo_role)
    free = await _field_officer(db, ids, ids.unique("free") + "@polysil.in", fo_role)
    await _lead(db, ids, owner_user_id=busy)   # busy has one open lead
    dealer_user = await make_partner_user(db, ids,
                                          mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, dealer_user)
    picked = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                               {"t": ids.territory_id})).scalar_one()
    assert str(picked) == str(free), "the field officer with the fewest open leads"
    assert str(picked) != str(manager)


async def test_auto_owner_is_null_when_no_field_officer_covers(
        db: AsyncSession, ids: Fixtures) -> None:
    """A unit staffed only by a manager assigns nobody; the lead waits unassigned."""
    await _grant(db, ids.portal_role_id, "leads", ["create"], "partner_subtree")
    await make_staff(db, ids, email=ids.unique("dm") + "@polysil.in")
    dealer_user = await make_partner_user(db, ids,
                                          mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, dealer_user)
    picked = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                               {"t": ids.territory_id})).scalar_one()
    assert picked is None


# ── notification_outbox INSERT is narrowed (ISS-062) ─────────────────────────

async def test_outbox_insert_admits_only_lead_ack_for_a_visible_lead(
        db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view", "create", "edit"], "own")
    me = await make_staff(db, ids, email=ids.unique("o") + "@polysil.in")
    mine = await _lead(db, ids, owner_user_id=me)
    mobile = (await db.execute(text("SELECT mobile FROM lead WHERE id = :i"),
                               {"i": mine})).scalar_one()
    await _as(db, me)
    # allowed: the acknowledgement for a lead I can see
    await db.execute(text(
        "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
        "VALUES ('whatsapp', 'lead_ack', :m, '{}')"), {"m": mobile})
    # refused: any other template, and lead_ack to a number that is not a visible lead's
    for template, to in (("anything_else", mobile), ("lead_ack", "+915550000000")):
        with pytest.raises(Exception, match="row-level security"):
            async with db.begin_nested():
                await db.execute(text(
                    "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                    "VALUES ('whatsapp', :t, :m, '{}')"), {"t": template, "m": to})


# ── cross-vendor round: allocator width, deleted work, merge guards ──────────

async def test_the_inquiry_number_grows_past_five_digits(db: AsyncSession, ids: Fixtures) -> None:
    """lpad truncates a six-digit counter to five and the number collides with an
    issued one (cross-vendor P2). Five digits is a minimum width, not a cap."""
    await _grant(db, ids.staff_role_id, "leads", ["create"], "global")
    me = await make_staff(db, ids, email=ids.unique("w") + "@polysil.in")
    fy = uuid.uuid4().hex[:6]
    await db.execute(text(
        "INSERT INTO inquiry_counter (state_code, financial_year, last_value) "
        "VALUES ('ZZ', :fy, 99999)"), {"fy": fy})
    await _as(db, me)
    got = (await db.execute(text("SELECT lead_allocate_inquiry_no('ZZ', :fy)"),
                            {"fy": fy})).scalar_one()
    assert got == f"POL/ZZ/{fy}/100000"


async def test_auto_owner_ignores_soft_deleted_leads(db: AsyncSession, ids: Fixtures) -> None:
    """A deleted lead is not open work (cross-vendor P2): two deleted leads lose to
    one live lead."""
    await _grant(db, ids.portal_role_id, "leads", ["create"], "partner_subtree")
    fo_role = (await db.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Field Officer', 1) RETURNING id"),
        {"c": ids.unique("fo")})).scalar_one()
    await _grant(db, fo_role, "leads", ["view", "edit"], "own")
    busy = await _field_officer(db, ids, ids.unique("busy") + "@polysil.in", fo_role)
    free = await _field_officer(db, ids, ids.unique("free") + "@polysil.in", fo_role)
    for _ in range(2):
        lid = await _lead(db, ids, owner_user_id=busy)
        await db.execute(text("UPDATE lead SET deleted_at = now() WHERE id = :i"), {"i": lid})
    await _lead(db, ids, owner_user_id=free)
    dealer_user = await make_partner_user(db, ids,
                                          mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, dealer_user)
    picked = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                               {"t": ids.territory_id})).scalar_one()
    assert str(picked) == str(busy), "zero live leads beats one, whatever was deleted"


async def test_merge_refuses_a_partner_user_inside_the_function(
        db: AsyncSession, ids: Fixtures) -> None:
    """Staff only, enforced by the definer itself and not only by the route, since
    the function is granted on its own (cross-vendor P1)."""
    await _grant(db, ids.portal_role_id, "leads", ["view", "edit", "create"], "partner_subtree")
    a = await _lead(db, ids, assigned_partner_id=ids.dealer_id)
    b = await _lead(db, ids, assigned_partner_id=ids.dealer_id)
    dealer_user = await make_partner_user(db, ids,
                                          mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, dealer_user)
    with pytest.raises(Exception, match="only staff"):
        async with db.begin_nested():
            await db.execute(text("SELECT lead_merge(:l, :s)"), {"l": a, "s": b})


async def test_merge_events_name_the_actor(db: AsyncSession, ids: Fixtures) -> None:
    """The timeline names actors from payload.actor_name; the definer's two
    lead.merged events carry it like every service-written event (cross-vendor P2)."""
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "global")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    a = await _lead(db, ids)
    b = await _lead(db, ids)
    await _as(db, me)
    await db.execute(text("SELECT lead_merge(:l, :s)"), {"l": a, "s": b})
    names = {r[0] for r in (await db.execute(text(
        "SELECT payload->>'actor_name' FROM activity_event "
        "WHERE kind = 'lead.merged' AND lead_id IN (:a, :b)"), {"a": a, "b": b})).all()}
    assert names == {"Asha Patel"}


# ── lead_merge / lead_close_links ────────────────────────────────────────────

async def test_merge_flattens_a_chain_and_repoints_a_hidden_link(db: AsyncSession,
                                                                 ids: Fixtures) -> None:
    """B into A, then A into C: B must end pointing at C, and a pending B-third link
    the merger can see is re-pointed. Run as a global editor."""
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "global")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    a = await _lead(db, ids)
    b = await _lead(db, ids)
    c = await _lead(db, ids)
    third = await _lead(db, ids)
    # a pending link between b and third
    lo, hi = sorted([b, third])
    await db.execute(text(
        "INSERT INTO lead_duplicate_link (lead_a_id, lead_b_id, signal, state) "
        "VALUES (:a, :b, 'mobile', 'pending')"), {"a": lo, "b": hi})
    await _as(db, me)
    await db.execute(text("SELECT lead_merge(:loser, :surv)"), {"loser": b, "surv": a})
    await db.execute(text("SELECT lead_merge(:loser, :surv)"), {"loser": a, "surv": c})
    # b now points at c (flattened), not the dead a
    b_into = (await db.execute(text("SELECT merged_into_id FROM lead WHERE id = :i"),
                               {"i": b})).scalar_one()
    assert str(b_into) == str(c)
    # a pending link between third and the survivor (c or a) exists; b's own link closed
    pending = (await db.execute(text(
        "SELECT count(*) FROM lead_duplicate_link WHERE state = 'pending' "
        "AND (lead_a_id = :t OR lead_b_id = :t)"), {"t": third})).scalar_one()
    assert pending >= 1, "the third-lead link was re-pointed, not lost"


async def test_merge_refuses_a_terminal_lead(db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "global")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    a = await _lead(db, ids)
    lost = await _lead(db, ids, stage="new")
    await _as(db, me)
    # take `lost` to lost first via a direct update as owner? simpler: mark won
    await _as_owner(db)
    await db.execute(text("UPDATE lead SET stage = 'won' WHERE id = :i"), {"i": lost})
    await _as(db, me)
    with pytest.raises(Exception, match="won, lost or merged"):
        async with db.begin_nested():
            await db.execute(text("SELECT lead_merge(:loser, :surv)"), {"loser": lost, "surv": a})


async def _as_owner(db: AsyncSession) -> None:
    await db.execute(text("SELECT set_config('role', 'none', true)"))
