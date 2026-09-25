"""Migration 003, against a real database.

The negative cases carry the weight here. Proving a consumer *cannot* hold a role,
that a staff row carrying a mobile is *not* reachable through the OTP door, and
that a lockout does *not* fire on stale failures are the assertions that get
skipped and the ones that matter (CLAUDE.md 1.4).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures, _anon_role, make_partner_user, make_staff

pytestmark = pytest.mark.db

# 007 binds a session to the token_version the credential was verified against
# (FS-006 rule 6). The fixtures mint with the row's own, read in the same statement.
_V = ", (SELECT token_version FROM app_user WHERE id = CAST(:u AS uuid)))"


LOCKOUT = timedelta(minutes=15)
MAX_FAILURES = 5

# The eight functions get_db_anon may reach, with the exact signatures the guarded
# grant block names. FS-001 section 10 enumerates rather than spot-checks, because
# the defect it guards against is a *missing* function as much as an extra one.
PRE_AUTH = {
    "auth_lookup_staff": "p_email citext, p_max_failures integer, p_lockout interval",
    "auth_lookup_by_mobile": "p_mobile text",
    "auth_create_session": ("p_user_id uuid, p_refresh_hash text, p_family_id uuid, "
                            "p_ttl interval, p_ua text, p_ip inet, p_door text, "
                            "p_token_version integer"),
    "auth_record_attempt": ("p_identifier citext, p_ip inet, p_succeeded boolean, "
                            "p_kind login_kind"),
    "auth_issue_otp_challenge": "p_mobile text, p_ip inet, p_code text, p_daily_cap integer",
    "auth_claim_refresh": "p_refresh_hash text",
    "auth_classify_refresh": "p_refresh_hash text",
    "auth_revoke_sessions": "p_session_id uuid, p_family_id uuid",
    # FS-005: the public quotation link, two more definer functions on app_anon
    "quotation_public_view": "p_token text",
    "quotation_public_open": "p_token text, p_user_agent text",
    # FS-003a: the public enquiry form and QR codes, five more
    "lead_intake_issue": ("p_mobile text, p_ip inet, p_code text, p_code_hash text, "
                          "p_ttl_seconds integer, p_ip_per_hour integer, p_codes_per_hour integer"),
    "lead_intake_consume": "p_mobile text, p_code_hash text",
    "lead_qr_public": "p_code text",
    "lead_public_form": "",
    "lead_public_territories": "p_parent uuid",
}


async def _attempt(db: AsyncSession, identifier: str, *, succeeded: bool,
                   kind: str = "password", ago: timedelta = timedelta()) -> None:
    await db.execute(
        text("INSERT INTO login_attempt (identifier, ip, succeeded, kind, attempted_at) "
             "VALUES (:i, '10.0.0.1', :s, CAST(:k AS login_kind), now() - CAST(:ago AS interval))"),
        {"i": identifier, "s": succeeded, "k": kind, "ago": ago},
    )


async def _lookup(db: AsyncSession, email: str):
    return (await db.execute(
        text("SELECT * FROM auth_lookup_staff(CAST(:e AS citext), :n, :l)"),
        {"e": email, "n": MAX_FAILURES, "l": LOCKOUT})).mappings().all()


# ── the pre-auth surface ─────────────────────────────────────────────────────

async def test_exactly_the_pre_auth_functions_exist(db: AsyncSession) -> None:
    """Keyed on the pre-auth role's privilege, not on the name prefix: 007 adds six
    `auth_*` functions that are not pre-auth. Extension functions are excluded,
    because app_anon inherits EXECUTE on 114 pgcrypto, pg_trgm and citext
    functions through PUBLIC (executed: 122 rows, 8 after the exclusion)."""
    role = _anon_role()
    got = {
        (r.proname, r.args)
        for r in (await db.execute(text(
            "SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS args "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e' "
            "WHERE n.nspname = 'public' AND d.objid IS NULL "
            "AND has_function_privilege(CAST(:role AS name), p.oid, 'EXECUTE')"),
            {"role": role})).all()
    }
    assert got == set(PRE_AUTH.items())


async def test_public_holds_execute_on_nothing_this_project_created(
        db: AsyncSession) -> None:
    """Round 4's B-6. A function's proacl is NULL right after CREATE and NULL means
    the default, which is EXECUTE to PUBLIC - so every SECURITY DEFINER helper was
    callable by anyone until the migration revoked it.

    Extension-owned functions are excluded, and that exclusion is not cosmetic:
    `appuser` cannot revoke them, because the grants to PUBLIC were made by a
    different role and PostgreSQL only lets the grantor revoke. FS-001 section 10
    asserted "PUBLIC holds EXECUTE on nothing in public", which is not achievable
    here and would fail in staging too. ISS-039 carries the evidence and the
    argument for why those 114 functions are not the same kind of exposure - none
    of them reads an application table.
    """
    leaked = (await db.execute(text(
        "SELECT p.proname FROM pg_proc p "
        "  JOIN pg_namespace n ON n.oid = p.pronamespace "
        "  LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e' "
        " WHERE n.nspname = 'public' AND d.objid IS NULL "
        "   AND has_function_privilege('public', p.oid, 'EXECUTE')"))).scalars().all()
    assert leaked == [], f"PUBLIC can execute: {leaked}"


async def test_the_extension_grants_we_cannot_revoke_are_only_extension_grants(
        db: AsyncSession) -> None:
    """The other half of the finding above, asserted rather than assumed.

    If a future extension shipped a function that read application data, the
    exclusion in the previous test would quietly cover it. This one fails when the
    unrevokable set grows beyond the extensions the migrations install, which is
    what it did the day 009 added `btree_gist` for the subsidy masters' exclusion
    constraints. Adding a name here is a decision, not a formality: it says the
    extension's public functions are safe for anyone to execute.
    """
    extensions = (await db.execute(text(
        "SELECT DISTINCT e.extname FROM pg_proc p "
        "  JOIN pg_namespace n ON n.oid = p.pronamespace "
        "  JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e' "
        "  JOIN pg_extension e ON e.oid = d.refobjid "
        " WHERE n.nspname = 'public' "
        "   AND has_function_privilege('public', p.oid, 'EXECUTE')"))).scalars().all()
    assert set(extensions) <= {"pgcrypto", "pg_trgm", "citext", "btree_gist"}, extensions


async def test_a_function_added_later_reopens_the_hole_and_this_suite_catches_it(
        db: AsyncSession) -> None:
    """Rule 24 said `ALTER DEFAULT PRIVILEGES` kept this property true rather than
    momentary. It does not, and the line is gone from the migration: executed
    against 16.14, a bare REVOKE in `ALTER DEFAULT PRIVILEGES` writes no
    `pg_default_acl` row at all, so it changes nothing (ISS-040).

    So the enforcement is the previous test, and this one proves that it bites. A
    new function IS executable by PUBLIC on creation - that is the built-in default
    and nothing prevents it - and the query that guards the schema returns it. A
    migration 004 that adds a function without repeating the REVOKE fails the
    suite, which is the property rule 24 wanted and now gets by verification.
    """
    name = f"_probe_{uuid.uuid4().hex[:8]}"
    await db.execute(text(f"CREATE FUNCTION {name}() RETURNS int LANGUAGE sql AS 'SELECT 1'"))

    granted = await db.execute(text(
        f"SELECT has_function_privilege('public', '{name}()'::regprocedure, 'EXECUTE')"))
    assert granted.scalar_one() is True, "the built-in default stopped being EXECUTE to PUBLIC"

    caught = (await db.execute(text(
        "SELECT p.proname FROM pg_proc p "
        "  JOIN pg_namespace n ON n.oid = p.pronamespace "
        "  LEFT JOIN pg_depend d ON d.objid = p.oid AND d.deptype = 'e' "
        " WHERE n.nspname = 'public' AND d.objid IS NULL "
        "   AND has_function_privilege('public', p.oid, 'EXECUTE')"))).scalars().all()
    assert name in caught, "the guard would not catch a function added by a later migration"

    # And the REVOKE the next migration owes closes it.
    await db.execute(text("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC"))
    closed = await db.execute(text(
        f"SELECT has_function_privilege('public', '{name}()'::regprocedure, 'EXECUTE')"))
    assert closed.scalar_one() is False


async def test_classify_refresh_is_declared_read_only(db: AsyncSession) -> None:
    """Section 4: "it classifies only, it never mints a token and never writes".
    STABLE makes that a property of the function rather than a promise about its
    caller - a write inside it would raise at runtime."""
    volatility = await db.execute(text(
        "SELECT provolatile FROM pg_proc WHERE proname = 'auth_classify_refresh'"))
    assert volatility.scalar_one() in ("s", b"s")


# ── the lockout, which is rule 5 and both its clauses ────────────────────────

async def test_unknown_email_returns_one_row_of_nulls(db: AsyncSession) -> None:
    """Uniform shape, so the caller's dummy-verify path is the default rather than
    something it has to remember. A plain SELECT would return no rows."""
    rows = await _lookup(db, "nobody@polysil.in")
    assert len(rows) == 1
    assert rows[0]["user_id"] is None and rows[0]["password_hash"] is None


async def test_five_failures_inside_the_window_lock(db: AsyncSession, ids: Fixtures) -> None:
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for _ in range(MAX_FAILURES):
        await _attempt(db, email, succeeded=False)
    assert (await _lookup(db, email))[0]["locked_until"] is not None


async def test_four_failures_do_not_lock(db: AsyncSession, ids: Fixtures) -> None:
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for _ in range(MAX_FAILURES - 1):
        await _attempt(db, email, succeeded=False)
    assert (await _lookup(db, email))[0]["locked_until"] is None


async def test_a_success_resets_the_count(db: AsyncSession, ids: Fixtures) -> None:
    """AC-AUTH-4. Four mistypes, a successful sign-in, one more mistype must not
    lock - round 4's B-3, where a pure trailing window dropped the reset."""
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for m in (5, 4, 3, 2):
        await _attempt(db, email, succeeded=False, ago=timedelta(minutes=m))
    await _attempt(db, email, succeeded=True, ago=timedelta(seconds=90))
    await _attempt(db, email, succeeded=False)
    assert (await _lookup(db, email))[0]["locked_until"] is None


