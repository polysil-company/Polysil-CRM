"""Migration 043 (FS-038): the webhook capture's database half, executed as the
roles that call it."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from tests.db.test_migration_015 import _refused

pytestmark = [pytest.mark.db, pytest.mark.rls]

ANON = ["whatsapp_webhook_record(text, text, inet, jsonb, bytea, text, jsonb)"]
ROLE = ["whatsapp_webhook_purge(timestamptz)"]
RECORD = ("SELECT whatsapp_webhook_record('inbound', 'POST', NULL, '[]'::jsonb, "
          "'\\x7b7d'::bytea, '{}', '{}'::jsonb)")


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
        assert row.anon and not row.app, "only the pre-auth role records a call"
    else:
        assert row.app and not row.anon


async def test_the_anon_role_records_and_neither_role_reads_or_writes_the_table(db: AsyncSession) -> None:
    await enter_role(db, "app_anon")
    await db.execute(text(RECORD))
    assert await _refused(db, "SELECT count(*) FROM whatsapp_webhook_event") == "42501"
    assert await _refused(db, "INSERT INTO whatsapp_webhook_event (kind, method, headers, body_raw, body_text) "
                              "VALUES ('inbound', 'POST', '[]', '', '')") == "42501"
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": get_settings().system_user_id})
    await enter_role(db, "app_role")
    assert await _refused(db, "SELECT count(*) FROM whatsapp_webhook_event") == "42501"


async def test_only_the_system_purges_and_only_rows_before_the_cut(db: AsyncSession) -> None:
    await db.execute(text(
        "INSERT INTO whatsapp_webhook_event (kind, method, headers, body_raw, body_text, received_at) VALUES "
        "('status', 'POST', '[]', 'old', 'fs038-old', now() - interval '40 days'), "
        "('status', 'POST', '[]', 'new', 'fs038-new', now())"))
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": get_settings().intake_user_id})
    await enter_role(db, "app_role")
    assert await _refused(db, "SELECT whatsapp_webhook_purge(now())") == "42501"
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": get_settings().system_user_id})
    await enter_role(db, "app_role")
    gone = (await db.execute(text("SELECT whatsapp_webhook_purge(now() - interval '30 days')"))).scalar_one()
    await db.execute(text("SELECT set_config('role', 'none', true)"))
    left = (await db.execute(text(
        "SELECT body_text FROM whatsapp_webhook_event WHERE body_text LIKE 'fs038-%'"))).scalars().all()
    assert gone >= 1 and left == ["fs038-new"]


async def test_a_body_over_64_kb_is_refused_by_the_table(db: AsyncSession) -> None:
    await enter_role(db, "app_anon")
    assert await _refused(db, "SELECT whatsapp_webhook_record('inbound', 'POST', NULL, '[]'::jsonb, "
                              "decode(repeat('00', 65537), 'hex'), '', NULL)") == "23514"
