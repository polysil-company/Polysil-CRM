"""006 leads: the lead table, its policies and the shared bits FS-003 needs.

FS-003. Built in steps and amended in place between them, the way 005 was: this
revision has run only on the development box, so a forward-only fix is a further
edit here rather than a 006a until it ships.

Step 0 needed the UPDATE path on idempotency_record (005 wrote none, so the store
step was 42501, plan review B-1) and the generator's parent-guard change re-applied
to the two tables that predate it (cross-vendor B-2, REAPPLY below). This step adds
the lead table, the four lookup masters, the duplicate-link table and the inquiry
counter, their policies, and the lead arm of activity_event's read policy. The nine
definer functions land with the endpoints that call them; lead_parent_guard, which
a parent change on UPDATE needs, is here.

GRANTS and HAND_POLICIES are read by tests/db/migration_grants.py, unioned with
005's: grants as verb sets per table, policies by name (so 006's activity_event_sel
supersedes 005's).
"""

from __future__ import annotations

# ruff: noqa: E501  (generated and embedded SQL; its line length is not ours to wrap)
from collections.abc import Sequence

from alembic import op

revision: str = "006_leads"
down_revision: str | None = "005_authorization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_role"
USER = "(SELECT app_current_user_id())"

GRANTS: dict[str, str] = {
    "idempotency_record": "UPDATE",
    "lead": "SELECT, INSERT, UPDATE",
    "lead_duplicate_link": "SELECT, INSERT, UPDATE",
    "lead_source": "SELECT, INSERT, UPDATE",
    "mis_system": "SELECT, INSERT, UPDATE",
    "won_lost_reason": "SELECT, INSERT, UPDATE",
    "lead_score_rule": "SELECT, INSERT, UPDATE",
}

HAND_POLICIES: list[tuple[str, str]] = [
    ("idempotency_record", """CREATE POLICY idempotency_record_upd ON idempotency_record FOR UPDATE USING (user_id = (SELECT app_current_user_id())) WITH CHECK (user_id = (SELECT app_current_user_id()))"""),
    ("lead_source", """CREATE POLICY lead_source_sel ON lead_source FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"""),
    ("lead_source", """CREATE POLICY lead_source_ins ON lead_source FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"""),
    ("lead_source", """CREATE POLICY lead_source_upd ON lead_source FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit')))"""),
    ("mis_system", """CREATE POLICY mis_system_sel ON mis_system FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"""),
    ("mis_system", """CREATE POLICY mis_system_ins ON mis_system FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"""),
    ("mis_system", """CREATE POLICY mis_system_upd ON mis_system FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit')))"""),
    ("won_lost_reason", """CREATE POLICY won_lost_reason_sel ON won_lost_reason FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"""),
    ("won_lost_reason", """CREATE POLICY won_lost_reason_ins ON won_lost_reason FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"""),
    ("won_lost_reason", """CREATE POLICY won_lost_reason_upd ON won_lost_reason FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit')))"""),
    ("lead_score_rule", """CREATE POLICY lead_score_rule_sel ON lead_score_rule FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"""),
    ("lead_score_rule", """CREATE POLICY lead_score_rule_ins ON lead_score_rule FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"""),
    ("lead_score_rule", """CREATE POLICY lead_score_rule_upd ON lead_score_rule FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit')))"""),
    ("lead_duplicate_link", """CREATE POLICY lead_duplicate_link_sel ON lead_duplicate_link FOR SELECT USING (
  EXISTS (SELECT 1 FROM lead a WHERE a.id = lead_a_id) AND EXISTS (SELECT 1 FROM lead b WHERE b.id = lead_b_id)
)"""),
    ("lead_duplicate_link", """CREATE POLICY lead_duplicate_link_ins ON lead_duplicate_link AS RESTRICTIVE FOR INSERT WITH CHECK ((SELECT app_has_permission('leads', 'edit')))"""),
    ("lead_duplicate_link", """CREATE POLICY lead_duplicate_link_ins_vis ON lead_duplicate_link FOR INSERT WITH CHECK (
  EXISTS (SELECT 1 FROM lead a WHERE a.id = lead_a_id) AND EXISTS (SELECT 1 FROM lead b WHERE b.id = lead_b_id)
)"""),
    ("lead_duplicate_link", """CREATE POLICY lead_duplicate_link_upd ON lead_duplicate_link FOR UPDATE USING (
  EXISTS (SELECT 1 FROM lead a WHERE a.id = lead_a_id) AND EXISTS (SELECT 1 FROM lead b WHERE b.id = lead_b_id)
) WITH CHECK (
  EXISTS (SELECT 1 FROM lead a WHERE a.id = lead_a_id) AND EXISTS (SELECT 1 FROM lead b WHERE b.id = lead_b_id)
)"""),
    ("lead_duplicate_link", """CREATE POLICY lead_duplicate_link_upd_perm ON lead_duplicate_link AS RESTRICTIVE FOR UPDATE USING ((SELECT app_has_permission('leads', 'edit')))"""),
    ("activity_event", """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    ELSE (SELECT app_is_system())
  END
)"""),
]

