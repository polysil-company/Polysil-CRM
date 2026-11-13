"""The policies migration 005 puts on the seventeen tables, run as app_role.

Every test switches into app_role with a claim before asserting, because the
owner is exempt from every policy and a test that forgets the switch passes
vacuously (FS-002 5.5). The db fixture rolls the whole thing back.

The negatives carry the weight: a user reading a colleague they should not, a
retype of their own role, the purge seeing nothing, an outbox row read by a user.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

# 007 binds a session to the token_version the credential was verified against
# (FS-006 rule 6). The fixtures mint with the row's own, read in the same statement.
_V = ", (SELECT token_version FROM app_user WHERE id = CAST(:u AS uuid)))"


REFUSED = (IntegrityError, InternalError, ProgrammingError, DBAPIError)
SYSTEM_ID = get_settings().system_user_id


async def _as(db: AsyncSession, user_id: str) -> None:
    """The same order as get_db: claim, then role. Fixtures are built before this,
    as the owner; everything after runs under policy."""
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _grant(db: AsyncSession, role_id: str, module: str, actions: list[str],
                 scope: str) -> None:
    for action in actions:
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) "
            "VALUES (:r, :m, CAST(:a AS permission_action), CAST(:s AS permission_scope))"),
            {"r": role_id, "m": module, "a": action, "s": scope})


async def _role(db: AsyncSession, ids: Fixtures, code: str, *, portal: bool = False,
                level: int = 2) -> str:
    return (await db.execute(text(
        "INSERT INTO role (code, name, level, is_portal) VALUES (:c, :n, :l, :p) RETURNING id"),
        {"c": ids.unique(code), "n": code, "l": level, "p": portal})).scalar_one()


async def _refused(db: AsyncSession, sql: str, params: dict, match: str = "") -> None:
    with pytest.raises(REFUSED, match=match):
        async with db.begin_nested():
            await db.execute(text(sql), params)


async def _count(db: AsyncSession, sql: str, **params: object) -> int:
    return (await db.execute(text(sql), params)).scalar_one()


# ── app_user: generated ─────────────────────────────────────────────────────

async def test_a_user_reads_their_own_row_and_no_other_without_users_view(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    other = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM app_user WHERE id = :i", i=me) == 1
    assert await _count(db, "SELECT count(*) FROM app_user WHERE id = :i", i=other) == 0


async def test_a_manager_with_org_scope_reads_the_subtree_and_not_outside(
        db: AsyncSession, ids: Fixtures) -> None:
    """The PII hole FS-002 rev 2 found against seed data, closed: the org branch
    needs users.view, and it stops at the subtree."""
    await _grant(db, ids.staff_role_id, "users", ["view"], "org_subtree")
    manager = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    child_org = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, parent_id) VALUES (:n, 1, :p) RETURNING id"),
        {"n": ids.unique("field"), "p": ids.org_unit_id})).scalar_one()
    other_org = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level) VALUES (:n, 2) RETURNING id"),
        {"n": ids.unique("elsewhere")})).scalar_one()
    below = (await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o) RETURNING id"),
        {"e": ids.unique("b") + "@polysil.in", "r": ids.staff_role_id,
         "o": child_org})).scalar_one()
    outside = (await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o) RETURNING id"),
        {"e": ids.unique("o") + "@polysil.in", "r": ids.staff_role_id,
         "o": other_org})).scalar_one()
    await _as(db, manager)
    assert await _count(db, "SELECT count(*) FROM app_user WHERE id = :i", i=below) == 1
    assert await _count(db, "SELECT count(*) FROM app_user WHERE id = :i", i=outside) == 0


async def test_a_user_cannot_change_their_own_role_or_anchor(db: AsyncSession,
                                                             ids: Fixtures) -> None:
    """FS-002 rev 2 EC-2: asserted in a table cell, shipped with no mechanism.
    Now a trigger clause, and it fires on the anchor columns too."""
    await _grant(db, ids.staff_role_id, "users", ["view", "edit"], "global")
    me = await make_staff(db, ids, email=ids.unique("me") + "@polysil.in")
    other_role = await _role(db, ids, "admin")
    await _as(db, me)
    await _refused(db, "UPDATE app_user SET role_id = :r WHERE id = :i",
                   {"r": other_role, "i": me}, "may not change their own")
    await _refused(db, "UPDATE app_user SET org_unit_id = NULL, user_type = 'partner_user' "
                       "WHERE id = :i", {"i": me}, "may not change their own")


# ── channel_partner: generated ──────────────────────────────────────────────

async def test_a_partner_user_reads_their_own_partner_without_partners_view(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM channel_partner WHERE id = :i",
                        i=ids.dealer_id) == 1
    assert await _count(db, "SELECT count(*) FROM channel_partner WHERE id = :i",
                        i=ids.distributor_id) == 0


async def test_a_dealer_with_partner_scope_reads_the_subtree_only(db: AsyncSession,
                                                                  ids: Fixtures) -> None:
    await _grant(db, ids.portal_role_id, "partners", ["view"], "partner_subtree")
    sub = (await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer') RETURNING id"),
        {"p": ids.dealer_id, "c": ids.unique("SD"), "t": ids.territory_id})).scalar_one()
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, me)
    visible = set((await db.execute(text("SELECT id FROM channel_partner"))).scalars().all())
    assert {str(x) for x in visible} == {str(ids.dealer_id), str(sub)}


async def test_the_territory_branch_reaches_partners_in_assigned_territories(
        db: AsyncSession, ids: Fixtures) -> None:
    """The State Co-ordinator's scope, executable on a real table for the first time."""
    coord_role = await _role(db, ids, "coord", level=3)
    await _grant(db, coord_role, "partners", ["view"], "territory")
    coord = (await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o) RETURNING id"),
        {"e": ids.unique("c") + "@polysil.in", "r": coord_role, "o": ids.org_unit_id})).scalar_one()
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
                     {"u": coord, "t": ids.territory_id})
    elsewhere = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": ids.unique("far")})).scalar_one()
    far = (await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'x', :t, 'dealer') RETURNING id"),
        {"c": ids.unique("FAR"), "t": elsewhere})).scalar_one()
    await _as(db, coord)
    assert await _count(db, "SELECT count(*) FROM channel_partner WHERE id = :i",
                        i=ids.dealer_id) == 1
    assert await _count(db, "SELECT count(*) FROM channel_partner WHERE id = :i", i=far) == 0


