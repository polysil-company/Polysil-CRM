"""050: the customer record (FS-041).

- `customer`: one per mobile number (GAP-258). Its name, email, area and address are
  its own once made; a new one copies them from the lead that made it (GAP-263).
- `lead.customer_id`, set by `lead_link_customer` when a lead reaches qualified or
  later, by any path. Find by mobile or create, `ON CONFLICT DO NOTHING` then read
  again, so two leads qualifying at once share one customer. A definer: the customer
  may be visible only through someone else's lead, and app_role cannot insert.
- Backfill with plain statements, before the trigger exists: one customer per mobile
  from the oldest lead that got past contacted, then every such lead linked, then
  merge losers follow their survivors. The audit trigger comes after, so backfilled
  customers have no audit INSERT row (as seeded rows elsewhere).
- `customer_sel`: see one of its leads, see the customer. `customer_upd` adds
  leads.edit and staff only. No INSERT or DELETE grant.
- `activity_event_sel` gains the `customer` arm (LIVE_TABLES in api/authz/activity.py).
  Customer events carry `customer_id`, never `lead_id`, so lead timelines are unchanged.

Revision ID: 050_customer_record
Revises: 049_campaigns
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "050_customer_record"
down_revision: str | None = "049_campaigns"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# stages a lead reaches only after qualifying (FS-041 rule 1)
LINKED = "('qualified', 'quoted', 'negotiation', 'won')"


def _got_there(a: str) -> str:
    """A lead that got past contacted once, whatever it is now (edge case 4); a
    quotation needs a qualified lead."""
    return (f"({a}.stage::text IN {LINKED} OR {a}.lost_from_stage::text IN {LINKED} "
            f"OR {a}.dormant_from_stage::text IN {LINKED} "
            f"OR EXISTS (SELECT 1 FROM quotation q WHERE q.lead_id = {a}.id))")


# A merge loser never makes a customer of its own; its survivor qualifies through it
# instead (code review F-5), and the loser then follows the survivor.
PASSED = (f"(l.stage::text <> 'merged' AND ({_got_there('l')} OR EXISTS (SELECT 1 FROM lead m "
          f"WHERE m.merged_into_id = l.id AND {_got_there('m')})))")

TABLES = [
    """CREATE TABLE customer (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_type text NOT NULL DEFAULT 'farmer' CHECK (customer_type IN ('farmer', 'institution', 'company')),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 200),
    mobile text NOT NULL CHECK (mobile ~ '^[+][1-9][0-9]{7,14}$'),
    email citext CHECK (email IS NULL OR length(email) <= 254),
    -- SET NULL: a customer outlives the rows that made it (test teardowns remove
    -- territories and people; production never hard-deletes either)
    territory_id uuid REFERENCES territory(id) ON DELETE SET NULL,
    village text CHECK (village IS NULL OR length(village) <= 200),
    address text CHECK (address IS NULL OR length(address) <= 500),
    survey_no text CHECK (survey_no IS NULL OR length(survey_no) <= 100),
    consent_given_at timestamptz,
    consent_channel text CHECK (consent_channel IN ('whatsapp', 'form', 'verbal', 'written')),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
    CONSTRAINT uq_customer_mobile UNIQUE (mobile),
    CONSTRAINT ck_customer_consent CHECK ((consent_given_at IS NULL) = (consent_channel IS NULL))
)""",
    "CREATE INDEX ix_customer_created ON customer (created_at DESC, id DESC)",
    "CREATE INDEX ix_customer_territory ON customer (territory_id) WHERE territory_id IS NOT NULL",
    "ALTER TABLE lead ADD COLUMN customer_id uuid REFERENCES customer(id)",
    # rule 9: customer_sel's EXISTS reads lead by this column
    "CREATE INDEX ix_lead_customer ON lead (customer_id) WHERE customer_id IS NOT NULL",
]
RLS_TABLES = ("customer",)
# the mobile is the identity and not editable (GAP-261): column grants, as 013 does for orders
GRANTS: dict[str, str] = {"customer": "SELECT, UPDATE (customer_type, name, email, territory_id, village, "
                                      "address, survey_no, consent_given_at, consent_channel, updated_by)"}

_SEES = "EXISTS (SELECT 1 FROM lead l WHERE l.customer_id = customer.id)"
# api/authz/activity.py policy_sql(), pasted; test_policy_drift_005 compares the two
ACTIVITY_SEL = "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  CASE entity_type\n    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)\n    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)\n    WHEN 'customer' THEN EXISTS (SELECT 1 FROM customer c WHERE c.id = customer_id)\n    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)\n    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)\n    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)\n    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)\n    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)\n    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)\n    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)\n    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)\n    WHEN 'subsidy_application' THEN EXISTS (SELECT 1 FROM subsidy_application c WHERE c.id = entity_id)\n    WHEN 'scheme' THEN EXISTS (SELECT 1 FROM scheme c WHERE c.id = entity_id)\n    WHEN 'marketing_order' THEN EXISTS (SELECT 1 FROM marketing_order c WHERE c.id = entity_id)\n    WHEN 'reward_rule' THEN EXISTS (SELECT 1 FROM reward_rule c WHERE c.id = entity_id)\n    WHEN 'gift' THEN EXISTS (SELECT 1 FROM gift c WHERE c.id = entity_id)\n    WHEN 'reward_setting' THEN EXISTS (SELECT 1 FROM reward_setting c WHERE c.id = entity_id)\n    WHEN 'visit' THEN EXISTS (SELECT 1 FROM visit c WHERE c.id = entity_id)\n    WHEN 'duty_session' THEN EXISTS (SELECT 1 FROM duty_session c WHERE c.id = entity_id)\n    WHEN 'tracking_consent' THEN EXISTS (SELECT 1 FROM tracking_consent c WHERE c.id = entity_id)\n    WHEN 'campaign' THEN EXISTS (SELECT 1 FROM campaign c WHERE c.id = entity_id)\n    ELSE (SELECT app_is_system())\n  END\n)"
HAND_POLICIES: list[tuple[str, str]] = [
    ("customer", f"CREATE POLICY customer_sel ON customer FOR SELECT USING ({_SEES})"),
    ("customer", f"CREATE POLICY customer_upd ON customer FOR UPDATE USING ({_SEES} AND (SELECT app_has_permission('leads', 'edit')) AND (SELECT app_current_partner()) IS NULL)"),
    ("activity_event", ACTIVITY_SEL),
]

BACKFILL = [
    f"""INSERT INTO customer (name, mobile, email, territory_id, village)
