"""The single source: one ScopeSpec per module.

Both enforcers are generated from these. Editing one without regenerating the
policy migration is caught by the drift test, which regenerates from here and
compares against the live pg_policies (FS-002 5.3).

Two declarations today, for the tables that exist. Business tables add theirs as
they land, and a test asserts every declared branch has a parity fixture.
"""

from __future__ import annotations

from api.domain.authz import ScopeSpec

SPECS: dict[str, ScopeSpec] = {
    # A user is their own row (own), sits in an org unit (org_subtree) or under a
    # partner (partner_subtree). self_column lets /auth/me read the caller's row
    # without users.view. No territory branch: user_territory is a separate table.
    "users": ScopeSpec(
        module="users",
        table="app_user",
        own="id",
        org_subtree="org_unit_id",
        partner_subtree="partner_id",
        parents={"org_unit_id": "org_unit", "partner_id": "channel_partner"},
        self_column="id",
        self_ref="user",
    ),
    # A partner has no owning user and no org-unit column (GAP-036). A manager's
    # org reach goes through the territories their org units cover; a partner user
    # reaches their own subtree by the row's own id through partner_closure; a State
    # Co-ordinator reaches by territory. This is also the only territory branch
    # executable before any business table exists.
    "partners": ScopeSpec(
        module="partners",
        table="channel_partner",
        org_subtree_via="territory_id",
        territory="territory_id",
        partner_subtree="id",
        parents={"parent_id": "channel_partner", "territory_id": "territory"},
        self_column="id",
        self_ref="partner",
    ),
    # A lead is owned by a staff user (own), sits under that user's org unit
    # (org_subtree), is in a territory a State Co-ordinator covers (territory), or
    # is assigned to a partner (partner_subtree). No self_column: a lead is not a
    # person. The three parents are checked on INSERT by the policy and on change
    # by lead_parent_guard(); owner_user_id, lost_reason_id and merged_into_id are
    # single-enforcer (the service), see FS-003 5.2 and GAP-057.
    "leads": ScopeSpec(
        module="leads",
        table="lead",
        own="owner_user_id",
        org_subtree="owner_org_unit_id",
        territory="territory_id",
        partner_subtree="assigned_partner_id",
        parents={"territory_id": "territory", "owner_org_unit_id": "org_unit",
                 "assigned_partner_id": "channel_partner"},
    ),
    # A quotation is scoped like its lead: its owner, org unit and territory are
    # the lead's, copied under the lead's lock and propagated by a trigger when
    # the lead moves (FS-005 rule 11). partner_subtree is the channel partner the
    # sale goes through, which decides the tier as well as who sees it. The lead
    # is a parent, so the INSERT policy carries an EXISTS on it: a quotation can
    # only be written on a lead the writer can see, by RLS as well as by the
    # service. No self_column: a quotation is not a person.
    "quotations": ScopeSpec(
        module="quotations",
        table="quotation",
        own="owner_user_id",
        org_subtree="owner_org_unit_id",
        territory="territory_id",
        partner_subtree="partner_id",
        parents={"lead_id": "lead", "territory_id": "territory",
                 "owner_org_unit_id": "org_unit", "partner_id": "channel_partner"},
    ),
    # FS-011: the quotation's shape. An order's scope is set at create (from its
    # quotations, else the raiser or the portal routing) and follows nothing after
    # (GAP-127); the parents guard a lead, office, territory or partner the caller
    # cannot see (edge case 22).
    "sales_orders": ScopeSpec(
        module="sales_orders",
        table="sales_order",
        own="owner_user_id",
        org_subtree="owner_org_unit_id",
        territory="territory_id",
        partner_subtree="partner_id",
        parents={"lead_id": "lead", "territory_id": "territory",
                 "owner_org_unit_id": "org_unit", "partner_id": "channel_partner"},
    ),
    # FS-014: a task is its assignee's (own) and sits under the assignee's office
    # (org_subtree), which is where a manager and the assigner read it (ADR-034
    # assigns only downwards). No partner branch: portal roles hold no tasks (RBAC
    # 6.3, GAP-141). No soft delete: a task is cancelled, never deleted. The three
    # links are parents, so a caller cannot hang a task off something they cannot see.
    "tasks": ScopeSpec(
        module="tasks",
        table="task",
        own="assigned_to",
        org_subtree="owner_org_unit_id",
        soft_delete=None,
        parents={"lead_id": "lead", "partner_id": "channel_partner",
                 "sales_order_id": "sales_order", "owner_org_unit_id": "org_unit"},
    ),
    # FS-015: the officer responsible (own), the owning office (org_subtree) and the
    # dealer involved (partner_subtree), all set at create and following nothing
    # (GAP-152). No territory branch: no role holds complaints at territory scope.
    # The links are parents, so nobody raises a complaint on something they cannot
    # see.
    "complaints": ScopeSpec(
        module="complaints",
        table="complaint",
        own="owner_user_id",
        org_subtree="owner_org_unit_id",
        partner_subtree="partner_id",
        parents={"lead_id": "lead", "sales_order_id": "sales_order",
                 "partner_id": "channel_partner", "owner_org_unit_id": "org_unit",
                 "territory_id": "territory"},
    ),
    # FS-009: an application is its lead's, copied and frozen at create (D5): the
    # owner (own), the office (org_subtree) and the territory, which is how the
    # State Co-ordinator reaches it. No partner branch: dealers hold no subsidy
    # row (RBAC 6.3). No soft delete: an application is cancelled.
    "subsidy": ScopeSpec(
        module="subsidy",
        table="subsidy_application",
        own="owner_user_id",
        org_subtree="owner_org_unit_id",
        territory="territory_id",
        soft_delete=None,
        parents={"lead_id": "lead", "territory_id": "territory",
                 "owner_org_unit_id": "org_unit"},
    ),
}
