"""086: a lead's owner says whether that person is still active (BE-042).

`lead_people()` (006) is the definer read that names a lead's people for anyone who
can see the lead. Its owner row now carries `detail = 'active'` or `'inactive'`, so a
restored lead whose owner has left can offer Assign (FS-073, GAP-524). A manager may
not be able to read the owner's `app_user` row, which is why this is not a join in
the service. CREATE OR REPLACE keeps the function's owner and grants.

Revision ID: 086_lead_owner_active
Revises: 085_product_import
"""

from __future__ import annotations

from alembic import op

revision: str = "086_lead_owner_active"
down_revision: str | None = "085_product_import"
branch_labels = None
depends_on = None

_BODY = """CREATE OR REPLACE FUNCTION lead_people(p_lead_id uuid)
RETURNS TABLE (kind text, id uuid, name text, detail text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT lead_visible(p_lead_id) THEN RETURN; END IF;
    RETURN QUERY
        SELECT 'owner', u.id, u.full_name, {owner_detail}
          FROM lead l JOIN app_user u ON u.id = l.owner_user_id WHERE l.id = p_lead_id
        UNION ALL
        SELECT 'created_by', u.id, u.full_name, NULL::text
          FROM lead l JOIN app_user u ON u.id = l.created_by WHERE l.id = p_lead_id
        UNION ALL
        SELECT 'assigned_partner', cp.id, cp.name, cp.partner_type::text
          FROM lead l JOIN channel_partner cp ON cp.id = l.assigned_partner_id
         WHERE l.id = p_lead_id
        UNION ALL
        SELECT 'merged_into', s.id, NULL::text, s.inquiry_no::text
          FROM lead l JOIN lead s ON s.id = l.merged_into_id WHERE l.id = p_lead_id;
END $fn$"""

# switched off or deleted: either way the person no longer works the lead
_ACTIVE = ("CASE WHEN u.is_active AND u.deleted_at IS NULL "
           "THEN 'active' ELSE 'inactive' END")


def upgrade() -> None:
    op.execute(_BODY.format(owner_detail=_ACTIVE))


def downgrade() -> None:
    op.execute(_BODY.format(owner_detail="NULL::text"))