async def test_a_stale_success_does_not_widen_the_window(db: AsyncSession,
                                                         ids: Fixtures) -> None:
    """The R5-3 regression, and the reason the bound is greatest() not coalesce().

    A success at 09:00, four mistypes 09:05-09:08 and one more at 14:00 is five
    failures after the success - so coalesce locks the account on four failures
    five hours outside the trailing fifteen minutes AC-AUTH-4 bounds it to.
    """
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    await _attempt(db, email, succeeded=True, ago=timedelta(hours=5))
    for m in (295, 294, 293, 292):
        await _attempt(db, email, succeeded=False, ago=timedelta(minutes=m))
    await _attempt(db, email, succeeded=False)
    assert (await _lookup(db, email))[0]["locked_until"] is None


async def test_a_lockout_expires_without_a_success(db: AsyncSession,
                                                   ids: Fixtures) -> None:
    """A success is impossible while locked, so a rule with no time bound never
    expires - round 3's B-6."""
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for _ in range(MAX_FAILURES):
        await _attempt(db, email, succeeded=False, ago=timedelta(minutes=20))
    assert (await _lookup(db, email))[0]["locked_until"] is None


async def test_locked_until_is_never_already_expired(db: AsyncSession,
                                                     ids: Fixtures) -> None:
    """The bound is never older than now() - lockout, so the fifth failure is always
    inside the window. A past locked_until would read as "not locked"."""
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for m in (14, 13, 12, 11, 10):
        await _attempt(db, email, succeeded=False, ago=timedelta(minutes=m))
    future = await db.execute(text(
        "SELECT locked_until > now() FROM auth_lookup_staff(CAST(:e AS citext), :n, :l)"),
        {"e": email, "n": MAX_FAILURES, "l": LOCKOUT})
    assert future.scalar_one() is True


