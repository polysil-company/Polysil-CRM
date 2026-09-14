"""Migration 004, against a real database.

The negatives carry the weight. The type-order trigger, the RESTRICT on parent_id
and the soft-deleted-parent refusal are the assertions that guard the table every
partner policy in FS-002 will read from, and each was found missing or wrong in
the FS-002a review before a line of it was written.

Grouped negatives use a savepoint per statement so one refusal does not abort the
rest of the test's transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures, make_partner_user
from tests.db.test_migrations_001_002 import _closure_agrees

pytestmark = pytest.mark.db

REFUSED = (IntegrityError, InternalError)


async def _partner(db: AsyncSession, ids: Fixtures, ptype: str, *, parent: str | None = None,
                   code: str | None = None, **cols: object) -> str:
    cols = {"partner_type": ptype,
            "code": code or ids.unique(ptype[:3].upper() + uuid.uuid4().hex[:4]),
            "name": f"{ptype} {uuid.uuid4().hex[:6]}", "territory_id": ids.territory_id,
            "price_tier": ptype, "parent_id": parent, **cols}
    names = ", ".join(cols)
    binds = ", ".join(f":{k}" for k in cols)
    return (await db.execute(text(
        f"INSERT INTO channel_partner ({names}) VALUES ({binds}) RETURNING id"),
        cols)).scalar_one()


async def _refused(db: AsyncSession, sql: str, params: dict, match: str) -> None:
    # pytest.raises OUTSIDE the savepoint. The other way round, the error is
    # swallowed inside the block, the savepoint tries to RELEASE on an aborted
    # transaction, and every statement after it fails with 25P02.
    with pytest.raises(REFUSED, match=match):
        async with db.begin_nested():
            await db.execute(text(sql), params)


# ── the closure ──────────────────────────────────────────────────────────────

async def test_closure_agrees_with_the_node_table(db: AsyncSession, ids: Fixtures) -> None:
    sub = await _partner(db, ids, "sub_dealer", parent=ids.dealer_id)
    await _closure_agrees(db, "channel_partner", "partner_closure")
    depth = (await db.execute(text(
        "SELECT depth FROM partner_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": ids.distributor_id, "d": sub})).scalar_one()
    assert depth == 2


async def test_a_child_first_multirow_insert_works(db: AsyncSession, ids: Fixtures) -> None:
    """The bulk-import shape. A BEFORE trigger cannot see the parent here; the
    constraint trigger in AFTER timing can. FS-002a EC-2, executed both ways."""
    ds, dl, sd = (str(uuid.uuid4()) for _ in range(3))
    await db.execute(text(
        "INSERT INTO channel_partner (id, parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES "
        "(:sd, :dl, 'sub_dealer', :c1, 'sd', :t, 'sub_dealer'), "
        "(:dl, :ds, 'dealer', :c2, 'dl', :t, 'dealer'), "
        "(:ds, NULL, 'distributor', :c3, 'ds', :t, 'distributor')"),
        {"sd": sd, "dl": dl, "ds": ds, "t": ids.territory_id,
         "c1": ids.unique("SD"), "c2": ids.unique("DL"), "c3": ids.unique("DS")})
    await _closure_agrees(db, "channel_partner", "partner_closure")


async def test_a_child_first_insert_that_is_type_illegal_is_still_refused(
        db: AsyncSession, ids: Fixtures) -> None:
    """The lenient fix for EC-2 skips the check when the parent is not visible and
    then stores two illegal edges. This is the assertion that catches it."""
    ds, sd = str(uuid.uuid4()), str(uuid.uuid4())
    await _refused(db,
        "INSERT INTO channel_partner (id, parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES "
        "(:sd, :ds, 'sub_dealer', :c1, 'sd', :t, 'sub_dealer'), "
        "(:ds, NULL, 'distributor', :c2, 'ds', :t, 'distributor')",
        {"sd": sd, "ds": ds, "t": ids.territory_id,
         "c1": ids.unique("SD"), "c2": ids.unique("DS")},
        "sub_dealer cannot sit under a distributor")


# ── the type order ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("child,parent_type", [
    ("sub_dealer", "distributor"),
    ("distributor", "dealer"),
    ("dealer", "sub_dealer"),
    ("distributor", "distributor"),
    ("dealer", "dealer"),
])
async def test_an_edge_that_skips_or_reverses_a_level_is_refused(
        db: AsyncSession, ids: Fixtures, child: str, parent_type: str) -> None:
    parent = await _partner(db, ids, parent_type)
    await _refused(db,
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, :ct, :c, 'x', :t, :tier)",
        {"p": parent, "ct": child, "tier": child, "c": ids.unique("X"), "t": ids.territory_id},
        f"{child} cannot sit under a {parent_type}")


@pytest.mark.parametrize("ptype", ["distributor", "dealer", "sub_dealer"])
async def test_a_root_may_be_any_type(db: AsyncSession, ids: Fixtures, ptype: str) -> None:
    """GAP-034. A direct dealer with no distributor above it is allowed until the
    client says otherwise."""
    await _partner(db, ids, ptype)


async def test_a_move_that_breaks_the_order_is_refused(db: AsyncSession, ids: Fixtures) -> None:
    sub = await _partner(db, ids, "sub_dealer", parent=ids.dealer_id)
    await _refused(db, "UPDATE channel_partner SET parent_id = :p WHERE id = :i",
                   {"p": ids.distributor_id, "i": sub},
                   "sub_dealer cannot sit under a distributor")


async def test_retyping_a_parent_whose_children_no_longer_fit_is_refused(
        db: AsyncSession, ids: Fixtures) -> None:
    """EC-6. The check runs against the children too, or a distributor with dealers
    under it quietly becomes a sub_dealer."""
    await _refused(db, "UPDATE channel_partner SET partner_type = 'sub_dealer', "
                       "price_tier = 'sub_dealer' WHERE id = :i",
                   {"i": ids.distributor_id}, "would no longer fit")


async def test_the_two_step_escape_is_closed(db: AsyncSession, ids: Fixtures) -> None:
    """Detach the dealer, then retype it. Its sub_dealer is still its child and
    still does not fit under a distributor."""
    await _partner(db, ids, "sub_dealer", parent=ids.dealer_id)
    await db.execute(text("UPDATE channel_partner SET parent_id = NULL WHERE id = :i"),
                     {"i": ids.dealer_id})
    await _refused(db, "UPDATE channel_partner SET partner_type = 'distributor', "
                       "price_tier = 'distributor' WHERE id = :i",
                   {"i": ids.dealer_id}, "would no longer fit")


async def test_a_cycle_is_refused_by_the_closure_guard(db: AsyncSession, ids: Fixtures) -> None:
    """Both AFTER triggers fire on UPDATE OF parent_id, in name order, so the closure
    trigger's cycle check runs first. EC-11: assert the message, not just the code,
    or this passes on the type trigger and proves nothing about the closure."""
    await _refused(db, "UPDATE channel_partner SET parent_id = :p WHERE id = :i",
                   {"p": ids.dealer_id, "i": ids.distributor_id},
                   "cannot be moved under its own descendant")


async def test_the_closure_trigger_sorts_before_the_type_trigger(db: AsyncSession) -> None:
    """F-7. Both AFTER triggers fire on UPDATE OF parent_id, in name order, and the
    cycle test above asserts the closure guard's message. Rename either trigger
    and this says why the cycle test broke."""
    names = (await db.execute(text(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'channel_partner'::regclass "
        "AND tgname IN ('trg_channel_partner_closure_move', 'trg_channel_partner_type_order') "
        "ORDER BY tgname"))).scalars().all()
    assert names == ["trg_channel_partner_closure_move", "trg_channel_partner_type_order"]


async def test_deferring_the_constraint_is_not_an_escape(db: AsyncSession,
                                                         ids: Fixtures) -> None:
    """F-11. DEFERRABLE lets a caller postpone the check to SET CONSTRAINTS IMMEDIATE
    or commit. Inside the window the illegal edge is visible; it never commits."""
    await db.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer')"),
        {"p": ids.distributor_id, "c": ids.unique("DEF"), "t": ids.territory_id})
    await _refused(db, "SET CONSTRAINTS ALL IMMEDIATE", {},
                   "sub_dealer cannot sit under a distributor")


async def test_a_shadowed_search_path_changes_nothing(db: AsyncSession, ids: Fixtures) -> None:
    """004a. Without SET search_path on the two tree functions, a schema that shadows
    channel_partner first on the path made the type check pass on NULL and made
    closure_maintain() write only the self row. Executed during the 004 review."""
    await db.execute(text("CREATE SCHEMA shadow_probe"))
    await db.execute(text(
        "CREATE TABLE shadow_probe.channel_partner (id uuid PRIMARY KEY, "
        "partner_type partner_type, deleted_at timestamptz, parent_id uuid)"))
    await db.execute(text(
        "CREATE TABLE shadow_probe.partner_closure (ancestor_id uuid, descendant_id uuid, "
        "depth int)"))
    await db.execute(text("SET LOCAL search_path = shadow_probe, public"))
    await _refused(db,
        "INSERT INTO public.channel_partner (parent_id, partner_type, code, name, "
        "territory_id, price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer')",
        {"p": ids.distributor_id, "c": ids.unique("SH"), "t": ids.territory_id},
        "sub_dealer cannot sit under a distributor")
    dealer = (await db.execute(text(
        "INSERT INTO public.channel_partner (parent_id, partner_type, code, name, "
        "territory_id, price_tier) VALUES (:p, 'dealer', :c, 'x', :t, 'dealer') RETURNING id"),
        {"p": ids.distributor_id, "c": ids.unique("SH2"), "t": ids.territory_id})).scalar_one()
    rows = (await db.execute(text(
        "SELECT count(*) FROM public.partner_closure WHERE descendant_id = :d"),
        {"d": dealer})).scalar_one()
    assert rows == 2, "closure_maintain() walked the shadow table and lost the ancestor row"


# ── soft delete and hard delete ──────────────────────────────────────────────

async def test_nothing_attaches_under_a_soft_deleted_parent(
        db: AsyncSession, ids: Fixtures) -> None:
    """EC-8, and the half of GAP-031 that needs no client answer."""
    await db.execute(text("UPDATE channel_partner SET deleted_at = now() WHERE id = :i"),
                     {"i": ids.dealer_id})
    await _refused(db,
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer')",
        {"p": ids.dealer_id, "c": ids.unique("X"), "t": ids.territory_id},
        "soft-deleted")


async def test_a_move_onto_a_soft_deleted_parent_is_refused(
        db: AsyncSession, ids: Fixtures) -> None:
    sub = await _partner(db, ids, "sub_dealer", parent=ids.dealer_id)
    other = await _partner(db, ids, "dealer", deleted_at=datetime(2026, 1, 1, tzinfo=UTC))
    await _refused(db, "UPDATE channel_partner SET parent_id = :p WHERE id = :i",
                   {"p": other, "i": sub}, "soft-deleted")


async def test_a_parent_cannot_be_deleted_from_under_its_children(
        db: AsyncSession, ids: Fixtures) -> None:
    await _refused(db, "DELETE FROM channel_partner WHERE id = :a",
                   {"a": ids.distributor_id}, "violates foreign key")


async def test_a_set_delete_is_a_known_hole_iss_053(db: AsyncSession,
                                                    ids: Fixtures) -> None:
    """EC-9, ISS-053. RESTRICT was proposed as the fix and does not help: RI checks
    fire at end of statement under RESTRICT too, so a DELETE naming parent and
    child together removes both and their closure rows. Executed, and asserted
    here so the hole is documented rather than believed closed. The guard is that
    app_role holds no DELETE on this table (FS-002 section 5.1); hard delete is an
    ops action."""
    await db.execute(text("DELETE FROM channel_partner WHERE id IN (:a, :b)"),
                     {"a": ids.distributor_id, "b": ids.dealer_id})
    left = (await db.execute(text(
        "SELECT count(*) FROM partner_closure WHERE ancestor_id IN (:a, :b)"),
        {"a": ids.distributor_id, "b": ids.dealer_id})).scalar_one()
    assert left == 0


async def test_a_leaf_delete_cascades_its_closure_rows(db: AsyncSession, ids: Fixtures) -> None:
    sub = await _partner(db, ids, "sub_dealer", parent=ids.dealer_id)
    await db.execute(text("DELETE FROM channel_partner WHERE id = :i"), {"i": sub})
    left = (await db.execute(text(
        "SELECT count(*) FROM partner_closure WHERE descendant_id = :i"), {"i": sub})).scalar_one()
    assert left == 0
    await _closure_agrees(db, "channel_partner", "partner_closure")


@pytest.mark.parametrize("table", ["channel_partner", "org_unit", "territory"])
async def test_app_role_cannot_hard_delete_a_tree_node(db: AsyncSession, table: str) -> None:
    """The guard ISS-053 names. Trivially true today because app_role holds nothing;
    red the day FS-002's grant block gives it DELETE by accident."""
    ok = (await db.execute(text(
        "SELECT has_table_privilege('app_role', :t, 'DELETE')"), {"t": table})).scalar_one()
    assert ok is False, f"app_role can hard-delete {table}"


