"""Migration 007's definers, triggers and policies, executed (FS-006 10, the RLS /
definer, security and lockout rows).

Everything runs inside the caller's transaction and rolls back with it. `_as`
switches the transaction into app_role under a claim, the way get_db does; the
checks that need the owner's eyes run before the switch or read rows the caller's
own policies admit (their own app_user row, their own sessions and events).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

REFUSED = (IntegrityError, InternalError, ProgrammingError, DBAPIError)
SYSTEM_ID = get_settings().system_user_id
LOCKOUT = timedelta(minutes=15)
MAX_FAILURES = 5


def _mobile() -> str:
    return "9199" + f"{uuid.uuid4().int % 10**8:08d}"


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _refused(db: AsyncSession, sql: str, params: dict, match: str = "") -> None:
    with pytest.raises(REFUSED, match=match):
        async with db.begin_nested():
            await db.execute(text(sql), params)


async def _count(db: AsyncSession, sql: str, **params: object) -> int:
    return int((await db.execute(text(sql), params)).scalar_one())


async def _grant(db: AsyncSession, role_id: str, module: str, actions: list[str],
                 scope: str) -> None:
    for action in actions:
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) "
            "VALUES (:r, :m, CAST(:a AS permission_action), CAST(:s AS permission_scope))"),
            {"r": role_id, "m": module, "a": action, "s": scope})


async def _role(db: AsyncSession, ids: Fixtures, code: str, *, level: int = 2,
                portal: bool = False) -> str:
    return str((await db.execute(text(
        "INSERT INTO role (code, name, level, is_portal) VALUES (:c, :n, :l, :p) RETURNING id"),
        {"c": ids.unique(code), "n": code, "l": level, "p": portal})).scalar_one())


async def _admin(db: AsyncSession, ids: Fixtures) -> str:
    """A staff user whose role holds users view and edit at global, anchored on the
    fixture office."""
    role = await _role(db, ids, "adm")
    await _grant(db, role, "users", ["view", "edit"], "global")
    return str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Admin', :r, :o) RETURNING id"),
        {"e": ids.unique("adm") + "@polysil.in", "r": role, "o": ids.org_unit_id})).scalar_one())


async def _session(db: AsyncSession, user_id: str) -> None:
    await db.execute(text(
        "SELECT auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), interval '1 day', "
        "'test', '10.0.0.1', 'password', "
        "(SELECT token_version FROM app_user WHERE id = CAST(:u AS uuid)))"),
        {"u": user_id, "h": uuid.uuid4().hex, "f": str(uuid.uuid4())})


async def _fail_five_times(db: AsyncSession, email: str) -> None:
    for i in range(MAX_FAILURES):
        await db.execute(text(
            "INSERT INTO login_attempt (identifier, ip, succeeded, kind, attempted_at) "
            "VALUES (CAST(:e AS citext), '10.0.0.1', false, 'password', "
            "now() - CAST(:ago AS interval))"), {"e": email, "ago": timedelta(minutes=5 - i)})


async def _locked_until(db: AsyncSession, email: str):
    return (await db.execute(text(
        "SELECT locked_until FROM auth_lookup_staff(CAST(:e AS citext), :n, :l)"),
        {"e": email, "n": MAX_FAILURES, "l": LOCKOUT})).scalar_one()


# ── user_territory DELETE (rule 7's other half) ─────────────────────────────

async def test_user_territory_delete_needs_users_edit(db: AsyncSession, ids: Fixtures) -> None:
    other = await make_staff(db, ids, email=ids.unique("o") + "@polysil.in")
    await db.execute(text(
        "INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
        {"u": other, "t": ids.territory_id})
    me = await make_staff(db, ids, email=ids.unique("me") + "@polysil.in")
    await _as(db, me)
    r = await db.execute(text("DELETE FROM user_territory WHERE user_id = :u"), {"u": other})
    assert r.rowcount == 0, "a staff user without users.edit removed a territory"

    admin = None
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    admin = await _admin(db, ids)
    await _as(db, admin)
    r = await db.execute(text("DELETE FROM user_territory WHERE user_id = :u"), {"u": other})
    assert r.rowcount == 1


# ── the guarded definers ─────────────────────────────────────────────────────

async def test_each_guarded_definer_refuses_without_users_edit_or_out_of_scope(
        db: AsyncSession, ids: Fixtures) -> None:
    """42501 from the definer is the second enforcer: a caller without users.edit,
    then one whose users scope (own) does not admit the target."""
    target = await make_staff(db, ids, email=ids.unique("t") + "@polysil.in")
    plain = await make_staff(db, ids, email=ids.unique("p") + "@polysil.in")
    own_role = await _role(db, ids, "own")
    await _grant(db, own_role, "users", ["view", "edit"], "own")
    narrow = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Narrow', :r, :o) RETURNING id"),
        {"e": ids.unique("n") + "@polysil.in", "r": own_role, "o": ids.org_unit_id})).scalar_one())
    calls = [
        ("SELECT auth_user_lockout(CAST(:t AS uuid), 5, interval '15 minutes')", "users.edit"),
        ("SELECT auth_revoke_user_sessions(CAST(:t AS uuid))", "users.edit"),
        ("SELECT auth_user_session_count(CAST(:t AS uuid))", "users.edit"),
        ("SELECT auth_unlock_user(CAST(:t AS uuid), 5, interval '15 minutes')", "users.edit"),
    ]
    for caller in (plain, narrow):
        await db.execute(text("SELECT set_config('role', 'none', true)"))
        await _as(db, caller)
        for sql, match in calls:
            await _refused(db, sql, {"t": target}, match)


async def test_the_guarded_definers_answer_an_administrator(db: AsyncSession,
                                                           ids: Fixtures) -> None:
    target = await make_staff(db, ids, email=ids.unique("t") + "@polysil.in")
    await _session(db, target)
    admin = await _admin(db, ids)
    await _as(db, admin)
    assert (await db.execute(text(
        "SELECT auth_user_lockout(CAST(:t AS uuid), 5, interval '15 minutes')"),
        {"t": target})).scalar_one() is None
    assert await _count(db, "SELECT auth_user_session_count(CAST(:t AS uuid))", t=target) == 1
    assert await _count(db, "SELECT auth_revoke_user_sessions(CAST(:t AS uuid))", t=target) == 1
    assert await _count(db, "SELECT auth_user_session_count(CAST(:t AS uuid))", t=target) == 0
    # the event names the admin as actor and the target as entity (edge case 9)
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_id = :t "
                            "AND actor_id = :a AND kind = 'auth.sessions_revoked'",
                        t=target, a=admin) == 1


async def test_the_lockout_oracle_and_the_scope_oracle_are_granted_to_nobody(
        db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("me") + "@polysil.in")
    await _as(db, me)
    await _refused(db, "SELECT auth_locked_until(CAST(:e AS citext), 5, interval '15 minutes')",
                   {"e": "nobody@polysil.in"}, "permission denied")
    await _refused(db, "SELECT authz_user_in_scope(CAST(:u AS uuid))", {"u": me},
                   "permission denied")


async def test_app_anon_cannot_reach_the_lockout_oracle(db: AsyncSession) -> None:
    await enter_role(db, "app_anon")
    await _refused(db, "SELECT auth_locked_until(CAST(:e AS citext), 5, interval '15 minutes')",
                   {"e": "nobody@polysil.in"}, "permission denied")


# ── own password ─────────────────────────────────────────────────────────────

async def test_a_field_officer_changes_their_own_password_and_is_signed_out(
        db: AsyncSession, ids: Fixtures) -> None:
    """Edge case 1: a non-admin's UPDATE of their own row affects zero rows; the
    definer writes it, revokes every session, bumps token_version and records it."""
    me = await make_staff(db, ids, email=ids.unique("fo") + "@polysil.in",
                          password_hash="old-hash")
    await db.execute(text("UPDATE app_user SET must_change_password = true WHERE id = :u"),
                     {"u": me})
    await _session(db, me)
    before = await _count(db, "SELECT token_version FROM app_user WHERE id = :u", u=me)
    await _as(db, me)
    assert (await db.execute(text("SELECT auth_set_own_password('old-hash', 'new-hash')"))
            ).scalar_one() is True
    row = (await db.execute(text(
        "SELECT password_hash, must_change_password, password_changed_at, token_version "
        "FROM app_user WHERE id = :u"), {"u": me})).one()
    assert row.password_hash == "new-hash" and row.must_change_password is False
    assert row.password_changed_at is not None and row.token_version == before + 1
    assert await _count(db, "SELECT count(*) FROM session WHERE user_id = :u "
                            "AND revoked_at IS NULL", u=me) == 0
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_id = :u "
                            "AND kind = 'auth.password_changed' AND actor_id = :u", u=me) == 1
    # compare-and-set: the hash it verified is gone, so nothing is written
    assert (await db.execute(text("SELECT auth_set_own_password('old-hash', 'third')"))
            ).scalar_one() is False
    assert await _count(db, "SELECT count(*) FROM app_user WHERE id = :u "
                            "AND password_hash = 'new-hash'", u=me) == 1


async def test_a_partner_user_and_the_principal_have_no_own_password(
        db: AsyncSession, ids: Fixtures) -> None:
    dealer = await make_partner_user(db, ids, mobile=_mobile())
    await _as(db, dealer)
    await _refused(db, "SELECT auth_set_own_password('x', 'y')", {}, "has no password")
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    await _as(db, SYSTEM_ID)
    await _refused(db, "SELECT auth_set_own_password('x', 'y')", {}, "not administrable")


# ── the role-family trigger, extended ────────────────────────────────────────

async def test_the_system_role_is_refused_on_any_other_row(db: AsyncSession,
                                                          ids: Fixtures) -> None:
    await _refused(db, (
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', (SELECT id FROM role WHERE code = 'system'), :o)"),
        {"e": ids.unique("sys") + "@polysil.in", "o": ids.org_unit_id}, "not assignable")


async def test_the_principal_is_not_administrable_even_by_the_owner(db: AsyncSession) -> None:
    for sql in ("UPDATE app_user SET password_hash = 'x' WHERE id = :s",
                "UPDATE app_user SET is_active = false WHERE id = :s",
                "UPDATE app_user SET deleted_at = now() WHERE id = :s",
                "UPDATE app_user SET role_id = (SELECT id FROM role WHERE code = 'board') "
                "WHERE id = :s"):
        await _refused(db, sql, {"s": SYSTEM_ID}, "not administrable")


async def test_the_login_lookup_never_returns_the_principal(db: AsyncSession) -> None:
    """Rule 19: even with a hash forced in past the trigger, the lookup excludes the
    row by id, so there is no interactive door for the worker's identity."""
    email = f"system_{uuid.uuid4().hex[:8]}@polysil.in"
    await db.execute(text("ALTER TABLE app_user DISABLE TRIGGER trg_app_user_role_family"))
    await db.execute(text(
        "UPDATE app_user SET email = CAST(:e AS citext), password_hash = 'x' WHERE id = :s"),
        {"e": email, "s": SYSTEM_ID})
    await db.execute(text("ALTER TABLE app_user ENABLE TRIGGER trg_app_user_role_family"))
    row = (await db.execute(text(
        "SELECT user_id, password_hash FROM auth_lookup_staff(CAST(:e AS citext), 5, "
        "interval '15 minutes')"), {"e": email})).one()
    assert row.user_id is None and row.password_hash is None


