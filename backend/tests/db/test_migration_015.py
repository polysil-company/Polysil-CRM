"""Migration 015 (FS-003a): the public lead capture's database half, executed as
the roles that call it."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role

pytestmark = [pytest.mark.db, pytest.mark.rls]

ANON = ["lead_intake_issue(text, inet, text, text, integer, integer, integer)",
        "lead_intake_consume(text, text)", "lead_qr_public(text)", "lead_public_form()",
        "lead_public_territories(uuid)"]
ROLE = ["lead_intake_record(uuid, uuid)", "lead_intake_purge(timestamptz)"]
INTAKE = get_settings().intake_user_id


async def _refused(db: AsyncSession, sql: str, params: dict[str, object] | None = None) -> str:
    await db.execute(text("SAVEPOINT sp"))
    try:
        await db.execute(text(sql), params or {})
    except DBAPIError as exc:
        await db.execute(text("ROLLBACK TO SAVEPOINT sp"))
        return str(getattr(exc.orig, "sqlstate", "") or "")
    await db.execute(text("ROLLBACK TO SAVEPOINT sp"))
    raise AssertionError(f"accepted: {sql[:80]}")


@pytest.mark.parametrize("sig", ANON + ROLE)
async def test_every_function_is_pinned_and_not_public(db: AsyncSession, sig: str) -> None:
    row = (await db.execute(text(
        "SELECT p.prosecdef, p.proconfig, "
        "has_function_privilege('app_anon', CAST(:s AS regprocedure), 'EXECUTE') AS anon, "
        "has_function_privilege('app_role', CAST(:s AS regprocedure), 'EXECUTE') AS app, "
        "EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0) AS public "
        "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
    assert row.prosecdef and row.proconfig == ["search_path=public, pg_temp"] and not row.public
    if sig in ANON:
        assert row.anon and not row.app, "only the pre-auth role consumes a code (plan review B-1)"
    else:
        assert row.app and not row.anon


async def test_neither_role_reads_a_challenge_or_the_anon_role_a_lead(db: AsyncSession) -> None:
    await enter_role(db, "app_anon")
    assert await _refused(db, "SELECT count(*) FROM lead_intake_challenge") == "42501"
    assert await _refused(db, "SELECT count(*) FROM lead") == "42501"
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": INTAKE})
    await enter_role(db, "app_role")
    assert await _refused(db, "SELECT count(*) FROM lead_intake_challenge") == "42501"


async def test_the_intake_principal_can_never_sign_in_change_role_or_be_retired(db: AsyncSession) -> None:
    row = (await db.execute(text(
        "SELECT u.password_hash, u.mobile, r.code FROM app_user u JOIN role r ON r.id = u.role_id "
        "WHERE u.id = CAST(:u AS uuid)"), {"u": INTAKE})).one()
    assert (row.password_hash, row.mobile, row.code) == (None, None, "intake")
    for sql in ("UPDATE app_user SET password_hash = 'x' WHERE id = CAST(:u AS uuid)",
                "UPDATE app_user SET mobile = '919812345678' WHERE id = CAST(:u AS uuid)",
                "UPDATE app_user SET role_id = (SELECT id FROM role WHERE code = 'admin_sales') "
                "WHERE id = CAST(:u AS uuid)",
                # code review F-3: deleted, switched off or moved, the public form
                # would keep creating leads under a dead actor
                "UPDATE app_user SET deleted_at = now() WHERE id = CAST(:u AS uuid)",
                "UPDATE app_user SET is_active = false WHERE id = CAST(:u AS uuid)",
                "UPDATE app_user SET org_unit_id = (SELECT id FROM org_unit WHERE id <> "
                "(SELECT org_unit_id FROM app_user WHERE id = CAST(:u AS uuid)) LIMIT 1) "
                "WHERE id = CAST(:u AS uuid)"):
        assert await _refused(db, sql, {"u": INTAKE}) == "42501"
    perms = (await db.execute(text(
        "SELECT p.module, p.action::text, p.scope::text FROM role_permission p JOIN role r "
        "ON r.id = p.role_id WHERE r.code = 'intake' ORDER BY 1, 2"))).all()
    assert {tuple(p) for p in perms} == {("leads", "view", "global"), ("leads", "create", "global"),
                                         ("leads", "edit", "global"), ("partners", "view", "global")}


async def test_only_the_intake_account_records_and_only_the_system_purges(db: AsyncSession) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": get_settings().system_user_id})
    await enter_role(db, "app_role")
    assert await _refused(db, "SELECT lead_intake_record(gen_random_uuid(), gen_random_uuid())") == "42501"
    await db.execute(text("SELECT lead_intake_purge(now() - interval '30 days')"))
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": INTAKE})
    await enter_role(db, "app_role")
    assert await _refused(db, "SELECT lead_intake_purge(now())") == "42501"


async def test_the_purge_deletes_old_challenges(db: AsyncSession) -> None:
    await db.execute(text(
        "INSERT INTO lead_intake_challenge (mobile, code_hash, expires_at, created_at) VALUES "
        "('+919800000001', 'h', now(), now() - interval '40 days'), "
        "('+919800000001', 'h', now(), now())"))
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": get_settings().system_user_id})
    await enter_role(db, "app_role")
    gone = (await db.execute(text("SELECT lead_intake_purge(now() - interval '30 days')"))).scalar_one()
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    left = (await db.execute(text(
        "SELECT count(*) FROM lead_intake_challenge WHERE mobile = '+919800000001'"))).scalar_one()
    assert gone >= 1 and left == 1


async def test_wrong_guesses_against_a_used_code_count_and_burn_it(db: AsyncSession) -> None:
    """Code review F-5: a used code answers its inquiry number for ten minutes, so
    guesses against it are counted and burn it at five, like an unused code's."""
    mobile = "+919800000002"
    await db.execute(text(
        "INSERT INTO lead_intake_challenge (mobile, code_hash, expires_at, state) "
        "VALUES (:m, 'right', now() + interval '10 minutes', 'consumed')"), {"m": mobile})
    await enter_role(db, "app_anon")
    for _ in range(5):
        outcome = (await db.execute(text("SELECT outcome FROM lead_intake_consume(:m, 'wrong')"),
                                    {"m": mobile})).scalar_one()
        assert outcome == "invalid"
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    state, attempts = (await db.execute(text(
        "SELECT state, attempts FROM lead_intake_challenge WHERE mobile = :m"), {"m": mobile})).one()
    assert (state, attempts) == ("burned", 5)


