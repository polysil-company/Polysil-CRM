"""API-layer fixtures.

`Staff` and `Dealer` moved up to the root conftest so `tests/db/` can use them too;
the names stay importable from here. The committed administrator (`admin`) and the
helpers the people, offices and partners tests share live here, so several test
modules use one fixture without importing each other.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Dealer, Staff

__all__ = ["Admin", "Dealer", "Staff", "admin", "scoped_admin"]

V1 = "/api/v1"
PASSWORD = "correct horse battery staple"
TEMP = "temporary-password-1"
_hasher = PasswordHasher()


@dataclass
class Admin:
    user: Staff
    territory_id: str          # the district the admin's office covers
    state_code: str
    distributor_id: str
    dealer_id: str


@pytest_asyncio.fixture
async def admin(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Admin]:
    tag = uuid.uuid4().hex[:10]
    email = f"staff_{tag}@polysil.in"
    code = "Z" + tag[:3].upper()
    s = sessions()
    state = (await s.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"api_state_{tag}", "c": code})).scalar_one()
    district = (await s.execute(text(
        "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, :p) RETURNING id"),
        {"n": f"api_{tag}", "p": state})).scalar_one()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 5, :t) RETURNING id"),
        {"n": f"api_{tag}", "t": district})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'API Admin', 5) RETURNING id"),
        {"c": f"api_adm_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'users', 'view', 'global'), (:r, 'users', 'create', 'global'), "
        "(:r, 'users', 'edit', 'global'), (:r, 'users', 'delete', 'global'), "
        "(:r, 'leads', 'view', 'global'), (:r, 'leads', 'create', 'global'), "
        "(:r, 'leads', 'edit', 'global'), (:r, 'leads', 'delete', 'global'), "
        "(:r, 'partners', 'view', 'global'), (:r, 'partners', 'create', 'global'), "
        "(:r, 'partners', 'edit', 'global'), "
        "(:r, 'masters', 'view', 'global'), (:r, 'masters', 'edit', 'global')"), {"r": role})
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, :p, 'API Admin', :r, :o) RETURNING id"),
        {"e": email, "p": _hasher.hash(PASSWORD), "r": role, "o": org})).scalar_one()
    distributor = (await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('distributor', :c, 'API Distributor', :t, 'distributor') RETURNING id"),
        {"c": f"API-D-{tag}", "t": district})).scalar_one()
    dealer = (await s.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'dealer', :c, 'API Dealer', :t, 'dealer') RETURNING id"),
        {"p": distributor, "c": f"API-L-{tag}", "t": district})).scalar_one()
    await s.commit()

    try:
        yield Admin(Staff(str(user), email, PASSWORD, str(org), str(role)),
                    str(district), code, str(distributor), str(dealer))
    finally:
        c = sessions()
        created = [str(r[0]) for r in (await c.execute(text(
            "SELECT id FROM app_user WHERE created_by = CAST(:a AS uuid)"),
            {"a": str(user)})).all()]
        everyone = [*created, str(user)]
        leaves = {
            "org_unit": "NOT EXISTS (SELECT 1 FROM org_unit c WHERE c.parent_id = t.id)",
            "channel_partner": "NOT EXISTS (SELECT 1 FROM channel_partner c "
                               "WHERE c.parent_id = t.id)",
            "territory": "NOT EXISTS (SELECT 1 FROM territory c WHERE c.parent_id = t.id) "
                         "AND NOT EXISTS (SELECT 1 FROM org_unit o WHERE o.territory_id = t.id) "
                         "AND NOT EXISTS (SELECT 1 FROM channel_partner p "
                         "WHERE p.territory_id = t.id)",
        }

        async def drop_created_masters() -> None:
            # FS-010's tables first, and by hand: `price_list_item` carries no
            # created_by, so it cannot be a leaf rule - it is reached through the
            # list that owns it. Everything else here is an ordinary child.
            for stmt in (
                "DELETE FROM price_list_item i USING price_list l WHERE l.id = i.price_list_id "
                "AND l.created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM price_list_item i USING product p WHERE p.id = i.product_id "
                "AND p.created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM price_list WHERE created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM product_hsn WHERE created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM product_hsn h USING product p WHERE p.id = h.product_id "
                "AND p.created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM gst_rate WHERE created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM seller_gstin WHERE created_by = ANY(CAST(:ids AS uuid[]))",
                "DELETE FROM product WHERE created_by = ANY(CAST(:ids AS uuid[]))",
            ):
                await c.execute(text(stmt), {"ids": everyone})

            # what the tests created through the API carries created_by: leaves first,
            # repeated until nothing goes (a two-level chain needs two passes; F-6)
            for table, free in leaves.items():
                while True:
                    gone = await c.execute(text(
                        f"DELETE FROM {table} t WHERE t.created_by = ANY(CAST(:ids AS uuid[])) "
                        f"AND {free}"), {"ids": everyone})
                    if not gone.rowcount:
                        break

        for stmt, params in (
            ("DELETE FROM activity_event WHERE lead_id IN "
             "(SELECT id FROM lead WHERE territory_id = :t)", {"t": str(district)}),
            ("DELETE FROM lead_duplicate_link WHERE lead_a_id IN "
             "(SELECT id FROM lead WHERE territory_id = :t) OR lead_b_id IN "
             "(SELECT id FROM lead WHERE territory_id = :t)", {"t": str(district)}),
            ("DELETE FROM notification_outbox WHERE recipient IN "
             "(SELECT mobile FROM lead WHERE territory_id = :t)", {"t": str(district)}),
            ("DELETE FROM lead WHERE territory_id = :t", {"t": str(district)}),
            ("DELETE FROM inquiry_counter WHERE state_code = :c", {"c": code}),
            ("DELETE FROM activity_event WHERE entity_id = ANY(CAST(:ids AS uuid[])) "
             "OR actor_id = ANY(CAST(:ids AS uuid[]))", {"ids": everyone}),
            ("DELETE FROM session WHERE user_id = ANY(CAST(:ids AS uuid[]))", {"ids": everyone}),
            ("DELETE FROM user_territory WHERE user_id = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("DELETE FROM login_attempt WHERE identifier IN (SELECT email::text FROM app_user "
             "WHERE id = ANY(CAST(:ids AS uuid[])) AND email IS NOT NULL UNION "
             "SELECT mobile FROM app_user WHERE id = ANY(CAST(:ids AS uuid[])) "
             "AND mobile IS NOT NULL)", {"ids": everyone}),
            ("DELETE FROM notification_outbox WHERE recipient IN (SELECT mobile FROM app_user "
             "WHERE id = ANY(CAST(:ids AS uuid[])) AND mobile IS NOT NULL)", {"ids": everyone}),
            ("DELETE FROM idempotency_record WHERE user_id = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("DELETE FROM app_user WHERE id = ANY(CAST(:ids AS uuid[]))", {"ids": created}),
            ("SELECT 1", {}),   # the leaf loop runs here, see below
            ("UPDATE org_unit SET created_by = NULL, updated_by = NULL WHERE created_by = "
             "ANY(CAST(:ids AS uuid[])) OR updated_by = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("UPDATE territory SET created_by = NULL, updated_by = NULL WHERE created_by = "
             "ANY(CAST(:ids AS uuid[])) OR updated_by = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("UPDATE channel_partner SET created_by = NULL, updated_by = NULL WHERE created_by = "
             "ANY(CAST(:ids AS uuid[])) OR updated_by = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("DELETE FROM app_user WHERE id = CAST(:a AS uuid)", {"a": str(user)}),
            ("DELETE FROM role_permission WHERE role_id = CAST(:r AS uuid)", {"r": str(role)}),
            ("DELETE FROM role WHERE id = CAST(:r AS uuid)", {"r": str(role)}),
            ("DELETE FROM org_unit WHERE id = CAST(:o AS uuid)", {"o": str(org)}),
            ("DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)", {"p": str(dealer)}),
            ("DELETE FROM channel_partner WHERE id = CAST(:p AS uuid)", {"p": str(distributor)}),
            ("DELETE FROM territory WHERE id = CAST(:t AS uuid)", {"t": str(district)}),
            ("DELETE FROM territory WHERE id = CAST(:t AS uuid)", {"t": str(state)}),
        ):
            if stmt == "SELECT 1":
                await drop_created_masters()
                continue
            await c.execute(text(stmt), params)
        await c.commit()


# ── helpers ──────────────────────────────────────────────────────────────────

async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict[str, str]:
    r = await client.post(f"{V1}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


async def _auth(client: httpx.AsyncClient, staff: Staff) -> dict[str, str]:
    return await _login(client, staff.email, staff.password)


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid.uuid4().hex}


def _staff_body(admin: Admin, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "user_type": "staff", "full_name": "Meera Joshi",
        "email": f"staff_{uuid.uuid4().hex[:8]}@polysil.in", "role": "field_officer",
        "org_unit_id": admin.user.org_unit_id, "password": TEMP,
    }
    body.update(over)
    return body


async def _create(client: httpx.AsyncClient, h: dict[str, str], body: dict[str, object]) -> dict:
    r = await client.post(f"{V1}/users", json=body, headers={**h, **_key()})
    assert r.status_code == 201, r.text
    return r.json()["data"]


@pytest_asyncio.fixture
async def scoped_admin(sessions: Callable[[], AsyncSession], admin: Admin) -> AsyncIterator[Staff]:
    """An administrator at org_subtree, in a child office of the global admin's:
    users view, create and edit over its own subtree and nothing beyond it. The
    negative half of the people tests (code review F-2)."""
    tag = uuid.uuid4().hex[:10]
    email = f"staff_{tag}@polysil.in"
    s = sessions()
    org = (await s.execute(text(
        "INSERT INTO org_unit (name, role_level, parent_id, territory_id) "
        "VALUES (:n, 3, :p, :t) RETURNING id"),
        {"n": f"api_sub_{tag}", "p": admin.user.org_unit_id, "t": admin.territory_id})).scalar_one()
    role = (await s.execute(text(
        "INSERT INTO role (code, name, level) VALUES (:c, 'API Scoped Admin', 3) RETURNING id"),
        {"c": f"api_sadm_{tag}"})).scalar_one()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'users', 'view', 'org_subtree'), (:r, 'users', 'create', 'org_subtree'), "
        "(:r, 'users', 'edit', 'org_subtree'), "
        "(:r, 'leads', 'view', 'org_subtree'), (:r, 'leads', 'edit', 'org_subtree')"), {"r": role})
    user = (await s.execute(text(
        "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, :p, 'Scoped Admin', :r, :o) RETURNING id"),
        {"e": email, "p": _hasher.hash(PASSWORD), "r": role, "o": org})).scalar_one()
    await s.commit()
    try:
        yield Staff(str(user), email, PASSWORD, str(org), str(role))
    finally:
        c = sessions()
        created = [str(r[0]) for r in (await c.execute(text(
            "SELECT id FROM app_user WHERE created_by = CAST(:a AS uuid)"),
            {"a": str(user)})).all()]
        everyone = [*created, str(user)]
        for stmt, params in (
            ("DELETE FROM activity_event WHERE entity_id = ANY(CAST(:ids AS uuid[])) "
             "OR actor_id = ANY(CAST(:ids AS uuid[]))", {"ids": everyone}),
            ("DELETE FROM session WHERE user_id = ANY(CAST(:ids AS uuid[]))", {"ids": everyone}),
            ("DELETE FROM user_territory WHERE user_id = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("DELETE FROM login_attempt WHERE identifier IN (SELECT email::text FROM app_user "
             "WHERE id = ANY(CAST(:ids AS uuid[])))", {"ids": everyone}),
            ("DELETE FROM idempotency_record WHERE user_id = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("UPDATE app_user SET updated_by = NULL WHERE updated_by = ANY(CAST(:ids AS uuid[]))",
             {"ids": everyone}),
            ("DELETE FROM app_user WHERE id = ANY(CAST(:ids AS uuid[]))", {"ids": created}),
            ("DELETE FROM app_user WHERE id = CAST(:a AS uuid)", {"a": str(user)}),
            ("DELETE FROM role_permission WHERE role_id = CAST(:r AS uuid)", {"r": str(role)}),
            ("DELETE FROM role WHERE id = CAST(:r AS uuid)", {"r": str(role)}),
            ("DELETE FROM org_unit WHERE id = CAST(:o AS uuid)", {"o": str(org)}),
        ):
            await c.execute(text(stmt), params)
        await c.commit()