async def test_a_user_cannot_deactivate_or_delete_themself(db: AsyncSession,
                                                          ids: Fixtures) -> None:
    admin = await _admin(db, ids)
    await _as(db, admin)
    await _refused(db, "UPDATE app_user SET is_active = false WHERE id = :u", {"u": admin},
                   "themself")
    await _refused(db, "UPDATE app_user SET deleted_at = now() WHERE id = :u", {"u": admin},
                   "themself")


async def test_the_seeded_portal_roles_carry_the_levels_the_trigger_expects(
        db: AsyncSession) -> None:
    """LEVEL_BY_TYPE is only true if the seed says so (F-3): the trigger reads
    role.level, and a reseed that moved a level would silently refuse every
    partner user of that type."""
    from api.domain.identity import LEVEL_BY_TYPE, PORTAL_ROLE_BY_TYPE

    rows = dict((await db.execute(text(
        "SELECT code::text, level FROM role WHERE is_portal AND deleted_at IS NULL "
        "AND code::text = ANY(CAST(:codes AS text[]))"),
        {"codes": list(PORTAL_ROLE_BY_TYPE.values())})).all())
    assert rows == {PORTAL_ROLE_BY_TYPE[t]: lvl for t, lvl in LEVEL_BY_TYPE.items()}


async def test_a_partner_users_role_level_must_match_its_partner_type(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 2: a sub-dealer's role (level 1) on a user at a dealer (level 2)."""
    sub = await _role(db, ids, "sub", level=1, portal=True)
    await _refused(db, (
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p)"),
        {"m": _mobile(), "r": sub, "p": ids.dealer_id}, "does not match the partner type")


async def test_a_closed_office_or_inactive_partner_refuses_a_create_or_reactivation(
        db: AsyncSession, ids: Fixtures) -> None:
    """Edge case 14. Never a deactivation: the partner-close cascade must still run."""
    dealer_user = await make_partner_user(db, ids, mobile=_mobile())
    await db.execute(text("UPDATE channel_partner SET is_active = false WHERE id = :p"),
                     {"p": ids.dealer_id})
    assert await _count(db, "SELECT count(*) FROM app_user WHERE id = :u AND NOT is_active",
                        u=dealer_user) == 1, "the cascade deactivated the dealer's user"
    await _refused(db, "UPDATE app_user SET is_active = true WHERE id = :u", {"u": dealer_user},
                   "partner is inactive")
    await _refused(db, (
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p)"),
        {"m": _mobile(), "r": ids.portal_role_id, "p": ids.dealer_id}, "partner is inactive")

    staff = await make_staff(db, ids, email=ids.unique("s") + "@polysil.in", is_active=False)
    await db.execute(text("UPDATE org_unit SET deleted_at = now() WHERE id = :o"),
                     {"o": ids.org_unit_id})
    await _refused(db, "UPDATE app_user SET is_active = true WHERE id = :u", {"u": staff},
                   "office is closed")
    await _refused(db, (
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o)"),
        {"e": ids.unique("c") + "@polysil.in", "r": ids.staff_role_id, "o": ids.org_unit_id},
        "office is closed")


# ── the administrator floor ──────────────────────────────────────────────────

async def test_the_last_administrator_cannot_be_deactivated_deleted_or_demoted(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 16. Every other administrator on the database is deactivated inside
    this transaction first, so the fixture's two are the only ones left."""
    a = await _admin(db, ids)
    role_b = await _role(db, ids, "adm2")
    await _grant(db, role_b, "users", ["view", "edit"], "global")
    b = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'B', :r, :o) RETURNING id"),
        {"e": ids.unique("b") + "@polysil.in", "r": role_b, "o": ids.org_unit_id})).scalar_one())
    await db.execute(text(
        "UPDATE app_user SET is_active = false WHERE id NOT IN (:a, :b) AND role_id IN "
        "(SELECT role_id FROM role_permission WHERE module = 'users' AND action = 'edit') "
        "AND is_active AND deleted_at IS NULL"), {"a": a, "b": b})
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :u"), {"u": a})
    # SET CONSTRAINTS holds for the rest of the transaction (executed): from here the
    # floor is checked at each statement, which is what the service relies on.
    await db.execute(text("SET CONSTRAINTS trg_app_user_admin_floor IMMEDIATE"))  # b remains
    for sql in ("UPDATE app_user SET is_active = false WHERE id = :u",
                "UPDATE app_user SET deleted_at = now() WHERE id = :u",
                "UPDATE app_user SET role_id = :fo WHERE id = :u"):
        with pytest.raises(REFUSED, match="last administrator"):
            async with db.begin_nested():
                await db.execute(text(sql), {"u": b, "fo": ids.staff_role_id})
                await db.execute(text("SET CONSTRAINTS trg_app_user_admin_floor IMMEDIATE"))
    # reactivating a is fine, and then b may go
    await db.execute(text("UPDATE app_user SET is_active = true WHERE id = :u"), {"u": a})
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :u"), {"u": b})
    await db.execute(text("SET CONSTRAINTS trg_app_user_admin_floor IMMEDIATE"))