async def test_a_subtree_move_rewrites_the_closure(db: AsyncSession, ids: Fixtures) -> None:
    """F-2. The move trigger is wired separately from the insert trigger, so a wrong
    TG_ARGV on it would leave every other test green and the closure stale."""
    other = await _partner(db, ids, "distributor")
    sub = await _partner(db, ids, "sub_dealer", parent=ids.dealer_id)
    await db.execute(text("UPDATE channel_partner SET parent_id = :p WHERE id = :i"),
                     {"p": other, "i": ids.dealer_id})
    await _closure_agrees(db, "channel_partner", "partner_closure")
    depth = (await db.execute(text(
        "SELECT depth FROM partner_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": other, "d": sub})).scalar_one()
    assert depth == 2
    stale = (await db.execute(text(
        "SELECT count(*) FROM partner_closure WHERE ancestor_id = :a AND descendant_id = :d"),
        {"a": ids.distributor_id, "d": sub})).scalar_one()
    assert stale == 0


# ── app_user.partner_id ──────────────────────────────────────────────────────

async def test_a_partner_user_must_point_at_a_real_partner(db: AsyncSession,
                                                           ids: Fixtures) -> None:
    """GAP-032 closed. The random uuid every fixture used to write is now refused."""
    await _refused(db,
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p)",
        {"m": "9199" + uuid.uuid4().hex[:8], "r": ids.portal_role_id, "p": str(uuid.uuid4())},
        "fk_app_user_partner_id")
    await make_partner_user(db, ids, mobile="9199" + uuid.uuid4().hex[:8])