async def test_the_intake_account_is_never_a_lead_assignee(db: AsyncSession) -> None:
    """Its role holds leads edit, which is 007's assignee rule: a global caller saw
    "Website and QR" in the owner picker and could hand it leads (ISS-075's shape)."""
    admin = (await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "SELECT 'staff', 'm015_admin_' || substr(md5(random()::text), 1, 8) || '@m015.in', 'x', "
        "'Admin', r.id, u.org_unit_id FROM role r, app_user u "
        "WHERE r.code = 'admin_sales' AND u.id = CAST(:i AS uuid) RETURNING id"),
        {"i": INTAKE})).scalar_one()
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(admin)})
    await enter_role(db, "app_role")
    assert (await db.execute(text("SELECT authz_user_assignable('leads', CAST(:i AS uuid))"),
                             {"i": INTAKE})).scalar_one() is False
    listed = {str(r[0]) for r in (await db.execute(text("SELECT id FROM staff_directory('leads')"))).all()}
    assert INTAKE not in listed and str(admin) in listed, "the directory still lists real people"


async def test_two_mobiles_from_one_address_cannot_both_pass_its_budget(sessions) -> None:  # type: ignore[no-untyped-def]
    """Cross-vendor review: the mobile's lock alone let two numbers pass the shared IP
    and hourly counts before either committed. The second must wait, then see the
    first's row."""
    import asyncio
    import random
    import uuid as _uuid

    ip = f"198.51.100.{random.randint(1, 254)}"
    m1, m2 = ("+9197" + f"{_uuid.uuid4().int % 10**8:08d}" for _ in range(2))
    issue = ("SELECT lead_intake_issue(:m, CAST(:ip AS inet), '123456', 'h', 600, 1, 1000)")
    a, b = sessions(), sessions()
    try:
        await enter_role(a, "app_anon")
        assert (await a.execute(text(issue), {"m": m1, "ip": ip})).scalar_one() == "issued"
        await enter_role(b, "app_anon")
        second = asyncio.create_task(b.execute(text(issue), {"m": m2, "ip": ip}))
        await asyncio.sleep(1.5)
        assert not second.done(), "the second request did not wait for the first"
        await a.commit()
        assert (await second).scalar_one() == "rate_limited"
        await b.rollback()
    finally:
        await a.rollback()
        await b.rollback()
        clean = sessions()
        await clean.execute(text("DELETE FROM notification_outbox WHERE template_key = 'lead.verify' "
                                 "AND recipient IN (:m1, :m2)"), {"m1": m1, "m2": m2})
        await clean.execute(text("DELETE FROM lead_intake_challenge WHERE mobile IN (:m1, :m2)"),
                            {"m1": m1, "m2": m2})
        await clean.commit()
        for s in (a, b, clean):
            await s.close()
