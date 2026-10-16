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
from tests.db import test_migration_013 as m13
from tests.db import test_migration_018 as m18
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
    dealer that IS on documents: no tier and no yes, so it cannot be used to probe.
    Built here, so it runs on an empty database too (PR 11 review: it skipped on CI)."""
    w = await m18._world(db)
    await db.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, "
        "mobile, territory_id, owner_user_id, owner_org_unit_id, assigned_partner_id, created_by) "
        "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'Farmer', :mob, CAST(:t AS uuid), "
        "CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:p AS uuid), CAST(:o AS uuid))"),
        {"no": f"M28-{uuid.uuid4().hex[:10]}", "mob": "+9196" + f"{uuid.uuid4().int % 10**8:08d}",
         "t": w.district, "o": w.officer, "ou": w.a, "p": w.partner})
    probe = ("SELECT partner_on_visible_document(CAST(:p AS uuid)) AS seen, "
             "document_partner_tier(CAST(:p AS uuid)) AS tier")
    await m13._as(db, w.officer)                 # the positive control: the lead's own officer
    assert (await db.execute(text(probe), {"p": w.partner})).one().seen is True
    await m13._as_owner(db)
    await m13._as(db, w.officer_b)               # a real officer in the other office
    row = (await db.execute(text(probe), {"p": w.partner})).one()
    await m13._as_owner(db)
    assert row.seen is False and row.tier is None
