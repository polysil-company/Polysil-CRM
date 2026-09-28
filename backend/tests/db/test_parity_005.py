"""Half two of the parity suite: row-scope parity per declared branch (FS-002 5.5).

For every ScopeSpec and every branch it declares, a witness pair: one row in
scope, one out. Both enforcers must give the same answer on both rows, and each
must be shown to do real work on a restricted branch:

  - enforcer 2: a raw SELECT with no service predicate returns only the in-scope
    witness, and a savepoint that opens the table with a permissive USING (true)
    policy makes the out-of-scope witness appear. As the owner it would be visible
    before and after, so this is also the proof the suite runs as app_role.
  - enforcer 1: with that policy in place the service predicate still excludes it.

Every declared branch has a witness or the coverage test fails, so a module cannot
ship a ScopeSpec without its parity rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, InternalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.modules import SPECS
from api.authz.predicate import Caller, parent_lookup, scope_predicate
from api.db.session import enter_role
from api.domain.authz import ScopeSpec
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]

REFUSED = (IntegrityError, InternalError, ProgrammingError, DBAPIError)

_ID = sa.Uuid()
TABLES = {
    "app_user": sa.table("app_user", sa.column("id", _ID), sa.column("org_unit_id", _ID),
                         sa.column("partner_id", _ID), sa.column("deleted_at")),
    "channel_partner": sa.table("channel_partner", sa.column("id", _ID),
                                sa.column("territory_id", _ID), sa.column("parent_id", _ID),
                                sa.column("deleted_at")),
    "lead": sa.table("lead", sa.column("id", _ID), sa.column("owner_user_id", _ID),
                     sa.column("owner_org_unit_id", _ID), sa.column("territory_id", _ID),
                     sa.column("assigned_partner_id", _ID), sa.column("deleted_at")),
    "quotation": sa.table("quotation", sa.column("id", _ID), sa.column("owner_user_id", _ID),
                          sa.column("owner_org_unit_id", _ID), sa.column("territory_id", _ID),
                          sa.column("partner_id", _ID), sa.column("deleted_at")),
    "sales_order": sa.table("sales_order", sa.column("id", _ID), sa.column("owner_user_id", _ID),
                            sa.column("owner_org_unit_id", _ID), sa.column("territory_id", _ID),
                            sa.column("partner_id", _ID), sa.column("deleted_at")),
    "task": sa.table("task", sa.column("id", _ID), sa.column("assigned_to", _ID),
                     sa.column("owner_org_unit_id", _ID)),
    "complaint": sa.table("complaint", sa.column("id", _ID), sa.column("owner_user_id", _ID),
                          sa.column("owner_org_unit_id", _ID), sa.column("partner_id", _ID),
                          sa.column("deleted_at")),
}


@dataclass
class Witness:
    caller: Caller
    expected: dict[str, bool]  # row id -> visible to this caller


Builder = Callable[[AsyncSession, Fixtures], Awaitable[Witness]]


# ── helpers ──────────────────────────────────────────────────────────────────

async def _grant(db: AsyncSession, role_id: str, module: str, actions: list[str],
                 scope: str) -> None:
    for action in actions:
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) "
            "VALUES (:r, :m, CAST(:a AS permission_action), CAST(:s AS permission_scope))"),
            {"r": role_id, "m": module, "a": action, "s": scope})


async def _role(db: AsyncSession, ids: Fixtures, code: str, *, portal: bool = False,
                level: int = 2) -> str:
    """A portal role's level must be its partner type's seeded level (007's
    role-family trigger): 3 at a distributor, 2 at a dealer, 1 at a sub-dealer."""
    return str((await db.execute(text(
        "INSERT INTO role (code, name, level, is_portal) VALUES (:c, :n, :l, :p) RETURNING id"),
        {"c": ids.unique(code), "n": code, "l": level, "p": portal})).scalar_one())


async def _staff(db: AsyncSession, ids: Fixtures, role_id: str, org_unit_id: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
        "VALUES ('staff', :e, 'x', :r, :o) RETURNING id"),
        {"e": ids.unique(uuid.uuid4().hex[:6]) + "@polysil.in", "r": role_id,
         "o": org_unit_id})).scalar_one())


async def _partner_user(db: AsyncSession, ids: Fixtures, role_id: str, partner_id: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p) RETURNING id"),
        {"m": "9188" + f"{uuid.uuid4().int % 10**8:08d}", "r": role_id,
         "p": partner_id})).scalar_one())


async def _org(db: AsyncSession, ids: Fixtures, name: str, parent: str | None = None,
               territory: str | None = None) -> str:
    return str((await db.execute(text(
        "INSERT INTO org_unit (name, role_level, parent_id, territory_id) "
        "VALUES (:n, 1, :p, :t) RETURNING id"),
        {"n": ids.unique(name), "p": parent, "t": territory})).scalar_one())


async def _territory(db: AsyncSession, ids: Fixtures, name: str) -> str:
    return str((await db.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": ids.unique(name)})).scalar_one())


async def _partner(db: AsyncSession, ids: Fixtures, code: str, territory: str,
                   parent: str | None = None, kind: str = "distributor") -> str:
    return str((await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, CAST(:k AS partner_type), :c, 'x', :t, "
        "CAST(:tier AS channel_tier)) RETURNING id"),
        {"p": parent, "k": kind, "tier": kind, "c": ids.unique(code),
         "t": territory})).scalar_one())


async def _lead(db: AsyncSession, ids: Fixtures, *, owner_user_id: str | None = None,
                owner_org_unit_id: str | None = None, territory_id: str | None = None,
                assigned_partner_id: str | None = None, deleted: bool = False) -> str:
    """A lead built as the owner. mis_system and lead_source are seeded by 006."""
    return str((await db.execute(text(
        "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, "
        "farmer_name, mobile, territory_id, owner_user_id, owner_org_unit_id, "
        "assigned_partner_id, deleted_at) VALUES (:no, 'commercial', "
        "(SELECT id FROM mis_system WHERE code = 'drip'), "
        "(SELECT id FROM lead_source WHERE code = 'employee'), 'Farmer', :mob, :terr, "
        ":ou, :oou, :ap, CASE WHEN :del THEN now() END) RETURNING id"),
        {"no": "POL-" + uuid.uuid4().hex[:12],
         "mob": "+9198" + f"{uuid.uuid4().int % 10**8:08d}",
         "terr": territory_id or ids.territory_id, "ou": owner_user_id,
         "oou": owner_org_unit_id or ids.org_unit_id, "ap": assigned_partner_id,
         "del": deleted})).scalar_one())


async def _quotation(db: AsyncSession, ids: Fixtures, *, owner_user_id: str | None = None,
                     owner_org_unit_id: str | None = None, territory_id: str | None = None,
                     partner_id: str | None = None, deleted: bool = False) -> str:
    """A draft quotation built as the owner, on a lead with the same scope: the
    scope columns mirror the lead's (FS-005 rule 11). The seller is the seeded
    registration; the place of supply is the row's own territory."""
    lead = await _lead(db, ids, owner_user_id=owner_user_id,
                       owner_org_unit_id=owner_org_unit_id, territory_id=territory_id,
                       assigned_partner_id=partner_id)
    return str((await db.execute(text(
        "INSERT INTO quotation (lead_id, sales_type, partner_id, owner_user_id, "
        "owner_org_unit_id, territory_id, party_name, party_mobile, seller_gstin_id, "
        "place_of_supply_territory_id, place_of_supply_state_id, intra_state, "
        "price_effective_date, deleted_at) VALUES (:lead, 'commercial', :p, :ou, :oou, :terr, "
        "'Farmer', '+919800000000', "
        "(SELECT id FROM seller_gstin ORDER BY is_default DESC LIMIT 1), "
        ":terr, :terr, true, CURRENT_DATE, CASE WHEN :del THEN now() END) RETURNING id"),
        {"lead": lead, "p": partner_id, "ou": owner_user_id,
         "oou": owner_org_unit_id or ids.org_unit_id, "terr": territory_id or ids.territory_id,
         "del": deleted})).scalar_one())