async def test_org_scope_on_partners_goes_through_territory(db: AsyncSession,
                                                            ids: Fixtures) -> None:
    """GAP-036. The fixture org unit sits in the fixture territory, which the two
    fixture partners are in."""
    await _grant(db, ids.staff_role_id, "partners", ["view"], "org_subtree")
    manager = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    await _as(db, manager)
    assert await _count(db, "SELECT count(*) FROM channel_partner") == 2


# ── the hand-written ones ───────────────────────────────────────────────────

async def test_sessions_are_self_only(db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    other = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")
    for u in (me, other):
        await db.execute(text(
            "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
            "interval '1 day', 'test', '10.0.0.1', 'password'" + _V),
            {"u": u, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM session WHERE user_id = :u", u=me) == 1
    assert await _count(db, "SELECT count(*) FROM session WHERE user_id = :u", u=other) == 0


async def test_the_principal_purges_other_users_expired_sessions(db: AsyncSession,
                                                                 ids: Fixtures) -> None:
    """Cross-vendor A-3, executed there and asserted here: a DELETE whose WHERE
    reads columns must pass the SELECT policies too. Without the principal's
    SELECT branch this deleted 0."""
    other = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")
    await db.execute(text(
        "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '-1 day', 'test', '10.0.0.1', 'password'" + _V),
        {"u": other, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})
    await _as(db, SYSTEM_ID)
    assert (await db.execute(text("SELECT app_is_system()"))).scalar_one() is True
    r = await db.execute(text("DELETE FROM session WHERE expires_at < now() AND user_id = :u"),
                         {"u": other})
    assert r.rowcount == 1


async def test_a_user_cannot_purge_and_is_not_the_principal(db: AsyncSession,
                                                            ids: Fixtures) -> None:
    other = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    await db.execute(text(
        "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '-1 day', 'test', '10.0.0.1', 'password'" + _V),
        {"u": other, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})
    await _as(db, me)
    assert (await db.execute(text("SELECT app_is_system()"))).scalar_one() is False
    r = await db.execute(text("DELETE FROM session WHERE expires_at < now()"))
    assert r.rowcount == 0


async def test_the_outbox_is_written_only_for_a_visible_lead_ack_and_read_by_the_principal_only(
        db: AsyncSession, ids: Fixtures) -> None:
    """ISS-062, closed by 006. 005 let any authenticated caller queue any template
    to any number. Now an ordinary caller may queue only a lead_ack for the mobile
    of a lead they can see (the allowed case is in test_functions_006); anything
    else is refused. The system principal writes anything and is the only reader."""
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    await _as(db, me)
    recipient = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    with pytest.raises(Exception, match="row-level security"):
        async with db.begin_nested():
            await db.execute(text(
                "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
                "VALUES ('sms', 'auth.otp', :r, '{}')"), {"r": recipient})
    assert await _count(db, "SELECT count(*) FROM notification_outbox WHERE recipient = :r",
                        r=recipient) == 0
    # The principal writes anything, and is the only reader.
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": SYSTEM_ID})
    await db.execute(text(
        "INSERT INTO notification_outbox (channel, template_key, recipient, payload) "
        "VALUES ('sms', 'auth.otp', :r, '{}')"), {"r": recipient})
    assert await _count(db, "SELECT count(*) FROM notification_outbox WHERE recipient = :r",
                        r=recipient) == 1
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(me)})
    assert await _count(db, "SELECT count(*) FROM notification_outbox WHERE recipient = :r",
                        r=recipient) == 0


async def test_the_catalog_is_readable_and_not_writable_without_masters_edit(
        db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.portal_role_id, "leads", ["view"], "partner_subtree")
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM role") > 0
    assert await _count(db, "SELECT count(*) FROM role_permission WHERE role_id = :r",
                        r=ids.portal_role_id) == 1
    assert await _count(db, "SELECT count(*) FROM org_closure") > 0
    await _refused(db, "INSERT INTO role (code, name, level) VALUES (:c, 'x', 1)",
                   {"c": ids.unique("nope")}, "row-level security")


async def test_deleting_a_view_row_that_strands_mutations_is_refused_at_commit(
        db: AsyncSession, ids: Fixtures) -> None:
    """Cross-vendor A-6. Deferred, so SET CONSTRAINTS IMMEDIATE stands in for commit."""
    await _grant(db, ids.staff_role_id, "leads", ["view", "edit"], "org_subtree")
    await db.execute(text(
        "DELETE FROM role_permission WHERE role_id = :r AND module = 'leads' AND action = 'view'"),
        {"r": ids.staff_role_id})
    await _refused(db, "SET CONSTRAINTS ALL IMMEDIATE", {}, "without a view row")


async def test_deactivating_a_partner_signs_out_its_users(db: AsyncSession,
                                                          ids: Fixtures) -> None:
    """ISS-028, as a trigger. Direct users only (GAP-042)."""
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await db.execute(text(
        "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '1 day', 'test', '10.0.0.1', 'otp'" + _V),
        {"u": me, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})
    before = (await db.execute(text("SELECT token_version FROM app_user WHERE id = :u"),
                               {"u": me})).scalar_one()
    await db.execute(text("UPDATE channel_partner SET is_active = false WHERE id = :p"),
                     {"p": ids.dealer_id})
    row = (await db.execute(text(
        "SELECT is_active, token_version FROM app_user WHERE id = :u"), {"u": me})).one()
    assert row.is_active is False and row.token_version == before + 1
    assert await _count(db, "SELECT count(*) FROM session WHERE user_id = :u "
                            "AND revoked_at IS NULL", u=me) == 0
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_id = :u "
                            "AND kind = 'auth.deactivated_by_anchor'", u=me) == 1
    # the distributor's users are untouched: directly anchored only
    assert await _count(db, "SELECT count(*) FROM app_user WHERE partner_id = :p "
                            "AND is_active", p=ids.distributor_id) == 0
    # and the anchor's own state change is on the timeline (rule 7, code review F-7)
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_type = "
                            "'channel_partner' AND entity_id = :p AND partner_id = :p "
                            "AND kind = 'partner.deactivated'", p=ids.dealer_id) == 1


