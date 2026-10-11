"""062: dealer recruitment (FS-051, client sheet item 8; closes GAP-135).

- `dealer_application`: staff start one; the applicant fills it through a token link
  after a WhatsApp code; a State Manager or above decides. Approval creates the
  dealer and its login inside `dealer_application_decide()`, because a State
  Manager may not create users (plan review B-2).
- The applicant's code and session live on the row, so the database checks every
  applicant read and write against them, and renewing the link clears both.
- FS-050's documents gain the `dealer_application` record type: the refusal, the
  lock and the event each get an arm (plan review B-1); applicant uploads carry no
  `uploaded_by`.

Revision ID: 062_dealer_recruitment
Revises: 063_land_hectares
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "062_dealer_recruitment"
down_revision: str | None = "063_land_hectares"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
ANON_ROLE = "app_anon"


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_062", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"062: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"062: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


_floor_spec = importlib.util.spec_from_file_location(
    "consumer_floor_062", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _floor_spec is not None and _floor_spec.loader is not None
floor = importlib.util.module_from_spec(_floor_spec)
_floor_spec.loader.exec_module(floor)

M061 = _load("061_record_documents")
M050 = _load("050_customer_record")

GSTIN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
PAN = r"^[A-Z]{5}[0-9]{4}[A-Z]$"

TABLES = [
    f"""CREATE TABLE dealer_application (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'draft',
    firm_name text NOT NULL,
    contact_name text NOT NULL,
    mobile text NOT NULL,
    territory_id uuid NOT NULL REFERENCES territory(id),
    lead_id uuid REFERENCES lead(id),
    firm_type text,
    gst_registered boolean NOT NULL DEFAULT true,
    gstin text,
    pan text,
    address text,
    pincode text,
    email text,
    godown_address text,
    years_in_business int,
    current_brands text,
    notes text,
    bank_account_name text,
    bank_account_no text,
    bank_ifsc text,
    gst_lookup jsonb,
    gst_state_mismatch boolean NOT NULL DEFAULT false,
    token_hash text NOT NULL UNIQUE,
    link_expires_at timestamptz NOT NULL,
    session_hash text,
    session_expires_at timestamptz,
    code_hash text,
    code_expires_at timestamptz,
    code_attempts int NOT NULL DEFAULT 0,
    codes_sent int NOT NULL DEFAULT 0,
    codes_window_start timestamptz,
    last_code_at timestamptz,
    partner_id uuid REFERENCES channel_partner(id),
    user_id uuid REFERENCES app_user(id),
    decided_by uuid REFERENCES app_user(id),
    decided_at timestamptz,
    decision_remark text,
    submitted_at timestamptz,
    created_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_dealer_application_status CHECK (status IN ('draft', 'submitted', 'returned', 'approved', 'rejected', 'withdrawn')),
    CONSTRAINT ck_dealer_application_firm CHECK (length(btrim(firm_name)) BETWEEN 1 AND 200),
    CONSTRAINT ck_dealer_application_contact CHECK (length(btrim(contact_name)) BETWEEN 1 AND 200),
    CONSTRAINT ck_dealer_application_mobile CHECK (mobile ~ '^91[6-9][0-9]{{9}}$'),
    CONSTRAINT ck_dealer_application_firm_type CHECK (firm_type IS NULL OR firm_type IN ('proprietorship', 'partnership', 'llp', 'company')),
    CONSTRAINT ck_dealer_application_gstin CHECK (gstin IS NULL OR gstin ~ '{GSTIN}'),
    CONSTRAINT ck_dealer_application_pan CHECK (pan IS NULL OR pan ~ '{PAN}'),
    CONSTRAINT ck_dealer_application_address CHECK (address IS NULL OR length(btrim(address)) BETWEEN 1 AND 1000),
    CONSTRAINT ck_dealer_application_pincode CHECK (pincode IS NULL OR pincode ~ '^[1-9][0-9]{{5}}$'),
    CONSTRAINT ck_dealer_application_email CHECK (email IS NULL OR length(email) <= 254),
    CONSTRAINT ck_dealer_application_texts CHECK ((godown_address IS NULL OR length(godown_address) <= 1000)
        AND (current_brands IS NULL OR length(current_brands) <= 500) AND (notes IS NULL OR length(notes) <= 2000)
        AND (decision_remark IS NULL OR length(decision_remark) <= 1000)),
    CONSTRAINT ck_dealer_application_years CHECK (years_in_business IS NULL OR years_in_business BETWEEN 0 AND 150),
    CONSTRAINT ck_dealer_application_bank CHECK ((bank_account_name IS NULL OR length(btrim(bank_account_name)) BETWEEN 1 AND 200)
        AND (bank_account_no IS NULL OR bank_account_no ~ '^[0-9]{{6,20}}$')
        AND (bank_ifsc IS NULL OR bank_ifsc ~ '^[A-Z]{{4}}0[A-Z0-9]{{6}}$'))
)""",
    "CREATE INDEX ix_dealer_application_territory ON dealer_application (territory_id)",
    "CREATE INDEX ix_dealer_application_status ON dealer_application (status, created_at DESC)",
    "CREATE INDEX ix_dealer_application_mobile ON dealer_application (mobile)",
    "CREATE INDEX ix_dealer_application_lead ON dealer_application (lead_id)",
    "CREATE INDEX ix_dealer_application_created_by ON dealer_application (created_by)",
    "CREATE INDEX ix_dealer_application_decided_by ON dealer_application (decided_by)",
    "CREATE INDEX ix_dealer_application_partner ON dealer_application (partner_id)",
    "CREATE INDEX ix_dealer_application_user ON dealer_application (user_id)",
    "CREATE TRIGGER trg_dealer_application_updated_at BEFORE UPDATE ON dealer_application FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    # FS-050's record types and document types, widened
    "ALTER TABLE record_document DROP CONSTRAINT ck_record_document_record_type",
    "ALTER TABLE record_document ADD CONSTRAINT ck_record_document_record_type CHECK (record_type IN ('lead', 'quotation', 'sales_order', 'dispatch', 'payment', 'dealer_application'))",
    "ALTER TABLE record_document DROP CONSTRAINT ck_record_document_doc_type",
    "ALTER TABLE record_document ADD CONSTRAINT ck_record_document_doc_type CHECK (doc_type IN ('purchase_order', 'payment_proof', 'signed_quotation', 'invoice', 'delivery_challan', 'transport_receipt', 'site_photo', 'land_record', 'subsidy_document', 'other', 'gst_certificate', 'pan_card', 'cancelled_cheque', 'shop_photo', 'shop_licence'))",
]

GRANTS: dict[str, str] = {"dealer_application": "SELECT"}

# staff only, the partners scope over the territory (028's guard, its staff arms)
_VISIBLE = """((SELECT app_current_partner()) IS NULL AND (SELECT app_has_permission('partners', 'view'))
  AND ((SELECT app_scope('partners')) = 'global'
    OR ((SELECT app_scope('partners')) = 'org_subtree'
      AND (territory_id IN (SELECT tc.descendant_id FROM territory_closure tc WHERE tc.ancestor_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))
        OR territory_id IN (SELECT tc.ancestor_id FROM territory_closure tc WHERE tc.descendant_id IN (SELECT ou.territory_id FROM org_unit ou WHERE ou.id IN (SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))))))
    OR ((SELECT app_scope('partners')) = 'territory'
      AND territory_id IN (SELECT tc.descendant_id FROM territory_closure tc JOIN user_territory ut ON ut.territory_id = tc.ancestor_id WHERE ut.user_id = (SELECT app_current_user_id())))))"""

# activity_event_sel with the dealer_application arm (api/authz/activity.py policy_sql())
ACTIVITY_SEL = _replace(
    next(st for t, st in M050.HAND_POLICIES if t == "activity_event"),
    "    WHEN 'campaign' THEN EXISTS (SELECT 1 FROM campaign c WHERE c.id = entity_id)\n",
    "    WHEN 'campaign' THEN EXISTS (SELECT 1 FROM campaign c WHERE c.id = entity_id)\n"
    "    WHEN 'dealer_application' THEN EXISTS (SELECT 1 FROM dealer_application c WHERE c.id = entity_id)\n")

DOC_SELECT_POLICY = _replace(
    M061.SELECT_POLICY,
    "    WHEN 'payment' THEN EXISTS (SELECT 1 FROM payment p WHERE p.id = record_id)\n",
    "    WHEN 'payment' THEN EXISTS (SELECT 1 FROM payment p WHERE p.id = record_id)\n"
    "    WHEN 'dealer_application' THEN EXISTS (SELECT 1 FROM dealer_application a WHERE a.id = record_id)\n")

HAND_POLICIES: list[tuple[str, str]] = [
    ("dealer_application", f"CREATE POLICY dealer_application_sel ON dealer_application FOR SELECT USING ({_VISIBLE})"),
    ("activity_event", ACTIVITY_SEL),
    ("record_document", DOC_SELECT_POLICY),
]


def _061(name: str) -> str:
    return next(f for f in M061.FUNCTIONS if f.startswith(f"CREATE FUNCTION {name}(") or
                f.startswith(f"CREATE FUNCTION {name} ("))


def _or_replace(text: str) -> str:
    return text.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)


REFUSAL_061 = _061("record_document_refusal")
EVENT_061 = _061("record_document_event")
ADD_061 = _061("record_document_add")

REFUSAL_062 = _or_replace(_replace(REFUSAL_061, """    END IF;
    RETURN 'DOCNF';
