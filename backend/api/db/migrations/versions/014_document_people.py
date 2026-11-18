"""014: names of the people and partners on documents the caller can see (GAP-060).

The rule (RBAC.md 6.2, 24 Sep): whoever can see a lead, quotation or order sees the
people on it. The matrix now gives every document-viewing role `users.view`, but a
scope cannot reach everyone who appears on a record: a dealer who created a lead
has no office, an administrator at head office sits outside a district manager's
subtree. So the lists and details resolve names through two definers.

- `people_names(uuid[])` returns id and name for each id that owns, created or
  decided a lead, quotation or order the caller can see. For a staff caller it
  also answers for the approvers and dispatchers of a visible order; a partner
  never learns who approved (question 15.14).
- `partner_names(uuid[])` returns id, name and type for each partner on a visible
  lead, quotation or order.

An id on nothing the caller can see returns no row, so neither is a directory: a
caller cannot name an arbitrary user by guessing ids. Both are pinned to
`public, pg_temp`, granted to app_role and revoked from PUBLIC. The indexes are on
the columns the lookups search by, which had none.

Revision ID: 014_document_people
Revises: 013_orders_approvals_dispatch
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "014_document_people"
down_revision: str | None = "013_orders_approvals_dispatch"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_lead_created_by ON lead (created_by)",
    "CREATE INDEX IF NOT EXISTS ix_quotation_created_by ON quotation (created_by)",
    "CREATE INDEX IF NOT EXISTS ix_quotation_decided_by ON quotation (decided_by)",
    "CREATE INDEX IF NOT EXISTS ix_sales_order_created_by ON sales_order (created_by)",
    "CREATE INDEX IF NOT EXISTS ix_approval_step_approver_user ON approval_step (approver_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_dispatch_dispatched_by ON dispatch (dispatched_by)",
]
INDEX_NAMES = ["ix_lead_created_by", "ix_quotation_created_by", "ix_quotation_decided_by",
               "ix_sales_order_created_by", "ix_approval_step_approver_user",
               "ix_dispatch_dispatched_by"]

FUNCTIONS = [
    """CREATE FUNCTION people_names(p_ids uuid[])
RETURNS TABLE (id uuid, full_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT u.id, u.full_name::text FROM app_user u
     WHERE u.id = ANY(p_ids)
       AND (EXISTS (SELECT 1 FROM lead l
                     WHERE (l.owner_user_id = u.id OR l.created_by = u.id) AND lead_visible(l.id))
         OR EXISTS (SELECT 1 FROM quotation q
                     WHERE (q.owner_user_id = u.id OR q.created_by = u.id OR q.decided_by = u.id)
                       AND quotation_visible(q.id))
         OR EXISTS (SELECT 1 FROM sales_order o
                     WHERE (o.owner_user_id = u.id OR o.created_by = u.id) AND order_visible(o.id))
         -- who approved and who dispatched are internal to Polysil (question 15.14)
         OR ((SELECT app_current_partner()) IS NULL
             AND (EXISTS (SELECT 1 FROM approval_step s JOIN approval_request r ON r.id = s.request_id
                           WHERE s.approver_user_id = u.id AND r.doc_type = 'sales_order'
                             AND order_visible(r.entity_id))
               OR EXISTS (SELECT 1 FROM dispatch d
                           WHERE d.dispatched_by = u.id AND order_visible(d.sales_order_id)))))
$fn$""",
    """CREATE FUNCTION partner_names(p_ids uuid[])
RETURNS TABLE (id uuid, name text, partner_type text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT cp.id, cp.name::text, cp.partner_type::text FROM channel_partner cp
     WHERE cp.id = ANY(p_ids)
       AND (EXISTS (SELECT 1 FROM lead l WHERE l.assigned_partner_id = cp.id AND lead_visible(l.id))
         OR EXISTS (SELECT 1 FROM quotation q WHERE q.partner_id = cp.id AND quotation_visible(q.id))
         OR EXISTS (SELECT 1 FROM sales_order o WHERE o.partner_id = cp.id AND order_visible(o.id)))
$fn$""",
]
SIGNATURES = ["people_names(uuid[])", "partner_names(uuid[])"]


def upgrade() -> None:
    for stmt in INDEXES + FUNCTIONS:
        op.execute(stmt)
    for sig in SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in SIGNATURES:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for name in INDEX_NAMES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