ENUMS = [
    """CREATE TYPE lead_stage AS ENUM ('new', 'contacted', 'qualified', 'quoted', 'negotiation', 'won', 'lost', 'merged', 'dormant')""",
    """CREATE TYPE inquiry_type AS ENUM ('commercial', 'subsidised', 'industrial')""",
    """CREATE TYPE lead_priority AS ENUM ('hot', 'warm', 'cold')""",
    """CREATE TYPE lead_dup_signal AS ENUM ('mobile', 'email', 'name_geo')""",
    """CREATE TYPE lead_dup_state AS ENUM ('pending', 'merged', 'dismissed')""",
    """CREATE TYPE won_lost_kind AS ENUM ('won', 'lost')""",
]

TABLES = [
    """CREATE TABLE lead_source (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE,
    name text NOT NULL,
    quality numeric(3,2) NOT NULL DEFAULT 0.5,
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz
)""",
    """CREATE TABLE mis_system (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE,
    name text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz
)""",
    """CREATE TABLE won_lost_reason (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind won_lost_kind NOT NULL,
    code citext NOT NULL,
    name text NOT NULL,
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz,
    CONSTRAINT uq_won_lost_reason UNIQUE (kind, code)
)""",
    """CREATE TABLE lead_score_rule (
    key citext PRIMARY KEY,
    value numeric(12,2) NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz
)""",
    """CREATE TABLE inquiry_counter (
    state_code text NOT NULL,
    financial_year text NOT NULL,
    last_value int NOT NULL DEFAULT 0,
    PRIMARY KEY (state_code, financial_year)
)""",
    """CREATE TABLE lead (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    inquiry_no citext NOT NULL UNIQUE,
    stage lead_stage NOT NULL DEFAULT 'new',
    inquiry_type inquiry_type NOT NULL,
    mis_system_id uuid NOT NULL REFERENCES mis_system(id),
    lead_source_id uuid NOT NULL REFERENCES lead_source(id),
    farmer_name text NOT NULL,
    mobile text NOT NULL,
    email citext,
    territory_id uuid NOT NULL REFERENCES territory(id),
    village text,
    owner_user_id uuid REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    assigned_partner_id uuid REFERENCES channel_partner(id),
    score numeric(6,2),
    priority lead_priority,
    estimated_value numeric(14,2),
    lost_reason_id uuid REFERENCES won_lost_reason(id),
    lost_note text,
    lost_from_stage lead_stage,
    reopen_count int NOT NULL DEFAULT 0,
    merged_into_id uuid REFERENCES lead(id),
    first_contacted_at timestamptz,
    last_activity_at timestamptz NOT NULL DEFAULT now(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz,
    CONSTRAINT ck_lead_lost_reason CHECK (stage <> 'lost' OR lost_reason_id IS NOT NULL),
    CONSTRAINT ck_lead_merged CHECK ((merged_into_id IS NULL) = (stage <> 'merged')),
    CONSTRAINT ck_lead_mobile_e164 CHECK (mobile ~ '^[+][1-9][0-9]{7,14}$'),
    CONSTRAINT ck_lead_not_merged_into_self CHECK (merged_into_id IS NULL OR merged_into_id <> id),
    CONSTRAINT ck_lead_farmer_name_shape CHECK (length(btrim(farmer_name)) BETWEEN 1 AND 200),
    CONSTRAINT ck_lead_estimated_value CHECK (estimated_value IS NULL OR estimated_value >= 0)
)""",
    """CREATE TABLE lead_duplicate_link (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_a_id uuid NOT NULL REFERENCES lead(id),
    lead_b_id uuid NOT NULL REFERENCES lead(id),
    signal lead_dup_signal NOT NULL,
    score numeric(4,2),
    state lead_dup_state NOT NULL DEFAULT 'pending',
    resolved_by uuid REFERENCES app_user(id),
    resolved_at timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz,
    CONSTRAINT ck_lead_dup_order CHECK (lead_a_id < lead_b_id),
    CONSTRAINT uq_lead_dup_pair UNIQUE (lead_a_id, lead_b_id)
)""",
]

