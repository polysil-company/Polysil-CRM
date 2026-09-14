"""Migrations 001 and 002, against a real database.

Nothing here is mocked. A closure table maintained by triggers is only correct if
the triggers are correct, and the triggers only exist inside the server
(CLAUDE.md 1.4).

Every test rolls back. The `db` fixture does it in its `finally`, and these tests
add nothing that could outlive it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db

# The closure table says the same thing as a recursive walk over the parent
# pointers, or one of them is wrong. This is the oracle for every closure test
# below: it does not encode what we expect the trigger to do, it recomputes the
# answer from the only other source of truth in the schema.
WALK = """
WITH RECURSIVE walk AS (
    SELECT id AS ancestor_id, id AS descendant_id, 0 AS depth FROM {node}
    UNION ALL
    SELECT w.ancestor_id, n.id, w.depth + 1
      FROM walk w JOIN {node} n ON n.parent_id = w.descendant_id
)
SELECT ancestor_id, descendant_id, depth FROM walk
"""


async def _closure_agrees(db: AsyncSession, node: str, closure: str) -> None:
    got = sorted((await db.execute(text(
        f"SELECT ancestor_id, descendant_id, depth FROM {closure}"))).all())
    want = sorted((await db.execute(text(WALK.format(node=node)))).all())
    assert got == want, f"{closure} disagrees with a recursive walk over {node}"


async def _tree(db: AsyncSession) -> dict[str, str]:
    """S -> (D1 -> (T1 -> V1, T2), D2)."""
    ids: dict[str, str] = {}
    for name, level, parent in (
        ("S", "state", None),
        ("D1", "district", "S"),
        ("D2", "district", "S"),
        ("T1", "taluka", "D1"),
        ("T2", "taluka", "D1"),
        ("V1", "village", "T1"),
    ):
        row = await db.execute(
            text("INSERT INTO territory (level, name, parent_id) "
                 "VALUES (:lvl, :name, :parent) RETURNING id"),
            {"lvl": level, "name": name, "parent": ids.get(parent)},
        )
        ids[name] = row.scalar_one()
    return ids


# ── 001 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ext", ["pgcrypto", "pg_trgm", "citext"])
async def test_extension_is_installed(db: AsyncSession, ext: str) -> None:
    got = await db.execute(text("SELECT 1 FROM pg_extension WHERE extname = :e"), {"e": ext})
    assert got.scalar() == 1


async def test_audit_log_exists_and_actor_carries_no_fk(db: AsyncSession) -> None:
    """FS-001 section 5: an audit row outlives the deletion of the actor it names,
    and an FK here would make 001 depend on 003."""
    cols = (await db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'audit_log'"))).scalars().all()
    assert set(cols) == {"id", "actor_id", "action", "table_name", "row_id",
                         "old_jsonb", "new_jsonb", "at"}

    fks = (await db.execute(text(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = 'audit_log'::regclass AND contype = 'f'"))).scalars().all()
    assert fks == [], f"audit_log must carry no foreign key, found {fks}"


async def test_audit_function_is_plpgsql(db: AsyncSession) -> None:
    """It calls app_current_user_id(), which 003 creates. A `sql` body is validated
    at CREATE FUNCTION time under check_function_bodies and would fail in 001."""
    lang = await db.execute(text(
        "SELECT l.lanname FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang "
        "WHERE p.proname = 'audit_row'"))
    assert lang.scalar_one() == "plpgsql"


async def test_check_function_bodies_is_on(db: AsyncSession) -> None:
    """The setting the two decisions above depend on. If it is ever turned off,
    both stop being load-bearing and the reasoning in the migrations reads as
    superstition."""
    assert (await db.execute(text("SHOW check_function_bodies"))).scalar_one() == "on"


# ── 002, closure maintenance ─────────────────────────────────────────────────

async def test_insert_builds_the_closure(db: AsyncSession) -> None:
    ids = await _tree(db)
    await _closure_agrees(db, "territory", "territory_closure")

    # Counted over this test's own six nodes, not the whole table. The demo seed
    # shares this database, so a global count asserts something about whatever
    # else happens to be in it.
    n = await db.execute(
        text("SELECT count(*) FROM territory_closure WHERE descendant_id = ANY(:ids)"),
        {"ids": list(ids.values())},
    )
    # 1 + 2 + 2 + 3 + 3 + 4, self rows included.
    assert n.scalar_one() == 15


async def test_root_gets_only_a_self_row(db: AsyncSession) -> None:
    row = await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('state','solo') RETURNING id"))
    tid = row.scalar_one()
    got = (await db.execute(text(
        "SELECT ancestor_id, depth FROM territory_closure WHERE descendant_id = :i"),
        {"i": tid})).all()
    assert got == [(tid, 0)]


async def test_subtree_move_rebuilds_the_closure(db: AsyncSession) -> None:
    ids = await _tree(db)
    await db.execute(text("UPDATE territory SET parent_id = :p WHERE id = :i"),
                     {"p": ids["D2"], "i": ids["T1"]})
    await _closure_agrees(db, "territory", "territory_closure")

    depth = await db.execute(text(
        "SELECT depth FROM territory_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": ids["S"], "d": ids["V1"]})
    assert depth.scalar_one() == 3, "S -> D2 -> T1 -> V1"

    stale = await db.execute(text(
        "SELECT count(*) FROM territory_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": ids["D1"], "d": ids["V1"]})
    assert stale.scalar_one() == 0, "the old ancestor still reaches the moved subtree"


async def test_promotion_to_root_rebuilds_the_closure(db: AsyncSession) -> None:
    ids = await _tree(db)
    await db.execute(text("UPDATE territory SET parent_id = NULL WHERE id = :i"),
                     {"i": ids["T1"]})
    await _closure_agrees(db, "territory", "territory_closure")


async def test_a_cycle_is_refused(db: AsyncSession) -> None:
    """Unguarded, the closure stops terminating and every RLS subtree query with
    it."""
    ids = await _tree(db)
    with pytest.raises((IntegrityError, InternalError), match="own descendant"):
        await db.execute(text("UPDATE territory SET parent_id = :p WHERE id = :i"),
                         {"p": ids["V1"], "i": ids["S"]})


async def test_self_parenting_is_refused(db: AsyncSession) -> None:
    ids = await _tree(db)
    with pytest.raises(IntegrityError, match="not_own_parent"):
        await db.execute(text("UPDATE territory SET parent_id = id WHERE id = :i"),
                         {"i": ids["T2"]})


async def test_deleting_a_leaf_cascades_its_closure_rows(db: AsyncSession) -> None:
    """The delete case is the FK cascade, not a third trigger."""
    ids = await _tree(db)
    await db.execute(text("DELETE FROM territory WHERE id = :i"), {"i": ids["V1"]})
    await _closure_agrees(db, "territory", "territory_closure")


async def test_deleting_a_node_with_children_is_refused(db: AsyncSession) -> None:
    ids = await _tree(db)
    with pytest.raises(IntegrityError):
        await db.execute(text("DELETE FROM territory WHERE id = :i"), {"i": ids["D1"]})


async def test_a_multirow_insert_listing_a_child_first_still_builds_ancestry(
        db: AsyncSession) -> None:
    """The cross-vendor review's X-6, and the reason ancestry is walked over the
    node table rather than the closure.

    AFTER ROW triggers fire in row order, so a child listed before its parent runs
    its trigger while the parent has no closure row yet. Reading the closure, the
    child silently got its self row and nothing else - no error, no missing FK,
    just a lost ancestor. A bulk territory import is exactly this shape.
    """
    child, parent = str(uuid.uuid4()), str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO territory (id, level, name, parent_id) VALUES "
             "(:c, 'taluka', 'child', :p), (:p, 'district', 'parent', NULL)"),
        {"c": child, "p": parent},
    )
    await _closure_agrees(db, "territory", "territory_closure")
    depth = await db.execute(text(
        "SELECT depth FROM territory_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": parent, "d": child})
    assert depth.scalar_one() == 1, "the child kept only its self row"


async def test_a_deep_multirow_insert_in_reverse_order(db: AsyncSession) -> None:
    """The general case: a whole branch inserted leaf-first in one statement."""
    ids = [str(uuid.uuid4()) for _ in range(4)]
    rows = ", ".join(
        f"(:i{n}, 'village', 'n{n}', {'NULL' if n == 3 else f':i{n + 1}'})"
        for n in range(4)
    )
    await db.execute(text(f"INSERT INTO territory (id, level, name, parent_id) VALUES {rows}"),
                     {f"i{n}": ids[n] for n in range(4)})
    await _closure_agrees(db, "territory", "territory_closure")
    depth = await db.execute(text(
        "SELECT depth FROM territory_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": ids[3], "d": ids[0]})
    assert depth.scalar_one() == 3


async def test_org_unit_closure_uses_the_same_function(db: AsyncSession) -> None:
    """One closure_maintain() serves all three trees; 004 wired partner_closure to
    it. A test on territory alone would not catch a wrong TG_ARGV."""
    parent = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level) VALUES ('hq', 5) RETURNING id"))).scalar_one()
    child = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, parent_id) VALUES ('rajkot', 2, :p) "
        "RETURNING id"), {"p": parent})).scalar_one()
    await _closure_agrees(db, "org_unit", "org_closure")
    depth = await db.execute(text(
        "SELECT depth FROM org_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": parent, "d": child})
    assert depth.scalar_one() == 1


# ── 002, the rest ────────────────────────────────────────────────────────────

async def test_set_updated_at_overrides_a_stale_value(db: AsyncSession) -> None:
    """now() is transaction time, so a row created and updated in one transaction
    keeps one stamp. The trigger is asserted against a value it has to move."""
    tid = (await db.execute(text(
        "INSERT INTO territory (level, name, updated_at) "
        "VALUES ('state','probe', now() - interval '10 days') RETURNING id"))).scalar_one()
    moved = await db.execute(text(
        "UPDATE territory SET name = 'probe2' WHERE id = :i "
        "RETURNING updated_at = now()"), {"i": tid})
    assert moved.scalar_one() is True


@pytest.mark.parametrize("table", ["territory", "org_unit", "channel_partner"])
async def test_common_columns_are_present(db: AsyncSession, table: str) -> None:
    """Proposed-Schema.md section 1.2. Missing one of these is only discovered when
    a later feature tries to soft-delete or sync the row."""
    cols = set((await db.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
        {"t": table})).scalars().all())
    assert {"id", "created_at", "created_by", "updated_at", "updated_by",
            "deleted_at", "external_id", "source_system", "synced_at"} <= cols


@pytest.mark.parametrize("closure", ["territory_closure", "org_closure", "partner_closure"])
async def test_closure_has_the_upward_index(db: AsyncSession, closure: str) -> None:
    """The primary key covers the downward walk. Every RLS policy in RBAC.md
    section 5 runs the upward one, and rule 9 admits no exceptions."""
    idx = (await db.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE tablename = :t"),
        {"t": closure})).scalars().all()
    assert any("(descendant_id)" in d for d in idx), idx