async def test_closing_an_office_with_active_users_is_refused(db: AsyncSession,
                                                              ids: Fixtures) -> None:
    """FS-006 rule 9, in the database: an office with active users cannot close;
    move them first. The cascade's office arm (cross-vendor P1 on FS-002) therefore
    never deactivates anyone: once the users are inactive the close goes through,
    emits the anchor event, and touches nobody's session."""
    me = await make_staff(db, ids, email=ids.unique("ou") + "@polysil.in")
    await db.execute(text(
        "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '1 day', 'test', '10.0.0.1', 'password'" + _V),
        {"u": me, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})
    await _refused(db, "UPDATE org_unit SET deleted_at = now() WHERE id = :o",
                   {"o": ids.org_unit_id}, "active users are anchored here")
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :u"), {"u": me})
    await db.execute(text("UPDATE org_unit SET deleted_at = now() WHERE id = :o"),
                     {"o": ids.org_unit_id})
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_type = "
                            "'org_unit' AND entity_id = :o AND kind = 'org_unit.deactivated'",
                        o=ids.org_unit_id) == 1
    assert await _count(db, "SELECT count(*) FROM session WHERE user_id = :u "
                            "AND revoked_at IS NULL", u=me) == 1


async def test_app_role_cannot_create_a_temp_table(db: AsyncSession, ids: Fixtures) -> None:
    """Cross-vendor P1, executed: with TEMP on the database and search_path =
    public, a temp channel_partner shadowed the real one inside the definer
    triggers. TEMP is revoked from PUBLIC (ISS-063)."""
    me = await make_staff(db, ids, email=ids.unique("tmp") + "@polysil.in")
    await _as(db, me)
    await _refused(db, "CREATE TEMP TABLE channel_partner (id uuid)", {},
                   match="permission denied")


