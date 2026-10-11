"""Migration 056: the two functions changed by the 10 Oct walk, run as app_role.

- `partner_ids_by_user_name()` finds a partner by its user's name (walk F-9), and
  the picker's join keeps channel_partner's own policies in force.
- `lead_auto_owner()` gives a district-only lead to an officer inside the district
  (walk F-6), and still prefers an officer whose territory covers the lead.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures, make_partner_user, make_staff
from tests.db.test_functions_006 import _as, _grant, _lead

pytestmark = [pytest.mark.db, pytest.mark.rls]


def _mobile() -> str:
    return "9199" + f"{uuid.uuid4().int % 10**8:08d}"


async def test_both_functions_are_granted_to_app_role_only(db: AsyncSession) -> None:
    for sig in ("partner_ids_by_user_name(text)", "lead_auto_owner(uuid)"):
        assert (await db.execute(text(
            "SELECT has_function_privilege('app_role', :s, 'EXECUTE')"), {"s": sig})).scalar_one()
        assert not (await db.execute(text(
            "SELECT has_function_privilege('public', :s, 'EXECUTE')"), {"s": sig})).scalar_one()


async def test_a_partner_is_found_by_its_users_name(db: AsyncSession, ids: Fixtures) -> None:
    """make_partner_user names the dealer's user Bhavesh Shah; the dealer is
    'Demo Dealer' with no contact name. A deleted user no longer matches."""
    user = await make_partner_user(db, ids, mobile=_mobile())
    found = {str(r) for r in (await db.execute(text(
        "SELECT partner_ids_by_user_name('%bhavesh%')"))).scalars()}
    assert str(ids.dealer_id) in found
    assert str(ids.distributor_id) not in found
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :u"), {"u": user})
    found = {str(r) for r in (await db.execute(text(
        "SELECT partner_ids_by_user_name('%bhavesh%')"))).scalars()}
    assert str(ids.dealer_id) not in found


async def test_the_name_match_never_shows_a_partner_outside_the_callers_scope(
        db: AsyncSession, ids: Fixtures) -> None:
    """A district manager whose territory does not hold the dealer: the definer
    finds the dealer by its user's name (the manager cannot read partner users),
    and the picker's join to channel_partner still returns nothing (review F-2)."""
    await make_partner_user(db, ids, mobile=_mobile())
    elsewhere = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": ids.unique("elsewhere")})).scalar_one()
    unit = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": ids.unique("elsewhere-dm"), "t": elsewhere})).scalar_one()
    await _grant(db, ids.staff_role_id, "partners", ["view"], "territory")
    me = await make_staff(db, ids, email=ids.unique("dm") + "@polysil.in")
    await db.execute(text("UPDATE app_user SET org_unit_id = :o WHERE id = :u"),
                     {"o": unit, "u": me})
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
                     {"u": me, "t": elsewhere})
    await _as(db, me)
    found = {str(r) for r in (await db.execute(text(
        "SELECT partner_ids_by_user_name('%bhavesh%')"))).scalars()}
    assert str(ids.dealer_id) in found
    rows = (await db.execute(text(
        "SELECT cp.id FROM channel_partner cp "
        "WHERE cp.id IN (SELECT partner_ids_by_user_name('%bhavesh%'))"))).all()
    assert rows == []


async def _taluka(db: AsyncSession, ids: Fixtures, name: str) -> Any:
    return (await db.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('taluka', :n, CAST(:p AS uuid)) "
        "RETURNING id"), {"n": ids.unique(name), "p": ids.territory_id})).scalar_one()


async def _officer_in(db: AsyncSession, ids: Fixtures, territory: Any, role: Any,
                      name: str) -> str:
    unit = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id, parent_id) "
        "VALUES (:n, 1, :t, :p) RETURNING id"),
        {"n": ids.unique(name), "t": territory, "p": ids.org_unit_id})).scalar_one()
    return str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', 'Officer', :r, :o) RETURNING id"),
        {"e": ids.unique(name) + "@polysil.in", "r": role, "o": unit})).scalar_one())


async def _officer_role(db: AsyncSession, ids: Fixtures) -> Any:
    role = (await db.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'Field Officer', 1) RETURNING id"),
        {"c": ids.unique("field_officer")})).scalar_one()
    await _grant(db, role, "leads", ["view", "edit"], "own")
    return role


async def test_a_district_lead_goes_to_the_least_loaded_officer_inside_the_district(
        db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.portal_role_id, "leads", ["create"], "partner_subtree")
    role = await _officer_role(db, ids)
    busy = await _officer_in(db, ids, await _taluka(db, ids, "gondal"), role, "busy")
    free = await _officer_in(db, ids, await _taluka(db, ids, "jetpur"), role, "free")
    await _lead(db, ids, owner_user_id=busy)
    await _as(db, await make_partner_user(db, ids, mobile=_mobile()))
    picked = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                               {"t": ids.territory_id})).scalar_one()
    assert str(picked) == free


async def test_an_officer_covering_the_lead_beats_one_inside_it(
        db: AsyncSession, ids: Fixtures) -> None:
    """An officer one level above the lead covers it, even when an officer in a
    taluka below is as near (depth 1) and has fewer open leads. Only the
    covering-first term of the ORDER BY decides this (review F-1)."""
    await _grant(db, ids.portal_role_id, "leads", ["create"], "partner_subtree")
    role = await _officer_role(db, ids)
    state = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('state', :n) RETURNING id"),
        {"n": ids.unique("state")})).scalar_one()
    await db.execute(text("UPDATE territory SET parent_id = :s WHERE id = :d"),
                     {"s": state, "d": ids.territory_id})
    covering = await _officer_in(db, ids, state, role, "cover")
    await _lead(db, ids, owner_user_id=covering)
    await _officer_in(db, ids, await _taluka(db, ids, "dhoraji"), role, "inside")
    await _as(db, await make_partner_user(db, ids, mobile=_mobile()))
    picked = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                               {"t": ids.territory_id})).scalar_one()
    assert str(picked) == covering


async def test_a_taluka_lead_never_goes_to_an_officer_of_a_sibling_taluka(
        db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.portal_role_id, "leads", ["create"], "partner_subtree")
    role = await _officer_role(db, ids)
    lead_taluka = await _taluka(db, ids, "upleta")
    await _officer_in(db, ids, await _taluka(db, ids, "kotda"), role, "sibling")
    await _as(db, await make_partner_user(db, ids, mobile=_mobile()))
    picked = (await db.execute(text("SELECT lead_auto_owner(:t)"),
                               {"t": lead_taluka})).scalar_one()
    assert picked is None


async def test_rounding_the_stored_scores_also_sets_the_band(
        db: AsyncSession, ids: Fixtures) -> None:
    """Review F-4: a closed lead is never scored again, so 056 sets its band from the
    rounded score now. 39.60 cold rounds to 40, which is warm at the stock thresholds."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("m056_test", Path(__file__).resolve().parents[2]
                                                  / "api/db/migrations/versions/056_walk_fixes.py")
    assert spec is not None and spec.loader is not None
    m056 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m056)
    warm = (await db.execute(text(
        "SELECT value FROM lead_score_rule WHERE key = 'threshold_warm'"))).scalar_one()
    lead = await _lead(db, ids, stage="won")
    await db.execute(text("UPDATE lead SET score = :s - 0.4, priority = 'cold' WHERE id = :i"),
                     {"s": warm, "i": lead})
    await db.execute(text(m056.ROUND_SCORES))
    row = (await db.execute(text("SELECT score, priority::text AS p FROM lead WHERE id = :i"),
                            {"i": lead})).one()
    assert row.score == warm and row.p == "warm"