async def test_otp_failures_do_not_feed_the_password_lockout(db: AsyncSession,
                                                             ids: Fixtures) -> None:
    """Rule 12. Counting them burns the code AND locks the number for 15 minutes,
    so a correctly entered fresh code is rejected."""
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for _ in range(MAX_FAILURES * 2):
        await _attempt(db, email, succeeded=False, kind="otp")
    assert (await _lookup(db, email))[0]["locked_until"] is None


# ── the two doors ────────────────────────────────────────────────────────────

async def test_staff_with_a_mobile_is_not_reachable_through_the_otp_door(
        db: AsyncSession, ids: Fixtures) -> None:
    """Round 3's B-5, and the reason the CHECK permits a mobile on staff but the
    lookup does not. Without the user_type filter this is a second, weaker door
    onto every password account - no password, no argon2, and no lockout."""
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in", mobile=mobile)
    rows = (await db.execute(text("SELECT * FROM auth_lookup_by_mobile(:m)"),
                             {"m": mobile})).all()
    assert rows == []


async def test_partner_user_with_an_email_is_not_reachable_through_the_password_door(
        db: AsyncSession, ids: Fixtures) -> None:
    """The mirror case. email is nullable and the CHECK does not forbid it on a
    portal row, so it must fail as invalid_credentials rather than verify against
    a NULL hash."""
    email = ids.unique("bhavesh") + "@dealer.in"
    await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}", email=email)
    assert (await _lookup(db, email))[0]["user_id"] is None


async def test_a_soft_deleted_row_is_invisible_to_both_lookups(
        db: AsyncSession, ids: Fixtures) -> None:
    """The corollary of the partial unique indexes: uniqueness holds among live
    rows only, so without this filter a soft-deleted row makes an otherwise-unique
    lookup ambiguous again (Schema-Corrections 5a.4)."""
    email = ids.unique("gone") + "@polysil.in"
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    uid = await make_staff(db, ids, email=email)
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :i"),
                     {"i": uid})
    assert (await _lookup(db, email))[0]["user_id"] is None

    puid = await make_partner_user(db, ids, mobile=mobile)
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :i"),
                     {"i": puid})
    assert (await db.execute(text("SELECT * FROM auth_lookup_by_mobile(:m)"),
                             {"m": mobile})).all() == []


async def test_a_soft_deleted_number_can_be_reissued(db: AsyncSession,
                                                     ids: Fixtures) -> None:
    """EC-2. A table-level UNIQUE would forbid this, and rural number reuse needs
    it: a dealer's staff member leaves and the number goes to their replacement."""
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    old = await make_partner_user(db, ids, mobile=mobile)
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :i"),
                     {"i": old})
    assert await make_partner_user(db, ids, mobile=mobile) != old


# ── the role family, which is EC-1 ───────────────────────────────────────────

async def test_a_consumer_cannot_hold_a_role(db: AsyncSession, ids: Fixtures) -> None:
    """A consumer row holding admin_sales passes the CHECK, and app_scope() and
    app_has_permission() resolve global delete on it - they join on role_id and
    never read user_type. Reachable by OTP on a phone the holder controls."""
    with pytest.raises((IntegrityError, InternalError), match="consumers hold no role"):
        await db.execute(text(
            "INSERT INTO app_user (user_type, mobile, full_name, role_id, customer_id) "
            "VALUES ('consumer', :m, 'Ramesh', :r, :c)"),
            {"m": "9199" + f"{uuid.uuid4().int % 10**8:08d}", "r": ids.staff_role_id,
             "c": str(uuid.uuid4())})


async def test_a_staff_user_must_hold_a_role(db: AsyncSession, ids: Fixtures) -> None:
    with pytest.raises((IntegrityError, InternalError), match="must hold a role"):
        await db.execute(text(
            "INSERT INTO app_user (user_type, email, full_name, org_unit_id) "
            "VALUES ('staff', :e, 'Asha', :o)"),
            {"e": ids.unique("x") + "@polysil.in", "o": ids.org_unit_id})


async def test_a_staff_user_cannot_hold_a_portal_role(db: AsyncSession,
                                                      ids: Fixtures) -> None:
    with pytest.raises((IntegrityError, InternalError), match="is a portal role"):
        await db.execute(text(
            "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
            "VALUES ('staff', :e, 'Asha', :r, :o)"),
            {"e": ids.unique("x") + "@polysil.in", "r": ids.portal_role_id,
             "o": ids.org_unit_id})


async def test_a_partner_user_cannot_hold_a_staff_role(db: AsyncSession,
                                                       ids: Fixtures) -> None:
    with pytest.raises((IntegrityError, InternalError), match="not a portal role"):
        await db.execute(text(
            "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
            "VALUES ('partner_user', :m, 'Bhavesh', :r, :p)"),
            {"m": "9199" + f"{uuid.uuid4().int % 10**8:08d}", "r": ids.staff_role_id,
             "p": str(uuid.uuid4())})


async def test_changing_user_type_bumps_token_version(db: AsyncSession,
                                                      ids: Fixtures) -> None:
    """Rule 27. The lookup filters stop the wrong door being opened; they do nothing
    about a session already behind it, so an OTP-minted session would otherwise
    survive a promotion to staff."""
    uid = await make_partner_user(db, ids, mobile="9199" + f"{uuid.uuid4().int % 10**8:08d}")
    before = (await db.execute(text("SELECT token_version FROM app_user WHERE id = :i"),
                               {"i": uid})).scalar_one()
    await db.execute(text(
        "UPDATE app_user SET user_type = 'staff', role_id = :r, org_unit_id = :o, "
        "partner_id = NULL, email = :e, mobile = NULL WHERE id = :i"),
        {"r": ids.staff_role_id, "o": ids.org_unit_id, "i": uid,
         "e": ids.unique("promoted") + "@polysil.in"})
    after = (await db.execute(text("SELECT token_version FROM app_user WHERE id = :i"),
                              {"i": uid})).scalar_one()
    assert after == before + 1


