"""084: a person's open leads move with them to a new office (FS-082 EC-1).

Tasks (018) and this month's targets (035) already follow a person's office.
Leads did not: a lead keeps `owner_org_unit_id`, and the leads `org_subtree` scope
reads that column. So a Field Officer moved from HQ to a district office left their
leads at HQ, where the new District Manager could not see them (ISS-233).

Open leads only: won, lost and merged leads stay with the office they closed in,
as past targets do. Dormant leads move: dormant is still open work that nobody
closed, while lost is a decision (code review F-6). A move into an office with no
territory moves nothing (rule 4, code review F-1).

Quotations follow their lead through `lead_scope_to_quotations` (012). Orders keep
their office (GAP-557). One `lead.rehomed` event per lead.

Revision ID: 084_lead_follows_office
Revises: 083_reporting_lines
"""

from __future__ import annotations

from alembic import op

revision: str = "084_lead_follows_office"
down_revision: str | None = "083_reporting_lines"
branch_labels = None
depends_on = None

SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005

FUNCTION = f"""CREATE FUNCTION lead_follow_office() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_me uuid := COALESCE(app_current_user_id(), '{SYSTEM_USER_ID}'::uuid);
    v_name text;
    r record;
BEGIN
    -- rule 4 (040 lead_owner_unit): a lead belongs to its owner's office only when
    -- that office covers an area; otherwise to the office covering the lead's own
    -- territory. A move into an office with no area leaves the leads where they are
    -- (code review F-1)
    IF NEW.org_unit_id IS NULL OR NOT EXISTS (
        SELECT 1 FROM org_unit WHERE id = NEW.org_unit_id AND territory_id IS NOT NULL) THEN
        RETURN NULL;
    END IF;
    SELECT full_name INTO v_name FROM app_user WHERE id = v_me;
    FOR r IN UPDATE lead SET owner_org_unit_id = NEW.org_unit_id
              WHERE owner_user_id = NEW.id AND deleted_at IS NULL AND merged_into_id IS NULL
                AND stage::text NOT IN ('won', 'lost', 'merged')
                AND owner_org_unit_id IS DISTINCT FROM NEW.org_unit_id
          RETURNING id LOOP
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('lead', r.id, r.id, 'lead.rehomed', v_me,
                jsonb_build_object('actor_name', COALESCE(v_name, ''),
                                   'owner_org_unit_id', NEW.org_unit_id,
                                   'previous_org_unit_id', OLD.org_unit_id));
    END LOOP;
    RETURN NULL;
END $fn$"""

TRIGGER = """CREATE TRIGGER trg_app_user_lead_office AFTER UPDATE OF org_unit_id ON app_user
FOR EACH ROW WHEN (OLD.org_unit_id IS DISTINCT FROM NEW.org_unit_id)
EXECUTE FUNCTION lead_follow_office()"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute("REVOKE EXECUTE ON FUNCTION lead_follow_office() FROM PUBLIC")
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_lead_office ON app_user")
    op.execute("DROP FUNCTION IF EXISTS lead_follow_office()")