async def test_the_service_turns_the_floor_into_a_422(db: AsyncSession, ids: Fixtures) -> None:
    """Code review F-2. A deferred constraint raising at COMMIT is a 500; the
    service forces it inside the request (_force_admin_floor) and maps 23514 to
    fields.id. Through the API the floor only trips under two concurrent admins
    (the caller is always counted), so the mapping is driven here directly."""
    from api.errors import ValidationFailed
    from api.services import users as users_service

    a = await _admin(db, ids)
    await db.execute(text(
        "UPDATE app_user SET is_active = false WHERE id <> :a AND role_id IN "
        "(SELECT role_id FROM role_permission WHERE module = 'users' AND action = 'edit') "
        "AND is_active AND deleted_at IS NULL"), {"a": a})
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :u"), {"u": a})
    with pytest.raises(ValidationFailed) as refused:
        await users_service._force_admin_floor(db)
    assert refused.value.fields == {"id": users_service.LAST_ADMIN}


async def test_deactivating_a_non_administrator_never_counts(db: AsyncSession,
                                                            ids: Fixtures) -> None:
    """The gate on OLD's role: a database with no administrator at all (here: no
    role holds users.edit any more) still lets an ordinary user be deactivated. An
    unconditional count would raise on every deactivation on such a database."""
    await db.execute(text(
        "DELETE FROM role_permission WHERE module = 'users' AND action = 'edit'"))
    me = await make_staff(db, ids, email=ids.unique("x") + "@polysil.in")
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :u"), {"u": me})
    await db.execute(text("SET CONSTRAINTS trg_app_user_admin_floor IMMEDIATE"))