@pytest.mark.parametrize("column", ["is_portal", "is_functional", "code"])
async def test_role_family_flags_are_seed_only(db: AsyncSession, ids: Fixtures,
                                               column: str) -> None:
    """B-10. The app_user trigger fires on app_user, so it cannot see the change
    that reopens EC-1 from the other side."""
    value = "'x'" if column == "code" else "NOT " + column
    with pytest.raises((IntegrityError, InternalError), match="seeded, not editable"):
        await db.execute(text(f"UPDATE role SET {column} = {value} WHERE id = :i"),
                         {"i": ids.portal_role_id})


async def test_an_idempotent_reseed_still_passes(db: AsyncSession,
                                                 ids: Fixtures) -> None:
    """IS DISTINCT FROM rather than <>. Writing identical values must pass, or
    every reseed in test setup fails."""
    await db.execute(text(
        "UPDATE role SET is_portal = is_portal, is_functional = is_functional, "
        "code = code, name = 'Renamed' WHERE id = :i"), {"i": ids.portal_role_id})
    name = await db.execute(text("SELECT name FROM role WHERE id = :i"),
                            {"i": ids.portal_role_id})
    assert name.scalar_one() == "Renamed"


@pytest.mark.parametrize(
    ("user_type", "cols", "vals"),
    [
        ("partner_user", "partner_id, org_unit_id, mobile",
         ":u, :o, '919900000001'"),
        ("consumer", "customer_id, partner_id, mobile", ":u, :u, '919900000002'"),
        ("staff", "org_unit_id, email, customer_id", ":o, 'x@polysil.in', :u"),
    ],
)
async def test_the_check_forbids_the_anchors_a_type_should_not_hold(
        db: AsyncSession, ids: Fixtures, user_type: str, cols: str, vals: str) -> None:
    """Proposed-Schema.md section 2 writes this as an OR of three positive
    conditions, which forbids nothing. A partner_user carrying an org_unit_id
    points a portal user at FS-002's org policy branch."""
    role = ids.portal_role_id if user_type == "partner_user" else ids.staff_role_id
    role_sql = "NULL" if user_type == "consumer" else ":r"
    with pytest.raises(IntegrityError, match="ck_app_user_anchors"):
        await db.execute(
            text(f"INSERT INTO app_user (user_type, full_name, role_id, {cols}) "
                 f"VALUES ('{user_type}', 'X', {role_sql}, {vals})"),
            {"u": str(uuid.uuid4()), "o": ids.org_unit_id, "r": role},
        )


# ── sessions, and the events they emit ───────────────────────────────────────

async def _session(db: AsyncSession, user_id: str, *, door: str | None = "password",
                   ttl: timedelta = timedelta(days=30), family: str | None = None):
    return (await db.execute(
        text("SELECT * FROM auth_create_session(:u, :h, :f, :t, 'ua', '10.0.0.1', :d" + _V),
        {"u": user_id, "h": uuid.uuid4().hex, "f": family or str(uuid.uuid4()),
         "t": ttl, "d": door})).mappings().all()


async def _events(db: AsyncSession, user_id: str, kind: str) -> int:
    return (await db.execute(text(
        "SELECT count(*) FROM activity_event WHERE entity_id = :i AND kind = :k"),
        {"i": user_id, "k": kind})).scalar_one()


async def test_sign_in_emits_one_event_and_stamps_last_login(
        db: AsyncSession, ids: Fixtures) -> None:
    """Rule 7, made structural: the insert is inside the function, so "same
    transaction" is not a convention the service has to keep."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    rows = await _session(db, uid, door="password")
    assert len(rows) == 1 and rows[0]["session_id"] is not None
    assert await _events(db, uid, "auth.signed_in") == 1
    stamped = await db.execute(text(
        "SELECT last_login_at IS NOT NULL FROM app_user WHERE id = :i"), {"i": uid})
    assert stamped.scalar_one() is True


async def test_rotation_emits_nothing(db: AsyncSession, ids: Fixtures) -> None:
    """A refresh creates a session and is not a sign-in. Section 5 lists sign-in,
    sign-out and family revocation, and rotation is none of them."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    await _session(db, uid, door=None)
    assert await _events(db, uid, "auth.signed_in") == 0


async def test_an_unknown_door_raises(db: AsyncSession, ids: Fixtures) -> None:
    """Rule 26. A function granted to app_anon that took a free-text kind would let
    an unauthenticated caller write rows on a user's timeline."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    with pytest.raises(DBAPIError, match="unknown sign-in door"):
        await _session(db, uid, door="magic")


async def test_a_session_snapshots_the_users_current_token_version(
        db: AsyncSession, ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    await db.execute(text("UPDATE app_user SET token_version = 7 WHERE id = :i"),
                     {"i": uid})
    row = (await _session(db, uid))[0]
    tv = await db.execute(text("SELECT token_version FROM session WHERE id = :i"),
                          {"i": row["session_id"]})
    assert tv.scalar_one() == 7


async def test_creating_a_session_for_nobody_returns_nothing(db: AsyncSession) -> None:
    assert await _session(db, str(uuid.uuid4())) == []


# ── refresh ──────────────────────────────────────────────────────────────────

async def _claim(db: AsyncSession, token_hash: str):
    return (await db.execute(text("SELECT * FROM auth_claim_refresh(:h)"),
                             {"h": token_hash})).mappings().one()


async def _issue(db: AsyncSession, user_id: str) -> str:
    token_hash = uuid.uuid4().hex
    await db.execute(
        text("SELECT auth_create_session(:u, :h, :f, interval '30 days', "
             "'ua', '10.0.0.1', 'password'" + _V),
        {"u": user_id, "h": token_hash, "f": str(uuid.uuid4())})
    return token_hash


async def test_a_fresh_token_claims_once(db: AsyncSession, ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    h = await _issue(db, uid)
    assert (await _claim(db, h))["outcome"] == "claimed"
    assert (await _claim(db, h))["outcome"] == "not_claimed"


async def test_an_unknown_token_is_not_claimed(db: AsyncSession) -> None:
    assert (await _claim(db, uuid.uuid4().hex))["outcome"] == "not_claimed"


async def test_a_deactivated_user_rolls_used_at_back(db: AsyncSession,
                                                     ids: Fixtures) -> None:
    """Without the rollback the client's retry presents a used token and classifies
    as reuse, killing the whole family for what should be a clean session_revoked."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    h = await _issue(db, uid)
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :i"),
                     {"i": uid})
    assert (await _claim(db, h))["outcome"] == "session_revoked"
    used = await db.execute(text(
        "SELECT used_at FROM session WHERE refresh_token_hash = :h"), {"h": h})
    assert used.scalar_one() is None