async def test_the_partner_foreign_key_is_validated(db: AsyncSession) -> None:
    """004 adds it NOT VALID because a seeded database holds a partner_user that
    pointed at nothing. seed_demo.py creates that partner and validates. If this
    fails, run the seed."""
    ok = (await db.execute(text(
        "SELECT convalidated FROM pg_constraint WHERE conname = 'fk_app_user_partner_id'"
    ))).scalar_one()
    assert ok, "fk_app_user_partner_id is NOT VALID: run scripts/seed_demo.py"


async def test_a_partner_with_users_cannot_be_hard_deleted(db: AsyncSession,
                                                           ids: Fixtures) -> None:
    await make_partner_user(db, ids, mobile="9199" + uuid.uuid4().hex[:8])
    await _refused(db, "DELETE FROM channel_partner WHERE id = :i", {"i": ids.dealer_id},
                   "fk_app_user_partner_id")


# ── the column checks ────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ["", "  ", "ABC ", " ABC", "X" * 33])
async def test_a_malformed_code_is_refused(db: AsyncSession, ids: Fixtures, code: str) -> None:
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'x', :t, 'dealer')",
        {"c": code, "t": ids.territory_id}, "ck_channel_partner_code_shape")


async def test_code_is_unique_among_live_rows_only(db: AsyncSession, ids: Fixtures) -> None:
    """citext folds case. A closed partner's code can be reissued; a live one's cannot."""
    first = await _partner(db, ids, "dealer", code=ids.unique("SHAH"))
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'x', :t, 'dealer')",
        {"c": ids.unique("shah"), "t": ids.territory_id}, "uq_channel_partner_code")
    await db.execute(text("UPDATE channel_partner SET deleted_at = now() WHERE id = :i"),
                     {"i": first})
    await _partner(db, ids, "dealer", code=ids.unique("SHAH"))