# ── partners: guarded columns and retype ─────────────────────────────────────

async def test_a_dealer_edits_its_contact_details_and_nothing_that_prices_or_closes_it(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 14 (ISS-061), in the database. The reparent guard still owns parent_id."""
    await _grant(db, ids.portal_role_id, "partners", ["view", "edit"], "partner_subtree")
    me = await make_partner_user(db, ids, mobile=_mobile())
    await _as(db, me)
    r = await db.execute(text("UPDATE channel_partner SET contact_name = 'Chirag' WHERE id = :p"),
                         {"p": ids.dealer_id})
    assert r.rowcount == 1
    for column, value in (("credit_limit", "1"), ("payment_terms_days", "45"),
                          ("price_tier", "'distributor'"), ("is_active", "false"),
                          ("deleted_at", "now()"),
                          ("territory_id", "(SELECT id FROM territory LIMIT 1)")):
        await _refused(db, f"UPDATE channel_partner SET {column} = {value} WHERE id = :p",
                       {"p": ids.dealer_id}, "contact details only")


async def test_a_partner_with_users_cannot_change_type(db: AsyncSession, ids: Fixtures) -> None:
    await make_partner_user(db, ids, mobile=_mobile())
    await _refused(db, "UPDATE channel_partner SET partner_type = 'sub_dealer' WHERE id = :p",
                   {"p": ids.dealer_id}, "users are anchored")


# ── territories and offices: names, codes, the numbered state ───────────────

async def test_names_are_unique_under_a_parent_and_codes_per_level(db: AsyncSession,
                                                                   ids: Fixtures) -> None:
    name = ids.unique("Dup")
    await db.execute(text("INSERT INTO territory (level, name, code) VALUES ('state', :n, :c)"),
                     {"n": name, "c": ids.unique("Z")[:6]})
    await _refused(db, "INSERT INTO territory (level, name) VALUES ('state', :n)",
                   {"n": "  " + name.upper() + " "}, "uq_territory_parent_name")
    await _refused(db, "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c)",
                   {"n": ids.unique("Other"), "c": ids.unique("Z")[:6]}, "uq_territory_level_code")
    # the same letters at another level are allowed (a district may share them)
    await db.execute(text("INSERT INTO territory (level, name, code) VALUES ('district', :n, :c)"),
                     {"n": ids.unique("D"), "c": ids.unique("Z")[:6]})
    await _refused(db, "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t)",
                   {"n": " Rajkot-DM ".replace("Rajkot-DM", ids.unique("rajkot-dm")),
                    "t": ids.territory_id}, "uq_org_unit_parent_name")


async def test_a_states_code_is_immutable_once_a_lead_is_numbered_under_it(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 15, keyed on the counter ledger (A-8): a moved lead leaves no evidence,
    the counter row does. The lock is reported by territory_code_locked()."""
    code = "Z" + uuid.uuid4().hex[:3].upper()
    state = str((await db.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": ids.unique("st"), "c": code})).scalar_one())
    district = str((await db.execute(text(
        "INSERT INTO territory (level, name, parent_id, code) "
        "VALUES ('district', :n, :p, :c) RETURNING id"),
        {"n": ids.unique("dt"), "p": state, "c": code})).scalar_one())
    await db.execute(text("UPDATE territory SET code = :c WHERE id = :s"),
                     {"c": code + "X", "s": state})   # unnumbered: free to edit
    await db.execute(text("UPDATE territory SET code = :c WHERE id = :s"), {"c": code, "s": state})
    await db.execute(text(
        "INSERT INTO inquiry_counter (state_code, financial_year, last_value) "
        "VALUES (:c, '2026-27', 1)"), {"c": code})
    await _refused(db, "UPDATE territory SET code = :c WHERE id = :s",
                   {"c": code + "Y", "s": state}, "numbered under this code")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    await _as(db, me)
    assert (await db.execute(text("SELECT territory_code_locked(CAST(:s AS uuid))"),
                             {"s": state})).scalar_one() is True
    assert (await db.execute(text("SELECT territory_code_locked(CAST(:d AS uuid))"),
                             {"d": district})).scalar_one() is False


# ── the office and territory events are visible ──────────────────────────────

async def test_an_office_event_is_visible_to_an_authenticated_caller(db: AsyncSession,
                                                                    ids: Fixtures) -> None:
    await db.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload) "
        "VALUES ('org_unit', :o, 'org_unit.updated', :s, '{}'), "
        "('territory', :t, 'territory.updated', :s, '{}')"),
        {"o": ids.org_unit_id, "t": ids.territory_id, "s": SYSTEM_ID})
    me = await make_staff(db, ids, email=ids.unique("v") + "@polysil.in")
    await _as(db, me)
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_type = 'org_unit' "
                            "AND entity_id = :o", o=ids.org_unit_id) == 1
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_type = 'territory' "
                            "AND entity_id = :t", t=ids.territory_id) == 1