async def _order(db: AsyncSession, ids: Fixtures, *, owner_user_id: str | None = None,
                 owner_org_unit_id: str | None = None, territory_id: str | None = None,
                 partner_id: str | None = None, deleted: bool = False) -> str:
    """A draft sales order with no lead: the scope columns are the order's own
    (FS-011 rule 11), so a consolidated order with a null lead is covered too."""
    order = str((await db.execute(text(
        "INSERT INTO sales_order (order_type, partner_id, owner_user_id, owner_org_unit_id, "
        "territory_id, party_name, party_mobile, seller_gstin_id, "
        "place_of_supply_territory_id, place_of_supply_state_id, intra_state, "
        "price_effective_date) VALUES ('commercial', :p, :ou, :oou, :terr, "
        "'Farmer', '+919800000000', "
        "(SELECT id FROM seller_gstin ORDER BY is_default DESC LIMIT 1), "
        ":terr, :terr, true, CURRENT_DATE) RETURNING id"),
        {"p": partner_id, "ou": owner_user_id,
         "oou": owner_org_unit_id or ids.org_unit_id,
         "terr": territory_id or ids.territory_id})).scalar_one())
    if deleted:
        # the insert trigger refuses anything but a fresh draft, so delete after
        await db.execute(text("UPDATE sales_order SET deleted_at = now() WHERE id = :o"),
                         {"o": order})
    return order


