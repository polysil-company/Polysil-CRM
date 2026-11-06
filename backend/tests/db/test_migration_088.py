"""088 (FS-086): every stored copy of the partners area takes the assigned districts.

A copy that names the offices' territories without the user_territory arm is a
paste 088 missed (plan review C-4): its readers would see fewer dealers than
the policy shows."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz import policy_sql
from tests.db.migration_grants import _load

pytestmark = [pytest.mark.db]


def _squash(s: str) -> str:
    return "".join(s.split())


def test_the_pasted_texts_are_the_generators() -> None:
    m = _load("088_held_districts")
    assert m is not None
    assert m.OFFICE == policy_sql.OFFICE_TERRITORIES
    assert m.AREA == policy_sql.AREA_TERRITORIES


async def test_every_stored_copy_of_the_partners_area_takes_the_assigned_districts(
        db: AsyncSession) -> None:
    office = _squash("FROM org_unit ou WHERE ou.id IN")
    arm = _squash("FROM user_territory ut JOIN territory t ON t.id = ut.territory_id")
    functions = (await db.execute(text(
        "SELECT p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public'"))).all()
    policies = (await db.execute(text(
        "SELECT policyname, coalesce(qual, '') || ' ' || coalesce(with_check, '') FROM pg_policies "
        "WHERE schemaname = 'public'"))).all()
    # pg_policies re-formats; compare without whitespace or brackets
    def bare(s: str) -> str:
        return _squash(s).replace("(", "").replace(")", "")

    fn_copies = {name for name, src in functions if office in _squash(src) and "partners" in src}
    pol_copies = {name for name, body in policies if bare(office) in bare(body)
                  and "partners" in body}
    assert fn_copies == {"channel_partner_user_counts", "dealer_application_visible",
                         "minutes_visible", "order_area_partner_ids",
                         "partner_visible_to_caller", "task_link_visible_as"}, fn_copies
    assert pol_copies == {"channel_partner_sel_org_subtree", "channel_partner_ins",
                          "channel_partner_upd", "channel_partner_del",
                          "dealer_application_sel"}, pol_copies
    for name, src in functions:
        if name in fn_copies:
            assert arm in _squash(src), name
    for name, body in policies:
        if name in pol_copies:
            assert bare(arm) in bare(body), name


async def test_the_automatic_owner_reads_the_assigned_districts(db: AsyncSession) -> None:
    src = (await db.execute(text(
        "SELECT prosrc FROM pg_proc WHERE proname = 'lead_auto_owner'"))).scalar_one()
    assert "user_territory" in src and "t.level <> 'state'" in src
