"""Migration 009's constraints refuse what they claim to, and its seeds are the
same figures the domain runs on (FS-008 section 10).

Two shapes are worth the round trips. The first is the effective-dating: an
exclusion constraint that looks right and is not, because `NULL = NULL` is not a
conflict and an empty daterange overlaps nothing. The second is the seed drift:
`api/domain/subsidy/defaults.py` and this migration state the same twenty-four
categories, seventeen parameters and seventeen rates, and nothing else compares
them, so a figure corrected in one and not the other would ship.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.domain.subsidy.defaults import CATEGORIES, SPRINKLER_RATES
from api.domain.subsidy.money import BLOCK_KEYS, LINE_KINDS
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = pytest.mark.db

TABLES = ("subsidy_scheme", "subsidy_system", "subsidy_category", "unit_cost_matrix",
          "unit_cost_cell", "quantity_matrix", "quantity_matrix_cell", "subsidy_component_rate",
          "crop_lateral_spacing", "subsidy_parameter")


async def _scheme(db: AsyncSession) -> str:
    """The seeded scheme, for the tests that read what 009 wrote."""
    got = await db.execute(text("SELECT id FROM subsidy_scheme WHERE code = 'GGRC'"))
    return str(got.scalar_one())


async def _own_scheme(db: AsyncSession) -> str:
    """A scheme of this test's own, for anything that writes a matrix or a crop.

    GGRC carries the real masters once `scripts/load_subsidy_masters.py` has run,
    and a test matrix with an open-ended range would collide with the loaded one
    through the very constraint it is trying to prove. Rolled back with the
    session like everything else here."""
    got = await db.execute(text(
        "INSERT INTO subsidy_scheme (code, name) VALUES (:c, 'test scheme') RETURNING id"),
        {"c": f"T{uuid.uuid4().hex[:12].upper()}"})
    return str(got.scalar_one())


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")


async def _matrix(db: AsyncSession, scheme: str, *, frm: str, to: str | None,
                  variant: str = "regular", active: bool = True) -> None:
    """asyncpg binds a date as a date; a string reaches its codec and raises."""
    await db.execute(
        text("INSERT INTO unit_cost_matrix (scheme_id, system_type, variant, dimensionality, "
             "effective_from, effective_to, is_active, source) "
             "VALUES (:s, 'drip', CAST(:v AS subsidy_matrix_variant), 2, :f, :t, :a, 'test')"),
        {"s": uuid.UUID(scheme), "v": variant, "f": dt.date.fromisoformat(frm),
         "t": dt.date.fromisoformat(to) if to else None, "a": active})


# ── the effective-dating, one round trip per claim ───────────────────────────

async def test_two_matrices_in_force_at_once_are_refused(db: AsyncSession) -> None:
    scheme = await _own_scheme(db)
    await _matrix(db, scheme, frm="2031-01-01", to=None)
    with pytest.raises(DBAPIError) as err:
        await _matrix(db, scheme, frm="2026-06-01", to=None)
    assert "ex_unit_cost_matrix" in str(err.value)
    await db.rollback()


async def test_adjacent_ranges_are_accepted_and_the_end_is_exclusive(db: AsyncSession) -> None:
    """A row in force to 2026-06-13 and its successor from 2026-06-13 do not
    overlap: `daterange(..., '[)')` excludes the upper bound."""
    scheme = await _own_scheme(db)
    await _matrix(db, scheme, frm="2031-01-01", to="2031-06-13")
    await _matrix(db, scheme, frm="2031-06-13", to=None)
    got = await db.execute(text(
        "SELECT count(*) FROM unit_cost_matrix WHERE scheme_id = :s AND system_type = 'drip' "
        "AND daterange(effective_from, effective_to, '[)') @> DATE '2031-06-13'"), {"s": scheme})
    assert got.scalar_one() == 1
    await db.rollback()


async def test_an_empty_range_is_refused_by_the_check_not_the_constraint(db: AsyncSession) -> None:
    """`effective_from = effective_to` is a row in force for no day at all, and an
    exclusion constraint accepts it because an empty range overlaps nothing."""
    scheme = await _own_scheme(db)
    with pytest.raises(DBAPIError) as err:
        await _matrix(db, scheme, frm="2031-06-13", to="2031-06-13")
    assert "ck_unit_cost_matrix_range" in str(err.value)
    await db.rollback()


async def test_deactivating_a_row_does_not_free_its_range(db: AsyncSession) -> None:
    """`is_active` hides a row from the config endpoint. Closing it is
    `effective_to`, and only that."""
    scheme = await _own_scheme(db)
    await _matrix(db, scheme, frm="2031-01-01", to=None, active=False)
    with pytest.raises(DBAPIError) as err:
        await _matrix(db, scheme, frm="2031-03-01", to=None)
    assert "ex_unit_cost_matrix" in str(err.value)
    await db.rollback()


async def test_the_two_variants_of_one_system_do_not_collide(db: AsyncSession) -> None:
    scheme = await _own_scheme(db)
    await _matrix(db, scheme, frm="2031-01-01", to=None, variant="regular")
    await _matrix(db, scheme, frm="2031-01-01", to=None, variant="seven_year")
    await db.rollback()


# ── the nullable discriminators ──────────────────────────────────────────────

async def test_two_overlapping_all_system_parameters_are_refused(db: AsyncSession) -> None:
    """The case a single `system_type WITH =` would have let through: both rows
    carry NULL, and NULL = NULL is not a conflict."""
    scheme = await _scheme(db)
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(
            "INSERT INTO subsidy_parameter (scheme_id, system_type, key, value, unit, "
            "effective_from) VALUES (:s, NULL, 'education_amount', 1200, 'rupees', "
            "DATE '2031-01-01')"), {"s": scheme})
    assert "ex_subsidy_parameter_all_systems" in str(err.value)
    await db.rollback()


async def test_a_system_parameter_may_sit_beside_the_all_system_row(db: AsyncSession) -> None:
    """The override of rule 5: a Drip row and the every-system row for one key."""
    scheme = await _scheme(db)
    await db.execute(text(
        "INSERT INTO subsidy_parameter (scheme_id, system_type, key, value, unit, effective_from) "
        "VALUES (:s, 'drip', 'education_amount', 0, 'rupees', DATE '2031-06-13')"), {"s": scheme})
    got = await db.execute(text(
        "SELECT count(*) FROM subsidy_parameter WHERE scheme_id = :s AND key = 'education_amount'"),
        {"s": scheme})
    assert got.scalar_one() == 2
    await db.rollback()


async def test_two_overlapping_rates_for_one_size_are_refused(db: AsyncSession) -> None:
    scheme = await _scheme(db)
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(
            "INSERT INTO subsidy_component_rate (scheme_id, system_type, component_code, "
            "pipe_size_mm, nozzle, rate, description, uom, source_cell, effective_from) "
            "VALUES (:s, 'sprinkler', 'pipe', 75, NULL, 600, 'x', 'Mtr.', 'test', "
            "DATE '2031-09-01')"), {"s": scheme})
    assert "ex_subsidy_component_rate_sized" in str(err.value)
    await db.rollback()


async def test_the_two_nozzle_rates_do_not_collide_with_each_other(db: AsyncSession) -> None:
    """Both carry a NULL pipe size and the same component code; only the nozzle
    tells them apart, which is why that constraint is the `IS NOT NULL` half."""
    scheme = await _scheme(db)
    got = await db.execute(text(
        "SELECT count(*) FROM subsidy_component_rate WHERE scheme_id = :s "
        "AND component_code = 'nozzle' AND pipe_size_mm IS NULL"), {"s": scheme})
    assert got.scalar_one() == 2
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(
            "INSERT INTO subsidy_component_rate (scheme_id, system_type, component_code, "
            "pipe_size_mm, nozzle, rate, description, uom, source_cell, effective_from) "
            "VALUES (:s, 'sprinkler', 'nozzle', NULL, 'brass', 310, 'x', 'No.', 'test', "
            "DATE '2031-09-01')"), {"s": scheme})
    assert "ex_subsidy_component_rate_nozzle" in str(err.value)
    await db.rollback()


async def test_a_one_dimensional_cell_cannot_be_written_twice(db: AsyncSession) -> None:
    """Sprinkler cells carry a NULL spacing, so a plain unique on three columns
    would admit the same area twice."""
    scheme = await _own_scheme(db)
    await _matrix(db, scheme, frm="2031-01-01", to=None)
    mid = (await db.execute(text(
        "SELECT id FROM unit_cost_matrix WHERE scheme_id = :s AND effective_from = "
        "DATE '2031-01-01'"), {"s": uuid.UUID(scheme)})).scalar_one()
    ins = text("INSERT INTO unit_cost_cell (matrix_id, lateral_spacing, area_breakpoint, "
               "unit_cost) VALUES (:m, NULL, 1.0, :c)")
    await db.execute(ins, {"m": mid, "c": "23182"})
    with pytest.raises(DBAPIError) as err:
        await db.execute(ins, {"m": mid, "c": "24194"})
    assert "uq_unit_cost_cell" in str(err.value)
    await db.rollback()


async def test_the_category_percentage_is_effective_dated(db: AsyncSession) -> None:
    """A percentage is a money input, so a quotation dated before a revision has to
    reproduce the old figure. `is_active` alone cannot do that, and the natural key
    is therefore a range, not a plain unique."""
    scheme = await _scheme(db)
    ins = text("INSERT INTO subsidy_category (scheme_id, system_type, code, name, pct, variant, "
               "effective_from, effective_to) VALUES (:s, 'drip', 'small_farmer', 'x', 75, "
               "'regular', :f, :t)")
    with pytest.raises(DBAPIError) as err:
        await db.execute(ins, {"s": uuid.UUID(scheme), "f": dt.date(2031, 9, 1), "t": None})
    assert "ex_subsidy_category" in str(err.value)
    await db.rollback()

    await db.execute(text("UPDATE subsidy_category SET effective_to = :t WHERE code = "
                          "'small_farmer' AND system_type = 'drip'"), {"t": dt.date(2031, 9, 1)})
    await db.execute(ins, {"s": uuid.UUID(scheme), "f": dt.date(2031, 9, 1), "t": None})
    got = await db.execute(text(
        "SELECT pct FROM subsidy_category WHERE code = 'small_farmer' AND system_type = 'drip' "
        "AND daterange(effective_from, effective_to, '[)') @> DATE '2031-08-31'"))
    assert Decimal(got.scalar_one()) == Decimal("70")
    await db.rollback()


async def test_the_standard_spacing_is_effective_dated_too(db: AsyncSession) -> None:
    """It picks the Jantri row, so it moves money as surely as a rate does."""
    scheme = await _own_scheme(db)
    ins = text("INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, "
               "effective_from, effective_to) VALUES (:s, 'Mango', :v, :f, :t)")
    await db.execute(ins, {"s": uuid.UUID(scheme), "v": 5, "f": dt.date(2031, 1, 1),
                           "t": dt.date(2031, 9, 1)})
    await db.execute(ins, {"s": uuid.UUID(scheme), "v": 6, "f": dt.date(2031, 9, 1), "t": None})
    with pytest.raises(DBAPIError) as err:
        await db.execute(ins, {"s": uuid.UUID(scheme), "v": 7, "f": dt.date(2026, 6, 1),
                               "t": None})
    assert "ex_crop_lateral_spacing" in str(err.value)
    await db.rollback()


# ── the two membership checks ────────────────────────────────────────────────

async def test_a_rounding_key_the_engine_does_not_know_is_refused(db: AsyncSession) -> None:
    with pytest.raises(DBAPIError) as err:
        await db.execute(text("UPDATE subsidy_system SET rounded_blocks = ARRAY['nonsense'] "
                              "WHERE system_type = 'drip'"))
    assert "ck_subsidy_system_blocks" in str(err.value)
    await db.rollback()


async def test_an_untrimmed_crop_name_is_refused(db: AsyncSession) -> None:
    """citext folds case but not whitespace, so without this check `' Mango '`
    would sit beside `'Mango'` as a second row and the lookup would find one."""
    scheme = await _own_scheme(db)
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(
            "INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, effective_from) "
            "VALUES (:s, ' Mango ', 5, DATE '2031-06-13')"), {"s": uuid.UUID(scheme)})
    assert "ck_crop_lateral_spacing_trimmed" in str(err.value)
    await db.rollback()


# ── the seeds are the figures the domain runs on ─────────────────────────────

async def test_the_seeded_categories_are_the_domain_defaults(db: AsyncSession) -> None:
    got = await db.execute(text(
        "SELECT system_type::text, code::text, name, pct, variant::text, gsdma_pct, per_ha_cap "
        "FROM subsidy_category ORDER BY system_type, sort_order"))
    rows = {(r[0], r[1]): r for r in got.all()}
    assert len(rows) == sum(len(v) for v in CATEGORIES.values()) == 24
    for system, cats in CATEGORIES.items():
        for cat in cats:
            row = rows[(system, cat.code)]
            assert row[2] == cat.name, (system, cat.code)
            assert Decimal(row[3]) == cat.pct
            assert row[4] == cat.variant
            assert (Decimal(row[5]) if row[5] is not None else None) == cat.gsdma_pct
            assert row[6] is None, "every per_ha_cap is seeded null (rule 11, GAP-084)"


async def test_the_seeded_rates_are_the_domain_defaults(db: AsyncSession) -> None:
    got = await db.execute(text(
        "SELECT component_code::text, pipe_size_mm, nozzle::text, rate, description, uom, "
        "source_cell FROM subsidy_component_rate"))
    rows = {(r[0], r[1], r[2]): r for r in got.all()}
    assert len(rows) == len(SPRINKLER_RATES) == 17
    for rate in SPRINKLER_RATES:
        row = rows[(rate.code, rate.pipe_size_mm, rate.nozzle)]
        assert Decimal(row[3]) == rate.rate, rate.code
        assert row[4] == rate.description, rate.code
        assert row[5] == rate.uom
        assert row[6], "every transcribed rate names the cell its formula came from"


async def test_the_seeded_rounding_arrays_are_the_domain_policies(db: AsyncSession) -> None:
    from api.domain.subsidy.defaults import POLICIES

    got = await db.execute(text(
        "SELECT system_type::text, rounded_blocks, rounded_lines FROM subsidy_system"))
    for system, blocks, lines in got.all():
        policy = POLICIES[system]
        assert set(blocks) == set(policy.rounding.blocks), system
        assert set(lines) == set(policy.rounding.lines), system
        assert set(blocks) <= set(BLOCK_KEYS) and set(lines) <= set(LINE_KINDS)


# ── RLS ──────────────────────────────────────────────────────────────────────

async def test_any_signed_in_principal_reads_the_masters(
        db: AsyncSession, ids: Fixtures) -> None:
    user = await make_staff(db, ids, email=ids.unique("reader") + "@example.com")
    await _as(db, user)
    for table in TABLES:
        await db.execute(text(f"SELECT count(*) FROM {table}"))
    got = await db.execute(text("SELECT count(*) FROM subsidy_category"))
    assert got.scalar_one() == 24
    await db.rollback()


async def test_a_partner_reads_them_too_and_writes_none_of_them(
        db: AsyncSession, ids: Fixtures) -> None:
    """A dealer holds no `masters.edit`, so the INSERT policy refuses the row.
    Reading is deliberate: the masters are global and carry nobody's data."""
    partner = await make_partner_user(db, ids, mobile="919" + f"{uuid.uuid4().int % 10**9:09d}")
    await _as(db, partner)
    got = await db.execute(text("SELECT count(*) FROM subsidy_parameter"))
    assert got.scalar_one() == 17
    with pytest.raises(DBAPIError) as err:
        await db.execute(text(
            "INSERT INTO crop_lateral_spacing (scheme_id, crop, standard_spacing, effective_from) "
            "SELECT id, 'Invented', 3, DATE '2031-06-13' FROM subsidy_scheme WHERE code = 'GGRC'"))
    assert "crop_lateral_spacing" in str(err.value)
    await db.rollback()


