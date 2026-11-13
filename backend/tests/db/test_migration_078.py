# ruff: noqa: E501  (SQL inline)

"""078 (FS-071) in the database: the two setting kinds, the old create gone, and the
downgrade's refusals. Each test runs in the `db` fixture's transaction and is rolled
back. The flows are over the API in tests/api/test_fs071_partner_applications.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.conftest import Fixtures, make_partner_user, make_staff
from tests.db.test_migration_012 import _as, _as_owner, _grant

VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _refused(db: AsyncSession, sql: str, params: dict[str, object], needle: str) -> None:
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await db.execute(text(sql), params)
        await sp.rollback()
    assert needle in str(err.value), err.value


_UPD = "UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"


async def test_the_seven_settings_and_their_defaults(db: AsyncSession) -> None:
    rows = dict((await db.execute(text(
        "SELECT key::text, kind FROM app_setting WHERE key IN ('dealer_deposit_amount', 'distributor_deposit_amount', "
        "'deposit_relaxation_roles', 'dealer_application_deciders', 'distributor_application_deciders', "
        "'dealer_application_required', 'distributor_application_required')"))).all())
    assert rows == {"dealer_deposit_amount": "int", "distributor_deposit_amount": "int",
                    "deposit_relaxation_roles": "staff_roles", "dealer_application_deciders": "staff_roles",
                    "distributor_application_deciders": "staff_roles", "dealer_application_required": "set",
                    "distributor_application_required": "set"}


async def test_the_default_deciders_are_fs051s_people(db: AsyncSession) -> None:
    """FS-051 let a line role at level 3 or more decide, or a holder of global
    partners.create. Over the seeded roles (tests add api_adm_* roles of their own),
    that is exactly the default list (plan review R-6)."""
    seeded = ("field_officer", "district_manager", "state_manager", "regional_manager", "md_ceo",
              "admin_sales", "account_manager", "dispatch_manager", "qc_manager", "marketing",
              "state_coordinator", "support", "board", "intake")
    old_rule = {r for (r,) in (await db.execute(text(
        "SELECT r.code::text FROM role r WHERE r.code = ANY(:s) AND r.deleted_at IS NULL AND ("
        " (NOT r.is_functional AND NOT r.is_portal AND r.level >= 3)"
        " OR EXISTS (SELECT 1 FROM role_permission rp WHERE rp.role_id = r.id AND rp.module = 'partners' "
        "            AND rp.action = 'create' AND rp.scope = 'global' AND rp.deleted_at IS NULL))"),
        {"s": list(seeded)})).all()}
    default = set((await db.execute(text(
        "SELECT jsonb_array_elements_text(value) FROM app_setting WHERE key = 'dealer_application_deciders'"))).scalars())
    assert old_rule and default == old_rule


async def test_staff_roles_needs_one_staff_role_each_once(db: AsyncSession) -> None:
    k = {"k": "dealer_application_deciders"}
    await db.execute(text(_UPD), {**k, "v": '["regional_manager"]'})
    for bad, needle in (("[]", "at least one role"), ('["dealer"]', "no staff role"),
                        ('["system"]', "is not a staff role"), ('["md_ceo", "md_ceo"]', "listed twice"),
                        ('["no_such_role"]', "no staff role"), ('"md_ceo"', "at least one role"),
                        ("[1]", "is not a staff role")):
        await _refused(db, _UPD, {**k, "v": bad}, needle)


async def test_a_set_holds_some_of_allowed_once_each(db: AsyncSession) -> None:
    k = {"k": "distributor_application_required"}
    await db.execute(text(_UPD), {**k, "v": '["manpower", "vehicles"]'})
    await db.execute(text(_UPD), {**k, "v": "[]"})
    for bad, needle in (('["pan"]', "is not one of"), ('["manpower", "manpower"]', "listed twice"),
                        ('"manpower"', "a list from"), ("[3]", "is not one of")):
        await _refused(db, _UPD, {**k, "v": bad}, needle)


async def test_the_seven_argument_create_is_gone(db: AsyncSession) -> None:
    """Edge E-1: a caller left on the old signature would make an application with no
    deposit. It is dropped, and the deposit columns have no DEFAULT."""
    gone = (await db.execute(text(
        "SELECT to_regprocedure('dealer_application_create(text,text,text,uuid,uuid,text,timestamptz)')"))).scalar_one()
    assert gone is None
    defaults = (await db.execute(text(
        "SELECT count(*) FROM information_schema.columns WHERE table_name = 'dealer_application' "
        "AND column_name IN ('deposit_set', 'deposit_due') AND column_default IS NOT NULL"))).scalar_one()
    assert defaults == 0


async def test_app_role_cannot_write_the_entries(db: AsyncSession) -> None:
    """Append only, through the definers: app_role reads, never writes."""
    privs = (await db.execute(text(
        "SELECT has_table_privilege('app_role', 'dealer_application_deposit_entry', 'SELECT'), "
        "has_table_privilege('app_role', 'dealer_application_deposit_entry', 'INSERT'), "
        "has_table_privilege('app_role', 'dealer_application_deposit_entry', 'UPDATE'), "
        "has_table_privilege('app_role', 'dealer_application_deposit_entry', 'DELETE')"))).one()
    assert tuple(privs) == (True, False, False, False)


# ── the downgrade ────────────────────────────────────────────────────────────

class _Op:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.sql.append(sql)


def _078() -> Any:
    spec = importlib.util.spec_from_file_location("m078", VERSIONS / "078_partner_application_deposit.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _run(db: AsyncSession, step: str) -> None:
    m = _078()
    op = _Op()
    m.op = op
    getattr(m, step)()
    conn = await db.connection()
    for sql in op.sql:
        await conn.exec_driver_sql(sql)


async def _application(db: AsyncSession) -> str:
    await _as_owner(db)
    return str((await db.execute(text(
        "INSERT INTO dealer_application (firm_name, contact_name, mobile, territory_id, token_hash, link_expires_at, "
        "  created_by, deposit_set, deposit_due) "
        "SELECT 'Mig Firm', 'Mig', '919812345678', (SELECT id FROM territory LIMIT 1), md5(random()::text), "
        "  now() + interval '1 day', (SELECT id FROM app_user WHERE user_type = 'staff' LIMIT 1), 0, 0 "
        "RETURNING id"))).scalar_one())


async def test_the_migration_round_trips_over_a_plain_application(db: AsyncSession) -> None:
    await _application(db)
    await _run(db, "downgrade")
    await _run(db, "upgrade")
    assert (await db.execute(text(
        "SELECT count(*) FROM dealer_application WHERE firm_name = 'Mig Firm' AND deposit_set = 0 "
        "AND partner_type = 'dealer'"))).scalar_one() == 1


@pytest.mark.parametrize("change", [
    "UPDATE dealer_application SET partner_type = 'distributor' WHERE id = CAST(:a AS uuid)",
    # code review F-7: a pending deposit with no entry yet would come back not_required
    "UPDATE dealer_application SET deposit_set = 100, deposit_due = 100 WHERE id = CAST(:a AS uuid)",
    "UPDATE dealer_application SET manpower = '[{\"category\": \"x\", \"people\": 1}]' WHERE id = CAST(:a AS uuid)",
    "INSERT INTO record_document (record_type, record_id, doc_type, storage_key, filename, content_type, "
    "  size_bytes, sha256, deleted_at) VALUES ('dealer_application', CAST(:a AS uuid), 'deposit_slip', 'k', 'f.pdf', "
    "  'application/pdf', 1, md5('x') || md5('y'), now())",
])
async def test_the_downgrade_refuses_a_distributor_a_sheet_or_a_slip(db: AsyncSession, change: str) -> None:
    """E-24, plan review R-7: a deleted slip counts too, or the old doc-type CHECK fails."""
    app = await _application(db)
    await db.execute(text(change), {"a": app})
    async with db.begin_nested() as sp:
        with pytest.raises(DBAPIError) as err:
            await _run(db, "downgrade")
        await sp.rollback()
    assert "remove them first" in str(err.value), err.value


# ── RLS: the entries follow the application (E-23) ───────────────────────────

async def test_staff_of_another_district_and_a_dealer_read_no_entry(db: AsyncSession, ids: Fixtures) -> None:
    """The negative case: a role that sees partners in its own territory reads no
    deposit entry of an application elsewhere, and a partner user reads none at all.
    The positive case alongside shows the read is not simply empty."""
    await _as_owner(db)
    other = str((await db.execute(text("INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
                                  {"n": ids.unique("other")})).scalar_one())
    await _grant(db, ids.staff_role_id, "partners", ["view"], "territory")
    near = await make_staff(db, ids, email=ids.unique("near") + "@polysil.in")
    far = await make_staff(db, ids, email=ids.unique("far") + "@polysil.in")
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t), (:f, :o)"),
                     {"u": near, "t": ids.territory_id, "f": far, "o": other})
    dealer = await make_partner_user(db, ids, mobile="919800011122")
    app = str((await db.execute(text(
        "INSERT INTO dealer_application (firm_name, contact_name, mobile, territory_id, token_hash, link_expires_at, "
        "  created_by, deposit_set, deposit_due) VALUES ('RLS Firm', 'R', '919812300000', :t, md5(random()::text), "
        "  now() + interval '1 day', :u, 100, 50) RETURNING id"), {"t": ids.territory_id, "u": near})).scalar_one())
    await db.execute(text(
        "INSERT INTO dealer_application_deposit_entry (application_id, kind, amount, from_due, reason, created_by) "
        "VALUES (:a, 'relaxation', 50, 100, 'old partner', :u)"), {"a": app, "u": near})

    count = "SELECT count(*) FROM dealer_application_deposit_entry WHERE application_id = CAST(:a AS uuid)"
    for user, expected in ((near, 1), (far, 0), (dealer, 0)):
        async with db.begin_nested() as sp:
            await _as(db, user)
            assert (await db.execute(text(count), {"a": app})).scalar_one() == expected, user
            await sp.rollback()