async def test_a_gujarati_name_round_trips(db: AsyncSession, ids: Fixtures) -> None:
    name = "શાહ ઇરિગેશન, રાજકોટ"
    pid = await _partner(db, ids, "dealer", name=name)
    got = (await db.execute(text("SELECT name FROM channel_partner WHERE id = :i"),
                            {"i": pid})).scalar_one()
    assert got == name


@pytest.mark.parametrize("col,value,constraint", [
    ("gstin", "24aaacp1234a1z5", "gstin_format"),
    ("gstin", "24AAACP1234A1Y5", "gstin_format"),
    ("gstin", "", "gstin_format"),
    ("pan", "AAACP12345", "pan_format"),
    ("mobile", "+919876543210", "mobile_format"),
    ("mobile", "98765", "mobile_format"),
    ("credit_limit", Decimal("-1"), "credit_limit"),
    ("payment_terms_days", -30, "payment_terms"),
])
async def test_a_malformed_value_is_refused(db: AsyncSession, ids: Fixtures,
                                            col: str, value: object, constraint: str) -> None:
    await _refused(db,
        f"INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, "
        f"{col}) VALUES ('dealer', :c, 'x', :t, 'dealer', :v)",
        {"c": ids.unique("V"), "t": ids.territory_id, "v": value},
        f"ck_channel_partner_{constraint}")


async def test_well_formed_values_are_accepted(db: AsyncSession, ids: Fixtures) -> None:
    await _partner(db, ids, "dealer", gstin="24AAACP1234A1Z5", pan="AAACP1234A",
                   mobile="919876543210", is_gst_registered=True,
                   credit_limit=Decimal("250000.00"), payment_terms_days=30)


