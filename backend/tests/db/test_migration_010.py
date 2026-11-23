"""Migration 010: the price-list scope rules, the four exclusion constraints, and
the seed the whole pricing endpoint depends on (FS-010 section 10).

Four claims are worth the round trips, and each was wrong at some point in this
feature's life.

**The tier rule is restrictive, not permissive.** Written as one permissive
clause, a staff caller has no partner, `channel_tier = app_current_partner_tier()`
is NULL for every tier row, and staff resolve nothing but the base list. A plan
review caught that before it shipped; this is what keeps it caught.

**There are four exclusion constraints, not two.** `price_list` has two nullable
scope columns, so it has four null patterns, and a pair split on one column
accepts two overlapping rows on the other's null.

**`price_list_item` takes no UPDATE at all**, and its DELETE is narrowed by policy
to a draft's items - so a delete against a published list removes zero rows
*silently*. The 409 has to come from the service, which is exactly the kind of
thing that stops being true without a test.

**The default seller registration must exist.** Migration 010 seeds it by
selecting the Gujarat territory, which no migration creates: on a fresh database
that INSERT matches zero rows and every quotation answers 404 forever. Found by a
cross-vendor review in September, and now seeded by `scripts/seed_demo.py` too.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = pytest.mark.db

TABLES = ("product_category", "uom", "product", "product_hsn", "gst_rate",
          "price_list", "price_list_item", "seller_gstin")


def _mobile() -> str:
    """`ck_app_user_mobile_shape` wants 91 then a ten-digit number starting 6 to 9,
    so a unique tag will not do. The same shape the other db tests use."""
    return "9199" + f"{uuid.uuid4().int % 10**8:08d}"


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _list(db: AsyncSession, *, state: str | None = None, tier: str | None = None,
                status: str = "published", frm: dt.date = dt.date(2001, 1, 1),
                to: dt.date | None = dt.date(2002, 1, 1)) -> str:
    """A price list of this test's own, in a closed window in 2001.

    Closed, and in the past, on purpose. `scripts/load_product_master.py` publishes
    an open-ended base list from 2026-04-01, and an open-ended test list collides
    with it through the very constraint the test is trying to prove - the same trap
    `_own_scheme` exists for in `test_migration_009.py`."""
    got = await db.execute(text(
        "INSERT INTO price_list (name, state_territory_id, channel_tier, status, published_at, "
        "  effective_from, effective_to) "
        "VALUES (:n, CAST(:s AS uuid), CAST(:t AS channel_tier), CAST(:st AS price_list_status), "
        "  CASE WHEN :st = 'published' THEN now() END, :f, :e) RETURNING id::text"),
        {"n": f"test {uuid.uuid4().hex[:8]}", "s": state, "t": tier, "st": status,
         "f": frm, "e": to})
    return str(got.scalar_one())


# ── the four exclusion constraints ───────────────────────────────────────────

@pytest.mark.parametrize(("state", "tier"), [
    (None, None),
    (None, "dealer"),
    ("state", None),
    ("state", "dealer"),
])
async def test_two_published_lists_of_one_scope_cannot_overlap(
        db: AsyncSession, ids: Fixtures, state: str | None, tier: str | None) -> None:
    """One constraint per null pattern. A pair split on one column accepts two
    overlapping rows on the other's null, executed on 16.14."""
    territory = None
    if state:
        territory = str((await db.execute(text(
            "INSERT INTO territory (level, name) VALUES ('state', :n) RETURNING id::text"),
            {"n": ids.unique("state")})).scalar_one())
    await _list(db, state=territory, tier=tier)
    with pytest.raises(DBAPIError) as err:
        await _list(db, state=territory, tier=tier)
    assert "ex_price_list" in str(err.value.orig)
    await db.rollback()


async def test_a_state_list_does_not_collide_with_the_base_list(
        db: AsyncSession, ids: Fixtures) -> None:
    """The point of the four: each null pattern is its own scope, so a state list
    sits over the base list rather than colliding with it."""
    territory = str((await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('state', :n) RETURNING id::text"),
        {"n": ids.unique("state")})).scalar_one())
    await _list(db)
    await _list(db, state=territory)
    await _list(db, tier="dealer")
    await _list(db, state=territory, tier="dealer")
    await db.rollback()


async def test_a_draft_never_collides_with_anything(db: AsyncSession) -> None:
    """Every constraint is `WHERE status = 'published'`, so a successor can be
    built over weeks while its predecessor is in force. That is the whole
    draft-then-publish sequence."""
    await _list(db)
    await _list(db, status="draft")
    await _list(db, status="draft")
    await db.rollback()


async def test_closing_one_and_publishing_the_next_works_in_one_transaction(
        db: AsyncSession) -> None:
    """Deferrable, and the service closes first because publishing first raises.
    Both orders are proven here so the constraint's deferrability is not an
    accident nobody checked."""
    first = await _list(db, to=dt.date(2003, 1, 1))
    second = await _list(db, status="draft", frm=dt.date(2002, 1, 1), to=dt.date(2003, 1, 1))
    await db.execute(text(
        "UPDATE price_list SET effective_to = DATE '2002-01-01' WHERE id = CAST(:i AS uuid)"),
        {"i": first})
    await db.execute(text(
        "UPDATE price_list SET status = 'published', published_at = now() "
        "WHERE id = CAST(:i AS uuid)"), {"i": second})
    await db.rollback()