# ── lockout: one arithmetic, and the unlock row ──────────────────────────────

async def test_the_login_path_and_the_admin_read_agree_and_an_unlock_row_clears_the_lock(
        db: AsyncSession, ids: Fixtures) -> None:
    email = ids.unique("locked") + "@polysil.in"
    me = await make_staff(db, ids, email=email)
    await _fail_five_times(db, email)
    locked = await _locked_until(db, email)
    assert locked is not None
    admin = await _admin(db, ids)
    await _as(db, admin)
    assert (await db.execute(text(
        "SELECT auth_user_lockout(CAST(:u AS uuid), :n, :l)"),
        {"u": me, "n": MAX_FAILURES, "l": LOCKOUT})).scalar_one() == locked
    assert (await db.execute(text(
        "SELECT auth_unlock_user(CAST(:u AS uuid), :n, :l)"),
        {"u": me, "n": MAX_FAILURES, "l": LOCKOUT})).scalar_one() is True
    assert (await db.execute(text(
        "SELECT auth_user_lockout(CAST(:u AS uuid), :n, :l)"),
        {"u": me, "n": MAX_FAILURES, "l": LOCKOUT})).scalar_one() is None
    # a second unlock reports it was not locked, and still appends its row
    assert (await db.execute(text(
        "SELECT auth_unlock_user(CAST(:u AS uuid), :n, :l)"),
        {"u": me, "n": MAX_FAILURES, "l": LOCKOUT})).scalar_one() is False
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    assert await _locked_until(db, email) is None
    assert await _count(db, "SELECT count(*) FROM login_attempt WHERE identifier = "
                            "CAST(:e AS citext) AND kind = 'password' AND NOT succeeded",
                        e=email) == MAX_FAILURES, "the failures are evidence and stay"
    assert await _count(db, "SELECT count(*) FROM login_attempt WHERE identifier = "
                            "CAST(:e AS citext) AND kind = 'unlock' AND succeeded", e=email) == 2
    assert await _count(db, "SELECT count(*) FROM activity_event WHERE entity_id = :u "
                            "AND kind = 'auth.unlocked' AND actor_id = :a", u=me, a=admin) == 2