SEEDS = [
    """INSERT INTO lead_source (code, name, quality, sort_order) VALUES ('whatsapp','WhatsApp',0.6,1),('website','Website',0.6,2),('employee','Employee',0.8,3),('dealer','Dealer',0.7,4),('campaign','Campaign',0.5,5),('agri_fair','Agri Fair',0.7,6),('farmer_meeting','Farmer Meeting',0.8,7),('qr_code','QR Code',0.5,8),('form_link','Form Link',0.5,9)""",
    """INSERT INTO mis_system (code, name) VALUES ('drip','Drip'),('mini_sprinkler','Mini Sprinkler'),('sprinkler','Sprinkler'),('automation','Automation'),('other','Other')""",
    """INSERT INTO won_lost_reason (kind, code, name, sort_order) VALUES ('lost','price','Price',1),('lost','competitor','Competitor',2),('lost','no_response','No response',3),('lost','product_mismatch','Product mismatch',4),('lost','financing_not_approved','Financing not approved',5),('lost','out_of_area','Out of area',6)""",
    """INSERT INTO lead_score_rule (key, value) VALUES ('w_source',25),('w_value',35),('w_speed',20),('w_engagement',20),('value_cap',500000),('speed_fast_hours',24),('speed_slow_hours',72),('engagement_cap',10),('threshold_hot',70),('threshold_warm',40)""",
]

TRIGGERS = [
    """CREATE TRIGGER trg_lead_source_updated_at BEFORE UPDATE ON lead_source FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_lead_source_audit AFTER INSERT OR UPDATE OR DELETE ON lead_source FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_mis_system_updated_at BEFORE UPDATE ON mis_system FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_mis_system_audit AFTER INSERT OR UPDATE OR DELETE ON mis_system FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_won_lost_reason_updated_at BEFORE UPDATE ON won_lost_reason FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_won_lost_reason_audit AFTER INSERT OR UPDATE OR DELETE ON won_lost_reason FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_lead_score_rule_updated_at BEFORE UPDATE ON lead_score_rule FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_lead_score_rule_audit AFTER INSERT OR UPDATE OR DELETE ON lead_score_rule FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_lead_updated_at BEFORE UPDATE ON lead FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_lead_audit AFTER INSERT OR UPDATE OR DELETE ON lead FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_lead_duplicate_link_updated_at BEFORE UPDATE ON lead_duplicate_link FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_lead_duplicate_link_audit AFTER INSERT OR UPDATE OR DELETE ON lead_duplicate_link FOR EACH ROW EXECUTE FUNCTION audit_row()""",
]