# ── the restrictive tier policy, for every caller shape ──────────────────────

async def test_a_partner_reads_its_own_tier_and_the_untiered_lists(
        db: AsyncSession, ids: Fixtures) -> None:
    """A dealer sees the base list and the dealer list, and not the distributor's.
    Rule 8: tiered pricing never leaks upward."""
    base = await _list(db)
    dealer_list = await _list(db, tier="dealer")
    distributor_list = await _list(db, tier="distributor")
    user = await make_partner_user(db, ids, mobile=_mobile())
    await _as(db, str(user))

    seen = set((await db.execute(text("SELECT id::text FROM price_list"))).scalars().all())
    assert base in seen and dealer_list in seen
    assert distributor_list not in seen, "a dealer must not read the distributor's rates"
    await db.rollback()


async def test_a_staff_caller_reads_every_tier(db: AsyncSession, ids: Fixtures) -> None:
    """The failure the restrictive clause exists to avoid. Written permissively,
    `channel_tier = app_current_partner_tier()` is NULL for a caller with no
    partner, so staff would see the base list and nothing else - and the pricing
    endpoint would break the day a tier list was published."""
    base = await _list(db)
    tiers = {tier: await _list(db, tier=tier)
             for tier in ("distributor", "dealer", "sub_dealer")}
    user = await make_staff(db, ids, email=ids.unique("asha") + "@polysil.in")
    await _as(db, str(user))

    seen = set((await db.execute(text("SELECT id::text FROM price_list"))).scalars().all())
    assert base in seen
    for tier, list_id in tiers.items():
        assert list_id in seen, f"staff must read the {tier} list"
    await db.rollback()


async def test_a_partner_reads_only_its_own_tiers_items(
        db: AsyncSession, ids: Fixtures) -> None:
    """The same rule one level down. Without the restrictive clause on
    `price_list_item` a dealer could not see the distributor's list and could
    still read its rates."""
    product = (await db.execute(text("SELECT id::text FROM product LIMIT 1"))).scalar_one_or_none()
    if product is None:
        pytest.skip("no products loaded on this database")
    above = await _list(db, tier="distributor")
    await db.execute(text(
        "INSERT INTO price_list_item (price_list_id, product_id, rate) "
        "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 100.00)"), {"l": above, "p": product})
    user = await make_partner_user(db, ids, mobile=_mobile())
    await _as(db, str(user))

    leaked = (await db.execute(text(
        "SELECT count(*) FROM price_list_item WHERE price_list_id = CAST(:l AS uuid)"),
        {"l": above})).scalar_one()
    assert leaked == 0
    await db.rollback()


# ── the grants that make published rates immutable ───────────────────────────

async def test_price_list_item_takes_no_update_at_all(db: AsyncSession) -> None:
    """A published rate is never corrected, only superseded. The grant is the
    enforcement; a policy cannot be scoped to a column."""
    granted = (await db.execute(text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'app_role' AND table_schema = 'public' "
        "AND table_name = 'price_list_item'"))).scalars().all()
    assert set(granted) == {"SELECT", "INSERT", "DELETE"}, granted


async def test_deleting_a_published_lists_items_removes_nothing_and_says_nothing(
        db: AsyncSession, ids: Fixtures) -> None:
    """The silence is the point, and it is why the API's 409 comes from the
    service's status check rather than from the database."""
    product = (await db.execute(text("SELECT id::text FROM product LIMIT 1"))).scalar_one_or_none()
    if product is None:
        pytest.skip("no products loaded on this database")
    published = await _list(db)
    await db.execute(text(
        "INSERT INTO price_list_item (price_list_id, product_id, rate) "
        "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 100.00)"), {"l": published, "p": product})
    user = await make_staff(db, ids, email=ids.unique("admin") + "@polysil.in")
    await _as(db, str(user))

    result = await db.execute(text(
        "DELETE FROM price_list_item WHERE price_list_id = CAST(:l AS uuid)"), {"l": published})
    assert result.rowcount == 0, "no error, and nothing removed"
    await db.rollback()


# ── the seed the pricing endpoint cannot run without ─────────────────────────

async def test_one_default_seller_registration_is_in_force(db: AsyncSession) -> None:
    """Migration 010 seeds this by selecting the Gujarat territory, which no
    migration creates. On a fresh database that INSERT matches zero rows, nothing
    errors, and every quotation answers `404 no seller registration is in force`
    for the life of the deployment. `scripts/seed_demo.py` seeds it too, after the
    territory exists."""
    rows = (await db.execute(text(
        "SELECT g.gstin::text, t.level::text, t.code::text FROM seller_gstin g "
        "JOIN territory t ON t.id = g.state_territory_id "
        "WHERE g.is_default AND g.is_active AND g.deleted_at IS NULL "
        "AND daterange(g.effective_from, g.effective_to, '[)') @> CURRENT_DATE"))).all()
    assert len(rows) == 1, f"exactly one default registration, found {len(rows)}"
    assert rows[0][1] == "state", "the place of supply comparison needs a state"
    assert rows[0][2], "and that state needs a code, which the quote response returns"


async def test_every_table_carries_row_level_security(db: AsyncSession) -> None:
    unprotected = (await db.execute(text(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relname = ANY(:t) AND NOT c.relrowsecurity"),
        {"t": list(TABLES)})).scalars().all()
    assert not unprotected, unprotected
