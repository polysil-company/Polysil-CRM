"""012: quotations (FS-005).

Three tables (`quotation`, `quotation_line`, `quotation_counter`), the generated
policies and indexes for the `quotations` ScopeSpec, the parent guard, two
immutability triggers, the lead-to-quotation scope propagation, sixteen functions,
two 006 functions replaced (`lead_merge()` re-scopes the losers' quotations,
`lead_timeline()` filters quotation events through the quotation's own
visibility), and `activity_event` regenerated with the quotation arm and the
quotation CHECK.

Everything here was reviewed by execution before it was written: the immutability
trigger admits the scope columns only at trigger depth 2 or more, because a
definer's direct UPDATE runs at depth 1 (plan review round 3); the render claim is
a lease committed before rendering, charged once (cross-vendor B-5); the seller
block is a snapshot (cross-vendor B-7).

GRANTS, HAND_POLICIES and the generated snapshots are read by
tests/db/migration_grants.py and the drift tests, unioned with the earlier
migrations. The revision ends with its own PUBLIC revoke: a new function is
PUBLIC-executable on creation and an earlier migration's sweep does not reach it.

Revision ID: 012_quotations
Revises: 011_master_immutability
"""

# ruff: noqa: E501  (generated and embedded SQL; its line length is not ours to wrap)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "012_quotations"
down_revision: str | None = "011_master_immutability"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
ANON_ROLE = "app_anon"
# uuid5(NAMESPACE_DNS, "polysil.system"), migration 005's principal: the actor of
# a public open, which no signed-in person performs.
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"
GSTIN_PATTERN = "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$"
MAX_RENDER_ATTEMPTS = 5

TABLES = ("quotation", "quotation_line", "quotation_counter")

# ── grants and hand-written policies, read by tests/db/migration_grants.py ────

GRANTS: dict[str, str] = {
    # no DELETE: a soft delete is an UPDATE, and a sent document is never deleted
    "quotation": "SELECT, INSERT, UPDATE",
    # a draft's lines are replaced by delete and insert, so this one takes DELETE;
    # the policies below gate every write on quotations.edit and the trigger
    # narrows them to drafts
    "quotation_line": "SELECT, INSERT, UPDATE, DELETE",
}

_LINE_PARENT = "EXISTS (SELECT 1 FROM quotation q WHERE q.id = quotation_id)"
_Q_VIEW = "(SELECT app_has_permission('quotations', 'view'))"
_Q_EDIT = "(SELECT app_has_permission('quotations', 'edit'))"

