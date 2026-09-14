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
}
