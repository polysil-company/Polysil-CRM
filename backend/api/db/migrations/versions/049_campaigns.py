"""049: campaigns (FS-040).

- `campaign`: Marketing's campaigns, with dates, an area and planned and actual
  cost. Every staff user reads the list (a lead form offers it); writes follow
  RBAC 6.2 `campaigns` (Marketing CEAD). Cost is hidden in the service from a
  caller without campaigns.view (rule 1, GAP-250). Admin Sales and the MD gain
  campaigns.view (RBAC 6.1).
- `lead.campaign_id` and `lead_qr_code.campaign_id`, both nullable.
- `lead_campaign_from_qr`: a lead inserted from a QR code with a campaign takes it,
  unless the insert named one. A definer, so the copy never depends on the inserter's
  scope covering the code (today only the intake principal inserts with a code, and it
  can read them).
- `lead_qr_public` is replaced with the same signature: `campaign` is the linked
  campaign's name, else the free-text label.
- `activity_event_sel` gains the `campaign` arm from `api/authz/activity.py`.

Revision ID: 049_campaigns
Revises: 043_whatsapp_webhook_capture
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "049_campaigns"
down_revision: str | None = "043_whatsapp_webhook_capture"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# rule 8 (GAP-253): fixed in code until the client asks for its own list
TYPES = ("exhibition", "agri_fair", "farmer_meeting", "dealer_meet", "promo_drive", "digital",
         "print", "other")

TABLES = [
    f"""CREATE TABLE campaign (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name citext NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    type text NOT NULL CHECK (type IN ({", ".join(f"'{t}'" for t in TYPES)})),
    territory_id uuid REFERENCES territory(id),
    start_date date NOT NULL,
    end_date date,
    cost_planned numeric(14,2) NOT NULL DEFAULT 0 CHECK (cost_planned >= 0),
    cost_actual numeric(14,2) CHECK (cost_actual IS NULL OR cost_actual >= 0),
    description text CHECK (description IS NULL OR length(description) <= 2000),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES app_user(id),
    CONSTRAINT uq_campaign_name UNIQUE (name),
    CONSTRAINT ck_campaign_dates CHECK (end_date IS NULL OR end_date >= start_date)
)""",
    "CREATE INDEX ix_campaign_start ON campaign (start_date DESC, id)",
    "CREATE INDEX ix_campaign_territory ON campaign (territory_id) WHERE territory_id IS NOT NULL",
    "ALTER TABLE lead ADD COLUMN campaign_id uuid REFERENCES campaign(id)",
    "CREATE INDEX ix_lead_campaign ON lead (campaign_id) WHERE campaign_id IS NOT NULL",
    "ALTER TABLE lead_qr_code ADD COLUMN campaign_id uuid REFERENCES campaign(id)",
    "CREATE INDEX ix_lead_qr_code_campaign ON lead_qr_code (campaign_id) WHERE campaign_id IS NOT NULL",
]
RLS_TABLES = ("campaign",)
GRANTS: dict[str, str] = {"campaign": "SELECT, INSERT, UPDATE, DELETE"}

_STAFF = "(SELECT app_current_user_id()) IS NOT NULL AND (SELECT app_current_partner()) IS NULL"
# api/authz/activity.py policy_sql(), pasted; test_policy_drift_005 compares the two
ACTIVITY_SEL = "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)\n    WHEN 'subsidy_application' THEN EXISTS (SELECT 1 FROM subsidy_application c WHERE c.id = entity_id)\n    WHEN 'scheme' THEN EXISTS (SELECT 1 FROM scheme c WHERE c.id = entity_id)\n    WHEN 'marketing_order' THEN EXISTS (SELECT 1 FROM marketing_order c WHERE c.id = entity_id)\n    WHEN 'reward_rule' THEN EXISTS (SELECT 1 FROM reward_rule c WHERE c.id = entity_id)\n    WHEN 'gift' THEN EXISTS (SELECT 1 FROM gift c WHERE c.id = entity_id)\n    WHEN 'reward_setting' THEN EXISTS (SELECT 1 FROM reward_setting c WHERE c.id = entity_id)\n    WHEN 'visit' THEN EXISTS (SELECT 1 FROM visit c WHERE c.id = entity_id)\n    WHEN 'duty_session' THEN EXISTS (SELECT 1 FROM duty_session c WHERE c.id = entity_id)\n    WHEN 'tracking_consent' THEN EXISTS (SELECT 1 FROM tracking_consent c WHERE c.id = entity_id)\n    WHEN 'campaign' THEN EXISTS (SELECT 1 FROM campaign c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"
HAND_POLICIES: list[tuple[str, str]] = [
    ("campaign", f"CREATE POLICY campaign_sel ON campaign FOR SELECT USING ({_STAFF})"),
    ("campaign", f"CREATE POLICY campaign_ins ON campaign FOR INSERT WITH CHECK ({_STAFF} AND (SELECT app_has_permission('campaigns', 'create')))"),
    ("campaign", f"CREATE POLICY campaign_upd ON campaign FOR UPDATE USING ({_STAFF} AND (SELECT app_has_permission('campaigns', 'edit')))"),
    ("campaign", f"CREATE POLICY campaign_del ON campaign FOR DELETE USING ({_STAFF} AND (SELECT app_has_permission('campaigns', 'delete')))"),
    ("activity_event", ACTIVITY_SEL),
]

FUNCTIONS = [
    # rule 5: the code's campaign at insert, unless the insert named one
    """CREATE FUNCTION lead_campaign_from_qr() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.campaign_id IS NULL AND NEW.qr_code_id IS NOT NULL THEN
        SELECT q.campaign_id INTO NEW.campaign_id FROM lead_qr_code q WHERE q.id = NEW.qr_code_id;
    END IF;
    RETURN NEW;