async def test_no_pinned_function_searches_pg_temp_first(db: AsyncSession, ids: Fixtures) -> None:
    """The other closure: pg_temp is explicit and last on every function that pins
    a search_path, so a temp table made by the owner cannot shadow either.
    Executed both ways: with `public` alone the helper read the empty temp table."""
    bad = (await db.execute(text(
        "SELECT string_agg(p.proname, ', ') FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proconfig IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM unnest(p.proconfig) c WHERE c LIKE 'search_path=%' "
        "AND c NOT LIKE '%pg_temp')"))).scalar_one()
    assert bad is None, bad
    me = await make_staff(db, ids, email=ids.unique("shadow") + "@polysil.in")
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(me)})
    await db.execute(text("CREATE TEMP TABLE app_user (id uuid, org_unit_id uuid) ON COMMIT DROP"))
    # a definer helper reads app_user unqualified; it must see the real row
    assert str((await db.execute(text("SELECT app_current_org_unit()"))).scalar_one()) \
        == str(ids.org_unit_id)


async def test_a_partner_cannot_move_itself_or_its_subtree(db: AsyncSession,
                                                           ids: Fixtures) -> None:
    """Code review F-1, executed before the fix: a dealer set its own parent_id
    to NULL, the closure was rewritten, and the distributor lost the dealer and
    everything under it. Now refused by authz_reparent_guard(), whichever way."""
    await _grant(db, ids.portal_role_id, "partners", ["view", "edit"], "partner_subtree")
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    other = (await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'x', :t, 'distributor') RETURNING id"),
        {"c": ids.unique("OTHER"), "t": ids.territory_id})).scalar_one()
    sub_dealer = (await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer') RETURNING id"),
        {"p": ids.dealer_id, "c": ids.unique("SUB"), "t": ids.territory_id})).scalar_one()
    await _as(db, me)
    for target, new_parent in ((ids.dealer_id, None), (ids.dealer_id, other),
                               (sub_dealer, None)):
        await _refused(db, "UPDATE channel_partner SET parent_id = :n WHERE id = :i",
                       {"n": new_parent, "i": target}, match="cannot move")
    assert await _count(db, "SELECT count(*) FROM partner_closure WHERE ancestor_id = :a "
                            "AND descendant_id = :d", a=ids.distributor_id, d=ids.dealer_id) == 1