END $fn$""", """    ELSIF p_type = 'dealer_application' THEN
        -- FS-051: staff who see the application add while it is open
        IF NOT dealer_application_visible(p_id) THEN RETURN 'DOCNF'; END IF;
        IF NOT EXISTS (SELECT 1 FROM dealer_application WHERE id = p_id
                         AND status IN ('draft', 'returned', 'submitted')) THEN
            RETURN 'DOCCL';
        END IF;
        RETURN NULL;
    END IF;
    RETURN 'DOCNF';
END $fn$"""))

EVENT_062 = _or_replace(_replace(EVENT_061, """    ELSIF d.record_type = 'dispatch' THEN""", """    ELSIF d.record_type = 'dealer_application' THEN
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        SELECT 'dealer_application', a.id, a.lead_id, p_kind, app_current_user_id(),
               v_payload || CASE WHEN app_current_user_id() IS NULL THEN '{"by": "applicant"}'::jsonb ELSE '{}'::jsonb END
          FROM dealer_application a WHERE a.id = d.record_id;
    ELSIF d.record_type = 'dispatch' THEN"""))

ADD_062 = _or_replace(_replace(ADD_061, """    ELSE PERFORM 1 FROM payment WHERE payment.id = p_id FOR UPDATE;
    END IF;""", """    ELSIF p_type = 'dealer_application' THEN PERFORM 1 FROM dealer_application WHERE dealer_application.id = p_id FOR UPDATE;
    ELSE PERFORM 1 FROM payment WHERE payment.id = p_id FOR UPDATE;
    END IF;"""))

# the applicant's fields, written from a jsonb by staff and applicant alike
_FIELDS = ["firm_name", "contact_name", "firm_type", "gstin", "pan", "address", "pincode", "email",
           "godown_address", "current_brands", "notes", "bank_account_name", "bank_account_no", "bank_ifsc"]
_SETS = ",\n           ".join(
    f"{f} = CASE WHEN p_fields ? '{f}' THEN NULLIF(btrim(p_fields ->> '{f}'), '') ELSE {f} END" for f in _FIELDS)

_EVENT = """INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    SELECT 'dealer_application', a.id, a.lead_id, {kind}, app_current_user_id(), {payload}
      FROM dealer_application a WHERE a.id = {id}"""

FUNCTIONS = [
    f"""CREATE FUNCTION dealer_application_visible(p_id uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT EXISTS (SELECT 1 FROM dealer_application WHERE dealer_application.id = p_id AND {_VISIBLE})
$fn$""",
    # Which required fields and documents are missing to submit (rule 2, rule 11)
    """CREATE FUNCTION dealer_application_missing(p_id uuid) RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(array_agg(x ORDER BY x), '{}') FROM (
        SELECT unnest(ARRAY[
            CASE WHEN a.firm_type IS NULL THEN 'firm_type' END,
            CASE WHEN a.gst_registered AND a.gstin IS NULL THEN 'gstin' END,
            CASE WHEN a.pan IS NULL THEN 'pan' END,
            CASE WHEN a.address IS NULL THEN 'address' END,
            CASE WHEN a.pincode IS NULL THEN 'pincode' END,
            CASE WHEN a.bank_account_name IS NULL THEN 'bank_account_name' END,
            CASE WHEN a.bank_account_no IS NULL THEN 'bank_account_no' END,
            CASE WHEN a.bank_ifsc IS NULL THEN 'bank_ifsc' END,
            CASE WHEN a.gst_registered AND NOT EXISTS (SELECT 1 FROM record_document r WHERE r.record_type = 'dealer_application'
                 AND r.record_id = a.id AND r.doc_type = 'gst_certificate' AND r.deleted_at IS NULL) THEN 'gst_certificate' END,
            CASE WHEN NOT EXISTS (SELECT 1 FROM record_document r WHERE r.record_type = 'dealer_application'
                 AND r.record_id = a.id AND r.doc_type = 'pan_card' AND r.deleted_at IS NULL) THEN 'pan_card' END,
            CASE WHEN NOT EXISTS (SELECT 1 FROM record_document r WHERE r.record_type = 'dealer_application'
                 AND r.record_id = a.id AND r.doc_type = 'cancelled_cheque' AND r.deleted_at IS NULL) THEN 'cancelled_cheque' END
        ]) AS x FROM dealer_application a WHERE a.id = p_id) s WHERE x IS NOT NULL
$fn$""",
    # Internal: the fields write, for staff and applicant (field names only in the event)
    f"""CREATE FUNCTION dealer_application_write(p_id uuid, p_fields jsonb, p_by text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_pan text; v_gstin text;
BEGIN
    UPDATE dealer_application SET
           {_SETS},
           gst_registered = CASE WHEN p_fields ? 'gst_registered' THEN (p_fields ->> 'gst_registered')::boolean ELSE gst_registered END,
           years_in_business = CASE WHEN p_fields ? 'years_in_business' THEN (p_fields ->> 'years_in_business')::int ELSE years_in_business END,
           gst_lookup = CASE WHEN p_fields ? 'gst_lookup' THEN p_fields -> 'gst_lookup' ELSE gst_lookup END,
           gst_state_mismatch = CASE WHEN p_fields ? 'gst_state_mismatch' THEN (p_fields ->> 'gst_state_mismatch')::boolean ELSE gst_state_mismatch END
     WHERE id = p_id
    RETURNING pan, gstin INTO v_pan, v_gstin;
    -- the PAN inside the GSTIN must be the PAN given (edge E-8)
    IF v_gstin IS NOT NULL AND v_pan IS NOT NULL AND substr(v_gstin, 3, 10) <> v_pan THEN
        RAISE EXCEPTION 'the PAN is not the one in the GSTIN' USING ERRCODE = 'DAPPN';
    END IF;
    {_EVENT.format(kind="'dealer_application.updated'", payload="jsonb_build_object('fields', (SELECT jsonb_agg(k) FROM jsonb_object_keys(p_fields) k WHERE k NOT IN ('gst_lookup', 'gst_state_mismatch')), 'by', p_by)", id="p_id")};
END $fn$""",
    # Staff create. Refuses a mobile that signs in staff or a partner user, or one with an open application
    f"""CREATE FUNCTION dealer_application_create(p_firm text, p_contact text, p_mobile text, p_territory uuid,
        p_lead uuid, p_token_hash text, p_expires timestamptz) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_id uuid;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT app_has_permission('partners', 'view') THEN
        RAISE EXCEPTION 'staff with partners view' USING ERRCODE = '42501';
    END IF;
    IF p_lead IS NOT NULL AND NOT lead_visible(p_lead) THEN
        RAISE EXCEPTION 'not a lead you can see' USING ERRCODE = 'DAPLD';
    END IF;
    IF EXISTS (SELECT 1 FROM app_user u WHERE u.mobile = p_mobile AND u.deleted_at IS NULL
                 AND u.user_type IN ('staff', 'partner_user')) THEN
        RAISE EXCEPTION 'mobile in use' USING ERRCODE = 'DAPMU';
    END IF;
    PERFORM pg_advisory_xact_lock(8, hashtext(p_mobile));
    IF EXISTS (SELECT 1 FROM dealer_application a WHERE a.mobile = p_mobile
                 AND a.status IN ('draft', 'submitted', 'returned')) THEN
        RAISE EXCEPTION 'an open application has this mobile' USING ERRCODE = 'DAPOP';
    END IF;
    INSERT INTO dealer_application (firm_name, contact_name, mobile, territory_id, lead_id, token_hash,
                                    link_expires_at, created_by)
    VALUES (btrim(p_firm), btrim(p_contact), p_mobile, p_territory, p_lead, p_token_hash, p_expires, v_me)
    RETURNING id INTO v_id;
    IF NOT dealer_application_visible(v_id) THEN
        RAISE EXCEPTION 'territory outside your scope' USING ERRCODE = 'DAPTR';
    END IF;
    {_EVENT.format(kind="'dealer_application.created'", payload="jsonb_build_object('firm_name', a.firm_name)", id="v_id")};
    RETURN v_id;
END $fn$""",
    # Staff edit, submit, withdraw, renew: visibility, then the status
    """CREATE FUNCTION dealer_application_staff(p_id uuid, p_action text, p_fields jsonb, p_remark text,
        p_token_hash text, p_expires timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE; v_missing text[];
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT dealer_application_visible(p_id) THEN
        RAISE EXCEPTION 'no such application' USING ERRCODE = 'DAPNF';
    END IF;
    SELECT * INTO a FROM dealer_application WHERE id = p_id FOR UPDATE;
    IF p_action = 'patch' THEN
        IF a.status NOT IN ('draft', 'returned', 'submitted') THEN
            RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
        END IF;
        PERFORM dealer_application_write(p_id, p_fields, 'staff');
    ELSIF p_action = 'submit' THEN
        IF a.status = 'submitted' THEN RETURN; END IF;
        IF a.status NOT IN ('draft', 'returned') THEN
            RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
        END IF;
        v_missing := dealer_application_missing(p_id);
        IF cardinality(v_missing) > 0 THEN
            RAISE EXCEPTION 'missing: %', array_to_string(v_missing, ', ') USING ERRCODE = 'DAPMS';
        END IF;
        UPDATE dealer_application SET status = 'submitted', submitted_at = now(), session_hash = NULL WHERE id = p_id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('dealer_application', p_id, a.lead_id, 'dealer_application.submitted', app_current_user_id(), '{"by": "staff"}');
    ELSIF p_action = 'withdraw' THEN
        IF a.status NOT IN ('draft', 'returned', 'submitted') THEN
            RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
        END IF;
        UPDATE dealer_application SET status = 'withdrawn', decision_remark = btrim(p_remark), session_hash = NULL
         WHERE id = p_id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('dealer_application', p_id, a.lead_id, 'dealer_application.withdrawn', app_current_user_id(), '{}');
    ELSIF p_action = 'renew' THEN
        IF a.status NOT IN ('draft', 'returned') THEN
            RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
        END IF;
        -- a new token: the old link and any open session stop working
        UPDATE dealer_application SET token_hash = p_token_hash, link_expires_at = p_expires,
               session_hash = NULL, session_expires_at = NULL, code_hash = NULL, last_code_at = NULL WHERE id = p_id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('dealer_application', p_id, a.lead_id, 'dealer_application.link_renewed', app_current_user_id(), '{}');
    END IF;
END $fn$""",
    # The decision. Approval creates the dealer and its login here (plan review B-2, R-4)
    """CREATE FUNCTION dealer_application_decide(p_id uuid, p_decision text, p_remark text, p_parent uuid,
        p_code text) RETURNS TABLE (partner_id uuid, user_id uuid)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE; v_me uuid := app_current_user_id(); v_level int; v_line boolean;
        v_partner uuid; v_user uuid; v_role uuid; v_code text; v_state text; v_n int; v_consumer uuid; v_fam uuid;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT dealer_application_visible(p_id) THEN
        RAISE EXCEPTION 'no such application' USING ERRCODE = 'DAPNF';
    END IF;
    SELECT * INTO a FROM dealer_application WHERE id = p_id FOR UPDATE;
    IF a.status <> 'submitted' THEN
        RAISE EXCEPTION 'already decided' USING ERRCODE = 'DAPDC';
    END IF;
    -- a State Manager or above (a line role at level 3 or more), or global partners.create;
    -- never whoever started it (rule 10)
    SELECT r.level, NOT r.is_functional AND NOT r.is_portal INTO v_level, v_line
      FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = v_me;
    IF v_me = a.created_by OR NOT ((v_line AND v_level >= 3)
           OR (app_has_permission('partners', 'create') AND app_scope('partners') = 'global')) THEN
        RAISE EXCEPTION 'not your decision' USING ERRCODE = 'DAPFB';
    END IF;
    IF p_decision IN ('reject', 'return') THEN
        IF p_remark IS NULL OR btrim(p_remark) = '' THEN
            RAISE EXCEPTION 'a remark' USING ERRCODE = 'DAPRM';
        END IF;
        UPDATE dealer_application SET status = CASE p_decision WHEN 'reject' THEN 'rejected' ELSE 'returned' END,
               decided_by = v_me, decided_at = now(), decision_remark = btrim(p_remark) WHERE id = p_id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('dealer_application', p_id, a.lead_id,
                CASE p_decision WHEN 'reject' THEN 'dealer_application.rejected' ELSE 'dealer_application.returned' END,
                v_me, '{}');
        RETURN;
    END IF;
    IF p_parent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = p_parent
           AND p.partner_type = 'distributor' AND p.is_active AND p.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'not an active distributor' USING ERRCODE = 'DAPPR';
    END IF;
    IF EXISTS (SELECT 1 FROM app_user u WHERE u.mobile = a.mobile AND u.deleted_at IS NULL
                 AND u.user_type IN ('staff', 'partner_user')) THEN
        RAISE EXCEPTION 'mobile in use' USING ERRCODE = 'DAPMU';
    END IF;
    -- a customer's portal account on the mobile is released, as 052's consumer_release_mobile
    -- does, inline: that function refuses a caller without users.create (plan review B-2)
    SELECT id INTO v_consumer FROM app_user
     WHERE mobile = a.mobile AND user_type = 'consumer' AND deleted_at IS NULL FOR UPDATE;
    IF v_consumer IS NOT NULL THEN
        FOR v_fam IN SELECT DISTINCT s.family_id FROM session s
                      WHERE s.user_id = v_consumer AND s.revoked_at IS NULL ORDER BY s.family_id LOOP
            PERFORM pg_advisory_xact_lock(3, hashtext(v_fam::text));
        END LOOP;
        -- qualified: user_id is also this function's output column
        WITH revoked AS (UPDATE session SET revoked_at = now()
                          WHERE session.user_id = v_consumer AND session.revoked_at IS NULL RETURNING 1)
        SELECT count(*)::int INTO v_n FROM revoked;
        INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
        VALUES ('app_user', v_consumer, 'auth.sessions_revoked', v_me, jsonb_build_object('sessions', v_n));
        UPDATE app_user SET deleted_at = now(), is_active = false, token_version = token_version + 1
         WHERE id = v_consumer;
        INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
        VALUES ('app_user', v_consumer, 'user.deleted', v_me, jsonb_build_object('reason', 'mobile_reassigned'));
    END IF;
    -- the code: DLR-<state>-0001, next over every code with the prefix (edge E-4)
    SELECT t.code::text INTO v_state FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = a.territory_id AND t.level = 'state' ORDER BY tc.depth LIMIT 1;
    v_code := NULLIF(btrim(p_code), '');
    PERFORM pg_advisory_xact_lock(9, hashtext('DLR-' || coalesce(v_state, 'GEN')));
    IF v_code IS NULL THEN
        SELECT coalesce(max(substring(code::text FROM '([0-9]+)$')::int), 0) + 1 INTO v_n
          FROM channel_partner WHERE code::text ~ ('^DLR-' || coalesce(v_state, 'GEN') || '-[0-9]+$');
        v_code := 'DLR-' || coalesce(v_state, 'GEN') || '-' || lpad(v_n::text, 4, '0');
    ELSIF EXISTS (SELECT 1 FROM channel_partner WHERE code = v_code::citext) THEN
        -- under the lock: a typed code racing another approval is refused, not a 23505
        RAISE EXCEPTION 'code in use' USING ERRCODE = 'DAPCD';
    END IF;
    INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, contact_name, mobile, email,
        address, gstin, pan, is_gst_registered, price_tier, created_by)
    VALUES (p_parent, 'dealer', v_code, a.firm_name, a.territory_id, a.contact_name, a.mobile, a.email,
        a.address, a.gstin, a.pan, a.gst_registered AND a.gstin IS NOT NULL, 'dealer', v_me)
    RETURNING id INTO v_partner;
    SELECT id INTO v_role FROM role WHERE code = 'dealer' AND deleted_at IS NULL;
    INSERT INTO app_user (user_type, mobile, full_name, role_id, partner_id, must_change_password, created_by)
    VALUES ('partner_user', a.mobile, a.contact_name, v_role, v_partner, false, v_me)
    RETURNING id INTO v_user;
    UPDATE dealer_application SET status = 'approved', decided_by = v_me, decided_at = now(),
           decision_remark = NULLIF(btrim(p_remark), ''), partner_id = v_partner, user_id = v_user,
           session_hash = NULL WHERE id = p_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, partner_id, kind, actor_id, payload)
    VALUES ('dealer_application', p_id, a.lead_id, NULL, 'dealer_application.approved', v_me,
            jsonb_build_object('partner_id', v_partner, 'code', v_code)),
           ('channel_partner', v_partner, NULL, v_partner, 'partner.created', v_me,
            jsonb_build_object('code', v_code, 'partner_type', 'dealer', 'parent_id', p_parent, 'application_id', p_id));
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('app_user', v_user, 'user.created', v_me, jsonb_build_object('user_type', 'partner_user', 'partner_id', v_partner));
    RETURN QUERY SELECT v_partner, v_user;
END $fn$""",
    # ── the applicant, on app_anon: the token, then the session ──────────────
    # The form. Without a session, only what the link may show (plan review B-3)
    """CREATE FUNCTION dealer_apply_view(p_token_hash text, p_session_hash text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE; v_session boolean;
BEGIN
    SELECT * INTO a FROM dealer_application WHERE token_hash = p_token_hash
       AND link_expires_at > now() AND status IN ('draft', 'returned', 'submitted');
    IF NOT FOUND THEN RETURN NULL; END IF;
    v_session := p_session_hash IS NOT NULL AND a.session_hash = p_session_hash AND a.session_expires_at > now();
    RETURN jsonb_build_object('firm_name', a.firm_name, 'status', a.status,
        'mobile_masked', '+91 ' || repeat('x', 6) || right(a.mobile, 4),
        'missing', to_jsonb(dealer_application_missing(a.id)), 'session', v_session)
      || CASE WHEN v_session THEN jsonb_build_object(
        'remark', CASE WHEN a.status = 'returned' THEN a.decision_remark END,
        'id', a.id, 'contact_name', a.contact_name, 'firm_type', a.firm_type, 'gst_registered', a.gst_registered,
        'gstin', a.gstin, 'pan', a.pan, 'address', a.address, 'pincode', a.pincode, 'email', a.email,
        'godown_address', a.godown_address, 'years_in_business', a.years_in_business,
        'current_brands', a.current_brands, 'notes', a.notes, 'bank_account_name', a.bank_account_name,
        'bank_account_no', a.bank_account_no, 'bank_ifsc', a.bank_ifsc, 'gst_lookup', a.gst_lookup,
        'documents', coalesce((SELECT jsonb_agg(jsonb_build_object('id', r.id, 'doc_type', r.doc_type, 'name', r.name,
                     'filename', r.filename, 'mine', r.uploaded_by IS NULL) ORDER BY r.uploaded_at)
                    FROM record_document r WHERE r.record_type = 'dealer_application' AND r.record_id = a.id
                     AND r.deleted_at IS NULL), '[]'::jsonb))
      ELSE '{}'::jsonb END;
END $fn$""",
    # A code to the application's mobile: one a minute, ten a day (FS-003a's limits)
    """CREATE FUNCTION dealer_apply_issue_code(p_token_hash text, p_code text, p_code_hash text, p_ttl int)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE;
BEGIN
    SELECT * INTO a FROM dealer_application WHERE token_hash = p_token_hash
       AND link_expires_at > now() AND status IN ('draft', 'returned') FOR UPDATE;
    IF NOT FOUND THEN RETURN 'not_found'; END IF;
    IF a.last_code_at > now() - interval '60 seconds' THEN RETURN 'too_soon'; END IF;
    IF a.codes_window_start > now() - interval '24 hours' AND a.codes_sent >= 10 THEN RETURN 'rate_limited'; END IF;
    UPDATE dealer_application SET code_hash = p_code_hash, code_expires_at = now() + make_interval(secs => p_ttl),
           code_attempts = 0, last_code_at = now(),
           codes_sent = CASE WHEN codes_window_start > now() - interval '24 hours' THEN codes_sent + 1 ELSE 1 END,
           codes_window_start = CASE WHEN codes_window_start > now() - interval '24 hours' THEN codes_window_start ELSE now() END
     WHERE id = a.id;
    UPDATE notification_outbox SET state = 'dead', error = 'superseded', payload = '{}'::jsonb
     WHERE id IN (SELECT o.id FROM notification_outbox o WHERE o.state = 'pending'
                    AND o.template_key = 'dealer.verify' AND o.recipient = a.mobile FOR UPDATE SKIP LOCKED);
    INSERT INTO notification_outbox (channel, template_key, recipient, payload, created_at, next_attempt_at)
    VALUES ('whatsapp', 'dealer.verify', a.mobile, jsonb_build_object('code', p_code),
            clock_timestamp(), clock_timestamp());
    RETURN 'issued';
END $fn$""",
    # Never raises for a wrong code, so the attempt count commits; five burns it
    """CREATE FUNCTION dealer_apply_check_code(p_token_hash text, p_code_hash text, p_session_hash text, p_ttl int)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE;
BEGIN
    SELECT * INTO a FROM dealer_application WHERE token_hash = p_token_hash
       AND link_expires_at > now() AND status IN ('draft', 'returned') FOR UPDATE;
    IF NOT FOUND OR a.code_hash IS NULL OR a.code_expires_at <= now() THEN RETURN 'invalid'; END IF;
    IF a.code_hash <> p_code_hash THEN
        UPDATE dealer_application SET code_attempts = code_attempts + 1,
               code_hash = CASE WHEN code_attempts + 1 >= 5 THEN NULL ELSE code_hash END WHERE id = a.id;
        RETURN 'invalid';
    END IF;
    UPDATE dealer_application SET code_hash = NULL, session_hash = p_session_hash,
           session_expires_at = now() + make_interval(secs => p_ttl) WHERE id = a.id;
    RETURN 'ok';
END $fn$""",
    # The applicant's writes: draft or returned only, with a live session (edge E-6)
    """CREATE FUNCTION dealer_apply_session(p_token_hash text, p_session_hash text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT id FROM dealer_application WHERE token_hash = p_token_hash AND link_expires_at > now()
       AND session_hash = p_session_hash AND session_expires_at > now() AND status IN ('draft', 'returned')
$fn$""",
    """CREATE FUNCTION dealer_apply_write(p_token_hash text, p_session_hash text, p_action text, p_fields jsonb)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid; v_missing text[]; a dealer_application%ROWTYPE;
BEGIN
    SELECT * INTO a FROM dealer_application WHERE token_hash = p_token_hash AND link_expires_at > now() FOR UPDATE;
    IF NOT FOUND THEN RETURN 'not_found'; END IF;
    IF p_action = 'submit' AND a.status = 'submitted' THEN RETURN 'ok'; END IF;   -- a replay
    IF a.status NOT IN ('draft', 'returned') THEN RETURN 'closed'; END IF;
    v_id := dealer_apply_session(p_token_hash, p_session_hash);
    IF v_id IS NULL THEN RETURN 'no_session'; END IF;
    IF p_action = 'patch' THEN
        PERFORM dealer_application_write(v_id, p_fields, 'applicant');
        RETURN 'ok';
    END IF;
    v_missing := dealer_application_missing(v_id);
    IF cardinality(v_missing) > 0 THEN
        RETURN 'missing:' || array_to_string(v_missing, ',');
    END IF;
    UPDATE dealer_application SET status = 'submitted', submitted_at = now(), session_hash = NULL WHERE id = v_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('dealer_application', v_id, a.lead_id, 'dealer_application.submitted', NULL, '{"by": "applicant"}');
    RETURN 'ok';
END $fn$""",
    # The applicant's documents: through FS-050's insert, with no uploader
    """CREATE FUNCTION dealer_apply_document(p_token_hash text, p_session_hash text, p_doc_type text, p_name text,
        p_key text, p_filename text, p_content_type text, p_size int, p_sha text)
RETURNS TABLE (id uuid, created boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_app uuid; v_id uuid;
BEGIN
    v_app := dealer_apply_session(p_token_hash, p_session_hash);
    IF v_app IS NULL THEN
        RAISE EXCEPTION 'no session' USING ERRCODE = 'DAPSS';
    END IF;
    PERFORM 1 FROM dealer_application WHERE dealer_application.id = v_app FOR UPDATE;
    INSERT INTO record_document (record_type, record_id, doc_type, name, storage_key, filename, content_type,
                                 size_bytes, sha256, uploaded_by)
    SELECT 'dealer_application', v_app, p_doc_type, NULLIF(btrim(p_name), ''), p_key, p_filename, p_content_type,
           p_size, p_sha, NULL
     WHERE (SELECT count(*) FROM record_document r WHERE r.record_type = 'dealer_application' AND r.record_id = v_app
              AND r.deleted_at IS NULL) < 50
    ON CONFLICT (record_type, record_id, doc_type, sha256) WHERE deleted_at IS NULL DO NOTHING
    RETURNING record_document.id INTO v_id;
    IF v_id IS NOT NULL THEN
        PERFORM record_document_event(v_id, 'document.added');
        RETURN QUERY SELECT v_id, true;
        RETURN;
    END IF;
    SELECT r.id INTO v_id FROM record_document r WHERE r.record_type = 'dealer_application' AND r.record_id = v_app
       AND r.doc_type = p_doc_type AND r.sha256 = p_sha AND r.deleted_at IS NULL;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'at most 50 documents' USING ERRCODE = 'DOCMX';
    END IF;
    RETURN QUERY SELECT v_id, false;
END $fn$""",
    # The applicant removes only its own uploads
    """CREATE FUNCTION dealer_apply_document_remove(p_token_hash text, p_session_hash text, p_doc uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_app uuid;
BEGIN
    v_app := dealer_apply_session(p_token_hash, p_session_hash);
    IF v_app IS NULL THEN RETURN 'no_session'; END IF;
    UPDATE record_document SET deleted_at = now()
     WHERE id = p_doc AND record_type = 'dealer_application' AND record_id = v_app
       AND uploaded_by IS NULL AND deleted_at IS NULL;
    IF NOT FOUND THEN RETURN 'not_found'; END IF;
    PERFORM record_document_event(p_doc, 'document.removed');
    RETURN 'ok';
END $fn$""",
    REFUSAL_062,
    EVENT_062,
    ADD_062,
]

GRANTED_STAFF = ["dealer_application_visible(uuid)", "dealer_application_missing(uuid)",
                 "dealer_application_create(text, text, text, uuid, uuid, text, timestamptz)",
                 "dealer_application_staff(uuid, text, jsonb, text, text, timestamptz)",
                 "dealer_application_decide(uuid, text, text, uuid, text)"]
GRANTED_ANON = ["dealer_apply_view(text, text)", "dealer_apply_issue_code(text, text, text, int)",
                "dealer_apply_check_code(text, text, text, int)",
                "dealer_apply_write(text, text, text, jsonb)",
                "dealer_apply_document(text, text, text, text, text, text, text, int, text)",
                "dealer_apply_document_remove(text, text, uuid)",
                # the application's id for its token and a live session: both secrets needed
                "dealer_apply_session(text, text)"]
INTERNAL = ["dealer_application_write(uuid, jsonb, text)"]


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE dealer_application ENABLE ROW LEVEL SECURITY")
    op.execute(floor.policy_sql("dealer_application"))
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute("DROP POLICY record_document_sel ON record_document")
    for stmt in FUNCTIONS[:1]:      # dealer_application_visible, before the policies that name it
        op.execute(stmt)
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS[1:]:
        op.execute(stmt)
    for sig in GRANTED_STAFF + GRANTED_ANON + INTERNAL:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
    for sig in GRANTED_STAFF:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for sig in GRANTED_ANON:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {ANON_ROLE}")


def downgrade() -> None:
    op.execute(_or_replace(REFUSAL_061))
    op.execute(_or_replace(EVENT_061))
    op.execute(_or_replace(ADD_061))
    op.execute("DROP POLICY record_document_sel ON record_document")
    op.execute(M061.SELECT_POLICY)
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(next(st for t, st in M050.HAND_POLICIES if t == "activity_event"))
    for sig in reversed(GRANTED_STAFF + GRANTED_ANON + INTERNAL):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE entity_type = 'dealer_application'")
    op.execute("DELETE FROM record_document WHERE record_type = 'dealer_application'")
    op.execute("ALTER TABLE record_document DROP CONSTRAINT ck_record_document_record_type")
    op.execute("ALTER TABLE record_document ADD CONSTRAINT ck_record_document_record_type CHECK (record_type IN ('lead', 'quotation', 'sales_order', 'dispatch', 'payment'))")
    op.execute("ALTER TABLE record_document DROP CONSTRAINT ck_record_document_doc_type")
    op.execute("ALTER TABLE record_document ADD CONSTRAINT ck_record_document_doc_type CHECK (doc_type IN ('purchase_order', 'payment_proof', 'signed_quotation', 'invoice', 'delivery_challan', 'transport_receipt', 'site_photo', 'land_record', 'subsidy_document', 'other'))")
    op.execute("DROP TABLE dealer_application")