async def test_a_moved_token_version_rolls_used_at_back(db: AsyncSession,
                                                        ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    h = await _issue(db, uid)
    await db.execute(text(
        "UPDATE app_user SET token_version = token_version + 1 WHERE id = :i"),
        {"i": uid})
    assert (await _claim(db, h))["outcome"] == "session_revoked"
    used = await db.execute(text(
        "SELECT used_at FROM session WHERE refresh_token_hash = :h"), {"h": h})
    assert used.scalar_one() is None


async def test_a_rejection_leaves_the_transaction_usable(db: AsyncSession,
                                                         ids: Fixtures) -> None:
    """It returns an outcome rather than raising. Raising would abort the caller's
    transaction, and the classification query still has to run in it."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    h = await _issue(db, uid)
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :i"),
                     {"i": uid})
    await _claim(db, h)
    still_works = await db.execute(text("SELECT 1"))
    assert still_works.scalar_one() == 1


async def test_the_successor_takes_the_users_current_version(db: AsyncSession,
                                                             ids: Fixtures) -> None:
    """Not the predecessor's, or a bump landing mid-rotation is carried forward and
    never detected. Here the bump matches, so the claim succeeds and returns the
    value the successor must record."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    h = await _issue(db, uid)
    claimed = await _claim(db, h)
    assert claimed["outcome"] == "claimed" and claimed["token_version"] == 0


async def test_classification_reads_every_field_the_precedence_needs(
        db: AsyncSession, ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    h = await _issue(db, uid)
    row = (await db.execute(text("SELECT * FROM auth_classify_refresh(:h)"),
                            {"h": h})).mappings().one()
    assert set(row) == {"session_id", "family_id", "used_at", "revoked_at", "expires_at"}


async def test_classification_of_an_unknown_token_is_no_row(db: AsyncSession) -> None:
    """Classification 4. An unknown token is not evidence of anything."""
    rows = (await db.execute(text("SELECT * FROM auth_classify_refresh(:h)"),
                             {"h": uuid.uuid4().hex})).all()
    assert rows == []


async def test_a_soft_deleted_user_cannot_claim_a_refresh_token(
        db: AsyncSession, ids: Fixtures) -> None:
    """The cross-vendor review's X-3. Both sign-in lookups filter deleted_at and
    this one did not, so a removed account kept refreshing indefinitely - and its
    mobile number can be reissued to someone else while those tokens still work."""
    uid = await make_staff(db, ids, email=ids.unique("gone") + "@polysil.in")
    h = await _issue(db, uid)
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :i"), {"i": uid})
    assert (await _claim(db, h))["outcome"] == "session_revoked"


async def test_a_soft_deleted_user_cannot_be_given_a_new_session(
        db: AsyncSession, ids: Fixtures) -> None:
    """The other half of X-3. auth_create_session is the one function that mints a
    session, so a caller that forgets to check eligibility gets zero rows rather
    than a working session for a removed account."""
    uid = await make_staff(db, ids, email=ids.unique("gone") + "@polysil.in")
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :i"), {"i": uid})
    assert await _session(db, uid) == []


async def test_a_deactivated_user_cannot_be_given_a_new_session(
        db: AsyncSession, ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("off") + "@polysil.in")
    await db.execute(text("UPDATE app_user SET is_active = false WHERE id = :i"), {"i": uid})
    assert await _session(db, uid) == []


async def test_a_lockout_lasts_to_its_deadline_not_to_its_window(
        db: AsyncSession, ids: Fixtures) -> None:
    """The cross-vendor review's X-5, and the reason the derivation is a window
    function rather than a count.

    Five failures at 09:00-09:04 lock until 09:19. Counting the failures currently
    inside a trailing fifteen minutes, by 09:16 only four remain and the lock
    reports as over - three minutes early, on a rule that says fifteen.
    """
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for m in (16, 15, 14, 13, 12):
        await _attempt(db, email, succeeded=False, ago=timedelta(minutes=m))
    row = (await db.execute(text(
        "SELECT locked_until, locked_until > now() AS live "
        "FROM auth_lookup_staff(CAST(:e AS citext), :n, :l)"),
        {"e": email, "n": MAX_FAILURES, "l": LOCKOUT})).mappings().one()
    assert row["locked_until"] is not None, "unlocked before the deadline"
    assert row["live"] is True


async def test_the_lockout_still_ends_at_its_deadline(db: AsyncSession,
                                                      ids: Fixtures) -> None:
    """The mirror of the test above. Holding a lock past its deadline would be the
    obvious over-correction, and it locks people out of their own accounts."""
    email = ids.unique("asha") + "@polysil.in"
    await make_staff(db, ids, email=email)
    for m in (20, 19, 18, 17, 16):
        await _attempt(db, email, succeeded=False, ago=timedelta(minutes=m))
    assert (await _lookup(db, email))[0]["locked_until"] is None


async def test_converting_to_consumer_bumps_token_version(db: AsyncSession,
                                                          ids: Fixtures) -> None:
    """The cross-vendor review's X-7. Rule 27 is about moving a user between doors,
    and the consumer branch returned before reaching the bump - so sessions minted
    through the old door survived the conversion."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    before = (await db.execute(text("SELECT token_version FROM app_user WHERE id = :i"),
                               {"i": uid})).scalar_one()
    await db.execute(text(
        "UPDATE app_user SET user_type = 'consumer', role_id = NULL, org_unit_id = NULL, "
        "email = NULL, mobile = :m, customer_id = :c WHERE id = :i"),
        {"m": "9199" + f"{uuid.uuid4().int % 10**8:08d}", "c": str(uuid.uuid4()), "i": uid})
    after = (await db.execute(text("SELECT token_version FROM app_user WHERE id = :i"),
                              {"i": uid})).scalar_one()
    assert after == before + 1


# ── revocation ───────────────────────────────────────────────────────────────

async def _revoke(db: AsyncSession, *, session_id: str | None = None,
                  family_id: str | None = None) -> int:
    return (await db.execute(text("SELECT auth_revoke_sessions(:s, :f)"),
                             {"s": session_id, "f": family_id})).scalar_one()


async def test_logout_revokes_one_session_and_emits_once(db: AsyncSession,
                                                         ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    other = (await _session(db, uid))[0]["session_id"]
    target = (await _session(db, uid))[0]["session_id"]

    assert await _revoke(db, session_id=target) == 1
    assert await _events(db, uid, "auth.signed_out") == 1
    alive = await db.execute(text("SELECT revoked_at IS NULL FROM session WHERE id = :i"),
                             {"i": other})
    assert alive.scalar_one() is True, "logging out of a phone signed out the desktop"


async def test_a_repeated_logout_writes_no_second_event(db: AsyncSession,
                                                        ids: Fixtures) -> None:
    """Logout is idempotent, so a signed-out client retrying gets a 204 and the
    timeline does not gain a row per retry."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    sid = (await _session(db, uid))[0]["session_id"]
    await _revoke(db, session_id=sid)
    assert await _revoke(db, session_id=sid) == 0
    assert await _events(db, uid, "auth.signed_out") == 1


async def test_family_revocation_kills_the_family_and_emits_once_per_user(
        db: AsyncSession, ids: Fixtures) -> None:
    """ADR-025. One event per distinct user among the rows this call changed, not
    one per session."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    family = str(uuid.uuid4())
    for _ in range(3):
        await _session(db, uid, family=family)
    await _session(db, uid)  # a different family, must survive

    assert await _revoke(db, family_id=family) == 3
    assert await _events(db, uid, "auth.family_revoked") == 1
    survivors = await db.execute(text(
        "SELECT count(*) FROM session WHERE user_id = :u AND revoked_at IS NULL"),
        {"u": uid})
    assert survivors.scalar_one() == 1


@pytest.mark.parametrize("args", [(None, None), ("both", "both")])
async def test_revocation_demands_exactly_one_id(db: AsyncSession,
                                                 ids: Fixtures, args: tuple) -> None:
    """EC-17 and EC-18. The guard is correct and must stay unreachable: the router
    returns 204 without calling this when neither credential is present, and Bearer's
    sid wins when both are."""
    sid = str(uuid.uuid4()) if args[0] else None
    fid = str(uuid.uuid4()) if args[1] else None
    with pytest.raises(DBAPIError, match="exactly one of"):
        await _revoke(db, session_id=sid, family_id=fid)


# ── the OTP challenge ────────────────────────────────────────────────────────

async def _issue_otp(db: AsyncSession, mobile: str, cap: int = 10) -> bool:
    return (await db.execute(
        text("SELECT auth_issue_otp_challenge(:m, '10.0.0.1', :c, :cap)"),
        {"m": mobile, "c": "482913", "cap": cap})).scalar_one()


async def test_a_code_reaches_the_outbox_and_the_ledger(db: AsyncSession,
                                                        ids: Fixtures) -> None:
    """Rule 6: outbound messages go to the outbox, never sent inside a request."""
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    await make_partner_user(db, ids, mobile=mobile)
    assert await _issue_otp(db, mobile) is True

    row = (await db.execute(text(
        "SELECT channel::text, template_key, recipient, payload, state::text "
        "FROM notification_outbox WHERE recipient = :m"), {"m": mobile})).mappings().one()
    assert row["template_key"] == "auth.otp" and row["state"] == "pending"
    assert row["payload"] == {"code": "482913"}

    issued = await db.execute(text(
        "SELECT count(*) FROM login_attempt WHERE identifier = CAST(:m AS citext) "
        "AND kind = 'otp_issue'"), {"m": mobile})
    assert issued.scalar_one() == 1


@pytest.mark.parametrize("reason", ["unknown", "inactive", "staff"])
async def test_the_challenge_is_false_for_every_reason_alike(
        db: AsyncSession, ids: Fixtures, reason: str) -> None:
    """Section 4's always-202. The caller cannot tell these apart, so a different
    response for an unknown number cannot become a "is this dealer registered"
    oracle."""
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    if reason == "inactive":
        await make_partner_user(db, ids, mobile=mobile, is_active=False)
    elif reason == "staff":
        await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in", mobile=mobile)

    assert await _issue_otp(db, mobile) is False
    written = await db.execute(text(
        "SELECT count(*) FROM notification_outbox WHERE recipient = :m"), {"m": mobile})
    assert written.scalar_one() == 0


async def test_the_daily_cap_holds(db: AsyncSession, ids: Fixtures) -> None:
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    await make_partner_user(db, ids, mobile=mobile)
    for _ in range(10):
        assert await _issue_otp(db, mobile) is True
    assert await _issue_otp(db, mobile) is False


async def test_a_successful_verify_resets_the_cap(db: AsyncSession,
                                                  ids: Fixtures) -> None:
    """Section 7 states this as a mechanism. Rev 4 claimed the reset without ever
    writing a success row for it to key on."""
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    await make_partner_user(db, ids, mobile=mobile)
    for _ in range(10):
        await _issue_otp(db, mobile)
    assert await _issue_otp(db, mobile) is False

    await _attempt(db, mobile, succeeded=True, kind="otp")
    assert await _issue_otp(db, mobile) is True


async def test_a_stale_success_does_not_reopen_the_cap(db: AsyncSession,
                                                       ids: Fixtures) -> None:
    """greatest(), for the same reason as the lockout bound: a success older than
    the window must not widen it."""
    mobile = "9199" + f"{uuid.uuid4().int % 10**8:08d}"
    await make_partner_user(db, ids, mobile=mobile)
    await _attempt(db, mobile, succeeded=True, kind="otp", ago=timedelta(hours=30))
    for _ in range(10):
        await _attempt(db, mobile, succeeded=True, kind="otp_issue", ago=timedelta(hours=2))
    assert await _issue_otp(db, mobile) is False


# ── the RBAC helpers ─────────────────────────────────────────────────────────

async def _as_user(db: AsyncSession, user_id: str | None) -> None:
    """Transaction-local, always. A plain SET leaks to the next request on this
    pooled connection - the failure this whole architecture exists to prevent."""
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id) if user_id else ""})


async def test_the_helpers_resolve_the_claim(db: AsyncSession, ids: Fixtures) -> None:
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'org_subtree'), (:r, 'leads', 'create', 'org_subtree')"),
        {"r": ids.staff_role_id})
    await _as_user(db, uid)

    got = (await db.execute(text(
        "SELECT app_current_user_id() = CAST(:u AS uuid) AS me, "
        "       app_current_org_unit() = CAST(:o AS uuid) AS org, "
        "       app_current_role() = CAST(:r AS uuid) AS role, "
        "       app_has_permission('leads', 'view') AS can_view, "
        "       app_has_permission('leads', 'delete') AS can_delete, "
        "       app_scope('leads') AS scope"),
        {"u": uid, "o": ids.org_unit_id, "r": ids.staff_role_id})).mappings().one()
    assert got["me"] and got["org"] and got["role"]
    assert got["can_view"] is True and got["can_delete"] is False
    assert got["scope"] == "org_subtree"


async def test_no_claim_resolves_to_nothing(db: AsyncSession) -> None:
    """The pre-auth case. Every helper must return NULL or false rather than
    matching a row, because get_db_anon sets no claim at all."""
    await _as_user(db, None)
    got = (await db.execute(text(
        "SELECT app_current_user_id() IS NULL AS a, app_current_org_unit() IS NULL AS b, "
        "app_current_role() IS NULL AS c, app_scope('leads') IS NULL AS d, "
        "app_has_permission('leads', 'view') AS e"))).mappings().one()
    assert got["a"] and got["b"] and got["c"] and got["d"]
    assert got["e"] is False


async def test_a_consumer_resolves_to_no_permission_on_every_seeded_module(
        db: AsyncSession, ids: Fixtures) -> None:
    """EC-11, enumerated from the seed rather than hard-coded to a count - the
    pattern ISS-031 says to follow, since the matrix is 20 modules and not 18."""
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'global'), (:r, 'orders', 'view', 'global')"),
        {"r": ids.staff_role_id})
    consumer = (await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, customer_id) "
        "VALUES ('consumer', :m, 'Ramesh', :c) RETURNING id"),
        {"m": "9199" + f"{uuid.uuid4().int % 10**8:08d}", "c": str(uuid.uuid4())})).scalar_one()
    await _as_user(db, consumer)

    modules = (await db.execute(text(
        "SELECT DISTINCT module FROM role_permission"))).scalars().all()
    assert modules, "nothing seeded, so this test would pass vacuously"
    for module in modules:
        allowed = await db.execute(text(
            "SELECT app_has_permission(:m, 'view'), app_scope(:m) IS NULL"),
            {"m": module})
        can, no_scope = allowed.one()
        assert can is False and no_scope is True, module


async def test_app_scope_reads_the_view_row(db: AsyncSession, ids: Fixtures) -> None:
    """RBAC.md section 6: create, edit, approve and delete inherit the view scope
    but check their own permission."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'own'), (:r, 'leads', 'create', 'own')"),
        {"r": ids.staff_role_id})
    await _as_user(db, uid)
    scope = await db.execute(text("SELECT app_scope('leads')"))
    assert scope.scalar_one() == "own"