HAND_INDEXES = [
    """CREATE INDEX ix_lead_org_stage ON lead (owner_org_unit_id, stage)""",
    """CREATE INDEX ix_lead_territory_stage ON lead (territory_id, stage)""",
    """CREATE INDEX ix_lead_mobile ON lead (mobile)""",
    """CREATE INDEX ix_lead_last_activity ON lead (last_activity_at)""",
    """CREATE INDEX ix_lead_name_trgm ON lead USING gin (farmer_name gin_trgm_ops)""",
    """CREATE INDEX ix_lead_created_keyset ON lead (created_at DESC, id)""",
    """CREATE INDEX ix_lead_merged_into ON lead (merged_into_id)""",
    """CREATE UNIQUE INDEX uq_lead_external ON lead (source_system, external_id) WHERE external_id IS NOT NULL""",
    """CREATE INDEX ix_lead_dup_b ON lead_duplicate_link (lead_b_id)""",
    """CREATE INDEX ix_lead_dup_resolved_by ON lead_duplicate_link (resolved_by)""",
]

LEAD_POLICIES = [
    """ALTER TABLE lead ENABLE ROW LEVEL SECURITY""",
    """CREATE POLICY lead_sel_own ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id())
)""",
    """CREATE POLICY lead_sel_org_subtree ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))
)""",
    """CREATE POLICY lead_sel_territory ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))
)""",
    """CREATE POLICY lead_sel_partner_subtree ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))
)""",
    """CREATE POLICY lead_sel_global ON lead FOR SELECT USING (
  (SELECT app_scope('leads')) = 'global'
)""",
    """CREATE POLICY lead_res_perm ON lead AS RESTRICTIVE FOR SELECT USING (
  (SELECT app_has_permission('leads', 'view'))
)""",
    """CREATE POLICY lead_res_deleted ON lead AS RESTRICTIVE FOR SELECT USING (
  deleted_at IS NULL OR (SELECT app_has_permission('leads', 'delete'))
)""",
    """CREATE POLICY lead_ins ON lead FOR INSERT WITH CHECK (
  (((SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('leads')) = 'global'))
  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))
  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))
  AND (assigned_partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = assigned_partner_id))
)""",
    """CREATE POLICY lead_ins_perm ON lead AS RESTRICTIVE FOR INSERT WITH CHECK (
  (SELECT app_has_permission('leads', 'create'))
)""",
    """CREATE POLICY lead_upd ON lead FOR UPDATE USING (
  ((SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('leads')) = 'global')
) WITH CHECK (
  ((SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('leads')) = 'global')
)""",
    """CREATE POLICY lead_upd_perm ON lead AS RESTRICTIVE FOR UPDATE USING (
  (SELECT app_has_permission('leads', 'edit'))
)""",
    """CREATE POLICY lead_del ON lead FOR DELETE USING (
  ((SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('leads')) = 'global')
)""",
    """CREATE POLICY lead_del_perm ON lead AS RESTRICTIVE FOR DELETE USING (
  (SELECT app_has_permission('leads', 'delete'))
)""",
]

LEAD_INDEXES = [
    """CREATE INDEX IF NOT EXISTS ix_lead_owner_user_id ON lead (owner_user_id)""",
    """CREATE INDEX IF NOT EXISTS ix_lead_owner_org_unit_id ON lead (owner_org_unit_id)""",
    """CREATE INDEX IF NOT EXISTS ix_lead_territory_id ON lead (territory_id)""",
    """CREATE INDEX IF NOT EXISTS ix_lead_assigned_partner_id ON lead (assigned_partner_id)""",
    """CREATE INDEX IF NOT EXISTS ix_lead_deleted_at_live ON lead (deleted_at) WHERE deleted_at IS NULL""",
]