SELECT DISTINCT ON (l.mobile) l.farmer_name, l.mobile, left(l.email::text, 254), l.territory_id,
       left(l.village, 200)
  FROM lead l WHERE {PASSED}
 ORDER BY l.mobile, l.created_at, l.id
ON CONFLICT (mobile) DO NOTHING""",
    f"UPDATE lead l SET customer_id = c.id FROM customer c WHERE c.mobile = l.mobile AND l.customer_id IS NULL AND {PASSED}",
    # a loser follows its survivor (rule 10)
    "UPDATE lead l SET customer_id = s.customer_id FROM lead s WHERE l.merged_into_id = s.id "
    "AND l.customer_id IS NULL AND s.customer_id IS NOT NULL",
    """INSERT INTO activity_event (entity_type, entity_id, customer_id, kind, actor_id, payload)
SELECT 'customer', c.id, c.id, 'customer.created', NULL,
       jsonb_build_object('name', c.name, 'actor_name', 'System', 'backfill', true)
  FROM customer c""",
]

FUNCTIONS = [
    f"""CREATE FUNCTION lead_link_customer() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid; v_me uuid := app_current_user_id();
BEGIN
    IF NEW.customer_id IS NOT NULL OR NEW.stage::text NOT IN {LINKED} THEN
        RETURN NEW;
    END IF;
    INSERT INTO customer (name, mobile, email, territory_id, village, created_by, updated_by)
    -- the lead's columns are uncapped; the customer's are not (code review F-3)
    VALUES (NEW.farmer_name, NEW.mobile, left(NEW.email::text, 254), NEW.territory_id,
            left(NEW.village, 200), v_me, v_me)
    ON CONFLICT (mobile) DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NOT NULL THEN
        INSERT INTO activity_event (entity_type, entity_id, customer_id, kind, actor_id, payload)
        VALUES ('customer', v_id, v_id, 'customer.created', v_me,
                -- no inquiry_no: a reader of another of its leads may not see this one (F-4)
                jsonb_build_object('name', NEW.farmer_name,
                                   'actor_name', coalesce((SELECT full_name FROM app_user WHERE id = v_me), 'System')));
    ELSE
        -- a new statement: it sees the row a concurrent transaction just committed (edge case 1)
        SELECT id INTO v_id FROM customer WHERE mobile = NEW.mobile;
        IF v_id IS NULL THEN     -- only under a snapshot older than the conflicting commit
            RAISE EXCEPTION 'customer for % not found after a conflict', NEW.mobile USING ERRCODE = '40001';
        END IF;
    END IF;
    NEW.customer_id := v_id;
    RETURN NEW;
END $fn$""",
]

TRIGGERS = [
    # INSERT too: a lead written at a later stage directly (imports, fixtures) links as well
    "CREATE TRIGGER trg_lead_link_customer BEFORE INSERT OR UPDATE OF stage ON lead FOR EACH ROW EXECUTE FUNCTION lead_link_customer()",
    "CREATE TRIGGER trg_customer_updated_at BEFORE UPDATE ON customer FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_customer_audit AFTER INSERT OR UPDATE OR DELETE ON customer FOR EACH ROW EXECUTE FUNCTION audit_row()",
]

INTERNAL = ["lead_link_customer()"]


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_050", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"050: migration {stem} not found beside it")
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
    for table, stmt in HAND_POLICIES:
        if table == "activity_event":
            op.execute("DROP POLICY activity_event_sel ON activity_event")
        op.execute(stmt)
    # the backfill must not move updated_at on every old lead (edge case 3); the
    # audit trigger still records the link
    op.execute("ALTER TABLE lead DISABLE TRIGGER trg_lead_updated_at")
    for stmt in BACKFILL:
        op.execute(stmt)
    op.execute("ALTER TABLE lead ENABLE TRIGGER trg_lead_updated_at")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for stmt in TRIGGERS:
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    m049 = _load("049")
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(m049.ACTIVITY_SEL)  # type: ignore[attr-defined]
    op.execute("DELETE FROM activity_event WHERE entity_type = 'customer'")
    op.execute("DROP TRIGGER IF EXISTS trg_lead_link_customer ON lead")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS customer_id")
    op.execute("DROP TABLE IF EXISTS customer")
    for sig in INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