async def test_a_partner_can_edit_its_own_row_otherwise(db: AsyncSession, ids: Fixtures) -> None:
    """Code review F-2: the UPDATE check re-validated the unchanged parent, which a
    dealer cannot see (its ancestor), so every self-edit was 42501. ISS-061 records
    that this includes price_tier and credit_limit until column rules land."""
    await _grant(db, ids.portal_role_id, "partners", ["view", "edit"], "partner_subtree")
    me = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    await _as(db, me)
    r = await db.execute(text("UPDATE channel_partner SET contact_name = 'Bhavesh' WHERE id = :i"),
                         {"i": ids.dealer_id})
    assert r.rowcount == 1
    r = await db.execute(text("UPDATE channel_partner SET contact_name = 'x' WHERE id = :i"),
                         {"i": ids.distributor_id})
    assert r.rowcount == 0, "the ancestor is out of scope"


async def test_a_manager_can_reparent_only_under_a_parent_they_can_see(
        db: AsyncSession, ids: Fixtures) -> None:
    """The other half of the guard: a staff caller may move a partner, but only
    under a parent their own policies return."""
    await _grant(db, ids.staff_role_id, "partners", ["view", "edit"], "org_subtree")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    far_territory = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": ids.unique("far")})).scalar_one()
    hidden = (await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'x', :t, 'distributor') RETURNING id"),
        {"c": ids.unique("FAR"), "t": far_territory})).scalar_one()
    visible = (await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'x', :t, 'distributor') RETURNING id"),
        {"c": ids.unique("NEAR"), "t": ids.territory_id})).scalar_one()
    await _as(db, me)
    await _refused(db, "UPDATE channel_partner SET parent_id = :n WHERE id = :i",
                   {"n": hidden, "i": ids.dealer_id}, match="not in your scope")
    r = await db.execute(text("UPDATE channel_partner SET parent_id = :n WHERE id = :i"),
                         {"n": visible, "i": ids.dealer_id})
    assert r.rowcount == 1
    assert await _count(db, "SELECT count(*) FROM partner_closure WHERE ancestor_id = :a "
                            "AND descendant_id = :d", a=visible, d=ids.dealer_id) == 1


async def test_forced_revocation_has_no_path_under_app_role_yet(db: AsyncSession,
                                                                ids: Fixtures) -> None:
    """Code review F-4. A users.edit UPDATE branch on session had no SELECT branch
    and affected zero rows, silently. The branch is gone: a direct UPDATE touches
    nothing, and auth_revoke_sessions() (the logout function) is granted to
    app_anon, not to app_role (executed: 42501). The forced path an admin uses is
    auth_revoke_user_sessions() from 007 (GAP-045 closed), guarded on users.edit and
    scope; this pins that the logout function never became that path."""
    await _grant(db, ids.staff_role_id, "users", ["view", "edit"], "global")
    admin = await make_staff(db, ids, email=ids.unique("adm") + "@polysil.in")
    victim = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    family = str(uuid.uuid4())
    sid = (await db.execute(text(
        "SELECT session_id FROM auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '1 day', 'test', '10.0.0.1', 'otp'" + _V),
        {"u": victim, "h": uuid.uuid4().hex, "f": family})).scalar_one()
    await _as(db, admin)
    r = await db.execute(text("UPDATE session SET revoked_at = now() WHERE id = :s"), {"s": sid})
    assert r.rowcount == 0
    await _refused(db, "SELECT auth_revoke_sessions(CAST(:s AS uuid), CAST(:f AS uuid))",
                   {"s": sid, "f": family}, match="permission denied")


async def test_deactivate_anchor_checks_permission_and_scope(db: AsyncSession,
                                                             ids: Fixtures) -> None:
    """Round-1 B-9. Without permission: 42501 by name. Out of scope: 42501 from
    the UPDATE seeing zero rows under the caller's own policies."""
    nobody = await make_staff(db, ids, email=ids.unique("n") + "@polysil.in")
    await _as(db, nobody)
    await _refused(db, "SELECT authz_deactivate_anchor('channel_partner', CAST(:p AS uuid))",
                   {"p": ids.dealer_id}, "partners.edit required")