async def test_unlocking_a_partner_user_is_refused(db: AsyncSession, ids: Fixtures) -> None:
    dealer = await make_partner_user(db, ids, mobile=_mobile())
    admin = await _admin(db, ids)
    await _as(db, admin)
    await _refused(db, "SELECT auth_unlock_user(CAST(:u AS uuid), 5, interval '15 minutes')",
                   {"u": dealer}, "no lockout")


# ── the session minter is bound to the verified version (ISS-077) ───────────

async def test_a_stale_token_version_mints_nothing(db: AsyncSession, ids: Fixtures) -> None:
    me = await make_staff(db, ids, email=ids.unique("v") + "@polysil.in")
    version = await _count(db, "SELECT token_version FROM app_user WHERE id = :u", u=me)
    stale = (await db.execute(text(
        "SELECT session_id FROM auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '1 day', 'ua', '10.0.0.1', 'password', :v)"),
        {"u": me, "h": uuid.uuid4().hex, "f": str(uuid.uuid4()), "v": version + 1})).all()
    assert stale == []
    fresh = (await db.execute(text(
        "SELECT session_id FROM auth_create_session(CAST(:u AS uuid), :h, CAST(:f AS uuid), "
        "interval '1 day', 'ua', '10.0.0.1', 'password', :v)"),
        {"u": me, "h": uuid.uuid4().hex, "f": str(uuid.uuid4()), "v": version})).all()
    assert len(fresh) == 1
    assert await _count(db, "SELECT count(*) FROM pg_proc "
                            "WHERE proname = 'auth_create_session'") == 1