async def test_gst_registered_needs_a_gstin(db: AsyncSession, ids: Fixtures) -> None:
    """EC-14. '' is not NULL, so the format check is what refuses it, not the
    registered check. Both are asserted here."""
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, "
        "is_gst_registered) VALUES ('dealer', :c, 'x', :t, 'dealer', true)",
        {"c": ids.unique("G"), "t": ids.territory_id}, "gstin_when_registered")
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, "
        "is_gst_registered, gstin) VALUES ('dealer', :c, 'x', :t, 'dealer', true, '')",
        {"c": ids.unique("G"), "t": ids.territory_id}, "gstin_format")


@pytest.mark.parametrize("ptype,tier,constraint", [
    ("dealer", "farmer", "tier_not_farmer|tier_matches_type"),
    ("sub_dealer", "distributor", "tier_matches_type"),
    ("dealer", "sub_dealer", "tier_matches_type"),
])
async def test_the_price_tier_follows_the_type(db: AsyncSession, ids: Fixtures,
                                               ptype: str, tier: str, constraint: str) -> None:
    """GAP-037. The reversible default: drop one CHECK if the client says otherwise."""
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES (:pt, :c, 'x', :t, :tier)",
        {"pt": ptype, "c": ids.unique("T"), "t": ids.territory_id, "tier": tier},
        f"ck_channel_partner_{constraint}")


async def test_the_same_external_row_cannot_be_imported_twice(db: AsyncSession,
                                                              ids: Fixtures) -> None:
    ext = ids.unique("ERP")
    await _partner(db, ids, "dealer", external_id=ext, source_system="erp")
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, "
        "external_id, source_system) VALUES ('dealer', :c, 'x', :t, 'dealer', :e, 'erp')",
        {"c": ids.unique("E"), "t": ids.territory_id, "e": ext}, "uq_channel_partner_external")


async def test_territory_is_required(db: AsyncSession, ids: Fixtures) -> None:
    """GAP-036. NOT NULL from the start, because it is the only staff-side scoping
    column and relaxing it later is one statement."""
    await _refused(db,
        "INSERT INTO channel_partner (partner_type, code, name, price_tier) "
        "VALUES ('dealer', :c, 'x', 'dealer')",
        {"c": ids.unique("N")}, "territory_id")


# ── the plumbing ─────────────────────────────────────────────────────────────

async def test_the_audit_trigger_fires(db: AsyncSession, ids: Fixtures) -> None:
    pid = await _partner(db, ids, "dealer")
    await db.execute(text("UPDATE channel_partner SET name = 'renamed' WHERE id = :i"),
                     {"i": pid})
    actions = (await db.execute(text(
        "SELECT action FROM audit_log WHERE table_name = 'channel_partner' AND row_id = :i"),
        {"i": pid})).scalars().all()
    # Both rows carry the same transaction-time `at`, so order by it is unstable.
    assert sorted(actions) == ["INSERT", "UPDATE"]


async def test_updated_at_moves_on_update(db: AsyncSession, ids: Fixtures) -> None:
    pid = await _partner(db, ids, "dealer", updated_at=datetime(2026, 1, 1, tzinfo=UTC))
    moved = (await db.execute(text(
        "UPDATE channel_partner SET name = 'x' WHERE id = :i RETURNING updated_at = now()"),
        {"i": pid})).scalar_one()
    assert moved is True


async def test_rls_is_enabled_on_the_table_and_on_the_closure(db: AsyncSession) -> None:
    """EC-19. 004 enabled channel_partner with no policies (fail closed) and left
    the closure open. 005 added the policies, and enabled the closure with an
    authenticated-read policy: the policies read it as the invoking user, and the
    definer trigger writes it."""
    rows = dict((await db.execute(text(
        "SELECT relname, relrowsecurity FROM pg_class "
        "WHERE relname IN ('channel_partner', 'partner_closure')"))).all())
    assert rows == {"channel_partner": True, "partner_closure": True}


@pytest.mark.parametrize("index", [
    "uq_channel_partner_code", "uq_channel_partner_external",
    "ix_channel_partner_parent", "ix_channel_partner_territory",
    "ix_partner_closure_descendant",
])
async def test_the_indexes_exist(db: AsyncSession, index: str) -> None:
    found = (await db.execute(text(
        "SELECT count(*) FROM pg_indexes WHERE indexname = :n"), {"n": index})).scalar_one()
    assert found == 1, index


async def test_the_type_order_function_is_not_public(db: AsyncSession) -> None:
    ok = (await db.execute(text(
        "SELECT has_function_privilege('public', 'channel_partner_type_order()', 'EXECUTE')"
    ))).scalar_one()
    assert ok is False