HAND_POLICIES: list[tuple[str, str]] = [
    # quotation_line follows its parent: a line is readable when its document is,
    # and every write is gated on quotations.edit, because neither a field officer
    # nor a district manager holds quotations.delete and both replace a draft's
    # lines (plan review round 2 B-5). The trigger below refuses writes on a
    # non-draft parent, which a policy cannot express without the parent's status.
    ("quotation_line", f"CREATE POLICY quotation_line_sel ON quotation_line FOR SELECT USING (\n  {_LINE_PARENT}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_res_perm ON quotation_line AS RESTRICTIVE FOR SELECT USING (\n  {_Q_VIEW}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_ins ON quotation_line FOR INSERT WITH CHECK (\n  {_LINE_PARENT}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_ins_perm ON quotation_line AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_Q_EDIT}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_upd ON quotation_line FOR UPDATE USING (\n  {_LINE_PARENT}\n) WITH CHECK (\n  {_LINE_PARENT}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_upd_perm ON quotation_line AS RESTRICTIVE FOR UPDATE USING (\n  {_Q_EDIT}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_del ON quotation_line FOR DELETE USING (\n  {_LINE_PARENT}\n)"),
    ("quotation_line", f"CREATE POLICY quotation_line_del_perm ON quotation_line AS RESTRICTIVE FOR DELETE USING (\n  {_Q_EDIT}\n)"),
    # activity_event gains the quotation arm, resolved through entity_id under the
    # quotation's own policies (api/authz/activity.py, ENTITY_BY_ID). Supersedes
    # 007's literal; the drift test compares the union's last-wins to the emitter.
    ("activity_event", """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)
    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)
    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""),
]

ACTIVITY_CHECK = ("(entity_type <> 'lead' OR lead_id IS NOT NULL) AND "
                  "(entity_type <> 'channel_partner' OR partner_id IS NOT NULL) AND "
                  "(entity_type <> 'customer' OR customer_id IS NOT NULL) AND "
                  "(entity_type <> 'quotation' OR lead_id IS NOT NULL)")
ACTIVITY_CHECK_BEFORE = ("(entity_type <> 'lead' OR lead_id IS NOT NULL) AND "
                         "(entity_type <> 'channel_partner' OR partner_id IS NOT NULL) AND "
                         "(entity_type <> 'customer' OR customer_id IS NOT NULL)")

# ── the schema ───────────────────────────────────────────────────────────────

ENUMS = [
    """CREATE TYPE quotation_source AS ENUM ('internal', 'external')""",
    """CREATE TYPE quotation_sales_type AS ENUM ('commercial', 'industrial', 'export', 'subsidised', 'marketing', 'sample')""",
    """CREATE TYPE quotation_status AS ENUM ('draft', 'sent', 'viewed', 'accepted', 'rejected', 'negotiation', 'expired')""",
]

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz"""

TABLES_SQL = [
    f"""CREATE TABLE quotation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quote_no citext,
    version int NOT NULL DEFAULT 1,
    supersedes_id uuid REFERENCES quotation(id),
    superseded_by_id uuid REFERENCES quotation(id),
    lead_id uuid NOT NULL REFERENCES lead(id),
    source quotation_source NOT NULL DEFAULT 'internal',
    sales_type quotation_sales_type NOT NULL,
    status quotation_status NOT NULL DEFAULT 'draft',
    partner_id uuid REFERENCES channel_partner(id),
    owner_user_id uuid REFERENCES app_user(id),
    owner_org_unit_id uuid NOT NULL REFERENCES org_unit(id),
    territory_id uuid NOT NULL REFERENCES territory(id),
    party_name text NOT NULL,
    party_mobile text NOT NULL,
    party_address text,
    party_gstin citext,
    seller_gstin_id uuid NOT NULL REFERENCES seller_gstin(id),
    seller_legal_name text,
    seller_gstin_no citext,
    seller_address text,
    seller_state_code text,
    place_of_supply_territory_id uuid NOT NULL REFERENCES territory(id),
    place_of_supply_state_id uuid NOT NULL REFERENCES territory(id),
    intra_state boolean NOT NULL,
    price_effective_date date NOT NULL,
    price_list_id uuid REFERENCES price_list(id),
    gross numeric(14,2) NOT NULL DEFAULT 0,
    discount numeric(14,2) NOT NULL DEFAULT 0,
    taxable numeric(14,2) NOT NULL DEFAULT 0,
    cgst numeric(14,2) NOT NULL DEFAULT 0,
    sgst numeric(14,2) NOT NULL DEFAULT 0,
    igst numeric(14,2) NOT NULL DEFAULT 0,
    total numeric(14,2) NOT NULL DEFAULT 0,
    is_provisional boolean NOT NULL DEFAULT false,
    terms text,
    valid_until date,
    sent_at timestamptz,
    viewed_at timestamptz,
    open_count int NOT NULL DEFAULT 0,
    accepted_at timestamptz,
    rejected_at timestamptz,
    decided_by uuid REFERENCES app_user(id),
    decision_remark text,
    share_token text UNIQUE,
    notify_channel text,
    pdf_state text,
    pdf_key text,
    pdf_attempts int NOT NULL DEFAULT 0,
    pdf_next_attempt_at timestamptz NOT NULL DEFAULT now(),
    pdf_lease_until timestamptz,
    pdf_lease_token uuid,
    pdf_error text,
    {AUDIT},
    CONSTRAINT uq_quotation_no_version UNIQUE (quote_no, version),
    CONSTRAINT ck_quotation_version CHECK (version >= 1),
    CONSTRAINT ck_quotation_draft_number CHECK (status <> 'draft' OR quote_no IS NULL OR version > 1),
    CONSTRAINT ck_quotation_sent_fields CHECK (source = 'external' OR status = 'draft' OR (
        quote_no IS NOT NULL AND sent_at IS NOT NULL AND valid_until IS NOT NULL
        AND share_token IS NOT NULL AND seller_legal_name IS NOT NULL
        AND seller_gstin_no IS NOT NULL AND seller_state_code IS NOT NULL
        AND pdf_state IS NOT NULL)),
    CONSTRAINT ck_quotation_validity CHECK (source = 'external' OR (status = 'draft') = (valid_until IS NULL)),
    CONSTRAINT ck_quotation_accepted CHECK (accepted_at IS NULL OR status = 'accepted'),
    CONSTRAINT ck_quotation_supersedes CHECK (supersedes_id IS NULL OR version > 1),
    CONSTRAINT ck_quotation_party_name CHECK (length(btrim(party_name)) BETWEEN 1 AND 200),
    CONSTRAINT ck_quotation_party_address CHECK (party_address IS NULL OR length(party_address) <= 500),
    CONSTRAINT ck_quotation_terms CHECK (terms IS NULL OR length(terms) <= 2000),
    CONSTRAINT ck_quotation_party_gstin CHECK (party_gstin IS NULL OR (
        party_gstin ~ '{GSTIN_PATTERN}' AND party_gstin = upper(party_gstin))),
    CONSTRAINT ck_quotation_pdf_state CHECK (pdf_state IS NULL OR pdf_state IN ('pending', 'rendering', 'ready', 'failed')),
    CONSTRAINT ck_quotation_notify_channel CHECK (notify_channel IS NULL OR notify_channel IN ('whatsapp', 'none'))
)""",
    """CREATE TABLE quotation_line (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    quotation_id uuid NOT NULL REFERENCES quotation(id) ON DELETE CASCADE,
    line_no int NOT NULL,
    product_id uuid NOT NULL REFERENCES product(id),
    description text NOT NULL,
    hsn_code text NOT NULL,
    uom text NOT NULL,
    qty numeric(12,3) NOT NULL,
    rate numeric(14,2) NOT NULL,
    price_list_id uuid NOT NULL REFERENCES price_list(id),
    price_list_item_id uuid NOT NULL REFERENCES price_list_item(id),
    gst_rate_id uuid NOT NULL REFERENCES gst_rate(id),
    gross numeric(14,2) NOT NULL,
    discount_pct numeric(6,3) NOT NULL DEFAULT 0,
    discount1_amt numeric(14,2) NOT NULL DEFAULT 0,
    after_discount1 numeric(14,2) NOT NULL,
    discount2_pct numeric(6,3) NOT NULL DEFAULT 0,
    discount2_amt numeric(14,2) NOT NULL DEFAULT 0,
    after_discount2 numeric(14,2) NOT NULL,
    discount3_pct numeric(6,3) NOT NULL DEFAULT 0,
    discount3_amt numeric(14,2) NOT NULL DEFAULT 0,
    discount numeric(14,2) NOT NULL DEFAULT 0,
    taxable numeric(14,2) NOT NULL,
    gst_slab numeric(6,3) NOT NULL,
    cgst_rate numeric(6,3) NOT NULL,
    sgst_rate numeric(6,3) NOT NULL,
    igst_rate numeric(6,3) NOT NULL,
    cgst numeric(14,2) NOT NULL,
    sgst numeric(14,2) NOT NULL,
    igst numeric(14,2) NOT NULL,
    total numeric(14,2) NOT NULL,
    provisional_fields text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_quotation_line_no UNIQUE (quotation_id, line_no),
    CONSTRAINT ck_quotation_line_qty CHECK (qty > 0),
    CONSTRAINT ck_quotation_line_pcts CHECK (
        discount_pct BETWEEN 0 AND 100 AND discount2_pct BETWEEN 0 AND 100
        AND discount3_pct BETWEEN 0 AND 100),
    CONSTRAINT ck_quotation_line_cascade CHECK (
        after_discount1 = gross - discount1_amt
        AND after_discount2 = after_discount1 - discount2_amt
        AND taxable = after_discount2 - discount3_amt
        AND discount = discount1_amt + discount2_amt + discount3_amt),
    CONSTRAINT ck_quotation_line_total CHECK (total = taxable + cgst + sgst + igst)
)""",
    """CREATE TABLE quotation_counter (
    state_code text NOT NULL,
    financial_year text NOT NULL,
    last_value int NOT NULL DEFAULT 0,
    PRIMARY KEY (state_code, financial_year)
)""",
]

# Generated by policy_sql.policies_for(SPECS["quotations"]) and pasted, the way 006
# pastes the lead's; the drift test regenerates and compares against pg_policies.
QUOTATION_POLICIES = [
    """ALTER TABLE quotation ENABLE ROW LEVEL SECURITY""",
    """CREATE POLICY quotation_sel_own ON quotation FOR SELECT USING (
  (SELECT app_scope('quotations')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id())
)""",
    """CREATE POLICY quotation_sel_org_subtree ON quotation FOR SELECT USING (
  (SELECT app_scope('quotations')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))
)""",
    """CREATE POLICY quotation_sel_territory ON quotation FOR SELECT USING (
  (SELECT app_scope('quotations')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id()))
)""",
    """CREATE POLICY quotation_sel_partner_subtree ON quotation FOR SELECT USING (
  (SELECT app_scope('quotations')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner()))
)""",
    """CREATE POLICY quotation_sel_global ON quotation FOR SELECT USING (
  (SELECT app_scope('quotations')) = 'global'
)""",
    """CREATE POLICY quotation_res_perm ON quotation AS RESTRICTIVE FOR SELECT USING (
  (SELECT app_has_permission('quotations', 'view'))
)""",
    """CREATE POLICY quotation_res_deleted ON quotation AS RESTRICTIVE FOR SELECT USING (
  deleted_at IS NULL OR (SELECT app_has_permission('quotations', 'delete'))
)""",
    """CREATE POLICY quotation_ins ON quotation FOR INSERT WITH CHECK (
  (((SELECT app_scope('quotations')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('quotations')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('quotations')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('quotations')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('quotations')) = 'global'))
  AND (lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))
  AND (territory_id IS NULL OR EXISTS (SELECT 1 FROM territory p WHERE p.id = territory_id))
  AND (owner_org_unit_id IS NULL OR EXISTS (SELECT 1 FROM org_unit p WHERE p.id = owner_org_unit_id))
  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id))
)""",
    """CREATE POLICY quotation_ins_perm ON quotation AS RESTRICTIVE FOR INSERT WITH CHECK (
  (SELECT app_has_permission('quotations', 'create'))
)""",
    """CREATE POLICY quotation_upd ON quotation FOR UPDATE USING (
  ((SELECT app_scope('quotations')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('quotations')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('quotations')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('quotations')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('quotations')) = 'global')
) WITH CHECK (
  ((SELECT app_scope('quotations')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('quotations')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('quotations')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('quotations')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('quotations')) = 'global')
)""",
    """CREATE POLICY quotation_upd_perm ON quotation AS RESTRICTIVE FOR UPDATE USING (
  (SELECT app_has_permission('quotations', 'edit'))
)""",
    """CREATE POLICY quotation_del ON quotation FOR DELETE USING (
  ((SELECT app_scope('quotations')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('quotations')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('quotations')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('quotations')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('quotations')) = 'global')
)""",
    """CREATE POLICY quotation_del_perm ON quotation AS RESTRICTIVE FOR DELETE USING (
  (SELECT app_has_permission('quotations', 'delete'))
)""",
]

# policy_sql.indexes_for(SPECS["quotations"]), verbatim: the policy-column test
# matches on these names.
GENERATED_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_quotation_owner_user_id ON quotation (owner_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_quotation_owner_org_unit_id ON quotation (owner_org_unit_id)",
    "CREATE INDEX IF NOT EXISTS ix_quotation_territory_id ON quotation (territory_id)",
    "CREATE INDEX IF NOT EXISTS ix_quotation_partner_id ON quotation (partner_id)",
    "CREATE INDEX IF NOT EXISTS ix_quotation_deleted_at_live ON quotation (deleted_at) WHERE deleted_at IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_quotation_lead_id ON quotation (lead_id)",
]

HAND_INDEXES = [
    "CREATE INDEX ix_quotation_lead_created ON quotation (lead_id, created_at DESC)",
    "CREATE INDEX ix_quotation_expiry ON quotation (status, valid_until) WHERE status IN ('sent', 'viewed', 'negotiation')",
    # both claim arms: pending by due time, rendering by an expired lease
    "CREATE INDEX ix_quotation_render ON quotation (pdf_state, pdf_next_attempt_at, pdf_lease_until) WHERE pdf_state IN ('pending', 'rendering')",
    "CREATE INDEX ix_quotation_list ON quotation (created_at DESC, id DESC) WHERE superseded_by_id IS NULL AND deleted_at IS NULL",
    "CREATE INDEX ix_quotation_party_name_trgm ON quotation USING gin (party_name gin_trgm_ops)",
    "CREATE INDEX ix_quotation_quote_no_trgm ON quotation USING gin ((quote_no::text) gin_trgm_ops)",
    "CREATE INDEX ix_quotation_party_mobile ON quotation (party_mobile)",
    "CREATE INDEX ix_quotation_supersedes ON quotation (supersedes_id)",
    "CREATE INDEX ix_quotation_superseded_by ON quotation (superseded_by_id)",
    # one open revision per number; a fresh draft has no number and is not counted
    "CREATE UNIQUE INDEX uq_quotation_open_draft ON quotation (quote_no) WHERE status = 'draft' AND deleted_at IS NULL AND quote_no IS NOT NULL",
    "CREATE INDEX ix_quotation_line_quotation ON quotation_line (quotation_id, line_no)",
    "CREATE INDEX ix_quotation_line_product ON quotation_line (product_id)",
]

# ── the generated parent guard (policy_sql.parent_guard_ddl), verbatim ────────

PARENT_GUARD = [
    """CREATE FUNCTION quotation_parent_guard() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = public, pg_temp AS $fn$
        BEGIN
            IF NEW.lead_id IS DISTINCT FROM OLD.lead_id AND NEW.lead_id IS NOT NULL
               AND NOT authz_visible('lead', NEW.lead_id) THEN
                RAISE EXCEPTION 'lead_id % is not in your scope', NEW.lead_id
                    USING ERRCODE = '42501';
            END IF;
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
            IF NEW.partner_id IS DISTINCT FROM OLD.partner_id AND NEW.partner_id IS NOT NULL
               AND NOT authz_visible('channel_partner', NEW.partner_id) THEN
                RAISE EXCEPTION 'partner_id % is not in your scope', NEW.partner_id
                    USING ERRCODE = '42501';
            END IF;
            RETURN NEW;
        END $fn$""",
    """CREATE TRIGGER trg_quotation_parent_guard
            BEFORE UPDATE OF lead_id, territory_id, owner_org_unit_id, partner_id ON quotation
            FOR EACH ROW EXECUTE FUNCTION quotation_parent_guard()""",
]

# ── the two immutability triggers and the scope propagation ───────────────────

# The columns a sent quotation may still change. Everything else is the document.
_MUTABLE_AFTER_SEND = ("'status', 'viewed_at', 'open_count', 'accepted_at', 'rejected_at', "
                       "'decided_by', 'decision_remark', 'superseded_by_id', 'pdf_state', "
                       "'pdf_key', 'pdf_attempts', 'pdf_next_attempt_at', 'pdf_lease_until', "
                       "'pdf_lease_token', 'pdf_error', 'updated_at', 'updated_by', "
                       "'synced_at', 'external_id'")

TRIGGER_FUNCTIONS = [
    f"""CREATE FUNCTION refuse_sent_quotation_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE
    v_allowed text[] := ARRAY[{_MUTABLE_AFTER_SEND}];
BEGIN
    -- A draft is freely editable. That is what drafts are for.
    IF OLD.status = 'draft' THEN
        RETURN NEW;
    END IF;
    -- The scope columns follow the lead, and only the lead's propagation trigger
    -- may move them: a statement runs at depth 1, a definer's own UPDATE runs at
    -- depth 1, the propagation runs at depth 2 or more (executed, plan review
    -- round 3).
    IF pg_trigger_depth() > 1 THEN
        v_allowed := v_allowed || ARRAY['owner_user_id', 'owner_org_unit_id', 'territory_id'];
    END IF;
    IF (to_jsonb(OLD) - v_allowed) <> (to_jsonb(NEW) - v_allowed) THEN
        RAISE EXCEPTION 'a sent quotation cannot change; revise it'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status <> OLD.status AND NOT (
        (OLD.status = 'sent' AND NEW.status IN ('viewed', 'accepted', 'rejected', 'negotiation', 'expired'))
        OR (OLD.status = 'viewed' AND NEW.status IN ('accepted', 'rejected', 'negotiation', 'expired'))
        OR (OLD.status = 'negotiation' AND NEW.status IN ('accepted', 'rejected', 'expired'))) THEN
        RAISE EXCEPTION 'a % quotation cannot become %', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;
    IF NEW.superseded_by_id IS DISTINCT FROM OLD.superseded_by_id
       AND NEW.superseded_by_id IS NOT NULL AND NEW.status = 'accepted' THEN
        RAISE EXCEPTION 'an accepted quotation cannot be superseded'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$""",
    """CREATE FUNCTION refuse_sent_quotation_line_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
DECLARE
    v_frozen boolean;
BEGIN
    -- Both parents on an UPDATE: checking only the destination let a line be
    -- moved out of a sent quotation into a draft (cross-vendor A-2, reproduced).
    -- A parent that is gone is a cascade or a cleanup, not an edit.
    SELECT bool_or(status <> 'draft') INTO v_frozen FROM quotation
     WHERE id IN (NEW.quotation_id, OLD.quotation_id);
    IF v_frozen THEN
        RAISE EXCEPTION 'the lines of a sent quotation cannot change; revise it'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END $fn$""",
    # DEFINER: the caller reassigning a lead may hold no quotation permission at
    # all (marketing, the portal roles), and a propagation filtered by RLS would
    # silently do nothing. Survivors cascade to their merged losers, which cascade
    # to their own quotations; after lead_merge() flattens a chain no loser has
    # losers of its own, so the recursion is one level deep.
    """CREATE FUNCTION lead_scope_to_quotations() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    UPDATE quotation
       SET owner_user_id = NEW.owner_user_id,
           owner_org_unit_id = NEW.owner_org_unit_id,
           territory_id = NEW.territory_id
     WHERE lead_id = NEW.id AND deleted_at IS NULL
       AND (owner_user_id IS DISTINCT FROM NEW.owner_user_id
            OR owner_org_unit_id IS DISTINCT FROM NEW.owner_org_unit_id
            OR territory_id IS DISTINCT FROM NEW.territory_id);
    IF NEW.merged_into_id IS NULL THEN
        UPDATE lead
           SET owner_user_id = NEW.owner_user_id,
               owner_org_unit_id = NEW.owner_org_unit_id,
               territory_id = NEW.territory_id
         WHERE merged_into_id = NEW.id
           AND (owner_user_id IS DISTINCT FROM NEW.owner_user_id
                OR owner_org_unit_id IS DISTINCT FROM NEW.owner_org_unit_id
                OR territory_id IS DISTINCT FROM NEW.territory_id);
    END IF;
    RETURN NULL;
END $fn$""",
]

TRIGGERS = [
    # BEFORE triggers fire in name order: parent_guard, refuse_sent_edit, updated_at.
    """CREATE TRIGGER trg_quotation_refuse_sent_edit BEFORE UPDATE ON quotation FOR EACH ROW EXECUTE FUNCTION refuse_sent_quotation_edit()""",
    """CREATE TRIGGER trg_quotation_updated_at BEFORE UPDATE ON quotation FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_quotation_audit AFTER INSERT OR UPDATE OR DELETE ON quotation FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_quotation_line_refuse_sent_edit BEFORE INSERT OR UPDATE OR DELETE ON quotation_line FOR EACH ROW EXECUTE FUNCTION refuse_sent_quotation_line_edit()""",
    """CREATE TRIGGER trg_quotation_line_updated_at BEFORE UPDATE ON quotation_line FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
    """CREATE TRIGGER trg_quotation_line_audit AFTER INSERT OR UPDATE OR DELETE ON quotation_line FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    """CREATE TRIGGER trg_lead_scope_to_quotations AFTER UPDATE OF owner_user_id, owner_org_unit_id, territory_id ON lead FOR EACH ROW EXECUTE FUNCTION lead_scope_to_quotations()""",
]

# ── the definer functions ─────────────────────────────────────────────────────

_VISIBLE = """(((SELECT app_scope('quotations')) = 'own'
  AND owner_user_id = (SELECT app_current_user_id()))
  OR ((SELECT app_scope('quotations')) = 'org_subtree'
  AND owner_org_unit_id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit())))
  OR ((SELECT app_scope('quotations')) = 'territory'
  AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))
  OR ((SELECT app_scope('quotations')) = 'partner_subtree'
  AND partner_id IN (SELECT descendant_id FROM partner_closure WHERE ancestor_id = (SELECT app_current_partner())))
  OR ((SELECT app_scope('quotations')) = 'global'))
  AND ((SELECT app_has_permission('quotations', 'view')))
  AND (deleted_at IS NULL OR (SELECT app_has_permission('quotations', 'delete')))"""

_PUBLIC_ROW = """jsonb_build_object(
        'id', q.id, 'quote_no', q.quote_no, 'version', q.version, 'status', q.status,
        'sales_type', q.sales_type,
        'seller', jsonb_build_object('legal_name', q.seller_legal_name, 'gstin', q.seller_gstin_no),
        'sent_at', q.sent_at, 'valid_until', q.valid_until,
        'superseded', q.superseded_by_id IS NOT NULL,
        'totals', jsonb_build_object('gross', q.gross, 'discount', q.discount, 'taxable', q.taxable,
                                     'cgst', q.cgst, 'sgst', q.sgst, 'igst', q.igst, 'total', q.total),
        'line_count', (SELECT count(*) FROM quotation_line l WHERE l.quotation_id = q.id),
        'pdf_state', q.pdf_state, 'pdf_key', q.pdf_key)"""

FUNCTIONS = [
    # The number, at send: lead_allocate_inquiry_no with the prefix QT/ and a
    # separate counter (GAP-103). Guarded on the permission that sends.
    """CREATE FUNCTION quotation_allocate_no(p_state_code text, p_fy text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT app_has_permission('quotations', 'edit') THEN
        RAISE EXCEPTION 'not permitted to send quotations' USING ERRCODE = '42501';
    END IF;
    INSERT INTO quotation_counter (state_code, financial_year, last_value)
    VALUES (p_state_code, p_fy, 1)
    ON CONFLICT (state_code, financial_year)
    DO UPDATE SET last_value = quotation_counter.last_value + 1
    RETURNING last_value INTO v_n;
    RETURN 'QT/' || p_state_code || '/' || p_fy || '/'
           || lpad(v_n::text, greatest(5, length(v_n::text)), '0');
END $fn$""",
    # The quotation's SELECT predicate as the owner (policy_sql.guard_sql), the
    # shape of lead_visible(): a definer cannot borrow RLS, so it evaluates the
    # generated rule directly over the claim.
    f"""CREATE FUNCTION quotation_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM quotation WHERE id = p_id AND (
{_VISIBLE}
    ))
$fn$""",
    # AC-LEAD-6, counted as the owner: an EXISTS under the caller's policies would
    # say no to an officer whose colleague raised the accepted quotation.
    """CREATE FUNCTION quotation_accepted_for_lead(p_lead_id uuid) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT lead_visible(p_lead_id) THEN
        RETURN false;
    END IF;
    RETURN EXISTS (SELECT 1 FROM quotation
                    WHERE lead_id = p_lead_id AND status = 'accepted' AND deleted_at IS NULL);
END $fn$""",
    """CREATE FUNCTION quotation_open_draft(p_quote_no citext) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('quotations', 'create') THEN
        RAISE EXCEPTION 'not permitted to create quotations' USING ERRCODE = '42501';
    END IF;
    RETURN (SELECT id FROM quotation
             WHERE quote_no = p_quote_no AND status = 'draft' AND deleted_at IS NULL
             LIMIT 1);
END $fn$""",
    # The next version of a number, counted as the owner over every row of it,
    # soft-deleted drafts included: those are invisible to a caller without
    # quotations.delete, and UNIQUE (quote_no, version) counts them all the same
    # (plan review round 2 B-6; code review F-1).
    """CREATE FUNCTION quotation_next_version(p_quotation_id uuid) RETURNS integer
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_has_permission('quotations', 'create') THEN
        RAISE EXCEPTION 'not permitted to create quotations' USING ERRCODE = '42501';
    END IF;
    IF NOT quotation_visible(p_quotation_id) THEN
        RAISE EXCEPTION 'quotation not found' USING ERRCODE = 'P0002';
    END IF;
    RETURN (SELECT COALESCE(max(version), 0) + 1 FROM quotation
             WHERE quote_no = (SELECT quote_no FROM quotation WHERE id = p_quotation_id));
END $fn$""",
    # The first call of every quotation mutation, create included: the lead's row
    # lock, so the order is lead, then quotation rows, then the counter, and a
    # refusal of a lead that is not open. Requires leads.edit, which every role
    # holding quotations.create or quotations.edit also holds (RBAC 6.1).
    """CREATE FUNCTION lead_lock_for_quotation(p_lead_id uuid, p_require_open boolean) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_stage text; v_deleted timestamptz;
BEGIN
    IF NOT app_has_permission('leads', 'edit') THEN
        RAISE EXCEPTION 'not permitted to edit leads' USING ERRCODE = '42501';
    END IF;
    IF NOT lead_visible(p_lead_id) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'LEADN';
    END IF;
    SELECT stage::text, deleted_at INTO v_stage, v_deleted FROM lead WHERE id = p_lead_id FOR UPDATE;
    -- p_require_open is false for editing or deleting a draft: those need the
    -- lock for ordering only, and a draft on a lead that was later lost or merged
    -- must stay editable and deletable rather than stranded (round 4 B-3).
    IF p_require_open THEN
        IF v_deleted IS NOT NULL THEN
            RAISE EXCEPTION 'lead is deleted' USING ERRCODE = 'QLNOP';
        END IF;
        IF v_stage IN ('lost', 'dormant', 'merged') THEN
            RAISE EXCEPTION 'lead is %', v_stage USING ERRCODE = 'QLNOP';
        END IF;
    END IF;
    RETURN v_stage;
END $fn$""",
    # The only path by which this module moves a lead. Bound to a quotation in
    # the state that justifies the move, and gated on quotations.edit as well as
    # the lead: marketing and every portal role hold leads.edit without it, and a
    # direct call could otherwise win a lead with nothing behind it (cross-vendor
    # B-2). Writes the lead's own event, as lead_merge() does.
    """CREATE FUNCTION lead_stage_from_quotation(p_quotation_id uuid, p_to text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    v_lead uuid; v_status text; v_stage text; v_new text; v_actor text; v_needed text;
BEGIN
    IF NOT app_has_permission('quotations', 'edit') THEN
        RAISE EXCEPTION 'not permitted to edit quotations' USING ERRCODE = '42501';
    END IF;
    IF NOT quotation_visible(p_quotation_id) THEN
        RAISE EXCEPTION 'quotation not found' USING ERRCODE = '42501';
    END IF;
    SELECT lead_id, status::text INTO v_lead, v_status FROM quotation WHERE id = p_quotation_id;
    v_needed := CASE p_to WHEN 'quoted' THEN 'sent' WHEN 'negotiation' THEN 'negotiation'
                          WHEN 'won' THEN 'accepted' END;
    IF v_needed IS NULL OR v_status IS DISTINCT FROM v_needed THEN
        RAISE EXCEPTION 'a % quotation does not move a lead to %', v_status, p_to
            USING ERRCODE = 'QLBND';
    END IF;
    IF NOT lead_visible(v_lead) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'LEADN';
    END IF;
    SELECT stage::text INTO v_stage FROM lead WHERE id = v_lead AND deleted_at IS NULL FOR UPDATE;
    IF v_stage IS NULL OR v_stage IN ('new', 'contacted', 'lost', 'dormant', 'merged') THEN
        RAISE EXCEPTION 'lead is %', COALESCE(v_stage, 'deleted') USING ERRCODE = 'QLNOP';
    END IF;
    v_new := CASE
        WHEN p_to = 'quoted' AND v_stage = 'qualified' THEN 'quoted'
        WHEN p_to = 'negotiation' AND v_stage = 'quoted' THEN 'negotiation'
        WHEN p_to = 'won' AND v_stage IN ('quoted', 'negotiation') THEN 'won'
        ELSE NULL END;
    IF v_new IS NULL THEN
        -- already there, or past it: a second unit on a quoted or won lead
        IF (p_to = 'quoted' AND v_stage IN ('quoted', 'negotiation', 'won'))
           OR (p_to = 'negotiation' AND v_stage IN ('negotiation', 'won'))
           OR (p_to = 'won' AND v_stage = 'won') THEN
            RETURN v_stage;
        END IF;
        RAISE EXCEPTION 'lead is %', v_stage USING ERRCODE = 'QLNOP';
    END IF;
    UPDATE lead SET stage = v_new::lead_stage, last_activity_at = now() WHERE id = v_lead;
    SELECT full_name INTO v_actor FROM app_user WHERE id = app_current_user_id();
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('lead', v_lead, v_lead, 'lead.stage_changed', app_current_user_id(),
            jsonb_build_object('from', v_stage, 'to', v_new, 'via', 'quotation',
                               'quotation_id', p_quotation_id, 'actor_name', v_actor));
    RETURN v_stage;
END $fn$""",
    # The public surface, as app_anon. The token is the whole authorisation; the
    # seller block is the snapshot, never the master.
    f"""CREATE FUNCTION quotation_public_view(p_token text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT {_PUBLIC_ROW}
      FROM quotation q
     WHERE q.share_token = p_token AND q.status <> 'draft' AND q.deleted_at IS NULL
$fn$""",
    # The view is recorded here, on the PDF request, once. Later opens count. The
    # event's actor is the system principal; the INSERT succeeds because the
    # function's owner is the table's owner and activity_event is ENABLEd, not
    # FORCEd (RBAC 5.2a). lead_id is set: the regenerated CHECK requires it.
    f"""CREATE FUNCTION quotation_public_open(p_token text, p_user_agent text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE q quotation%ROWTYPE; v_first boolean;
BEGIN
    SELECT * INTO q FROM quotation
     WHERE share_token = p_token AND status <> 'draft' AND deleted_at IS NULL
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    v_first := q.viewed_at IS NULL;
    UPDATE quotation
       SET viewed_at = COALESCE(viewed_at, now()),
           status = CASE WHEN status = 'sent' THEN 'viewed'::quotation_status ELSE status END,
           open_count = open_count + 1
     WHERE id = q.id;
    IF v_first THEN
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('quotation', q.id, q.lead_id, 'quotation.viewed', '{SYSTEM_USER_ID}',
                jsonb_build_object('from', q.status, 'to',
                                   CASE WHEN q.status = 'sent' THEN 'viewed' ELSE q.status::text END,
                                   'user_agent', left(COALESCE(p_user_agent, ''), 200),
                                   'actor_name', 'the customer'));
    END IF;
    SELECT * INTO q FROM quotation WHERE id = q.id;
    RETURN {_PUBLIC_ROW};
END $fn$""",
    # The render lease, its own transaction, committed before rendering: a charge
    # inside the transaction that also renders is rolled back with it when the
    # process dies, and the row is re-claimed every five seconds forever
    # (cross-vendor B-5). Exactly one charge per attempt, here and nowhere else.
    f"""CREATE FUNCTION quotation_render_claim(p_lease interval) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE q quotation%ROWTYPE; v_token uuid;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO q FROM quotation
     WHERE deleted_at IS NULL
       AND ((pdf_state = 'pending' AND pdf_next_attempt_at <= now())
            OR (pdf_state = 'rendering' AND pdf_lease_until < now()))
     ORDER BY pdf_next_attempt_at
     LIMIT 1
       FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    IF q.pdf_attempts >= {MAX_RENDER_ATTEMPTS} THEN
        UPDATE quotation SET pdf_state = 'failed', pdf_lease_until = NULL, pdf_lease_token = NULL,
               pdf_error = 'render abandoned after 5 attempts: ' || COALESCE(pdf_error, 'the worker died on the last one')
         WHERE id = q.id;
        RETURN NULL;
    END IF;
    v_token := gen_random_uuid();
    UPDATE quotation
       SET pdf_state = 'rendering', pdf_lease_until = now() + p_lease, pdf_lease_token = v_token,
           pdf_attempts = pdf_attempts + 1
     WHERE id = q.id;
    RETURN jsonb_build_object(
        'lease_token', v_token, 'attempt', q.pdf_attempts + 1,
        'quotation', to_jsonb(q) - ARRAY['pdf_lease_token'],
        'lines', (SELECT COALESCE(jsonb_agg(to_jsonb(l) ORDER BY l.line_no), '[]'::jsonb)
                    FROM quotation_line l WHERE l.quotation_id = q.id));
END $fn$""",
    # Conditional on the lease: a stale worker finishing after its lease was
    # reclaimed writes nothing. The message is queued only now, so a farmer never
    # opens a link whose PDF is not there; the worker passes the whole link.
    """CREATE FUNCTION quotation_render_done(p_id uuid, p_lease_token uuid, p_key text, p_link text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE q quotation%ROWTYPE;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    UPDATE quotation
       SET pdf_state = 'ready', pdf_key = p_key, pdf_lease_until = NULL, pdf_lease_token = NULL,
           pdf_error = NULL
     WHERE id = p_id AND pdf_state = 'rendering' AND pdf_lease_token = p_lease_token
     RETURNING * INTO q;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF q.notify_channel = 'whatsapp' THEN
        INSERT INTO notification_outbox (channel, template_key, recipient, payload)
        VALUES ('whatsapp', 'quotation_share', q.party_mobile,
                jsonb_build_object('party_name', q.party_name, 'quote_no', q.quote_no,
                                   'link', p_link));
    END IF;
    RETURN true;
END $fn$""",
    # Does not charge: the claim did. Backs off, or gives up at the fifth attempt.
    f"""CREATE FUNCTION quotation_render_failed(p_id uuid, p_lease_token uuid, p_error text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_attempts int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal renders' USING ERRCODE = '42501';
    END IF;
    SELECT pdf_attempts INTO v_attempts FROM quotation
     WHERE id = p_id AND pdf_state = 'rendering' AND pdf_lease_token = p_lease_token
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    UPDATE quotation
       SET pdf_error = left(p_error, 2000), pdf_lease_until = NULL, pdf_lease_token = NULL,
           pdf_state = CASE WHEN v_attempts >= {MAX_RENDER_ATTEMPTS} THEN 'failed' ELSE 'pending' END,
           pdf_next_attempt_at = now() + CASE v_attempts
               WHEN 1 THEN interval '30 seconds' WHEN 2 THEN interval '2 minutes'
               WHEN 3 THEN interval '10 minutes' ELSE interval '1 hour' END
     WHERE id = p_id;
    RETURN true;
END $fn$""",
    # Nightly, with the IST date passed in: current_date is UTC on this box. A
    # superseded row is closed history and keeps the status it had.
    """CREATE FUNCTION quotation_expire_due(p_today date) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE r record; v_count int := 0;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal expires quotations' USING ERRCODE = '42501';
    END IF;
    FOR r IN SELECT id, lead_id, status::text AS status FROM quotation
              WHERE status IN ('sent', 'viewed', 'negotiation') AND valid_until < p_today
                AND superseded_by_id IS NULL AND deleted_at IS NULL
                FOR UPDATE SKIP LOCKED
    LOOP
        UPDATE quotation SET status = 'expired' WHERE id = r.id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('quotation', r.id, r.lead_id, 'quotation.expired', app_current_user_id(),
                jsonb_build_object('from', r.status, 'to', 'expired', 'actor_name', 'System'));
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END $fn$""",
]

# The two 006 functions this migration replaces. Their new bodies are the 006
# bodies with one addition each; the originals are restored on downgrade from the
# 006 module itself, so nothing is duplicated here.
_MERGE_RESCOPE = """    -- FS-005 rule 12: every loser in the group takes the survivor's scope, and
    -- the propagation trigger carries it to their quotations at depth 2 (a direct
    -- UPDATE of quotation from here would run at depth 1 and be refused).
    UPDATE lead l
       SET owner_user_id = s.owner_user_id, owner_org_unit_id = s.owner_org_unit_id,
           territory_id = s.territory_id
      FROM lead s
     WHERE s.id = p_survivor AND l.merged_into_id = p_survivor
       AND (l.owner_user_id IS DISTINCT FROM s.owner_user_id
            OR l.owner_org_unit_id IS DISTINCT FROM s.owner_org_unit_id
            OR l.territory_id IS DISTINCT FROM s.territory_id);
END $fn$"""

_TIMELINE_FILTER = """         WHERE (lead_id = p_lead_id
                OR lead_id IN (SELECT id FROM lead WHERE merged_into_id = p_lead_id))
           AND (entity_type <> 'quotation' OR quotation_visible(entity_id))"""


def _006() -> list[str]:
    path = Path(__file__).with_name("006_leads.py")
    spec = importlib.util.spec_from_file_location("mig_006_for_012", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.FUNCTIONS)


def _replaced_006() -> tuple[str, str]:
    """The 006 bodies of lead_merge() and lead_timeline() with this migration's
    additions, as CREATE OR REPLACE."""
    merge = next(f for f in _006() if f.startswith("CREATE FUNCTION lead_merge("))
    timeline = next(f for f in _006() if f.startswith("CREATE FUNCTION lead_timeline("))
    assert merge.rstrip().endswith("END $fn$"), "006's lead_merge() ends where expected"
    merge = merge.rstrip()[: -len("END $fn$")] + _MERGE_RESCOPE
    old_where = ("         WHERE (lead_id = p_lead_id\n"
                 "                OR lead_id IN (SELECT id FROM lead WHERE merged_into_id = p_lead_id))")
    assert old_where in timeline, "006's lead_timeline() reads as expected"
    timeline = timeline.replace(old_where, _TIMELINE_FILTER)
    return (merge.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1),
            timeline.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))