# ── the pickers require the candidate to hold leads.edit (ISS-075) ──────────

async def test_only_a_role_that_edits_leads_can_receive_one(db: AsyncSession,
                                                           ids: Fixtures) -> None:
    assigner_role = await _role(db, ids, "assigner")
    await _grant(db, assigner_role, "leads", ["view", "edit", "create"], "global")
    me = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Assigner', :r, :o) RETURNING id"),
        {"e": ids.unique("as") + "@polysil.in", "r": assigner_role,
         "o": ids.org_unit_id})).scalar_one())
    viewer_role = await _role(db, ids, "viewer")
    await _grant(db, viewer_role, "leads", ["view"], "global")
    viewer = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Viewer', :r, :o) RETURNING id"),
        {"e": ids.unique("vw") + "@polysil.in", "r": viewer_role,
         "o": ids.org_unit_id})).scalar_one())
    await _as(db, me)
    assert (await db.execute(text("SELECT authz_user_assignable('leads', CAST(:u AS uuid))"),
                             {"u": viewer})).scalar_one() is False
    assert (await db.execute(text("SELECT authz_user_assignable('leads', CAST(:u AS uuid))"),
                             {"u": me})).scalar_one() is True
    assert (await db.execute(text("SELECT authz_user_assignable('leads', CAST(:u AS uuid))"),
                             {"u": SYSTEM_ID})).scalar_one() is False
    listed = {str(r.id) for r in (await db.execute(text(
        "SELECT id FROM staff_directory('leads')"))).all()}
    assert me in listed and viewer not in listed and SYSTEM_ID not in listed


