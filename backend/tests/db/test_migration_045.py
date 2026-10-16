"""Migration 045 (FS-042): the LUT table and the export and sample CHECKs, as the
table sees them. Every test runs in the `db` fixture's transaction and is rolled
back. The definers' refusals are exercised end to end in
tests/api/test_export_sample_orders.py."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import random
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _gstin(db: AsyncSession) -> str:
    tag = uuid.uuid4().hex[:6]
    state = str((await db.execute(text(
        "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
        {"n": f"m045_{tag}", "c": ("Q" + tag[:3]).upper()})).scalar_one())
    return str((await db.execute(text(
        "INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, effective_from) "
        "VALUES (:g, 'm045', CAST(:s AS uuid), DATE '2019-01-01') RETURNING id"),
        {"g": f"{random.randint(10, 37)}AB{random.choice('CDEFGH')}DE{random.randint(1000, 9999)}F1Z{random.randint(1, 9)}",
         "s": state})).scalar_one())


async def _lut(db: AsyncSession, gstin: str, arn: str, f: str, t: str) -> None:
    await db.execute(text("INSERT INTO seller_gstin_lut (seller_gstin_id, arn, valid_from, valid_to) "
                          "VALUES (CAST(:g AS uuid), :a, CAST(:f AS date), CAST(:t AS date))"),
                     {"g": gstin, "a": arn, "f": dt.date.fromisoformat(f), "t": dt.date.fromisoformat(t)})


async def _refused(db: AsyncSession, sql: str, params: dict[str, object], constraint: str) -> None:
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(sql), params)
        await sp.rollback()
    assert constraint in str(err.value), err.value


async def test_a_lut_is_one_financial_year_and_never_overlaps_on_its_registration(db: AsyncSession) -> None:
    g, other = await _gstin(db), await _gstin(db)
    await _lut(db, g, "AD0000000001", "2026-04-01", "2027-03-31")
    await _lut(db, g, "AD0000000002", "2027-04-01", "2028-03-31")   # the next year, adjacent
    await _lut(db, other, "AD0000000001", "2026-04-01", "2027-03-31")   # another registration
    ins = ("INSERT INTO seller_gstin_lut (seller_gstin_id, arn, valid_from, valid_to) "
           "VALUES (CAST(:g AS uuid), :a, CAST(:f AS date), CAST(:t AS date))")
    d = dt.date.fromisoformat
    await _refused(db, ins, {"g": g, "a": "AD0000000003", "f": d("2027-01-01"), "t": d("2027-03-31")},
                   "ex_seller_gstin_lut_overlap")
    await _refused(db, ins, {"g": g, "a": "AD0000000004", "f": d("2028-04-01"), "t": d("2029-04-01")},
                   "ck_seller_gstin_lut_one_year")
    await _refused(db, ins, {"g": g, "a": "AD0000000001", "f": d("2029-04-01"), "t": d("2030-03-31")},
                   "uq_seller_gstin_lut_arn")
    await _refused(db, ins, {"g": g, "a": "lower-case!", "f": d("2029-04-01"), "t": d("2030-03-31")},
                   "seller_gstin_lut_arn_check")
    got = (await db.execute(text("SELECT seller_gstin_lut_on(CAST(:g AS uuid), DATE '2027-03-31'), "
                                 "seller_gstin_lut_on(CAST(:g AS uuid), DATE '2027-04-01'), "
                                 "seller_gstin_lut_on(CAST(:g AS uuid), DATE '2030-01-01')"),
                            {"g": g})).one()
    assert tuple(got) == ("AD0000000001", "AD0000000002", None)


async def test_app_role_reads_and_adds_luts_but_never_updates_or_deletes_them(db: AsyncSession) -> None:
    grants = (await db.execute(text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_name = 'seller_gstin_lut' AND grantee = 'app_role' ORDER BY 1"))).scalars().all()
    assert grants == ["INSERT", "SELECT"]
    assert (await db.execute(text(
        "SELECT relrowsecurity FROM pg_class WHERE relname = 'seller_gstin_lut'"))).scalar_one()
    for fn in ("seller_gstin_lut_delete(uuid)", "seller_gstin_lut_on(uuid, date)"):
        assert (await db.execute(text("SELECT has_function_privilege('app_role', :f, 'EXECUTE')"),
                                 {"f": fn})).scalar_one(), fn
    cols = (await db.execute(text(
        "SELECT column_name, privilege_type FROM information_schema.column_privileges "
        "WHERE table_name = 'sales_order' AND grantee = 'app_role' AND privilege_type IN ('INSERT', 'UPDATE') "
        "AND column_name IN ('tax_treatment', 'export_country', 'sample_pricing', 'lut_arn', 'amended_from_gross')"))).all()
    assert {(c, p) for c, p in cols} == {(c, p) for c in ("tax_treatment", "export_country", "sample_pricing")
                                         for p in ("INSERT", "UPDATE")}, "lut_arn is order_submit's"


async def test_the_checks_hold_an_export_and_a_free_sample_together(db: AsyncSession) -> None:
    """Rules 6, 2 and 11 at the table: a row a direct caller writes is held to the
    same shape the service writes."""
    g = await _gstin(db)
    state = (await db.execute(text("SELECT state_territory_id FROM seller_gstin WHERE id = CAST(:g AS uuid)"),
                              {"g": g})).scalar_one()
    office = (await db.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, :t) RETURNING id"),
        {"n": f"m045_office_{uuid.uuid4().hex[:6]}", "t": state})).scalar_one()
    row = (await db.execute(text(
        "INSERT INTO sales_order (order_type, party_name, owner_org_unit_id, territory_id, seller_gstin_id, "
        "place_of_supply_territory_id, place_of_supply_state_id, intra_state, price_effective_date) "
        "VALUES ('commercial', 'm045', :o, :s, CAST(:g AS uuid), :s, :s, true, DATE '2020-06-15') RETURNING id"),
        {"o": office, "s": state, "g": g})).scalar_one()
    upd = "UPDATE sales_order SET {set} WHERE id = CAST(:o AS uuid)"
    o = {"o": str(row)}
    await _refused(db, upd.format(set="tax_treatment = 'export_lut'"), o, "ck_sales_order_export_treatment")
    await _refused(db, upd.format(set="export_country = 'Kenya'"), o, "ck_sales_order_export_party")
    await _refused(db, upd.format(set="order_type = 'export', tax_treatment = 'export_igst'"), o,
                   "ck_sales_order_export_party")
    await _refused(db, upd.format(set="sample_pricing = 'free'"), o, "ck_sales_order_sample_pricing")
    await _refused(db, upd.format(set="order_type = 'sample'"), o, "ck_sales_order_sample_pricing")
    await _refused(db, upd.format(set="lut_arn = 'AD0000000001'"), o, "ck_sales_order_lut")



async def test_lut_rows_are_read_with_products_view_and_written_with_products_edit(db: AsyncSession) -> None:
    """Code review F-3: the table refuses a caller the router would, with the
    router out of the way."""
    g = await _gstin(db)
    await _lut(db, g, "AD0000000009", "2026-04-01", "2027-03-31")
    user = (await db.execute(text(
        "SELECT u.id FROM app_user u JOIN role r ON r.id = u.role_id "
        "WHERE u.is_active AND u.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM role_permission p "
        "WHERE p.role_id = r.id AND p.module = 'products') LIMIT 1"))).scalar_one_or_none()
    if user is None:
        pytest.skip("every role here holds a products permission")
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": str(user)})
    await enter_role(db, "app_role")
    seen = (await db.execute(text("SELECT count(*) FROM seller_gstin_lut WHERE arn = 'AD0000000009'"))).scalar_one()
    assert seen == 0
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(
                "INSERT INTO seller_gstin_lut (seller_gstin_id, arn, valid_from, valid_to) "
                "VALUES (CAST(:g AS uuid), 'AD0000000010', DATE '2027-04-01', DATE '2028-03-31')"), {"g": g})
        await sp.rollback()
    assert "row-level security" in str(err.value) or "42501" in str(err.value), err.value