LEAD_PARENT_GUARD = [
    """CREATE FUNCTION lead_parent_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
        BEGIN
            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL
               AND NOT authz_visible('territory', NEW.territory_id) THEN
                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.owner_org_unit_id IS DISTINCT FROM OLD.owner_org_unit_id AND NEW.owner_org_unit_id IS NOT NULL
               AND NOT authz_visible('org_unit', NEW.owner_org_unit_id) THEN
                RAISE EXCEPTION 'owner_org_unit_id % is not in your scope', NEW.owner_org_unit_id
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.assigned_partner_id IS DISTINCT FROM OLD.assigned_partner_id AND NEW.assigned_partner_id IS NOT NULL
               AND NOT authz_visible('channel_partner', NEW.assigned_partner_id) THEN
                RAISE EXCEPTION 'assigned_partner_id % is not in your scope', NEW.assigned_partner_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $fn$""",
    """CREATE TRIGGER trg_lead_parent_guard
            BEFORE UPDATE OF territory_id, owner_org_unit_id, assigned_partner_id ON lead
            FOR EACH ROW EXECUTE FUNCTION lead_parent_guard()""",
]

FUNCTIONS = [
    """CREATE FUNCTION lead_allocate_inquiry_no(p_state_code text, p_fy text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT app_has_permission('leads', 'create') THEN
        RAISE EXCEPTION 'not permitted to create leads' USING ERRCODE = '42501';
    END IF;
    INSERT INTO inquiry_counter (state_code, financial_year, last_value)
    VALUES (p_state_code, p_fy, 1)
    ON CONFLICT (state_code, financial_year)
    DO UPDATE SET last_value = inquiry_counter.last_value + 1
    RETURNING last_value INTO v_n;
    RETURN 'POL/' || p_state_code || '/' || p_fy || '/' || lpad(v_n::text, 5, '0');
END $fn$""",
    """CREATE FUNCTION lead_visible(p_lead_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM lead WHERE id = p_lead_id AND (
(((SELECT app_scope('leads')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('leads')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('leads')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('leads')) = 'partner_subtree'
  AND assigned_partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('leads')) = 'global'))
  AND ((SELECT app_has_permission('leads', 'view')))
  AND (deleted_at IS NULL OR (SELECT app_has_permission('leads', 'delete')))
    ))
$fn$""",
    """CREATE FUNCTION lead_people(p_lead_id uuid)
RETURNS TABLE (kind text, id uuid, name text, detail text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT lead_visible(p_lead_id) THEN RETURN; END IF;
    RETURN QUERY
        SELECT 'owner', u.id, u.full_name, NULL::text
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
END $fn$""",
    """CREATE FUNCTION lead_timeline(p_lead_id uuid, p_before_at timestamptz,
                                  p_before_id uuid, p_limit int)
RETURNS SETOF activity_event
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT lead_visible(p_lead_id) THEN RETURN; END IF;
    RETURN QUERY
        SELECT * FROM activity_event
         WHERE (lead_id = p_lead_id
                OR lead_id IN (SELECT id FROM lead WHERE merged_into_id = p_lead_id))
           AND (p_before_at IS NULL OR (occurred_at, id) < (p_before_at, p_before_id))
         ORDER BY occurred_at DESC, id DESC
         LIMIT p_limit;
END $fn$""",
    """CREATE FUNCTION lead_merge(p_loser uuid, p_survivor uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('leads', 'edit') THEN
        RAISE EXCEPTION 'not permitted to edit leads' USING ERRCODE = '42501';
    END IF;
    IF p_loser = p_survivor THEN
        RAISE EXCEPTION 'a lead cannot merge into itself' USING ERRCODE = 'LEADM';
    END IF;
    IF NOT lead_visible(p_loser) OR NOT lead_visible(p_survivor) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'LEADN';
    END IF;
    IF EXISTS (SELECT 1 FROM lead WHERE id IN (p_loser, p_survivor)
                 AND stage IN ('won', 'lost', 'merged')) THEN
        RAISE EXCEPTION 'a won, lost or merged lead cannot be merged' USING ERRCODE = 'LEADT';
    END IF;
    UPDATE lead SET merged_into_id = p_survivor WHERE merged_into_id = p_loser;
    INSERT INTO lead_duplicate_link (lead_a_id, lead_b_id, signal, score, state, created_by)
    SELECT least(x.other, p_survivor), greatest(x.other, p_survivor), x.signal, x.score,
           'pending', app_current_user_id()
      FROM (SELECT dl.signal, dl.score,
                   CASE WHEN dl.lead_a_id = p_loser THEN dl.lead_b_id ELSE dl.lead_a_id END AS other
              FROM lead_duplicate_link dl
             WHERE dl.state = 'pending' AND (dl.lead_a_id = p_loser OR dl.lead_b_id = p_loser)) x
     WHERE x.other <> p_survivor
    ON CONFLICT (lead_a_id, lead_b_id) DO NOTHING;
    UPDATE lead_duplicate_link SET state = 'merged', resolved_by = app_current_user_id(),
           resolved_at = now()
     WHERE state = 'pending' AND (lead_a_id = p_loser OR lead_b_id = p_loser);
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('lead', p_survivor, p_survivor, 'lead.merged', app_current_user_id(),
            jsonb_build_object('loser', p_loser, 'survivor', p_survivor)),
           ('lead', p_loser, p_loser, 'lead.merged', app_current_user_id(),
            jsonb_build_object('loser', p_loser, 'survivor', p_survivor));
    UPDATE lead SET stage = 'merged', merged_into_id = p_survivor WHERE id = p_loser;
END $fn$""",
    """CREATE FUNCTION lead_close_links(p_lead_id uuid, p_state text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('leads', 'edit') THEN
        RAISE EXCEPTION 'not permitted to edit leads' USING ERRCODE = '42501';
    END IF;
    IF NOT lead_visible(p_lead_id) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'LEADN';
    END IF;
    UPDATE lead_duplicate_link SET state = p_state::lead_dup_state,
           resolved_by = app_current_user_id(), resolved_at = now()
     WHERE state = 'pending' AND (lead_a_id = p_lead_id OR lead_b_id = p_lead_id);
END $fn$""",
    """CREATE FUNCTION authz_user_assignable(p_module text, p_user_id uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_scope text;
BEGIN
    IF p_module NOT IN ('leads') THEN RETURN false; END IF;
    IF NOT app_has_permission(p_module, 'edit') THEN RETURN false; END IF;
    v_scope := app_scope(p_module);
    RETURN EXISTS (
        SELECT 1 FROM app_user u
         WHERE u.id = p_user_id AND u.user_type = 'staff' AND u.is_active
           AND u.deleted_at IS NULL
           AND (v_scope = 'global'
                OR (v_scope = 'org_subtree' AND u.org_unit_id IN
                    (SELECT descendant_id FROM org_closure
                      WHERE ancestor_id = app_current_org_unit()))));
END $fn$""",
    """CREATE FUNCTION staff_directory(p_module text)
RETURNS TABLE (id uuid, full_name text, org_unit_id uuid)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_scope text;
BEGIN
    IF p_module NOT IN ('leads') THEN RETURN; END IF;
    IF NOT app_has_permission(p_module, 'edit') THEN RETURN; END IF;
    v_scope := app_scope(p_module);
    RETURN QUERY
        SELECT u.id, u.full_name, u.org_unit_id FROM app_user u
         WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
           AND (v_scope = 'global'
                OR (v_scope = 'org_subtree' AND u.org_unit_id IN
                    (SELECT descendant_id FROM org_closure
                      WHERE ancestor_id = app_current_org_unit())));
END $fn$""",
    """CREATE FUNCTION lead_auto_owner(p_territory_id uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_owner uuid;
BEGIN
    IF NOT app_has_permission('leads', 'create') THEN
        RAISE EXCEPTION 'not permitted to create leads' USING ERRCODE = '42501';
    END IF;
    SELECT u.id INTO v_owner
      FROM app_user u
      JOIN org_unit ou ON ou.id = u.org_unit_id
      JOIN territory_closure tc ON tc.ancestor_id = ou.territory_id
                               AND tc.descendant_id = p_territory_id
     WHERE u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
     ORDER BY tc.depth ASC,
              (SELECT count(*) FROM lead l
                WHERE l.owner_user_id = u.id
                  AND l.stage NOT IN ('won', 'lost', 'merged', 'dormant')) ASC,
              u.id ASC
     LIMIT 1;
    RETURN v_owner;
END $fn$""",
]