async def test_nobody_may_delete_a_master(db: AsyncSession, ids: Fixtures) -> None:
    """No DELETE grant anywhere: a rate in force cannot be removed out from under
    a quotation that used it (CLAUDE.md 4.1 rule 10)."""
    user = await make_staff(db, ids, email=ids.unique("deleter") + "@example.com")
    for table in ("subsidy_parameter", "subsidy_component_rate", "subsidy_category"):
        # The claim and the role are transaction-local, so the rollback at the foot
        # of the loop drops both and the next statement would run as the owner.
        await _as(db, user)
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(f"DELETE FROM {table}"))
        assert "permission denied" in str(err.value).lower(), table
        await db.rollback()


async def test_the_masters_are_closed_to_the_pre_auth_role(
        sessions: Callable[[], AsyncSession]) -> None:
    """`app_anon` has no grant on any of them, so the login surface cannot read a
    price list."""
    from api.config import get_settings

    anon = get_settings().db_anon_role
    if not anon:
        pytest.skip("DB_ANON_ROLE is unset")
    session = sessions()
    await enter_role(session, anon)
    with pytest.raises(DBAPIError) as err:
        await session.execute(text("SELECT count(*) FROM subsidy_component_rate"))
    assert "permission denied" in str(err.value).lower()
    await session.rollback()
