"""Migration 011: a dated master cannot be edited in place, a published price
list cannot be unpublished, and identity is case-insensitive where the column
says it is.

Three holes a cross-vendor review found in September, all of the same shape: the
rule was written in a service and nothing below the service enforced it. So every
test here goes straight to the table and writes what the service would never
write. A test that went through the service would pass on the day the trigger was
dropped.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db

# The value each master is edited on, and the lifecycle column that must still
# move. Written out per table rather than read from the migration: a test that
# imports FROZEN passes whatever FROZEN happens to say.
VALUE_EDITS: tuple[tuple[str, str], ...] = (
    ("subsidy_category", "pct = pct + 1"),
    ("subsidy_category", "per_ha_cap = 1"),
    ("subsidy_parameter", "value = value + 1"),
    ("subsidy_component_rate", "rate = rate + 1"),
    ("crop_lateral_spacing", "standard_spacing = 9.9"),
    ("gst_rate", "rate = 28"),
    ("product_hsn", "hsn_code = '9999'"),
)

LIFECYCLE_EDITS: tuple[tuple[str, str], ...] = (
    ("subsidy_category", "effective_to = DATE '2099-01-01'"),
    ("subsidy_parameter", "is_active = false"),
    ("subsidy_component_rate", "effective_to = DATE '2099-01-01'"),
    ("crop_lateral_spacing", "is_active = false"),
    ("gst_rate", "effective_to = DATE '2099-01-01'"),
    ("product_hsn", "deleted_at = now()"),
)


async def _one(db: AsyncSession, table: str) -> str | None:
    got = await db.execute(text(f"SELECT id::text FROM {table} LIMIT 1"))
    return got.scalar_one_or_none()


@pytest.mark.parametrize(("table", "edit"), VALUE_EDITS)
async def test_a_value_cannot_be_edited_in_place(db: AsyncSession, table: str,
                                                 edit: str) -> None:
    """The defect: 009 withheld UPDATE from the two cell tables and stopped, so
    every other dated master's value was editable by anyone with `masters.edit`.
    Nothing refused it, and after the 60-second cache expired every past
    calculation used the new figure."""
    row = await _one(db, table)
    if row is None:
        pytest.skip(f"{table} is empty on this database")
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(f"UPDATE {table} SET {edit} WHERE id = CAST(:i AS uuid)"),
                         {"i": row})
    assert "effective-dated" in str(err.value.orig)
    await db.rollback()


@pytest.mark.parametrize(("table", "edit"), LIFECYCLE_EDITS)
async def test_the_lifecycle_columns_still_move(db: AsyncSession, table: str,
                                                edit: str) -> None:
    """The other half, and the reason UPDATE could not simply be revoked: closing
    a row **is** an update, and it is how every revision supersedes its
    predecessor."""
    row = await _one(db, table)
    if row is None:
        pytest.skip(f"{table} is empty on this database")
    await db.execute(text(f"UPDATE {table} SET {edit} WHERE id = CAST(:i AS uuid)"), {"i": row})
    await db.rollback()


# ── a published price list is final ──────────────────────────────────────────

async def _published(db: AsyncSession) -> str:
    """A published list of this test's own, scoped to a tier and dated far enough
    back that it cannot collide with whatever the loader published."""
    got = await db.execute(text(
        "INSERT INTO price_list (name, effective_from, channel_tier, status, published_at) "
        "VALUES (:n, DATE '2001-01-01', 'sub_dealer', 'published', now()) RETURNING id::text"),
        {"n": f"test {uuid.uuid4().hex[:8]}"})
    return str(got.scalar_one())


@pytest.mark.parametrize(("what", "edit"), [
    ("back to draft", "status = 'draft', published_at = NULL"),
    ("unstamped", "published_at = NULL, status = 'published'"),
    ("a later start", "effective_from = DATE '2002-01-01'"),
    ("a different tier", "channel_tier = 'dealer'"),
    ("a different state", "state_territory_id = (SELECT id FROM territory WHERE level = 'state' "
                          "LIMIT 1)"),
    ("no longer provisional", "is_provisional = true"),
])
async def test_a_published_list_refuses_the_edit(db: AsyncSession, what: str, edit: str) -> None:
    """`status = 'draft', published_at = NULL` satisfied the CHECK and the UPDATE
    policy, and the draft-only item policies then allowed deleting and replacing
    rates a quotation had already been built on. Withholding UPDATE on
    `price_list_item` was meant to make published rates immutable; this walked
    around it."""
    list_id = await _published(db)
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(f"UPDATE price_list SET {edit} WHERE id = CAST(:i AS uuid)"),
                         {"i": list_id})
    assert "published price list" in str(err.value.orig), what
    await db.rollback()


async def test_a_published_list_may_still_be_closed(db: AsyncSession) -> None:
    """`effective_to` is the one thing that moves, and it has to: it is how a
    successor supersedes this list."""
    list_id = await _published(db)
    await db.execute(text(
        "UPDATE price_list SET effective_to = DATE '2030-01-01' WHERE id = CAST(:i AS uuid)"),
        {"i": list_id})
    await db.rollback()


async def test_a_draft_is_still_freely_editable(db: AsyncSession) -> None:
    """Which is the whole reason publication is a separate step."""
    got = await db.execute(text(
        "INSERT INTO price_list (name, effective_from) VALUES (:n, DATE '2001-01-01') "
        "RETURNING id::text"), {"n": f"draft {uuid.uuid4().hex[:8]}"})
    await db.execute(text(
        "UPDATE price_list SET channel_tier = 'dealer', effective_from = DATE '2002-01-01', "
        "name = 'renamed' WHERE id = CAST(:i AS uuid)"), {"i": str(got.scalar_one())})
    await db.rollback()


# ── identity is case-insensitive where the column says so ────────────────────

async def test_two_crops_differing_only_in_case_cannot_overlap(db: AsyncSession) -> None:
    """`btree_gist` has no operator class for citext, so 009 cast to text - and
    the cast also downgraded equality to case-sensitive. Executed on 16.14 both
    rows inserted, holding different spacings over the same dates, while the
    service lowercases both into one dictionary key and keeps whichever it read
    last. A subsidy figure decided by row order."""
    scheme = str((await db.execute(text(
        "INSERT INTO subsidy_scheme (code, name) VALUES (:c, 'test scheme') RETURNING id"),
        {"c": f"T{uuid.uuid4().hex[:12]}"})).scalar_one())
    insert = text("INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, "
                  "effective_from) VALUES (CAST(:s AS uuid), :c, :sp, :f)")
    await db.execute(insert, {"s": scheme, "c": "Mango", "sp": "1.2",
                              "f": dt.date(2020, 1, 1)})
    with pytest.raises(DBAPIError) as err:
        await db.execute(insert, {"s": scheme, "c": "MANGO", "sp": "9.9",
                                  "f": dt.date(2020, 1, 1)})
    assert "ex_crop_lateral_spacing" in str(err.value.orig)
    await db.rollback()


async def test_the_same_crop_in_another_case_may_still_follow_in_time(
        db: AsyncSession) -> None:
    """Case-insensitive identity narrows what may overlap, not what may succeed.
    A revision typed in a different case is still a revision."""
    scheme = str((await db.execute(text(
        "INSERT INTO subsidy_scheme (code, name) VALUES (:c, 'test scheme') RETURNING id"),
        {"c": f"T{uuid.uuid4().hex[:12]}"})).scalar_one())
    await db.execute(text(
        "INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, effective_from, "
        "effective_to) VALUES (CAST(:s AS uuid), 'Mango', 1.2, :f, :t)"),
        {"s": scheme, "f": dt.date(2020, 1, 1), "t": dt.date(2021, 1, 1)})
    await db.execute(text(
        "INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, effective_from) "
        "VALUES (CAST(:s AS uuid), 'MANGO', 1.5, :f)"),
        {"s": scheme, "f": dt.date(2021, 1, 1)})
    await db.rollback()


async def test_two_parameters_differing_only_in_case_cannot_overlap(
        db: AsyncSession) -> None:
    """The same correction, on the key the calculation looks parameters up by."""
    scheme = str((await db.execute(text(
        "INSERT INTO subsidy_scheme (code, name) VALUES (:c, 'test scheme') RETURNING id"),
        {"c": f"T{uuid.uuid4().hex[:12]}"})).scalar_one())
    insert = text("INSERT INTO subsidy_parameter (scheme_id, key, value, unit, "
                  "effective_from) VALUES (CAST(:s AS uuid), :k, :v, 'ratio', :f)")
    await db.execute(insert, {"s": scheme, "k": "insurance_pct", "v": "0.28",
                              "f": dt.date(2020, 1, 1)})
    with pytest.raises(DBAPIError) as err:
        await db.execute(insert, {"s": scheme, "k": "INSURANCE_PCT", "v": "9.99",
                                  "f": dt.date(2020, 1, 1)})
    assert "ex_subsidy_parameter_all_systems" in str(err.value.orig)
    await db.rollback()
