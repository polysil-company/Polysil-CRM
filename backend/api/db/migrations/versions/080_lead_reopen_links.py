"""080: restoring a deleted lead reopens its duplicate pairs (FS-073, BE-033).

- `lead_reopen_links(uuid)`: the mirror of `lead_close_links()` (006). A definer for
  the same reason: the delete closed every pair, hidden ones included, and a pair
  whose other lead is outside the restorer's scope cannot be updated under the link
  policy (plan review B-1).
  - Reopens a dismissed pair only when a delete closed it: a `lead.deleted` event on
    either lead at the pair's `resolved_at` (the delete's own `now()`). So a pair
    closed by the other lead's earlier delete reopens too, and a pair dismissed by
    hand stays dismissed (plan review R-1).
  - Only when both leads are live and neither is merged (EC-4, R-2).
  - Needs `leads.edit` and `leads.delete`, and the lead visible to the caller.
  - Returns the reopened links, for the `lead.restored` event (rule 7, R-3).

Revision ID: 080_lead_reopen_links
Revises: 079_tracking_device_token
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "080_lead_reopen_links"
down_revision: str | None = "079_tracking_device_token"
branch_labels = None
depends_on = None

SIG = "lead_reopen_links(uuid)"

FUNCTION = """CREATE FUNCTION lead_reopen_links(p_lead_id uuid)
RETURNS TABLE (link_id uuid, other_lead_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT (app_has_permission('leads', 'edit') AND app_has_permission('leads', 'delete')) THEN
        RAISE EXCEPTION 'not permitted to restore leads' USING ERRCODE = '42501';
    END IF;
    IF NOT lead_visible(p_lead_id) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'LEADN';
    END IF;
    RETURN QUERY WITH r AS (
    UPDATE lead_duplicate_link dl
       SET state = 'pending', resolved_by = NULL, resolved_at = NULL
     WHERE dl.state = 'dismissed'
       AND (dl.lead_a_id = p_lead_id OR dl.lead_b_id = p_lead_id)
       AND EXISTS (SELECT 1 FROM activity_event e
                    WHERE e.kind = 'lead.deleted' AND e.lead_id IN (dl.lead_a_id, dl.lead_b_id)
                      AND e.occurred_at = dl.resolved_at)
       AND NOT EXISTS (SELECT 1 FROM lead x
                        WHERE x.id IN (dl.lead_a_id, dl.lead_b_id)
                          AND (x.deleted_at IS NOT NULL OR x.stage = 'merged'))
    RETURNING dl.id AS lid, CASE WHEN dl.lead_a_id = p_lead_id THEN dl.lead_b_id ELSE dl.lead_a_id END AS oid)
    SELECT r.lid, r.oid FROM r;
END $fn$"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {SIG} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {SIG} TO app_role")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {SIG}")