async def test_deactivate_anchor_out_of_scope_is_refused(db: AsyncSession, ids: Fixtures) -> None:
    role = await _role(db, ids, "dm2")
    await _grant(db, role, "partners", ["view", "edit"], "org_subtree")
    far_org = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level) VALUES (:n, 2) RETURNING id"),
        {"n": ids.unique("far")})).scalar_one()
    manager = (await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o) RETURNING id"),
        {"e": ids.unique("m") + "@polysil.in", "r": role, "o": far_org})).scalar_one()
    await _as(db, manager)
    await _refused(db, "SELECT authz_deactivate_anchor('channel_partner', CAST(:p AS uuid))",
                   {"p": ids.dealer_id}, "not in your scope")


async def test_deactivate_anchor_in_scope_works(db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "partners", ["view", "edit"], "global")
    admin = await make_staff(db, ids, email=ids.unique("adm") + "@polysil.in")
    await _as(db, admin)
    await db.execute(text("SELECT authz_deactivate_anchor('channel_partner', CAST(:p AS uuid))"),
                     {"p": ids.dealer_id})
    assert await _count(db, "SELECT count(*) FROM channel_partner WHERE id = :p AND is_active",
                        p=ids.dealer_id) == 0


async def test_a_user_sees_their_own_sign_in_events_and_not_others(db: AsyncSession,
                                                                   ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    other = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")
    for u in (me, other):
        await db.execute(text(
            "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
            "interval '1 day', 'test', '10.0.0.1', 'password'" + _V),
            {"u": u, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_id = :u", u=me) >= 1
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_id = :u",
                        u=other) == 0


async def test_an_event_can_only_be_written_as_oneself(db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    other = await make_staff(db, ids, email=ids.unique("b") + "@polysil.in")
    await _as(db, me)
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id) "
        "VALUES ('app_user', :u, 'test.event', :u)"), {"u": me})
    await _refused(db, "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id) "
                       "VALUES ('app_user', :u, 'test.event', :o)", {"u": me, "o": other},
                   "row-level security")


async def test_an_unmapped_entity_type_is_visible_to_the_principal_only(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("a") + "@polysil.in")
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id) "
        "VALUES ('widget', gen_random_uuid(), 'test.event', :u)"), {"u": me})
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_type = 'widget'") == 0
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": SYSTEM_ID})
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_type = 'widget'") == 1


async def test_a_mapped_entity_type_must_carry_its_reference(db: AsyncSession,
                                                             ids: Fixtures) -> None:
    await _refused(db, "INSERT INTO activity_event (entity_type, entity_id, kind) "
                       "VALUES ('channel_partner', gen_random_uuid(), 'x')", {},
                   "ck_activity_event_reference")


async def test_login_attempts_and_audit_need_global_users_view(db: AsyncSession,
                                                               ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "users", ["view"], "org_subtree")
    scoped = await make_staff(db, ids, email=ids.unique("s") + "@polysil.in")
    await _as(db, scoped)
    assert await _count(db, "SELECT count(*) FROM login_attempt") == 0
    assert await _count(db, "SELECT count(*) FROM audit_log") == 0


async def test_the_principal_has_no_matrix_rows(db: AsyncSession) -> None:
    n = await _count(db, "SELECT count(*) FROM role_permission rp JOIN role r ON r.id = rp.role_id "
                         "WHERE r.code = 'system'")
    assert n == 0


async def test_every_table_has_rls_enabled(db: AsyncSession) -> None:
    rows = (await db.execute(text(
        "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname <> 'alembic_version' "
        "AND NOT c.relrowsecurity"))).scalars().all()
    assert rows == [], f"RLS not enabled on {rows}"
    forced = (await db.execute(text(
        "SELECT relname FROM pg_class WHERE relforcerowsecurity"))).scalars().all()
    assert forced == [], f"FORCE set on {forced}; FS-002 5.2 fact 2"
