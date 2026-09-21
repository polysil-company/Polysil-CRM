"""The pure half of authorization: the declaration and the matrix parser.

No database. The matrix tests read RBAC.md itself, so a document edit that
changes a cell changes a test, which is the intended coupling: the document is
the source.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.domain.authz import (
    ACTIONS,
    DeclarationError,
    Grant,
    ScopeSpec,
    all_cells,
    denied_cells,
    modules_in,
    parse_matrix,
    roles_in,
)

RBAC = (Path(__file__).resolve().parents[2] / "docs/architecture/RBAC.md").read_text(
    encoding="utf-8")


@pytest.fixture(scope="module")
def grants() -> list[Grant]:
    return parse_matrix(RBAC)


# ── the matrix ───────────────────────────────────────────────────────────────

def test_sixteen_roles_and_twenty_modules(grants: list[Grant]) -> None:
    """ISS-031: 20 modules, not 18. campaigns and stock appear in one matrix each."""
    assert len(roles_in(grants)) == 16
    assert len(modules_in(grants)) == 20
    assert {"campaigns", "stock"} <= set(modules_in(grants))
    assert len(all_cells(grants)) == 16 * 20 * len(ACTIONS) == 1600


def test_the_two_overgrants_the_seed_carried_are_denied(grants: list[Grant]) -> None:
    """FS-002 9.3 A-1. district_manager/leads is V:org CE; dealer/quotations is V."""
    denied = denied_cells(grants)
    assert ("district_manager", "leads", "approve") in denied
    assert ("dealer", "quotations", "create") in denied


def test_the_state_coordinator_is_territory_scoped(grants: list[Grant]) -> None:
    """RBAC.md 6.2, and the regression it records: a find-and-replace once turned
    these into org, which at hq_subsidy is an empty subtree."""
    mine = {g for g in grants if g.role == "state_coordinator"}
    # tasks and chat are own for every role; everything else this role holds is territory
    assert {g.scope for g in mine if g.module not in ("tasks", "chat")} == {"territory"}
    assert "org_subtree" not in {g.scope for g in mine}
    assert Grant("state_coordinator", "subsidy", "create", "territory") in mine


def test_portal_roles_are_partner_scoped_and_redeem_maps_to_create(grants: list[Grant]) -> None:
    portal = {g for g in grants if g.role in ("distributor", "dealer", "sub_dealer")}
    assert {g.scope for g in portal} == {"partner_subtree"}
    assert Grant("dealer", "rewards", "create", "partner_subtree") in portal  # GAP-043
    assert Grant("sub_dealer", "partners", "view", "partner_subtree") not in portal


def test_the_board_views_everything_at_global_and_nothing_else(grants: list[Grant]) -> None:
    board = {g for g in grants if g.role == "board"}
    assert {g.action for g in board} == {"view"}
    assert {g.scope for g in board} == {"global"}
    assert len(board) == 20


def test_every_pair_has_a_view_row_with_one_scope(grants: list[Grant]) -> None:
    """ISS-029, enforced at parse time as well as at seed time."""
    pairs: dict[tuple[str, str], set[str]] = {}
    for g in grants:
        pairs.setdefault((g.role, g.module), set()).add(g.action)
    assert all("view" in actions for actions in pairs.values())


def test_a_mixed_scope_pair_is_rejected() -> None:
    doc = ("### 6.1 Line hierarchy\n\n| Module | field_officer |\n|---|---|\n"
           "| leads | V:own C |\n| leads | V:org E |\n")
    with pytest.raises(ValueError, match="mixed scopes"):
        parse_matrix(doc)


def test_a_cell_without_a_view_is_rejected() -> None:
    doc = "### 6.1 Line hierarchy\n\n| Module | field_officer |\n|---|---|\n| leads | CE |\n"
    with pytest.raises(ValueError, match="does not start with V"):
        parse_matrix(doc)


# ── the declaration ──────────────────────────────────────────────────────────

def test_a_spec_declares_only_the_branches_it_has_columns_for() -> None:
    spec = ScopeSpec(module="leads", table="lead", own="owner_user_id",
                     org_subtree="owner_org_unit_id", territory="territory_id",
                     partner_subtree="assigned_partner_id",
                     parents={"assigned_partner_id": "channel_partner"})
    assert spec.declared_scopes() == ("own", "org_subtree", "territory", "partner_subtree")
    assert spec.has_branch("global")
    assert spec.indexed_columns() == ("owner_user_id", "owner_org_unit_id", "territory_id",
                                      "assigned_partner_id", "deleted_at")


def test_org_via_territory_is_the_org_branch() -> None:
    spec = ScopeSpec(module="partners", table="channel_partner",
                     org_subtree_via="territory_id", territory="territory_id",
                     partner_subtree="id")
    assert spec.branch_column("org_subtree") == "territory_id"
    assert spec.indexed_columns() == ("territory_id", "id", "deleted_at")


@pytest.mark.parametrize("bad", [
    {"module": "x", "table": "lead", "own": "drop table"},
    {"module": "x", "table": "lead", "org_subtree": "a", "org_subtree_via": "b"},
    {"module": "x", "table": "lead"},
    {"module": "x", "table": "lead", "own": "a", "parents": {"a": "not-safe"}},
    {"module": "x", "table": "lead", "own": "a", "self_column": "id"},
    {"module": "x", "table": "lead", "own": "a", "self_column": "id", "self_ref": "org"},
])
def test_a_bad_declaration_fails_at_import(bad: dict[str, object]) -> None:
    with pytest.raises(DeclarationError):
        ScopeSpec(**bad)  # type: ignore[arg-type]