END $fn$""",
    # true when any lead or QR code names it, including rows the caller cannot see
    """CREATE FUNCTION campaign_in_use(p_campaign uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM lead WHERE campaign_id = p_campaign)
        OR EXISTS (SELECT 1 FROM lead_qr_code WHERE campaign_id = p_campaign)
$fn$""",
]

NEW_QR_PUBLIC = """CREATE OR REPLACE FUNCTION lead_qr_public(p_code text)
RETURNS TABLE (code text, label text, campaign text, territory_id uuid, partner_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT q.code::text, q.label, coalesce(c.name::text, q.campaign), q.territory_id, q.partner_id
      FROM lead_qr_code q
      LEFT JOIN channel_partner cp ON cp.id = q.partner_id
      LEFT JOIN campaign c ON c.id = q.campaign_id
     WHERE q.code = p_code::citext AND q.is_active
       AND (q.partner_id IS NULL OR (cp.is_active AND cp.deleted_at IS NULL))
$fn$"""

TRIGGERS = [
    "CREATE TRIGGER trg_lead_campaign_from_qr BEFORE INSERT ON lead FOR EACH ROW EXECUTE FUNCTION lead_campaign_from_qr()",
    "CREATE TRIGGER trg_campaign_updated_at BEFORE UPDATE ON campaign FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_campaign_audit AFTER INSERT OR UPDATE OR DELETE ON campaign FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

# RBAC 6.1 (FS-040 edge case 2): Admin Sales and the MD see campaigns and their cost.
# Marketing's CEAD and the board's view came with 005's matrix.
SEED = """INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'campaigns', 'view', 'global' FROM role r WHERE r.code IN ('admin_sales', 'md_ceo')
ON CONFLICT (role_id, module, action) DO NOTHING"""

GRANTED = ["campaign_in_use(uuid)"]
INTERNAL = ["lead_campaign_from_qr()"]


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_049", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"049: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(NEW_QR_PUBLIC)
    for table, stmt in HAND_POLICIES:
        if table == "activity_event":
            op.execute("DROP POLICY activity_event_sel ON activity_event")
        op.execute(stmt)
    for stmt in TRIGGERS:
        op.execute(stmt)
    op.execute(SEED)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    # 030 is the last to write activity_event_sel before this one (migration_grants order)
    m030 = _load("030")
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(st for t, st in m030.HAND_POLICIES if t == "activity_event"))  # type: ignore[attr-defined]
    op.execute("DELETE FROM activity_event WHERE entity_type = 'campaign'")
    op.execute("DELETE FROM role_permission WHERE module = 'campaigns' AND action = 'view' AND role_id IN "
               "(SELECT id FROM role WHERE code IN ('admin_sales', 'md_ceo'))")
    m015 = _load("015")
    op.execute(next(f for f in m015.FUNCTIONS if "FUNCTION lead_qr_public" in f)  # type: ignore[attr-defined]
               .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute("DROP TRIGGER IF EXISTS trg_lead_campaign_from_qr ON lead")
    op.execute("ALTER TABLE lead_qr_code DROP COLUMN IF EXISTS campaign_id")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS campaign_id")
    op.execute("DROP TABLE IF EXISTS campaign")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