# ── the seed assertion, which is EC-4 ────────────────────────────────────────

async def test_the_invariant_passes_on_a_well_formed_matrix(db: AsyncSession,
                                                            ids: Fixtures) -> None:
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'own'), (:r, 'leads', 'create', 'own')"),
        {"r": ids.staff_role_id})
    await db.execute(text("SELECT assert_role_permission_invariants()"))


async def test_a_mutation_without_a_view_row_is_caught(db: AsyncSession,
                                                       ids: Fixtures) -> None:
    """app_scope() would resolve NULL, and every UPDATE would filter to zero rows.
    Zero rows affected is not an error, so a job runs successfully forever while
    doing nothing (ISS-029)."""
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (:r, 'leads', 'edit', 'own')"), {"r": ids.staff_role_id})
    with pytest.raises(DBAPIError, match="without a view row"):
        await db.execute(text("SELECT assert_role_permission_invariants()"))


async def test_mixed_scopes_for_one_module_are_caught(db: AsyncSession,
                                                      ids: Fixtures) -> None:
    """A create row carrying a different scope silently claims something it does
    not grant, because app_scope() only ever reads the view row."""
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'view', 'own'), (:r, 'leads', 'create', 'global')"),
        {"r": ids.staff_role_id})
    with pytest.raises(DBAPIError, match="mixed scopes"):
        await db.execute(text("SELECT assert_role_permission_invariants()"))


