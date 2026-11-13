"""Fixtures for the identity migration's tests.

Everything is built inside the caller's transaction and rolled back with it. The
`db` fixture in the parent conftest owns that boundary, so nothing here commits
and no test can see another's rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings


@dataclass
class Fixtures:
    """Ids for a minimal but complete identity graph."""

    territory_id: str
    org_unit_id: str
    staff_role_id: str
    portal_role_id: str
    distributor_id: str
    dealer_id: str
    unique: Callable[[str], str]


@pytest_asyncio.fixture
async def ids(db: AsyncSession) -> Fixtures:
    tag = uuid.uuid4().hex[:8]

    def unique(prefix: str) -> str:
        return f"{prefix}_{tag}"

    territory = (await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": unique("rajkot")})).scalar_one()
    org_unit = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) "
        "VALUES (:n, 2, :t) RETURNING id"),
        {"n": unique("rajkot-dm"), "t": territory})).scalar_one()
    staff_role = (await db.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'District Manager', 2) "
        "RETURNING id"), {"c": unique("district_manager")})).scalar_one()
    portal_role = (await db.execute(text(
        "INSERT INTO role (code, name, level, is_portal) "
        "VALUES (:c, 'Dealer', 2, true) RETURNING id"),
        {"c": unique("dealer")})).scalar_one()

    # Migration 004: a partner user must point at a channel_partner. One
    # distributor and one dealer under it is the smallest tree that exercises the
    # closure and the type-order trigger.
    distributor = (await db.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'Demo Distributor', :t, 'distributor') RETURNING id"),
        {"c": unique("DIST"), "t": territory})).scalar_one()
    dealer = (await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'dealer', :c, 'Demo Dealer', :t, 'dealer') RETURNING id"),
        {"p": distributor, "c": unique("DLR"), "t": territory})).scalar_one()

    return Fixtures(territory, org_unit, staff_role, portal_role,
                    distributor, dealer, unique)


async def make_staff(db: AsyncSession, ids: Fixtures, *, email: str,
                     password_hash: str | None = "argon2-placeholder",
                     mobile: str | None = None, is_active: bool = True) -> str:
    row = await db.execute(
        text("INSERT INTO app_user (user_type, email, mobile, password_hash, "
             "full_name, role_id, org_unit_id, is_active) "
             "VALUES ('staff', :e, :m, :p, 'Asha Patel', :r, :o, :a) RETURNING id"),
        {"e": email, "m": mobile, "p": password_hash,
         "r": ids.staff_role_id, "o": ids.org_unit_id, "a": is_active},
    )
    return row.scalar_one()


async def make_partner_user(db: AsyncSession, ids: Fixtures, *, mobile: str,
                            email: str | None = None,
                            is_active: bool = True) -> str:
    """Anchored at the fixture's dealer. Migration 004 made partner_id a real FK."""
    row = await db.execute(
        text("INSERT INTO app_user (user_type, mobile, email, full_name, role_id, "
             "partner_id, is_active) "
             "VALUES ('partner_user', :m, :e, 'Bhavesh Shah', :r, :p, :a) RETURNING id"),
        {"m": mobile, "e": email, "r": ids.portal_role_id,
         "p": ids.dealer_id, "a": is_active},
    )
    return row.scalar_one()


def _anon_role() -> str:
    """The pre-auth role, or a skip. Lives here because test_pre_auth_grants imports
    PRE_AUTH from the identity test, and the reverse import would be circular."""
    role = get_settings().db_anon_role
    if not role:
        pytest.skip("DB_ANON_ROLE unset; pre-auth containment is not active on this box")
    return role
