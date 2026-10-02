"""Migration 028 (FS-020): the dealer area rule and the dealer on a document.

The behaviour is driven end to end in tests/api/test_dealer_area_access.py. These
pin the database side: the two functions are not PUBLIC and are pinned, the pasted
partners guard inside minutes_visible() and channel_partner_user_counts() is the
generator's, and the definer answers nothing for a dealer on no visible document.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.policy_sql import guard_sql
from tests.db.migration_grants import _load

pytestmark = [pytest.mark.db]

SIGNATURES = ("partner_on_visible_document(uuid)", "document_partner_tier(uuid)")


def _norm(s: str) -> str:
    return " ".join(s.split())


async def test_the_functions_are_pinned_definers_not_callable_by_public(db: AsyncSession) -> None:
    for sig in SIGNATURES:
        row = (await db.execute(text(
            "SELECT p.prosecdef, p.proconfig, "
            "has_function_privilege('public', CAST(:s AS regprocedure), 'EXECUTE') AS pub, "
            "has_function_privilege('app_role', CAST(:s AS regprocedure), 'EXECUTE') AS app "
            "FROM pg_proc p WHERE p.oid = CAST(:s AS regprocedure)"), {"s": sig})).one()
        assert row.prosecdef, sig
        assert "search_path=public, pg_temp" in (row.proconfig or []), sig
        assert row.pub is False and row.app is True, sig


async def test_the_pasted_partners_guard_is_the_generators(db: AsyncSession) -> None:
    m = _load("028_dealer_area_access")
    assert m is not None
    guard = _norm(guard_sql(SPECS["partners"]))
    assert _norm(m.PARTNERS_GUARD) == guard
    for fn in ("minutes_visible(uuid)", "channel_partner_user_counts(uuid[])",
               "task_link_visible_as(uuid, uuid, uuid, uuid)"):
        body = (await db.execute(text("SELECT pg_get_functiondef(CAST(:f AS regprocedure))"),
                                 {"f": fn})).scalar_one()
        assert guard in _norm(body), fn


async def test_no_body_or_policy_keeps_the_exact_territory_partner_rule(db: AsyncSession) -> None:
    """Code review F-1: a third function pasted the guard and was missed. Any stored
    copy of the old exact match, in a function or a policy, fails here."""
    # compared without whitespace: pg_policies holds a re-formatted text
    old = "%territory_idIN(SELECTou.territory_idFROMorg_unitou%"
    bare = "regexp_replace(coalesce({}, ''), '[[:space:]]+', '', 'g') LIKE :o"
    fns = (await db.execute(text(
        "SELECT proname FROM pg_proc WHERE " + bare.format("prosrc")), {"o": old})).scalars().all()
    pols = (await db.execute(text(
        "SELECT tablename || '.' || policyname FROM pg_policies WHERE "
        + bare.format("qual") + " OR " + bare.format("with_check")), {"o": old})).scalars().all()
    assert fns == [] and pols == [], (fns, pols)


async def test_a_dealer_on_no_visible_document_gets_no_tier(db: AsyncSession) -> None:
    """As a staff caller who sees no documents, the definer says nothing about a
    dealer that IS on documents: no tier and no yes, so it cannot be used to probe."""
    dealer = (await db.execute(text(
        "SELECT l.assigned_partner_id FROM lead l "
        "JOIN channel_partner cp ON cp.id = l.assigned_partner_id "
        "WHERE cp.deleted_at IS NULL LIMIT 1"))).scalar_one_or_none()
    if dealer is None:
        pytest.skip("no dealer on this database")
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(uuid.uuid4())})
    await db.execute(text("SET LOCAL ROLE app_role"))
    row = (await db.execute(text(
        "SELECT partner_on_visible_document(CAST(:p AS uuid)) AS seen, "
        "document_partner_tier(CAST(:p AS uuid)) AS tier"), {"p": str(dealer)})).one()
    assert row.seen is False and row.tier is None
