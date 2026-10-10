"""API-layer fixtures.

`Staff` and `Dealer` moved up to the root conftest so `tests/db/` can use them too;
the names stay importable from here. The committed administrator (`admin`) and the
helpers the people, offices and partners tests share live here, so several test
modules use one fixture without importing each other.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest_asyncio
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Dealer, Staff


@contextlib.asynccontextmanager
async def only_these_render(sessions: Callable[[], AsyncSession], table: str,
                            ids: list[str]) -> AsyncIterator[None]:
    """The render claim takes the earliest due row in the whole database, so a test
    that renders would claim, and mark ready, someone else's document (PR 11 review).
    Every other pending row on `table` is set aside for the duration, then restored."""
    assert table in ("quotation", "sales_order")
    s = sessions()
    moved: list[str] = []
    try:
        moved = [str(x) for x in (await s.execute(text(
            f"UPDATE {table} SET pdf_next_attempt_at = pdf_next_attempt_at + interval '100 years' "
            "WHERE pdf_state = 'pending' AND pdf_next_attempt_at IS NOT NULL "
            "AND id <> ALL(CAST(:i AS uuid[])) RETURNING id"), {"i": ids})).scalars().all()]
        await s.commit()
        yield
    finally:
        if moved:
            await s.execute(text(
                f"UPDATE {table} SET pdf_next_attempt_at = "
                "pdf_next_attempt_at - interval '100 years' "
                "WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": moved})
            await s.commit()
        await s.close()

__all__ = ["Admin", "Catalogue", "Dealer", "Staff", "admin", "catalogue", "scoped_admin"]

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


# ── the catalogue FS-010 and FS-005 both quote from ──────────────────────────

@dataclass
class Catalogue:
    """One product, classified and taxed, priced in a list of this test's own."""

    product_id: str
    description: str
    category: str
    uom: str
    gstin_id: str
    gujarat_district_id: str
    price_list_id: str
    rate: str


def _gstin() -> str:
    """A registration number of this test's own.

    `ck_seller_gstin_format` is two digits, five letters, four digits, a letter,
    then three alphanumerics, and `gstin` is uniquely indexed. Varying one
    character of a hex tag gives sixteen possible numbers, so a file with thirty
    tests collides with itself - and one of the sixteen is the seeded
    registration, which collides on the first run.
    """
    alnum = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = uuid.uuid4().int
    tail = "".join(alnum[(n >> (6 * i)) % 36] for i in range(3))
    return f"24AAAAA{n % 9000 + 1000:04d}A{tail}"


@pytest_asyncio.fixture
async def catalogue(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Catalogue]:
    tag = uuid.uuid4().hex[:8]
    description = f"TEST PIPE {tag}"
    s = sessions()
    category = (await s.execute(text(
        "SELECT code::text FROM product_category ORDER BY sort_order LIMIT 1"))).scalar_one()
    uom = (await s.execute(text(
        "SELECT code::text FROM uom WHERE decimals = 0 LIMIT 1"))).scalar_one()
    product = str((await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id, "
        "  provisional_fields) "
        "SELECT CAST(:d AS citext), c.id, 'field', u.id, ARRAY['gst_slab','mrp']::text[] "
        "FROM product_category c, uom u "
        "WHERE c.code = CAST(:c AS citext) AND u.code = CAST(:u AS citext) RETURNING id"),
        {"d": description, "c": category, "u": uom})).scalar_one())
    await s.execute(text(
        "INSERT INTO product_hsn (product_id, hsn_code, effective_from) "
        "VALUES (CAST(:p AS uuid), '3917', DATE '2019-01-01')"), {"p": product})
    # 3917 already carries a rate from 2026-04-01; this one covers the test window
    # and closes before it, so the two never overlap.
    await s.execute(text(
        "INSERT INTO gst_rate (hsn_code, rate, effective_from, effective_to) "
        "VALUES ('3917', 5, DATE '2019-01-01', DATE '2021-01-01')"))
    # A second registration, not the default: the unique index allows only one
    # default, and the seeded one does not start until 2026.
    gstin = str((await s.execute(text(
        "INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, effective_from, "
        "  effective_to) "
        "SELECT CAST(:g AS citext), 'Polysil Test', t.id, DATE '2019-01-01', DATE '2021-01-01' "
        "FROM territory t WHERE t.level = 'state' AND t.code = 'GJ' RETURNING id"),
        {"g": _gstin()})).scalar_one())
    district = str((await s.execute(text(
        "SELECT d.id FROM territory d JOIN territory s ON s.id = d.parent_id "
        "WHERE s.level = 'state' AND s.code = 'GJ' AND d.level = 'district' LIMIT 1"
    ))).scalar_one())
    price_list = str((await s.execute(text(
        "INSERT INTO price_list (name, channel_tier, status, published_at, effective_from, "
        "  effective_to, is_provisional) "
        "VALUES (:n, 'farmer', 'published', now(), DATE '2020-01-01', DATE '2021-01-01', true) "
        "RETURNING id"), {"n": f"test list {tag}"})).scalar_one())
    await s.execute(text(
        "INSERT INTO price_list_item (price_list_id, product_id, rate) "
        "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 103.19)"),
        {"l": price_list, "p": product})
    await s.commit()

    try:
        yield Catalogue(product, description, category, uom, gstin, district, price_list,
                        "103.19")
    finally:
        c = sessions()
        for stmt in (
            "DELETE FROM price_list_item WHERE product_id = CAST(:p AS uuid)",
            "DELETE FROM price_list WHERE id = CAST(:l AS uuid)",
            "DELETE FROM product_hsn WHERE product_id = CAST(:p AS uuid)",
            "DELETE FROM gst_rate WHERE hsn_code = '3917' AND effective_to = DATE '2021-01-01'",
            "DELETE FROM seller_gstin WHERE id = CAST(:g AS uuid)",
            "DELETE FROM product WHERE id = CAST(:p AS uuid)",
        ):
            await c.execute(text(stmt), {"p": product, "l": price_list, "g": gstin})
        await c.commit()
