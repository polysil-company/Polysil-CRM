"""054: whether a document's waiting approval step has nobody of its own role.

`approval_step_stalled()` (013) is internal: the queue calls it as the owner. The
order and quotation pages need the same answer for the step waiting now, so a
step a higher manager will decide stops reading "Waiting on District Manager"
(walk 10 Oct F-11). `approval_waiting_stalled()` answers for a request whose
document (an order, a quotation, or a complaint's refund) the caller can see, and
false for anything else.

Revision ID: 054_approval_step_stalled
Revises: 053_warranty
"""



from __future__ import annotations

from alembic import op

revision: str = "054_approval_step_stalled"
down_revision: str | None = "053_warranty"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

FUNCTIONS = [
    """CREATE FUNCTION approval_waiting_stalled(p_request uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r approval_request%ROWTYPE; v_step uuid; v_visible boolean;
BEGIN
    SELECT * INTO r FROM approval_request WHERE id = p_request;
    IF NOT FOUND OR r.status <> 'pending' THEN
        RETURN false;
    END IF;
    -- the same answer as the document's own GET: nothing for a document you cannot see.
    -- A variable: inside IF, the CASE's first THEN would end the condition.
    v_visible := CASE r.doc_type WHEN 'sales_order' THEN order_visible(r.entity_id)
                                 WHEN 'quotation' THEN quotation_visible(r.entity_id)
                                 WHEN 'complaint' THEN complaint_visible(r.entity_id)
                                 ELSE false END;
    IF NOT COALESCE(v_visible, false) THEN
        RETURN false;
    END IF;
    SELECT id INTO v_step FROM approval_step
     WHERE request_id = p_request AND decision IS NULL ORDER BY seq LIMIT 1;
    RETURN v_step IS NOT NULL AND approval_step_stalled(v_step);
END $fn$""",
]

GRANTED = ["approval_waiting_stalled(uuid)"]


def upgrade() -> None:
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in reversed(GRANTED):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
