"""The Caller dependency (FS-002 stage 3, api/deps.py:get_caller).

Resolved once per request from two reads under the caller's own claim: the anchor
row and the permission rows. get_caller takes (session, claims) and its body uses
only db.execute and claims.sub, so it is called here directly against a session
that has the claim set and app_role entered - the same shape as the policy tests -
rather than through an ASGI probe, so every branch is reached without a committed
fixture.

scope is the view row's scope; deletes is the modules the caller may delete, which
is what lets them read a soft-deleted row (FS-002 code review F-5). A module with
no permission is in neither map.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.deps import get_caller
from api.domain.auth import AccessClaims
from tests.db.conftest import Fixtures, make_partner_user, make_staff

pytestmark = [pytest.mark.db, pytest.mark.rls]


async def _grant(db: AsyncSession, role_id: str, module: str, actions: list[str],
                 scope: str) -> None:
    for action in actions:
        await db.execute(text(
            "INSERT INTO role_permission (role_id, module, action, scope) "
            "VALUES (:r, :m, CAST(:a AS permission_action), CAST(:s AS permission_scope))"),
            {"r": role_id, "m": module, "a": action, "s": scope})


async def _caller(db: AsyncSession, user_id: str):
    """Set the claim, enter app_role, resolve. The claim GUC drives the queries;
    claims.sub is what lands in Caller.user_id."""
    await db.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                     {"u": str(user_id)})
    await enter_role(db, "app_role")
    return await get_caller(db, AccessClaims(sub=str(user_id), sid=str(uuid.uuid4()),
                                             token_version=0))


async def test_a_staff_caller_carries_its_org_unit_and_view_scopes(
        db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view", "create"], "org_subtree")
    await _grant(db, ids.staff_role_id, "users", ["view"], "own")
    me = await make_staff(db, ids, email=ids.unique("m") + "@polysil.in")
    caller = await _caller(db, me)
    assert caller.user_id == str(me)
    assert caller.org_unit_id == str(ids.org_unit_id)
    assert caller.partner_id is None
    assert caller.scopes == {"leads": "org_subtree", "users": "own"}
    assert caller.deletes == frozenset()


async def test_the_scope_is_the_view_rows_scope_not_a_mutations(
        db: AsyncSession, ids: Fixtures) -> None:
    """app_scope() reads the view row, so a module whose create/edit rows exist
    resolves to the view scope, never a mutation's."""
    await _grant(db, ids.staff_role_id, "leads", ["view", "create", "edit"], "org_subtree")
    me = await make_staff(db, ids, email=ids.unique("v") + "@polysil.in")
    caller = await _caller(db, me)
    assert caller.scopes == {"leads": "org_subtree"}


async def test_a_partner_caller_carries_its_partner_and_no_org_unit(
        db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.portal_role_id, "leads", ["view"], "partner_subtree")
    me = await make_partner_user(db, ids, mobile="9199" + uuid.uuid4().hex[:8])
    caller = await _caller(db, me)
    assert caller.org_unit_id is None
    assert caller.partner_id == str(ids.dealer_id)
    assert caller.scopes == {"leads": "partner_subtree"}


async def test_the_delete_action_lands_in_deletes(db: AsyncSession, ids: Fixtures) -> None:
    await _grant(db, ids.staff_role_id, "leads", ["view", "delete"], "org_subtree")
    me = await make_staff(db, ids, email=ids.unique("d") + "@polysil.in")
    caller = await _caller(db, me)
    assert caller.deletes == frozenset({"leads"})


async def test_a_caller_with_no_permissions_has_empty_maps(
        db: AsyncSession, ids: Fixtures) -> None:
    """A user_type with no role_permission rows: the predicate for every module is
    the self row or false, never an unscoped read."""
    me = await make_staff(db, ids, email=ids.unique("n") + "@polysil.in")
    caller = await _caller(db, me)
    assert caller.scopes == {}
    assert caller.deletes == frozenset()
    assert caller.org_unit_id == str(ids.org_unit_id)