async def test_every_offender_is_named_not_just_the_first(db: AsyncSession,
                                                          ids: Fixtures) -> None:
    """plpgsql SELECT INTO keeps the first row and discards the rest, so the
    grouped query is wrapped. Unwrapped, the migration fails while naming one
    arbitrary offender out of however many exist."""
    await db.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'leads', 'edit', 'own'), (:r, 'orders', 'edit', 'own')"),
        {"r": ids.staff_role_id})
    with pytest.raises(DBAPIError) as exc:
        await db.execute(text("SELECT assert_role_permission_invariants()"))
    assert "leads" in str(exc.value) and "orders" in str(exc.value)


# ── audit ────────────────────────────────────────────────────────────────────

async def test_no_audit_row_ever_contains_a_password_hash(db: AsyncSession,
                                                          ids: Fixtures) -> None:
    """The generic trigger writes the whole row, so attached unmodified it would
    copy every Argon2 hash into a table with no delete path and a wider read
    audience than app_user itself."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in",
                           password_hash="$argon2id$v=19$m=65536,t=3,p=4$SECRET")
    await db.execute(text("UPDATE app_user SET full_name = 'Asha P' WHERE id = :i"),
                     {"i": uid})
    leaked = await db.execute(text(
        "SELECT count(*) FROM audit_log WHERE table_name = 'app_user' "
        "AND (old_jsonb ? 'password_hash' OR new_jsonb ? 'password_hash')"))
    assert leaked.scalar_one() == 0

    logged = await db.execute(text(
        "SELECT count(*) FROM audit_log WHERE table_name = 'app_user' AND row_id = :i"),
        {"i": uid})
    assert logged.scalar_one() == 2, "insert and update should both be audited"


async def test_a_sign_in_writes_no_audit_row(db: AsyncSession, ids: Fixtures) -> None:
    """last_login_at moves on every sign-in. Audited, that is a few thousand rows a
    day saying nothing activity_event does not already say, burying the changes a
    human opens audit_log to find."""
    uid = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    before = (await db.execute(text(
        "SELECT count(*) FROM audit_log WHERE row_id = :i"), {"i": uid})).scalar_one()
    await _session(db, uid, door="password")
    after = (await db.execute(text(
        "SELECT count(*) FROM audit_log WHERE row_id = :i"), {"i": uid})).scalar_one()
    assert after == before


async def test_the_audit_row_names_its_actor(db: AsyncSession, ids: Fixtures) -> None:
    actor = await make_staff(db, ids, email=ids.unique("admin") + "@polysil.in")
    await _as_user(db, actor)
    target = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    named = await db.execute(text(
        "SELECT actor_id FROM audit_log WHERE row_id = :i AND action = 'INSERT'"),
        {"i": target})
    assert str(named.scalar_one()) == str(actor)


@pytest.mark.parametrize(
    "table", ["session", "login_attempt", "idempotency_record",
              "notification_outbox", "activity_event"])
async def test_infrastructure_tables_are_not_audited(db: AsyncSession,
                                                     table: str) -> None:
    """Append-and-expire. Auditing them duplicates their own content at volume."""
    triggers = (await db.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = CAST(:t AS regclass) "
        "AND NOT tgisinternal"), {"t": table})).scalars().all()
    assert triggers == [], f"{table} carries {triggers}"


# ── idempotency ──────────────────────────────────────────────────────────────

async def test_two_anonymous_callers_with_one_key_collide(db: AsyncSession) -> None:
    """NULLS NOT DISTINCT. user_id is nullable because intake_submit is public, and
    under the default two anonymous callers with the same key never conflict - so
    the exactly-once guarantee every module inherits does not exist."""
    key = uuid.uuid4().hex
    await db.execute(text(
        "INSERT INTO idempotency_record (key, route, request_hash, state) "
        "VALUES (:k, '/intake', 'h', 'in_progress')"), {"k": key})
    with pytest.raises(IntegrityError, match="uq_idempotency"):
        await db.execute(text(
            "INSERT INTO idempotency_record (key, route, request_hash, state) "
            "VALUES (:k, '/intake', 'h', 'in_progress')"), {"k": key})


async def test_a_done_record_must_carry_a_response(db: AsyncSession) -> None:
    """A 'done' record with nothing to replay returns an empty response to the
    retry, which is worse than executing twice would have been."""
    with pytest.raises(IntegrityError, match="ck_idempotency_done"):
        await db.execute(text(
            "INSERT INTO idempotency_record (key, route, request_hash, state) "
            "VALUES (:k, '/leads', 'h', 'done')"), {"k": uuid.uuid4().hex})


# ── the deferred foreign keys ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "table", ["territory", "org_unit", "role", "role_permission",
              "app_user", "user_territory"])
@pytest.mark.parametrize("col", ["created_by", "updated_by"])
async def test_the_deferred_foreign_keys_landed(db: AsyncSession, table: str,
                                                col: str) -> None:
    """002's two could not carry them, and `role` is a genuine cycle: app_user.role_id
    points at role, and section 1.2 puts created_by references app_user on role."""
    found = await db.execute(text(
        "SELECT count(*) FROM pg_constraint WHERE conname = :n "
        "AND conrelid = CAST(:t AS regclass) AND contype = 'f'"),
        {"n": f"fk_{table}_{col}", "t": table})
    assert found.scalar_one() == 1


async def test_partner_id_gained_its_foreign_key_in_004(db: AsyncSession) -> None:
    """Schema-Corrections.md 5a.6. Bare in 003 because channel_partner did not exist;
    a real constraint from 004 on, named the way 003 names the deferred ones."""
    found = await db.execute(text(
        "SELECT count(*) FROM pg_constraint WHERE conname = 'fk_app_user_partner_id' "
        "AND conrelid = 'app_user'::regclass AND contype = 'f'"))
    assert found.scalar_one() == 1


@pytest.mark.parametrize("col", ["customer_id"])
async def test_the_forward_references_stay_bare(db: AsyncSession, col: str) -> None:
    """customer is 005. A constraint here would make 003 unrunnable on an empty
    database. partner_id left this list when 004 landed."""
    fks = (await db.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'app_user'::regclass "
        "AND contype = 'f' AND :c = ANY (SELECT attname FROM pg_attribute "
        "  WHERE attrelid = conrelid AND attnum = ANY (conkey))"),
        {"c": col})).scalars().all()
    assert fks == []