FUNCTION_SIGS = ['lead_allocate_inquiry_no(text, text)', 'lead_visible(uuid)', 'lead_people(uuid)', 'lead_timeline(uuid, timestamptz, uuid, integer)', 'lead_merge(uuid, uuid)', 'lead_close_links(uuid, text)', 'authz_user_assignable(text, uuid)', 'staff_directory(text)', 'lead_auto_owner(uuid)']

RLS_TABLES = ['lead_source', 'mis_system', 'won_lost_reason', 'lead_score_rule', 'lead_duplicate_link']

# Re-applied from the generator when its cross-table-parent handling changed
# (cross-vendor B-2). 005 created these _upd policies with an EXISTS on each
# parent in WITH CHECK, which on UPDATE re-validates an unchanged parent the
# row's own editor may not see. The generator now keeps parents out of UPDATE
# and guards a *change* with {t}_parent_guard(), which sees OLD. Embedded as
# snapshots, the way 005 embeds its generated block; a fresh generation is
# compared to live by the drift test.
REAPPLY: dict[str, dict[str, object]] = {
    "app_user": {
        "new": """CREATE POLICY app_user_upd ON app_user FOR UPDATE USING (
  ((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global')
) WITH CHECK (
  ((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global')
)""",
        "old": """CREATE POLICY app_user_upd ON app_user FOR UPDATE USING (
  ((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global')
) WITH CHECK (
  (((SELECT app_scope('users')) = 'own'
  AND id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('users')) = 'org_subtree'
  AND org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('users')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('users')) = 'global'))
  AND (org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = org_unit_id))
  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))
)""",
        "guard": [
            """CREATE FUNCTION app_user_parent_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
        BEGIN
            IF NEW.org_unit_id IS DISTINCT FROM OLD.org_unit_id AND NEW.org_unit_id IS NOT NULL
               AND NOT authz_visible('org_unit', NEW.org_unit_id) THEN
                RAISE EXCEPTION 'org_unit_id % is not in your scope', NEW.org_unit_id
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL
               AND NOT authz_visible('channel_partner', NEW.partner_id) THEN
                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $fn$""",
            """CREATE TRIGGER trg_app_user_parent_guard
            BEFORE UPDATE OF org_unit_id, partner_id ON app_user
            FOR EACH ROW EXECUTE FUNCTION app_user_parent_guard()""",
        ],
    },
    "channel_partner": {
        "new": """CREATE POLICY channel_partner_upd ON channel_partner FOR UPDATE USING (
  ((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('partners')) = 'global')
) WITH CHECK (
  ((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND ((id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))) OR (parent_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))))
  OR ((SELECT app_scope('partners')) = 'global')
)""",
        "old": """CREATE POLICY channel_partner_upd ON channel_partner FOR UPDATE USING (
  ((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('partners')) = 'global')
) WITH CHECK (
  (((SELECT app_scope('partners')) = 'org_subtree'
  AND territory_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
  OR ((SELECT app_scope('partners')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('partners')) = 'partner_subtree'
  AND ((id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))) OR (parent_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))))
  OR ((SELECT app_scope('partners')) = 'global'))
  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))
)""",
        "guard": [
            """CREATE FUNCTION channel_partner_parent_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
        BEGIN
            IF NEW.territory_id IS DISTINCT FROM OLD.territory_id AND NEW.territory_id IS NOT NULL
               AND NOT authz_visible('territory', NEW.territory_id) THEN
                RAISE EXCEPTION 'territory_id % is not in your scope', NEW.territory_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $fn$""",
            """CREATE TRIGGER trg_channel_partner_parent_guard
            BEFORE UPDATE OF territory_id ON channel_partner
            FOR EACH ROW EXECUTE FUNCTION channel_partner_parent_guard()""",
        ],
    },
}


