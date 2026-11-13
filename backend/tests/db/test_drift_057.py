# ruff: noqa: E501  (embedded SQL)

"""The live `rating_record` is migration 057's text (FS-060): built from 051's by
anchored replacements, so a later edit to either shows here. And the grants: the
portal's two entry points to app_role, the document helper to nobody."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.migration_grants import _load

pytestmark = pytest.mark.db


def _body(stmt: str) -> str:
    tag = "$fn$" if "$fn$" in stmt else "$function$"
    return " ".join(stmt[stmt.index(tag) + len(tag):stmt.rindex(tag)].split())


async def test_the_live_rating_record_is_057s(db: AsyncSession) -> None:
    m = _load("057_portal_ratings")
    assert m is not None
    live = (await db.execute(text(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'rating_record'"))).scalars().all()
    assert len(live) == 1, "one signature only"
    assert _body(live[0]) == _body(m.rating_record_057())


@pytest.mark.parametrize(("sig", "app_role"), [
    ("portal_rate(text, text, text, integer, text)", True),
    ("portal_ratings(uuid)", True),
    ("portal_rating_docs()", False),
    ("rating_record(text, uuid, uuid, uuid, integer, text)", True),
])
async def test_grants(db: AsyncSession, sig: str, app_role: bool) -> None:
    assert (await db.execute(text("SELECT has_function_privilege('app_role', :s, 'EXECUTE')"),
                             {"s": sig})).scalar_one() is app_role
    assert (await db.execute(text("SELECT has_function_privilege('public', :s, 'EXECUTE')"),
                             {"s": sig})).scalar_one() is False


async def test_entered_via_is_required_and_checked(db: AsyncSession) -> None:
    row = (await db.execute(text(
        "SELECT is_nullable, (SELECT count(*) FROM pg_constraint WHERE conname = 'ck_rating_entered_via') AS ck "
        "FROM information_schema.columns WHERE table_name = 'rating' AND column_name = 'entered_via'"))).one()
    assert row.is_nullable == "NO" and row.ck == 1