async def _visible(db: AsyncSession, table: str, ids_: list[str],
                   predicate: sa.ColumnElement[bool] | None = None) -> set[str]:
    t = TABLES[table]
    stmt = sa.select(t.c.id).where(t.c.id.in_([uuid.UUID(str(i)) for i in ids_]))
    if predicate is not None:
        stmt = stmt.where(predicate)
    return {str(r) for r in (await db.execute(stmt)).scalars().all()}


async def _as(db: AsyncSession, user_id: str) -> None:
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
    await enter_role(db, "app_role")


async def _as_owner(db: AsyncSession) -> None:
    await db.execute(text("SELECT set_config('role', 'none', true)"))


# ── witnesses: users ─────────────────────────────────────────────────────────

async def users_own(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "fo")
    await _grant(db, role, "users", ["view"], "own")
    me = await _staff(db, ids, role, ids.org_unit_id)
    other = await _staff(db, ids, role, ids.org_unit_id)
    return Witness(Caller(me, ids.org_unit_id, None, {"users": "own"}), {me: True, other: False})


async def users_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dm")
    await _grant(db, role, "users", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    below = await _staff(db, ids, role, await _org(db, ids, "child", parent=ids.org_unit_id))
    outside = await _staff(db, ids, role, await _org(db, ids, "elsewhere"))
    return Witness(Caller(manager, ids.org_unit_id, None, {"users": "org_subtree"}),
                   {below: True, outside: False})


async def users_partner_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "users", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    below = str(await make_partner_user(db, ids, mobile="9188" + f"{uuid.uuid4().int % 10**8:08d}"))
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    outside = await _partner_user(db, ids, role, other_tree)
    return Witness(Caller(me, None, ids.distributor_id, {"users": "partner_subtree"}),
                   {below: True, outside: False})


async def users_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "users", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    a = await _staff(db, ids, role, await _org(db, ids, "elsewhere"))
    b = await make_partner_user(db, ids, mobile="9188" + f"{uuid.uuid4().int % 10**8:08d}")
    return Witness(Caller(admin, ids.org_unit_id, None, {"users": "global"}),
                   {str(a): True, str(b): True})


# ── witnesses: partners ──────────────────────────────────────────────────────

async def partners_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    """GAP-036: no org column, so the reach is the territories the caller's org
    units cover. The fixture org unit covers the fixture territory."""
    role = await _role(db, ids, "dm")
    await _grant(db, role, "partners", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    far = await _partner(db, ids, "FAR", await _territory(db, ids, "far"))
    return Witness(Caller(manager, ids.org_unit_id, None, {"partners": "org_subtree"}),
                   {str(ids.dealer_id): True, far: False})


async def partners_territory(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "sc")
    await _grant(db, role, "partners", ["view"], "territory")
    coordinator = await _staff(db, ids, role, ids.org_unit_id)
    await db.execute(text(
        "INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
        {"u": coordinator, "t": ids.territory_id})
    far = await _partner(db, ids, "FAR", await _territory(db, ids, "far"))
    return Witness(Caller(coordinator, ids.org_unit_id, None, {"partners": "territory"}),
                   {str(ids.dealer_id): True, far: False})


async def partners_partner_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "partners", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    return Witness(Caller(me, None, ids.distributor_id, {"partners": "partner_subtree"}),
                   {str(ids.dealer_id): True, other_tree: False})


async def partners_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "partners", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    far = await _partner(db, ids, "FAR", await _territory(db, ids, "far"))
    return Witness(Caller(admin, ids.org_unit_id, None, {"partners": "global"}),
                   {str(ids.dealer_id): True, far: True})


# ── witnesses: leads ─────────────────────────────────────────────────────────

async def leads_own(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "fo")
    await _grant(db, role, "leads", ["view"], "own")
    me = await _staff(db, ids, role, ids.org_unit_id)
    other = await _staff(db, ids, role, ids.org_unit_id)
    mine = await _lead(db, ids, owner_user_id=me)
    theirs = await _lead(db, ids, owner_user_id=other)
    return Witness(Caller(me, ids.org_unit_id, None, {"leads": "own"}),
                   {mine: True, theirs: False})


async def leads_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dm")
    await _grant(db, role, "leads", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    below = await _lead(db, ids, owner_org_unit_id=await _org(db, ids, "child",
                                                              parent=ids.org_unit_id))
    outside = await _lead(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    return Witness(Caller(manager, ids.org_unit_id, None, {"leads": "org_subtree"}),
                   {below: True, outside: False})


async def leads_territory(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "sc")
    await _grant(db, role, "leads", ["view"], "territory")
    coord = await _staff(db, ids, role, ids.org_unit_id)
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
                     {"u": coord, "t": ids.territory_id})
    here = await _lead(db, ids, territory_id=ids.territory_id)
    there = await _lead(db, ids, territory_id=await _territory(db, ids, "far"))
    return Witness(Caller(coord, ids.org_unit_id, None, {"leads": "territory"}),
                   {here: True, there: False})


async def leads_partner_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "leads", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    mine = await _lead(db, ids, assigned_partner_id=ids.dealer_id)        # dealer under distributor
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    theirs = await _lead(db, ids, assigned_partner_id=other_tree)
    return Witness(Caller(me, None, ids.distributor_id, {"leads": "partner_subtree"}),
                   {mine: True, theirs: False})


async def leads_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "leads", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    a = await _lead(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    b = await _lead(db, ids, assigned_partner_id=ids.dealer_id)
    return Witness(Caller(admin, ids.org_unit_id, None, {"leads": "global"}),
                   {a: True, b: True})


# ── witnesses: quotations (FS-005), the lead's shape one table along ─────────

async def quotations_own(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "fo")
    await _grant(db, role, "quotations", ["view"], "own")
    me = await _staff(db, ids, role, ids.org_unit_id)
    other = await _staff(db, ids, role, ids.org_unit_id)
    mine = await _quotation(db, ids, owner_user_id=me)
    theirs = await _quotation(db, ids, owner_user_id=other)
    return Witness(Caller(me, ids.org_unit_id, None, {"quotations": "own"}),
                   {mine: True, theirs: False})


async def quotations_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dm")
    await _grant(db, role, "quotations", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    below = await _quotation(db, ids, owner_org_unit_id=await _org(db, ids, "child",
                                                                   parent=ids.org_unit_id))
    outside = await _quotation(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    return Witness(Caller(manager, ids.org_unit_id, None, {"quotations": "org_subtree"}),
                   {below: True, outside: False})


async def quotations_territory(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "sc")
    await _grant(db, role, "quotations", ["view"], "territory")
    coord = await _staff(db, ids, role, ids.org_unit_id)
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
                     {"u": coord, "t": ids.territory_id})
    here = await _quotation(db, ids, territory_id=ids.territory_id)
    there = await _quotation(db, ids, territory_id=await _territory(db, ids, "far"))
    return Witness(Caller(coord, ids.org_unit_id, None, {"quotations": "territory"}),
                   {here: True, there: False})


async def quotations_partner_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    """A dealer sees the quotations routed through its subtree and not a direct
    sale on a lead it is assigned to (FS-005 rule 17): partner_id, not the
    lead's assigned partner, is the branch column."""
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "quotations", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    mine = await _quotation(db, ids, partner_id=ids.dealer_id)        # dealer under distributor
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    theirs = await _quotation(db, ids, partner_id=other_tree)
    direct = await _quotation(db, ids, partner_id=None)
    return Witness(Caller(me, None, ids.distributor_id, {"quotations": "partner_subtree"}),
                   {mine: True, theirs: False, direct: False})


async def quotations_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "quotations", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    a = await _quotation(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    b = await _quotation(db, ids, partner_id=ids.dealer_id)
    return Witness(Caller(admin, ids.org_unit_id, None, {"quotations": "global"}),
                   {a: True, b: True})


# ── witnesses: sales orders (FS-011), the quotation's shape ───────────────────

async def sales_orders_own(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "fo")
    await _grant(db, role, "sales_orders", ["view"], "own")
    me = await _staff(db, ids, role, ids.org_unit_id)
    other = await _staff(db, ids, role, ids.org_unit_id)
    mine = await _order(db, ids, owner_user_id=me)
    theirs = await _order(db, ids, owner_user_id=other)
    return Witness(Caller(me, ids.org_unit_id, None, {"sales_orders": "own"}),
                   {mine: True, theirs: False})


async def sales_orders_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dm")
    await _grant(db, role, "sales_orders", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    below = await _order(db, ids, owner_org_unit_id=await _org(db, ids, "child",
                                                               parent=ids.org_unit_id))
    outside = await _order(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    return Witness(Caller(manager, ids.org_unit_id, None, {"sales_orders": "org_subtree"}),
                   {below: True, outside: False})


async def sales_orders_territory(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "sc")
    await _grant(db, role, "sales_orders", ["view"], "territory")
    coord = await _staff(db, ids, role, ids.org_unit_id)
    await db.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (:u, :t)"),
                     {"u": coord, "t": ids.territory_id})
    here = await _order(db, ids, territory_id=ids.territory_id)
    there = await _order(db, ids, territory_id=await _territory(db, ids, "far"))
    return Witness(Caller(coord, ids.org_unit_id, None, {"sales_orders": "territory"}),
                   {here: True, there: False})


async def sales_orders_partner_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    """A distributor sees orders placed by its subtree, not another tree's and
    not a direct sale."""
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "sales_orders", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    mine = await _order(db, ids, partner_id=ids.dealer_id)
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    theirs = await _order(db, ids, partner_id=other_tree)
    direct = await _order(db, ids, partner_id=None)
    return Witness(Caller(me, None, ids.distributor_id, {"sales_orders": "partner_subtree"}),
                   {mine: True, theirs: False, direct: False})


async def sales_orders_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "sales_orders", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    a = await _order(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    b = await _order(db, ids, partner_id=ids.dealer_id)
    return Witness(Caller(admin, ids.org_unit_id, None, {"sales_orders": "global"}),
                   {a: True, b: True})


# ── witnesses: tasks (FS-014), own on the assignee, org_subtree on the office ──

async def _task(db: AsyncSession, ids: Fixtures, *, assigned_to: str,
                owner_org_unit_id: str | None = None) -> str:
    """A personal task as the owner: no link, given by its assignee."""
    return str((await db.execute(text(
        "INSERT INTO task (title, task_type, due_at, assigned_to, assigned_by, owner_org_unit_id) "
        "VALUES ('Call', 'call', now(), CAST(:u AS uuid), CAST(:u AS uuid), CAST(:o AS uuid)) "
        "RETURNING id"),
        {"u": assigned_to, "o": owner_org_unit_id or ids.org_unit_id})).scalar_one())


async def tasks_own(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "fo")
    await _grant(db, role, "tasks", ["view"], "own")
    me = await _staff(db, ids, role, ids.org_unit_id)
    other = await _staff(db, ids, role, ids.org_unit_id)
    mine = await _task(db, ids, assigned_to=me)
    theirs = await _task(db, ids, assigned_to=other)
    return Witness(Caller(me, ids.org_unit_id, None, {"tasks": "own"}),
                   {mine: True, theirs: False})


async def tasks_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dm")
    await _grant(db, role, "tasks", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    child = await _org(db, ids, "child", parent=ids.org_unit_id)
    elsewhere = await _org(db, ids, "elsewhere")
    below = await _task(db, ids, assigned_to=await _staff(db, ids, role, child),
                        owner_org_unit_id=child)
    outside = await _task(db, ids, assigned_to=await _staff(db, ids, role, elsewhere),
                          owner_org_unit_id=elsewhere)
    return Witness(Caller(manager, ids.org_unit_id, None, {"tasks": "org_subtree"}),
                   {below: True, outside: False})


async def tasks_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "tasks", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    elsewhere = await _org(db, ids, "elsewhere")
    a = await _task(db, ids, assigned_to=await _staff(db, ids, role, elsewhere),
                    owner_org_unit_id=elsewhere)
    return Witness(Caller(admin, ids.org_unit_id, None, {"tasks": "global"}), {a: True})


# ── witnesses: complaints (FS-015), own, office and the dealer's subtree ──────

async def _complaint(db: AsyncSession, ids: Fixtures, *, owner_user_id: str | None = None,
                     owner_org_unit_id: str | None = None, partner_id: str | None = None,
                     deleted: bool = False) -> str:
    """A draft as the table owner; the raiser is any staff row (the trigger holds
    only app_role to the caller)."""
    raiser = owner_user_id or str((await db.execute(text(
        "SELECT id FROM app_user WHERE user_type = 'staff' LIMIT 1"))).scalar_one())
    return str((await db.execute(text(
        "INSERT INTO complaint (complaint_type_id, description, contact_name, contact_mobile, "
        "territory_id, state_code, partner_id, owner_user_id, owner_org_unit_id, raised_by, "
        "deleted_at) VALUES ((SELECT id FROM complaint_type WHERE code = 'dripline'), 'x', 'x', "
        "'+919812345678', CAST(:t AS uuid), 'GJ', CAST(:p AS uuid), CAST(:u AS uuid), "
        "CAST(:o AS uuid), CAST(:r AS uuid), CASE WHEN :d THEN now() END) RETURNING id"),
        {"t": ids.territory_id, "p": partner_id, "u": owner_user_id,
         "o": owner_org_unit_id or ids.org_unit_id, "r": raiser, "d": deleted})).scalar_one())


async def complaints_own(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "fo")
    await _grant(db, role, "complaints", ["view"], "own")
    me = await _staff(db, ids, role, ids.org_unit_id)
    other = await _staff(db, ids, role, ids.org_unit_id)
    mine = await _complaint(db, ids, owner_user_id=me)
    theirs = await _complaint(db, ids, owner_user_id=other)
    return Witness(Caller(me, ids.org_unit_id, None, {"complaints": "own"}),
                   {mine: True, theirs: False})


async def complaints_org_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "dm")
    await _grant(db, role, "complaints", ["view"], "org_subtree")
    manager = await _staff(db, ids, role, ids.org_unit_id)
    below = await _complaint(db, ids, owner_org_unit_id=await _org(db, ids, "child",
                                                                   parent=ids.org_unit_id))
    outside = await _complaint(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    return Witness(Caller(manager, ids.org_unit_id, None, {"complaints": "org_subtree"}),
                   {below: True, outside: False})


async def complaints_partner_subtree(db: AsyncSession, ids: Fixtures) -> Witness:
    """A distributor sees its subtree's complaints, not another tree's and not a
    complaint with no dealer."""
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "complaints", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    mine = await _complaint(db, ids, partner_id=ids.dealer_id)
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    theirs = await _complaint(db, ids, partner_id=other_tree)
    direct = await _complaint(db, ids)
    return Witness(Caller(me, None, ids.distributor_id, {"complaints": "partner_subtree"}),
                   {mine: True, theirs: False, direct: False})


async def complaints_global(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "complaints", ["view"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    a = await _complaint(db, ids, owner_org_unit_id=await _org(db, ids, "elsewhere"))
    b = await _complaint(db, ids, partner_id=ids.dealer_id)
    return Witness(Caller(admin, ids.org_unit_id, None, {"complaints": "global"}),
                   {a: True, b: True})


WITNESSES: dict[tuple[str, str], Builder] = {
    ("complaints", "own"): complaints_own,
    ("complaints", "org_subtree"): complaints_org_subtree,
    ("complaints", "partner_subtree"): complaints_partner_subtree,
    ("complaints", "global"): complaints_global,
    ("tasks", "own"): tasks_own,
    ("tasks", "org_subtree"): tasks_org_subtree,
    ("tasks", "global"): tasks_global,
    ("sales_orders", "own"): sales_orders_own,
    ("sales_orders", "org_subtree"): sales_orders_org_subtree,
    ("sales_orders", "territory"): sales_orders_territory,
    ("sales_orders", "partner_subtree"): sales_orders_partner_subtree,
    ("sales_orders", "global"): sales_orders_global,
    ("quotations", "own"): quotations_own,
    ("quotations", "org_subtree"): quotations_org_subtree,
    ("quotations", "territory"): quotations_territory,
    ("quotations", "partner_subtree"): quotations_partner_subtree,
    ("quotations", "global"): quotations_global,
    ("users", "own"): users_own,
    ("users", "org_subtree"): users_org_subtree,
    ("users", "partner_subtree"): users_partner_subtree,
    ("users", "global"): users_global,
    ("partners", "org_subtree"): partners_org_subtree,
    ("partners", "territory"): partners_territory,
    ("partners", "partner_subtree"): partners_partner_subtree,
    ("partners", "global"): partners_global,
    ("leads", "own"): leads_own,
    ("leads", "org_subtree"): leads_org_subtree,
    ("leads", "territory"): leads_territory,
    ("leads", "partner_subtree"): leads_partner_subtree,
    ("leads", "global"): leads_global,
}


# ── witnesses: soft delete (code review F-5) ─────────────────────────────────

async def users_deleted(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "users", ["view", "edit"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    live = await _staff(db, ids, role, ids.org_unit_id)
    gone = await _staff(db, ids, role, ids.org_unit_id)
    await db.execute(text("UPDATE app_user SET deleted_at = now() WHERE id = :i"), {"i": gone})
    return Witness(Caller(admin, ids.org_unit_id, None, {"users": "global"}),
                   {live: True, gone: False})


async def partners_deleted(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "partners", ["view", "edit"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    gone = await _partner(db, ids, "GONE", ids.territory_id)
    await db.execute(text("UPDATE channel_partner SET deleted_at = now() WHERE id = :i"),
                     {"i": gone})
    return Witness(Caller(admin, ids.org_unit_id, None, {"partners": "global"}),
                   {str(ids.dealer_id): True, gone: False})


async def leads_deleted(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "leads", ["view", "edit"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    live = await _lead(db, ids)
    gone = await _lead(db, ids, deleted=True)
    return Witness(Caller(admin, ids.org_unit_id, None, {"leads": "global"}),
                   {live: True, gone: False})


async def quotations_deleted(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "quotations", ["view", "edit"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    live = await _quotation(db, ids)
    gone = await _quotation(db, ids, deleted=True)
    return Witness(Caller(admin, ids.org_unit_id, None, {"quotations": "global"}),
                   {live: True, gone: False})


async def sales_orders_deleted(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "sales_orders", ["view", "edit"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    live = await _order(db, ids)
    gone = await _order(db, ids, deleted=True)
    return Witness(Caller(admin, ids.org_unit_id, None, {"sales_orders": "global"}),
                   {live: True, gone: False})


async def complaints_deleted(db: AsyncSession, ids: Fixtures) -> Witness:
    role = await _role(db, ids, "admin")
    await _grant(db, role, "complaints", ["view", "edit"], "global")
    admin = await _staff(db, ids, role, ids.org_unit_id)
    live = await _complaint(db, ids)
    gone = await _complaint(db, ids, deleted=True)
    return Witness(Caller(admin, ids.org_unit_id, None, {"complaints": "global"}),
                   {live: True, gone: False})


DELETED: dict[str, Builder] = {"users": users_deleted, "partners": partners_deleted,
                               "leads": leads_deleted, "quotations": quotations_deleted,
                               "sales_orders": sales_orders_deleted,
                               "complaints": complaints_deleted}


def test_every_spec_with_a_soft_delete_column_has_a_deleted_witness() -> None:
    assert {n for n, s in SPECS.items() if s.soft_delete} == set(DELETED)


@pytest.mark.parametrize("module", sorted(DELETED))
async def test_a_soft_deleted_row_is_hidden_without_delete_in_both_enforcers(
        db: AsyncSession, ids: Fixtures, module: str) -> None:
    """Executed before the fix: the predicate said `true` for a global caller and
    RLS returned 0 rows for the deleted one."""
    spec = SPECS[module]
    w = await DELETED[module](db, ids)
    rows = list(w.expected)
    want = {r for r, ok in w.expected.items() if ok}
    pred = scope_predicate(spec, w.caller, TABLES[spec.table])
    assert await _visible(db, spec.table, rows, pred) == want, "service predicate"
    await _as(db, w.caller.user_id)
    assert await _visible(db, spec.table, rows) == want, "policy"
    assert await _visible(db, spec.table, rows, pred) == want, "both"


def test_every_declared_branch_has_a_witness_pair() -> None:
    """A ScopeSpec cannot ship without its parity rows."""
    declared = {(name, scope) for name, spec in SPECS.items()
                for scope in (*spec.declared_scopes(), "global")}
    assert declared == set(WITNESSES), declared ^ set(WITNESSES)


# ── the parity assertions ────────────────────────────────────────────────────

@pytest.mark.parametrize("branch", sorted(WITNESSES), ids=lambda b: f"{b[0]}.{b[1]}")
async def test_both_enforcers_agree_on_both_witnesses(
        db: AsyncSession, ids: Fixtures, branch: tuple[str, str]) -> None:
    module, _ = branch
    spec: ScopeSpec = SPECS[module]
    w = await WITNESSES[branch](db, ids)
    rows = list(w.expected)
    want = {r for r, ok in w.expected.items() if ok}
    pred = scope_predicate(spec, w.caller, TABLES[spec.table])

    # enforcer 1 alone, as the owner: the predicate gives the matrix's answer
    assert await _visible(db, spec.table, rows) == set(rows), "owner sees everything"
    assert await _visible(db, spec.table, rows, pred) == want, "service predicate"

    # enforcer 2 alone, as the caller: a raw read gives the same answer
    await _as(db, w.caller.user_id)
    assert await _visible(db, spec.table, rows) == want, "policy"
    # and both together
    assert await _visible(db, spec.table, rows, pred) == want, "both"


@pytest.mark.parametrize("branch", sorted(b for b in WITNESSES if b[1] != "global"),
                         ids=lambda b: f"{b[0]}.{b[1]}")
async def test_each_enforcer_does_real_work_on_a_restricted_branch(
        db: AsyncSession, ids: Fixtures, branch: tuple[str, str]) -> None:
    """The two mutation checks. Open the table with USING (true) in a savepoint:
    the raw read now returns the out-of-scope witness (so the policy was the
    thing hiding it, and the suite is not running as the owner), and the service
    predicate still excludes it."""
    module, _ = branch
    spec = SPECS[module]
    w = await WITNESSES[branch](db, ids)
    rows = list(w.expected)
    want = {r for r, ok in w.expected.items() if ok}
    assert want != set(rows), "a restricted branch needs an out-of-scope witness"
    pred = scope_predicate(spec, w.caller, TABLES[spec.table])

    await db.execute(text("SAVEPOINT opened"))
    await db.execute(text(f"CREATE POLICY parity_open ON {spec.table} FOR SELECT USING (true)"))
    await _as(db, w.caller.user_id)
    assert await _visible(db, spec.table, rows) == set(rows), "policy dropped, row still hidden"
    assert await _visible(db, spec.table, rows, pred) == want, "predicate did no work"
    await db.execute(text("ROLLBACK TO SAVEPOINT opened"))

    await _as(db, w.caller.user_id)
    assert await _visible(db, spec.table, rows) == want, "policy restored"


# ── writes: fact 5, both halves ──────────────────────────────────────────────

async def test_a_partner_row_cannot_attach_under_an_out_of_scope_parent(
        db: AsyncSession, ids: Fixtures) -> None:
    """Enforcer 2 refuses with 42501; enforcer 1's parent lookup returns no row,
    which the service turns into a 422 naming parent_id."""
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "partners", ["view", "create"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    spec = SPECS["partners"]

    await _as(db, me)
    assert (await db.execute(parent_lookup(spec, "parent_id", uuid.UUID(str(ids.dealer_id))))
            ).scalar_one_or_none() is not None
    assert (await db.execute(parent_lookup(spec, "parent_id", uuid.UUID(other_tree)))
            ).scalar_one_or_none() is None
    with pytest.raises(REFUSED, match="row-level security"):
        async with db.begin_nested():
            await db.execute(text(
                "INSERT INTO channel_partner (parent_id, partner_type, code, name, "
                "territory_id, price_tier) VALUES (:p, 'dealer', :c, 'x', :t, 'dealer')"),
                {"p": other_tree, "c": ids.unique("UNDER-OTHER"), "t": ids.territory_id})
    # the in-scope parent is accepted by both
    await db.execute(text(
        "INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, "
        "price_tier) VALUES (:p, 'sub_dealer', :c, 'x', :t, 'sub_dealer')"),
        {"p": ids.dealer_id, "c": ids.unique("UNDER-MINE"), "t": ids.territory_id})


async def test_a_user_cannot_be_anchored_at_an_out_of_scope_partner(
        db: AsyncSession, ids: Fixtures) -> None:
    role = await _role(db, ids, "dist", portal=True, level=3)
    await _grant(db, role, "users", ["view", "create"], "partner_subtree")
    await _grant(db, role, "partners", ["view"], "partner_subtree")
    me = await _partner_user(db, ids, role, ids.distributor_id)
    other_tree = await _partner(db, ids, "OTHER", ids.territory_id)
    spec = SPECS["users"]

    await _as(db, me)
    assert (await db.execute(parent_lookup(spec, "partner_id", uuid.UUID(other_tree)))
            ).scalar_one_or_none() is None
    with pytest.raises(REFUSED, match="row-level security"):
        async with db.begin_nested():
            await db.execute(text(
                "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
                "VALUES ('partner_user', :m, 'x', :r, :p)"),
                {"m": "9188" + f"{uuid.uuid4().int % 10**8:08d}", "r": role, "p": other_tree})
    await db.execute(text(
        "INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id) "
        "VALUES ('partner_user', :m, 'x', :r, :p)"),
        {"m": "9188" + f"{uuid.uuid4().int % 10**8:08d}", "r": ids.portal_role_id,
         "p": ids.dealer_id})


async def test_the_self_profile_reads_without_users_view_and_a_colleague_does_not(
        db: AsyncSession, ids: Fixtures) -> None:
    """FS-002 5.4's one deliberate exception, in both enforcers."""
    me = str(await make_staff(db, ids, email=ids.unique("me") + "@polysil.in"))
    colleague = str(await make_staff(db, ids, email=ids.unique("c") + "@polysil.in"))
    caller = Caller(me, ids.org_unit_id, None, scopes={})
    pred = scope_predicate(SPECS["users"], caller, TABLES["app_user"])
    assert await _visible(db, "app_user", [me, colleague], pred) == {me}
    await _as(db, me)
    assert await _visible(db, "app_user", [me, colleague]) == {me}