def _hand(table: str) -> None:
    for t, stmt in HAND_POLICIES:
        if t == table:
            op.execute(stmt)


def upgrade() -> None:
    # Shared: the idempotency UPDATE path (B-1).
    op.execute(f"GRANT UPDATE ON idempotency_record TO {APP_ROLE}")
    op.execute(next(s for t, s in HAND_POLICIES if t == "idempotency_record"))

    # The lead schema.
    for stmt in ENUMS + TABLES + SEEDS + TRIGGERS + HAND_INDEXES + LEAD_INDEXES:
        op.execute(stmt)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for table, verbs in GRANTS.items():
        if table != "idempotency_record":
            op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")

    # lead's policies (generated) and the parent guard for a cross-table parent
    # change on UPDATE.
    for stmt in LEAD_POLICIES:
        op.execute(stmt)
    for stmt in LEAD_PARENT_GUARD:
        op.execute(stmt)

    # The nine definer functions the endpoints call, and their grants. Created
    # before the REVOKE sweep below so PUBLIC is stripped from them too.
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in FUNCTION_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")

    # The lookup masters and the duplicate-link table: RLS on, then their policies.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _hand(table)

    # inquiry_counter carries no grant and no policy: RLS on so it is fail-closed
    # like every other table, and the definer allocator writes it as the owner.
    op.execute("ALTER TABLE inquiry_counter ENABLE ROW LEVEL SECURITY")

    # activity_event gains the lead arm: drop 005's read policy, create the new one.
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    _hand("activity_event")

    # The generator's parent-guard change, applied to the two tables that predate it.
    for table, sql in REAPPLY.items():
        op.execute(f"DROP POLICY {table}_upd ON {table}")
        op.execute(sql["new"])
        for stmt in sql["guard"]:
            op.execute(stmt)

    # New functions are PUBLIC-executable until this runs; a migration's sweep does
    # not reach a later migration's, so 006 runs its own (cross-vendor B-6).
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    # Reverse the reapply: restore the 005 form of the two _upd policies.
    for table, sql in REAPPLY.items():
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_parent_guard ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {table}_parent_guard()")
        op.execute(f"DROP POLICY {table}_upd ON {table}")
        op.execute(sql["old"])

    # activity_event back to 005's read policy (no lead arm).
    op.execute("DROP POLICY IF EXISTS activity_event_sel ON activity_event")
    op.execute(
        "CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (\n  "
        "CASE entity_type\n    "
        "WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) "
        "OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)\n    "
        "WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)"
        "\n    ELSE (SELECT app_is_system())\n  END\n)"
    )

    op.execute("DROP TRIGGER IF EXISTS trg_lead_parent_guard ON lead")
    op.execute("DROP FUNCTION IF EXISTS lead_parent_guard()")
    for sig in FUNCTION_SIGS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")

    # The lead schema. Tables drop their own policies, triggers and indexes.
    for table in ("lead_duplicate_link", "lead", "inquiry_counter", "lead_score_rule",
                  "won_lost_reason", "mis_system", "lead_source"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for enum in ("lead_dup_state", "lead_dup_signal", "won_lost_kind", "lead_priority",
                 "inquiry_type", "lead_stage"):
        op.execute(f"DROP TYPE IF EXISTS {enum}")

    op.execute("DROP POLICY IF EXISTS idempotency_record_upd ON idempotency_record")
    op.execute(f"REVOKE UPDATE ON idempotency_record FROM {APP_ROLE}")