# ── the count definers answer only inside the caller's scope (cross-vendor P2-1) ─

async def test_partner_user_counts_answer_only_for_partners_the_caller_can_see(
        db: AsyncSession, ids: Fixtures) -> None:
    """A dealer could count any partner's users by id: the definer runs unscoped
    and checked a permission, not a scope. It now filters the ids through the
    partners guard, so an invisible partner is simply not in the answer."""
    await _grant(db, ids.portal_role_id, "partners", ["view"], "partner_subtree")
    me = await make_partner_user(db, ids, mobile=_mobile())
    other = str((await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'x', :t, 'distributor') RETURNING id"),
        {"c": ids.unique("OTHER"), "t": ids.territory_id})).scalar_one())
    dist_role = await _role(db, ids, "dist", level=3, portal=True)
    await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p)"), {"m": _mobile(), "r": dist_role, "p": other})
    await _as(db, me)
    rows = (await db.execute(text(
        "SELECT partner_id::text, users FROM channel_partner_user_counts(CAST(:ids AS uuid[]))"),
        {"ids": [str(ids.dealer_id), other]})).all()
    assert [(r[0], r[1]) for r in rows] == [(str(ids.dealer_id), 1)], rows


async def test_open_lead_counts_answer_only_for_people_in_the_callers_users_scope(
        db: AsyncSession, ids: Fixtures) -> None:
    """The same shape on people: a users.view holder at org_subtree could count an
    outside person's open leads by id."""
    role = await _role(db, ids, "sub")
    await _grant(db, role, "users", ["view"], "org_subtree")
    me = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Me', :r, :o) RETURNING id"),
        {"e": ids.unique("me") + "@polysil.in", "r": role, "o": ids.org_unit_id})).scalar_one())
    elsewhere = str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level) VALUES (:n, 2) RETURNING id"),
        {"n": ids.unique("elsewhere")})).scalar_one())
    inside = await make_staff(db, ids, email=ids.unique("in") + "@polysil.in")
    outside = str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Out', :r, :o) RETURNING id"),
        {"e": ids.unique("out") + "@polysil.in", "r": ids.staff_role_id,
         "o": elsewhere})).scalar_one())
    for owner, unit in ((inside, ids.org_unit_id), (outside, elsewhere)):
        await db.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, "
            "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id) VALUES "
            "(:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
            "(SELECT id FROM lead_source WHERE code = 'employee'), 'F', :m, :t, :u, :ou)"),
            {"no": "F7-" + uuid.uuid4().hex[:10], "m": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
             "t": ids.territory_id, "u": owner, "ou": unit})
    await _as(db, me)
    rows = (await db.execute(text(
        "SELECT user_id::text FROM user_open_leads_bulk(CAST(:ids AS uuid[]))"),
        {"ids": [str(inside), outside]})).all()
    assert [r[0] for r in rows] == [str(inside)], rows


async def test_stripping_users_edit_from_every_administrator_role_is_refused(
        db: AsyncSession, ids: Fixtures) -> None:
    """Cross-vendor P2-2: a masters.edit holder may write role_permission, and
    taking users.edit away from the last administrator's role leaves nobody. The
    floor watches those rows too."""
    a = await _admin(db, ids)
    await db.execute(text(
        "UPDATE app_user SET is_active = false WHERE id <> :a AND role_id IN "
        "(SELECT role_id FROM role_permission WHERE module = 'users' AND action = 'edit') "
        "AND is_active AND deleted_at IS NULL"), {"a": a})
    await db.execute(text("SET CONSTRAINTS trg_app_user_admin_floor IMMEDIATE"))   # a remains
    with pytest.raises(REFUSED, match="last administrator"):
        async with db.begin_nested():
            await db.execute(text(
                "DELETE FROM role_permission WHERE module = 'users' AND action = 'edit' "
                "AND role_id = (SELECT role_id FROM app_user WHERE id = :a)"), {"a": a})
            await db.execute(text("SET CONSTRAINTS trg_role_permission_admin_floor IMMEDIATE"))