def _restored_006() -> tuple[str, str]:
    merge = next(f for f in _006() if f.startswith("CREATE FUNCTION lead_merge("))
    timeline = next(f for f in _006() if f.startswith("CREATE FUNCTION lead_timeline("))
    return (merge.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1),
            timeline.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))


def _007_activity_policy() -> str:
    path = Path(__file__).with_name("007_administration.py")
    spec = importlib.util.spec_from_file_location("mig_007_for_012", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return next(s for t, s in mod.HAND_POLICIES if t == "activity_event")


FUNCTION_SIGS = [
    "quotation_allocate_no(text, text)", "quotation_visible(uuid)",
    "quotation_accepted_for_lead(uuid)", "quotation_open_draft(citext)",
    "quotation_next_version(uuid)",
    "lead_lock_for_quotation(uuid, boolean)", "lead_stage_from_quotation(uuid, text)",
    "quotation_render_claim(interval)", "quotation_render_done(uuid, uuid, text, text)",
    "quotation_render_failed(uuid, uuid, text)", "quotation_expire_due(date)",
]
ANON_SIGS = ["quotation_public_view(text)", "quotation_public_open(text, text)"]
ALL_NEW_FUNCTIONS = FUNCTION_SIGS + ANON_SIGS + [
    "refuse_sent_quotation_edit()", "refuse_sent_quotation_line_edit()",
    "lead_scope_to_quotations()", "quotation_parent_guard()",
]


def _hand(table: str) -> None:
    for t, stmt in HAND_POLICIES:
        if t == table:
            op.execute(stmt)


def upgrade() -> None:
    for stmt in ENUMS + TABLES_SQL + GENERATED_INDEXES + HAND_INDEXES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")

    for stmt in QUOTATION_POLICIES + PARENT_GUARD:
        op.execute(stmt)
    op.execute("ALTER TABLE quotation_line ENABLE ROW LEVEL SECURITY")
    _hand("quotation_line")
    # quotation_counter carries no grant and no policy: RLS on so it is fail-closed
    # like every other table, and the definer allocator writes it as the owner.
    op.execute("ALTER TABLE quotation_counter ENABLE ROW LEVEL SECURITY")

    for stmt in TRIGGER_FUNCTIONS + TRIGGERS:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in FUNCTION_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    # 003b's guarded block: the local compose profile migrates without the role.
    grants = "\n".join(f"                GRANT EXECUTE ON FUNCTION {sig} TO {ANON_ROLE};"
                       for sig in ANON_SIGS)
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ANON_ROLE}') THEN
{grants}
            ELSE
                RAISE NOTICE 'role {ANON_ROLE} does not exist; public quotation grants skipped';
            END IF;
        END $$
    """)

    merge, timeline = _replaced_006()
    op.execute(merge)
    op.execute(timeline)

    # activity_event: the quotation arm and the quotation reference.
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    _hand("activity_event")
    op.execute("ALTER TABLE activity_event DROP CONSTRAINT ck_activity_event_reference")
    op.execute(f"ALTER TABLE activity_event ADD CONSTRAINT ck_activity_event_reference "
               f"CHECK ({ACTIVITY_CHECK}) NOT VALID")
    op.execute("ALTER TABLE activity_event VALIDATE CONSTRAINT ck_activity_event_reference")

    # New functions are PUBLIC-executable until this runs; a migration's sweep does
    # not reach a later migration's, so 012 runs its own (006, cross-vendor B-6).
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(_007_activity_policy())
    op.execute("ALTER TABLE activity_event DROP CONSTRAINT ck_activity_event_reference")
    op.execute(f"ALTER TABLE activity_event ADD CONSTRAINT ck_activity_event_reference "
               f"CHECK ({ACTIVITY_CHECK_BEFORE}) NOT VALID")
    op.execute("ALTER TABLE activity_event VALIDATE CONSTRAINT ck_activity_event_reference")
    merge, timeline = _restored_006()
    op.execute(timeline)
    op.execute(merge)
    op.execute("DROP TRIGGER IF EXISTS trg_lead_scope_to_quotations ON lead")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for sig in ALL_NEW_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for name in ("quotation_status", "quotation_sales_type", "quotation_source"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
