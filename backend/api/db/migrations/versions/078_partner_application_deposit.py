"""078: partner applications: distributors, the data sheet, the deposit (FS-071).

- `dealer_application` gains `partner_type`, the data sheet's fields, and the deposit
  copied from a setting at creation (`deposit_set`, `deposit_due`, no DEFAULT: a
  writer that forgets them fails, edge E-1).
- `dealer_application_deposit_entry`: payments and relaxations, append only.
- `dealer_application_deposit_status()` and `dealer_application_can()`: one
  definition each, for the read, the gate and the buttons (E-4, E-7).
- Documents on a dealer application: frozen once it is closed, and the slip a
  payment points to cannot be removed, on the staff path and the applicant's
  (E-2, plan review B-1). The application row is locked before the document
  everywhere (plan review R-1).
- Settings: kinds `set` and `staff_roles`, and seven rows the admin changes.

Revision ID: 078_partner_application_deposit
Revises: 077_gst_choice_and_freight
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "078_partner_application_deposit"
down_revision: str | None = "077_gst_choice_and_freight"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_078", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"078: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"078: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _or_replace(text: str) -> str:
    return text.replace("CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", 1)


_floor_spec = importlib.util.spec_from_file_location(
    "consumer_floor_078", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _floor_spec is not None and _floor_spec.loader is not None
floor = importlib.util.module_from_spec(_floor_spec)
_floor_spec.loader.exec_module(floor)

M061 = _load("061_record_documents")
M062 = _load("062_dealer_recruitment")
M077 = _load("077_gst_choice_and_freight")


def _f062(name: str) -> str:
    return next(f for f in M062.FUNCTIONS if f.lstrip().startswith(f"CREATE FUNCTION {name}(")
                or f.lstrip().startswith(f"CREATE OR REPLACE FUNCTION {name}("))


def _f061(name: str) -> str:
    return next(f for f in M061.FUNCTIONS if f.startswith(f"CREATE FUNCTION {name}("))


# ── the data sheet's columns ─────────────────────────────────────────────────

_TEXTS = {"telephone": 32, "bank_name": 200, "bank_branch": 200, "bank_address": 1000,
          "other_vehicles": 200, "appointment_place": 200}
_INTS = {"two_wheelers": 999, "cars": 999, "sales_executives": 9999, "technicians": 9999}
_DECIMALS = {"other_sources_lakhs": ("numeric(7,2)", "99999.99"),
             "office_area": ("numeric(9,2)", "9999999.99"),
             "godown_area": ("numeric(9,2)", "9999999.99")}
_LISTS = {"working_capital": 10, "manpower": 20, "previous_installations": 50}
DATA_SHEET = [*_TEXTS, "established_on", *_INTS, *_DECIMALS, "area_unit", *_LISTS]

COLUMNS = (
    ["ADD COLUMN partner_type text NOT NULL DEFAULT 'dealer'",
     "ADD CONSTRAINT ck_dealer_application_partner_type CHECK (partner_type IN ('dealer', 'distributor'))",
     "ADD COLUMN established_on date",
     "ADD CONSTRAINT ck_dealer_application_established CHECK (established_on IS NULL OR established_on >= DATE '1900-01-01')",
     "ADD COLUMN area_unit text NOT NULL DEFAULT 'sq_ft'",
     "ADD CONSTRAINT ck_dealer_application_area_unit CHECK (area_unit IN ('sq_m', 'sq_ft'))",
     "ADD COLUMN deposit_set numeric(14,2)",
     "ADD COLUMN deposit_due numeric(14,2)"]
    + [f"ADD COLUMN {c} text, ADD CONSTRAINT ck_dealer_application_{c} CHECK ({c} IS NULL OR length(btrim({c})) BETWEEN 1 AND {n})"
       for c, n in _TEXTS.items()]
    + [f"ADD COLUMN {c} int, ADD CONSTRAINT ck_dealer_application_{c} CHECK ({c} IS NULL OR {c} BETWEEN 0 AND {n})"
       for c, n in _INTS.items()]
    + [f"ADD COLUMN {c} {t}, ADD CONSTRAINT ck_dealer_application_{c} CHECK ({c} IS NULL OR {c} BETWEEN 0 AND {m})"
       for c, (t, m) in _DECIMALS.items()]
    + [f"ADD COLUMN {c} jsonb, ADD CONSTRAINT ck_dealer_application_{c} CHECK ({c} IS NULL OR "
       f"(jsonb_typeof({c}) = 'array' AND jsonb_array_length({c}) BETWEEN 1 AND {n}))"
       for c, n in _LISTS.items()]
)

TABLES = [
    "ALTER TABLE dealer_application " + ",\n    ".join(COLUMNS),
    # applications open when this ships carry no deposit (rule 4, E-25); then no DEFAULT (E-1)
    "UPDATE dealer_application SET deposit_set = 0, deposit_due = 0",
    "ALTER TABLE dealer_application ALTER COLUMN deposit_set SET NOT NULL, ALTER COLUMN deposit_due SET NOT NULL, "
    "ADD CONSTRAINT ck_dealer_application_deposit CHECK (deposit_due >= 0 AND deposit_due <= deposit_set AND deposit_set <= 10000000)",
    "CREATE INDEX ix_dealer_application_partner_type ON dealer_application (partner_type)",
    """CREATE TABLE dealer_application_deposit_entry (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL REFERENCES dealer_application(id),
    kind text NOT NULL,
    amount numeric(14,2) NOT NULL,
    from_due numeric(14,2),
    paid_on date,
    reference text,
    slip_id uuid REFERENCES record_document(id),
    reason text,
    created_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_deposit_entry_kind CHECK (kind IN ('payment', 'relaxation')),
    CONSTRAINT ck_deposit_entry_amount CHECK (amount >= 0 AND amount <= 10000000),
    CONSTRAINT ck_deposit_entry_payment CHECK (kind <> 'payment' OR (amount > 0 AND paid_on IS NOT NULL
        AND slip_id IS NOT NULL AND reason IS NULL AND from_due IS NULL)),
    CONSTRAINT ck_deposit_entry_relaxation CHECK (kind <> 'relaxation' OR (from_due IS NOT NULL AND amount < from_due
        AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 1000 AND paid_on IS NULL AND slip_id IS NULL)),
    CONSTRAINT ck_deposit_entry_reference CHECK (reference IS NULL OR length(reference) <= 100)
)""",
    "CREATE INDEX ix_deposit_entry_application ON dealer_application_deposit_entry (application_id, created_at)",
    "CREATE INDEX ix_deposit_entry_slip ON dealer_application_deposit_entry (slip_id)",
    "CREATE INDEX ix_deposit_entry_created_by ON dealer_application_deposit_entry (created_by)",
    "ALTER TABLE record_document DROP CONSTRAINT ck_record_document_doc_type",
    "ALTER TABLE record_document ADD CONSTRAINT ck_record_document_doc_type CHECK (doc_type IN ('purchase_order', 'payment_proof', 'signed_quotation', 'invoice', 'delivery_challan', 'transport_receipt', 'site_photo', 'land_record', 'subsidy_document', 'other', 'gst_certificate', 'pan_card', 'cancelled_cheque', 'shop_photo', 'shop_licence', 'deposit_slip'))",
]
DOC_TYPES_062 = "('purchase_order', 'payment_proof', 'signed_quotation', 'invoice', 'delivery_challan', 'transport_receipt', 'site_photo', 'land_record', 'subsidy_document', 'other', 'gst_certificate', 'pan_card', 'cancelled_cheque', 'shop_photo', 'shop_licence')"

GRANTS: dict[str, str] = {"dealer_application_deposit_entry": "SELECT"}

# the parent's policy does the scope, through a subselect (rule 8; edge E-23)
HAND_POLICIES: list[tuple[str, str]] = [
    ("dealer_application_deposit_entry",
     "CREATE POLICY dealer_application_deposit_entry_sel ON dealer_application_deposit_entry FOR SELECT "
     "USING (application_id IN (SELECT id FROM dealer_application))"),
]

# ── settings ─────────────────────────────────────────────────────────────────

REQUIRED_ALLOWED = ["email", "godown_address", "telephone", "established_on", "bank_name", "bank_branch",
                    "bank_address", "working_capital", "vehicles", "office_area", "godown_area", "manpower",
                    "previous_installations", "staff_counts", "appointment_place", "shop_photo", "shop_licence"]
_ALLOWED = "[" + ", ".join(f'"{x}"' for x in REQUIRED_ALLOWED) + "]"

SETTING_KEYS = ["dealer_deposit_amount", "distributor_deposit_amount", "deposit_relaxation_roles",
                "dealer_application_deciders", "distributor_application_deciders",
                "dealer_application_required", "distributor_application_required"]

SEED = f"""INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('dealer_deposit_amount', 'int', '0', NULL, 0, 10000000,
 'The deposit, in rupees, a new dealer pays before approval. 0: no deposit.'),
('distributor_deposit_amount', 'int', '0', NULL, 0, 10000000,
 'The deposit, in rupees, a new distributor pays before approval. 0: no deposit.'),
('deposit_relaxation_roles', 'staff_roles', '["regional_manager", "md_ceo"]', NULL, NULL, NULL,
 'Who may lower or waive a deposit on a partner application.'),
('dealer_application_deciders', 'staff_roles', '["state_manager", "regional_manager", "md_ceo", "admin_sales"]', NULL, NULL, NULL,
 'Who approves, returns or rejects a dealer application.'),
('distributor_application_deciders', 'staff_roles', '["regional_manager", "md_ceo", "admin_sales"]', NULL, NULL, NULL,
 'Who approves, returns or rejects a distributor application.'),
('dealer_application_required', 'set', '[]', '{_ALLOWED}', NULL, NULL,
 'Extra fields a dealer application must have before it is submitted.'),
('distributor_application_required', 'set', '[]', '{_ALLOWED}', NULL, NULL,
 'Extra fields a distributor application must have before it is submitted.')
ON CONFLICT (key) DO NOTHING"""

KINDS_077 = "'choice', 'int', 'roles', 'bands', 'slabs'"
KINDS_078 = KINDS_077 + ", 'set', 'staff_roles'"

CHECK_BEFORE = M077.CHECK_AFTER
_ANCHOR = """    ELSE
        IF jsonb_typeof(NEW.value) <> 'array' THEN
            RAISE EXCEPTION 'setting %: a list of role codes', NEW.key USING ERRCODE = 'SETVL';"""
CHECK_AFTER = _replace(CHECK_BEFORE, _ANCHOR, """    ELSIF NEW.kind = 'set' THEN
        -- FS-071: some of `allowed`, none twice; none at all is fine
        IF jsonb_typeof(NEW.value) <> 'array' THEN
            RAISE EXCEPTION 'setting %: a list from %', NEW.key, NEW.allowed USING ERRCODE = 'SETVL';
        END IF;
        FOR e IN SELECT x FROM jsonb_array_elements(NEW.value) x LOOP
            IF jsonb_typeof(e) <> 'string' OR NOT (NEW.allowed @> jsonb_build_array(e)) THEN
                RAISE EXCEPTION 'setting %: % is not one of %', NEW.key, e, NEW.allowed USING ERRCODE = 'SETVL';
            END IF;
        END LOOP;
        IF (SELECT count(DISTINCT x) FROM jsonb_array_elements(NEW.value) x) <> jsonb_array_length(NEW.value) THEN
            RAISE EXCEPTION 'setting %: a value is listed twice', NEW.key USING ERRCODE = 'SETVL';
        END IF;
    ELSIF NEW.kind = 'staff_roles' THEN
        -- FS-071: at least one staff role. An empty list would strand every
        -- application it decides (edge E-6)
        IF jsonb_typeof(NEW.value) <> 'array' OR jsonb_array_length(NEW.value) = 0 THEN
            RAISE EXCEPTION 'setting %: at least one role', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        FOR e IN SELECT x FROM jsonb_array_elements(NEW.value) x LOOP
            IF jsonb_typeof(e) <> 'string' OR (e #>> '{}') = 'system' THEN
                RAISE EXCEPTION 'setting %: % is not a staff role', NEW.key, e USING ERRCODE = 'SETVL';
            END IF;
        END LOOP;
        IF (SELECT count(DISTINCT x) FROM jsonb_array_elements(NEW.value) x) <> jsonb_array_length(NEW.value) THEN
            RAISE EXCEPTION 'setting %: a role is listed twice', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        -- a fresh database migrates before the roles are seeded, as the roles kind
        -- says below: existence is checked from the first change on (plan review B-2)
        IF TG_OP = 'UPDATE' THEN
            FOR r IN SELECT jsonb_array_elements_text(NEW.value) LOOP
                IF NOT EXISTS (SELECT 1 FROM role WHERE code = r AND deleted_at IS NULL AND NOT is_portal) THEN
                    RAISE EXCEPTION 'setting %: no staff role %', NEW.key, r USING ERRCODE = 'SETVL';
                END IF;
            END LOOP;
        END IF;
""" + _ANCHOR)


# ── functions ────────────────────────────────────────────────────────────────

_EVENT = M062._EVENT

# FS-051's text fields plus the new ones, as 062's `_SETS` builds them
_TEXT_FIELDS = M062._FIELDS + list(_TEXTS)
_SETS = ",\n           ".join(
    [f"{f} = CASE WHEN p_fields ? '{f}' THEN NULLIF(btrim(p_fields ->> '{f}'), '') ELSE {f} END" for f in _TEXT_FIELDS]
    # a typed column: null and "" are SQL NULL, never a cast of "" (edge E-3, ISS-217)
    + [f"{f} = CASE WHEN p_fields ? '{f}' THEN NULLIF(p_fields ->> '{f}', '')::int ELSE {f} END"
       for f in ["years_in_business", *_INTS]]
    + [f"{f} = CASE WHEN p_fields ? '{f}' THEN NULLIF(p_fields ->> '{f}', '')::numeric ELSE {f} END" for f in _DECIMALS]
    + ["established_on = CASE WHEN p_fields ? 'established_on' THEN NULLIF(p_fields ->> 'established_on', '')::date ELSE established_on END",
       "area_unit = CASE WHEN p_fields ? 'area_unit' THEN coalesce(NULLIF(p_fields ->> 'area_unit', ''), 'sq_ft') ELSE area_unit END",
       # a yes/no cleared falls back to its default, as the column is NOT NULL
       "gst_registered = CASE WHEN p_fields ? 'gst_registered' THEN coalesce(NULLIF(p_fields ->> 'gst_registered', '')::boolean, true) ELSE gst_registered END"]
    + [f"{f} = CASE WHEN p_fields ? '{f}' THEN CASE WHEN jsonb_typeof(p_fields -> '{f}') = 'array' "
       f"AND jsonb_array_length(p_fields -> '{f}') > 0 THEN p_fields -> '{f}' END ELSE {f} END" for f in _LISTS])

WRITE_078 = f"""CREATE OR REPLACE FUNCTION dealer_application_write(p_id uuid, p_fields jsonb, p_by text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_pan text; v_gstin text; v_old dealer_application%ROWTYPE; v_type text; v_set numeric;
BEGIN
    SELECT * INTO v_old FROM dealer_application WHERE id = p_id FOR UPDATE;
    -- FS-071: the type is staff's, before any deposit entry, while draft or returned (E-8)
    v_type := NULLIF(p_fields ->> 'partner_type', '');
    IF v_type IS NOT NULL AND v_type <> v_old.partner_type THEN
        IF p_by <> 'staff' THEN
            RAISE EXCEPTION 'the applicant does not choose the type' USING ERRCODE = 'DAPTY';
        END IF;
        IF v_old.status NOT IN ('draft', 'returned') THEN
            RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
        END IF;
        IF EXISTS (SELECT 1 FROM dealer_application_deposit_entry e WHERE e.application_id = p_id) THEN
            RAISE EXCEPTION 'a deposit is recorded' USING ERRCODE = 'DAPDR';
        END IF;
        v_set := (app_setting_json(v_type || '_deposit_amount') #>> '{{}}')::numeric;
        UPDATE dealer_application SET partner_type = v_type, deposit_set = v_set, deposit_due = v_set WHERE id = p_id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('dealer_application', p_id, v_old.lead_id, 'dealer_application.type_changed', app_current_user_id(),
                jsonb_build_object('from', v_old.partner_type, 'to', v_type, 'deposit_set', v_set::text));
    END IF;
    UPDATE dealer_application SET
           {_SETS},
           gst_lookup = CASE WHEN p_fields ? 'gst_lookup' THEN p_fields -> 'gst_lookup' ELSE gst_lookup END,
           gst_state_mismatch = CASE WHEN p_fields ? 'gst_state_mismatch' THEN (p_fields ->> 'gst_state_mismatch')::boolean ELSE gst_state_mismatch END
     WHERE id = p_id
    RETURNING pan, gstin INTO v_pan, v_gstin;
    -- the PAN inside the GSTIN must be the PAN given (edge E-8)
    IF v_gstin IS NOT NULL AND v_pan IS NOT NULL AND substr(v_gstin, 3, 10) <> v_pan THEN
        RAISE EXCEPTION 'the PAN is not the one in the GSTIN' USING ERRCODE = 'DAPPN';
    END IF;
    {_EVENT.format(kind="'dealer_application.updated'", payload="jsonb_build_object('fields', (SELECT jsonb_agg(k) FROM jsonb_object_keys(p_fields) k WHERE k NOT IN ('gst_lookup', 'gst_state_mismatch', 'partner_type')), 'by', p_by)", id="p_id")};
END $fn$"""

CREATE_078 = f"""CREATE FUNCTION dealer_application_create(p_firm text, p_contact text, p_mobile text, p_territory uuid,
        p_lead uuid, p_token_hash text, p_expires timestamptz, p_type text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_id uuid; v_set numeric;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT app_has_permission('partners', 'view') THEN
        RAISE EXCEPTION 'staff with partners view' USING ERRCODE = '42501';
    END IF;
    IF p_type IS NULL OR p_type NOT IN ('dealer', 'distributor') THEN
        RAISE EXCEPTION 'dealer or distributor' USING ERRCODE = 'DAPTY';
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
    -- FS-071 rule 4: the deposit is the setting's now, and stays
    v_set := (app_setting_json(p_type || '_deposit_amount') #>> '{{}}')::numeric;
    INSERT INTO dealer_application (firm_name, contact_name, mobile, territory_id, lead_id, token_hash,
                                    link_expires_at, created_by, partner_type, deposit_set, deposit_due)
    VALUES (btrim(p_firm), btrim(p_contact), p_mobile, p_territory, p_lead, p_token_hash, p_expires, v_me,
            p_type, v_set, v_set)
    RETURNING id INTO v_id;
    IF NOT dealer_application_visible(v_id) THEN
        RAISE EXCEPTION 'territory outside your scope' USING ERRCODE = 'DAPTR';
    END IF;
    {_EVENT.format(kind="'dealer_application.created'", payload="jsonb_build_object('firm_name', a.firm_name, 'partner_type', a.partner_type)", id="v_id")};
    RETURN v_id;
END $fn$"""

_DOC_MISSING = """CASE WHEN NOT EXISTS (SELECT 1 FROM record_document r WHERE r.record_type = 'dealer_application'
                 AND r.record_id = a.id AND r.doc_type = '{t}' AND r.deleted_at IS NULL) THEN '{t}' END"""
_REQ = [("email", "a.email IS NULL"), ("godown_address", "a.godown_address IS NULL"),
        ("telephone", "a.telephone IS NULL"), ("established_on", "a.established_on IS NULL"),
        ("bank_name", "a.bank_name IS NULL"), ("bank_branch", "a.bank_branch IS NULL"),
        ("bank_address", "a.bank_address IS NULL"), ("working_capital", "a.working_capital IS NULL"),
        ("vehicles", "a.two_wheelers IS NULL AND a.cars IS NULL"), ("office_area", "a.office_area IS NULL"),
        ("godown_area", "a.godown_area IS NULL"), ("manpower", "a.manpower IS NULL"),
        ("previous_installations", "a.previous_installations IS NULL"),
        ("staff_counts", "a.sales_executives IS NULL OR a.technicians IS NULL"),
        ("appointment_place", "a.appointment_place IS NULL")]
assert [k for k, _ in _REQ] + ["shop_photo", "shop_licence"] == REQUIRED_ALLOWED
_REQ_SQL = ",\n            ".join(
    [f"CASE WHEN r.req ? '{k}' AND ({cond}) THEN '{k}' END" for k, cond in _REQ]
    + [f"CASE WHEN r.req ? '{t}' THEN " + _DOC_MISSING.format(t=t).replace("CASE WHEN", "(CASE WHEN", 1) + ") END"
       for t in ("shop_photo", "shop_licence")])

MISSING_078 = f"""CREATE OR REPLACE FUNCTION dealer_application_missing(p_id uuid) RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(array_agg(DISTINCT x ORDER BY x), '{{}}') FROM (
        SELECT unnest(ARRAY[
            CASE WHEN a.firm_type IS NULL THEN 'firm_type' END,
            CASE WHEN a.gst_registered AND a.gstin IS NULL THEN 'gstin' END,
            CASE WHEN a.pan IS NULL THEN 'pan' END,
            CASE WHEN a.address IS NULL THEN 'address' END,
            CASE WHEN a.pincode IS NULL THEN 'pincode' END,
            CASE WHEN a.bank_account_name IS NULL THEN 'bank_account_name' END,
            CASE WHEN a.bank_account_no IS NULL THEN 'bank_account_no' END,
            CASE WHEN a.bank_ifsc IS NULL THEN 'bank_ifsc' END,
            CASE WHEN a.gst_registered THEN {_DOC_MISSING.format(t='gst_certificate')} END,
            {_DOC_MISSING.format(t='pan_card')},
            {_DOC_MISSING.format(t='cancelled_cheque')},
            -- FS-071 rule 10: what the type's setting adds
            {_REQ_SQL}
        ]) AS x
          FROM dealer_application a
         CROSS JOIN LATERAL (SELECT app_setting_json(a.partner_type || '_application_required') AS req) r
         WHERE a.id = p_id) s WHERE x IS NOT NULL
$fn$"""

# FS-071 section 3: the first match wins
DEPOSIT_STATUS = """CREATE FUNCTION dealer_application_deposit_status(p_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT CASE
        WHEN p.amount IS NOT NULL AND p.amount >= a.deposit_due THEN 'paid'
        WHEN a.deposit_due = 0 AND EXISTS (SELECT 1 FROM dealer_application_deposit_entry e
                                            WHERE e.application_id = a.id AND e.kind = 'relaxation') THEN 'waived'
        WHEN a.deposit_due > 0 THEN 'pending'
        ELSE 'not_required' END
      FROM dealer_application a
      LEFT JOIN LATERAL (SELECT e.amount FROM dealer_application_deposit_entry e
                          WHERE e.application_id = a.id AND e.kind = 'payment'
                          ORDER BY e.created_at DESC, e.id DESC LIMIT 1) p ON true
     WHERE a.id = p_id AND dealer_application_visible(a.id)
$fn$"""

# What the caller may do, for the buttons and for the definers alike (edge E-7)
CAN = """CREATE FUNCTION dealer_application_can(p_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE; v_me uuid := app_current_user_id(); v_role text; v_open boolean;
        v_paid boolean; v_mine boolean;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT dealer_application_visible(p_id) THEN
        RETURN '{}'::jsonb;
    END IF;
    SELECT * INTO a FROM dealer_application WHERE id = p_id;
    SELECT r.code::text INTO v_role FROM app_user u JOIN role r ON r.id = u.role_id
     WHERE u.id = v_me AND NOT r.is_portal;
    v_open := a.status IN ('draft', 'returned', 'submitted');
    v_mine := a.created_by = v_me;
    v_paid := EXISTS (SELECT 1 FROM dealer_application_deposit_entry e WHERE e.application_id = p_id AND e.kind = 'payment');
    RETURN jsonb_build_object(
        'edit', v_open,
        'withdraw', v_open,
        'renew', a.status IN ('draft', 'returned'),
        'decide', a.status = 'submitted' AND NOT v_mine AND v_role IS NOT NULL
                  AND app_setting_json(a.partner_type || '_application_deciders') ? v_role,
        'record_deposit', v_open AND a.deposit_due > 0,
        'relax_deposit', v_open AND NOT v_mine AND NOT v_paid AND a.deposit_due > 0 AND v_role IS NOT NULL
                         AND app_setting_json('deposit_relaxation_roles') ? v_role);
END $fn$"""

DEPOSIT_RECORD = """CREATE FUNCTION dealer_application_deposit_record(p_id uuid, p_amount numeric, p_paid_on date,
        p_reference text, p_slip uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE; v_prev numeric;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT dealer_application_visible(p_id) THEN
        RAISE EXCEPTION 'no such application' USING ERRCODE = 'DAPNF';
    END IF;
    -- the application, then the slip: the order remove takes too (plan review R-1)
    SELECT * INTO a FROM dealer_application WHERE id = p_id FOR UPDATE;
    IF a.status NOT IN ('draft', 'returned', 'submitted') THEN
        RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
    END IF;
    IF a.deposit_due = 0 THEN
        RAISE EXCEPTION 'nothing is due' USING ERRCODE = 'DAPND';
    END IF;
    IF p_amount IS NULL OR p_amount <= 0 OR p_amount > a.deposit_set OR p_amount <> round(p_amount, 2) THEN
        RAISE EXCEPTION 'amount' USING ERRCODE = 'DAPAM';
    END IF;
    IF p_amount < a.deposit_due THEN
        RAISE EXCEPTION 'below the amount due' USING ERRCODE = 'DAPSH';
    END IF;
    IF p_paid_on IS NULL OR p_paid_on > (now() AT TIME ZONE 'Asia/Kolkata')::date
       OR p_paid_on < (a.created_at AT TIME ZONE 'Asia/Kolkata')::date - 365 THEN
        RAISE EXCEPTION 'paid on' USING ERRCODE = 'DAPPO';
    END IF;
    PERFORM 1 FROM record_document r WHERE r.id = p_slip AND r.record_type = 'dealer_application'
       AND r.record_id = p_id AND r.doc_type = 'deposit_slip' AND r.deleted_at IS NULL FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such slip' USING ERRCODE = 'DAPSL';
    END IF;
    SELECT e.amount INTO v_prev FROM dealer_application_deposit_entry e
     WHERE e.application_id = p_id AND e.kind = 'payment' ORDER BY e.created_at DESC, e.id DESC LIMIT 1;
    INSERT INTO dealer_application_deposit_entry (application_id, kind, amount, paid_on, reference, slip_id, created_by)
    VALUES (p_id, 'payment', p_amount, p_paid_on, NULLIF(btrim(p_reference), ''), p_slip, app_current_user_id());
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('dealer_application', p_id, a.lead_id, 'dealer_application.deposit_recorded', app_current_user_id(),
            jsonb_build_object('amount', p_amount::text, 'previous_amount', v_prev::text, 'paid_on', p_paid_on, 'slip_id', p_slip));
END $fn$"""

RELAX = """CREATE FUNCTION dealer_application_relax(p_id uuid, p_due numeric, p_reason text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE a dealer_application%ROWTYPE; v_role text;
BEGIN
    IF app_current_partner() IS NOT NULL OR NOT dealer_application_visible(p_id) THEN
        RAISE EXCEPTION 'no such application' USING ERRCODE = 'DAPNF';
    END IF;
    SELECT * INTO a FROM dealer_application WHERE id = p_id FOR UPDATE;
    IF a.status NOT IN ('draft', 'returned', 'submitted') THEN
        RAISE EXCEPTION 'closed' USING ERRCODE = 'DAPCL';
    END IF;
    SELECT r.code::text INTO v_role FROM app_user u JOIN role r ON r.id = u.role_id
     WHERE u.id = app_current_user_id() AND NOT r.is_portal;
    IF a.created_by = app_current_user_id() OR v_role IS NULL
       OR NOT app_setting_json('deposit_relaxation_roles') ? v_role THEN
        RAISE EXCEPTION 'not your relaxation' USING ERRCODE = 'DAPRX';
    END IF;
    IF EXISTS (SELECT 1 FROM dealer_application_deposit_entry e WHERE e.application_id = p_id AND e.kind = 'payment') THEN
        RAISE EXCEPTION 'a payment is recorded' USING ERRCODE = 'DAPPD';
    END IF;
    IF p_reason IS NULL OR btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'a reason' USING ERRCODE = 'DAPRR';
    END IF;
    IF p_due IS NULL OR p_due < 0 OR p_due >= a.deposit_due OR p_due <> round(p_due, 2) THEN
        RAISE EXCEPTION 'not lower' USING ERRCODE = 'DAPNL';
    END IF;
    INSERT INTO dealer_application_deposit_entry (application_id, kind, amount, from_due, reason, created_by)
    VALUES (p_id, 'relaxation', p_due, a.deposit_due, btrim(p_reason), app_current_user_id());
    UPDATE dealer_application SET deposit_due = p_due WHERE id = p_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('dealer_application', p_id, a.lead_id, 'dealer_application.deposit_relaxed', app_current_user_id(),
            jsonb_build_object('from', a.deposit_due::text, 'to', p_due::text));
END $fn$"""

# ── the decision: the setting decides who, the deposit gates, a distributor branch ──

DECIDE_062 = _f062("dealer_application_decide")
_d = _or_replace(DECIDE_062)
_d = _replace(_d, """DECLARE a dealer_application%ROWTYPE; v_me uuid := app_current_user_id(); v_level int; v_line boolean;
        v_partner uuid; v_user uuid; v_role uuid; v_code text; v_state text; v_n int; v_consumer uuid; v_fam uuid;""",
              """DECLARE a dealer_application%ROWTYPE; v_me uuid := app_current_user_id();
        v_partner uuid; v_user uuid; v_role uuid; v_code text; v_state text; v_n int; v_consumer uuid; v_fam uuid;
        v_prefix text; v_status text;""")
_d = _replace(_d, """    -- a State Manager or above (a line role at level 3 or more), or global partners.create;
    -- never whoever started it (rule 10)
    SELECT r.level, NOT r.is_functional AND NOT r.is_portal INTO v_level, v_line
      FROM app_user u JOIN role r ON r.id = u.role_id WHERE u.id = v_me;
    IF v_me = a.created_by OR NOT ((v_line AND v_level >= 3)
           OR (app_has_permission('partners', 'create') AND app_scope('partners') = 'global')) THEN
        RAISE EXCEPTION 'not your decision' USING ERRCODE = 'DAPFB';
    END IF;""", """    -- FS-071 rule 8: a role in the type's decider setting, never whoever started it
    IF NOT coalesce((dealer_application_can(p_id) ->> 'decide')::boolean, false) THEN
        RAISE EXCEPTION 'not your decision' USING ERRCODE = 'DAPFB';
    END IF;""")
_d = _replace(_d, """    IF p_parent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = p_parent""",
              """    -- FS-071 rule 7: the deposit first, and a paid one by the slip its payment names
    v_status := dealer_application_deposit_status(p_id);
    IF v_status = 'pending' THEN
        RAISE EXCEPTION 'the deposit is pending' USING ERRCODE = 'DAPDP';
    END IF;
    IF v_status = 'paid' AND NOT EXISTS (
           SELECT 1 FROM (SELECT e.slip_id FROM dealer_application_deposit_entry e
                           WHERE e.application_id = p_id AND e.kind = 'payment'
                           ORDER BY e.created_at DESC, e.id DESC LIMIT 1) p
             JOIN record_document r ON r.id = p.slip_id AND r.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'the slip is gone' USING ERRCODE = 'DAPDS';
    END IF;
    -- FS-071 rule 9: a distributor sits under Polysil
    IF a.partner_type = 'distributor' AND p_parent IS NOT NULL THEN
        RAISE EXCEPTION 'a distributor has no parent' USING ERRCODE = 'DAPPX';
    END IF;
    IF p_parent IS NOT NULL AND NOT EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = p_parent""")
_d = _replace(_d, """    -- the code: DLR-<state>-0001, next over every code with the prefix (edge E-4)
    SELECT t.code::text INTO v_state FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = a.territory_id AND t.level = 'state' ORDER BY tc.depth LIMIT 1;
    v_code := NULLIF(btrim(p_code), '');
    PERFORM pg_advisory_xact_lock(9, hashtext('DLR-' || coalesce(v_state, 'GEN')));
    IF v_code IS NULL THEN
        SELECT coalesce(max(substring(code::text FROM '([0-9]+)$')::int), 0) + 1 INTO v_n
          FROM channel_partner WHERE code::text ~ ('^DLR-' || coalesce(v_state, 'GEN') || '-[0-9]+$');
        v_code := 'DLR-' || coalesce(v_state, 'GEN') || '-' || lpad(v_n::text, 4, '0');""",
              """    -- the code: DLR- or DIST-<state>-0001, next over every code with the prefix (edge E-4);
    -- at most 9 digits read, so a typed overlong code cannot overflow the count (FS-071 E-18)
    SELECT t.code::text INTO v_state FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = a.territory_id AND t.level = 'state' ORDER BY tc.depth LIMIT 1;
    v_prefix := CASE a.partner_type WHEN 'distributor' THEN 'DIST-' ELSE 'DLR-' END || coalesce(v_state, 'GEN');
    v_code := NULLIF(btrim(p_code), '');
    PERFORM pg_advisory_xact_lock(9, hashtext(v_prefix));
    IF v_code IS NULL THEN
        SELECT coalesce(max(substring(code::text FROM '([0-9]+)$')::int), 0) + 1 INTO v_n
          FROM channel_partner WHERE code::text ~ ('^' || v_prefix || '-[0-9]{1,9}$');
        -- lpad truncates: 10000 would print as 1000 (code review F-2)
        v_code := v_prefix || '-' || CASE WHEN v_n < 10000 THEN lpad(v_n::text, 4, '0') ELSE v_n::text END;""")
_d = _replace(_d, """    INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, contact_name, mobile, email,
        address, gstin, pan, is_gst_registered, price_tier, created_by)
    VALUES (p_parent, 'dealer', v_code, a.firm_name, a.territory_id, a.contact_name, a.mobile, a.email,
        a.address, a.gstin, a.pan, a.gst_registered AND a.gstin IS NOT NULL, 'dealer', v_me)
    RETURNING id INTO v_partner;
    SELECT id INTO v_role FROM role WHERE code = 'dealer' AND deleted_at IS NULL;""",
              """    BEGIN
        INSERT INTO channel_partner (parent_id, partner_type, code, name, territory_id, contact_name, mobile, email,
            address, gstin, pan, is_gst_registered, price_tier, created_by)
        VALUES (p_parent, a.partner_type::partner_type, v_code, a.firm_name, a.territory_id, a.contact_name, a.mobile,
            a.email, a.address, a.gstin, a.pan, a.gst_registered AND a.gstin IS NOT NULL,
            a.partner_type::channel_tier, v_me)
        RETURNING id INTO v_partner;
    EXCEPTION WHEN unique_violation THEN
        -- a code typed elsewhere, outside this prefix lock (FS-071 E-18)
        RAISE EXCEPTION 'code in use' USING ERRCODE = 'DAPCD';
    END;
    SELECT id INTO v_role FROM role WHERE code = a.partner_type AND deleted_at IS NULL;""")
_d = _replace(_d, """            jsonb_build_object('code', v_code, 'partner_type', 'dealer', 'parent_id', p_parent, 'application_id', p_id));""",
              """            jsonb_build_object('code', v_code, 'partner_type', a.partner_type, 'parent_id', p_parent, 'application_id', p_id));""")
DECIDE_078 = _d

# ── the applicant's view: the new fields, the deposit without its history, the place ──

VIEW_062 = _f062("dealer_apply_view")
_v = _or_replace(VIEW_062)
_v = _replace(_v, """        'bank_account_no', a.bank_account_no, 'bank_ifsc', a.bank_ifsc, 'gst_lookup', a.gst_lookup,""",
              """        'bank_account_no', a.bank_account_no, 'bank_ifsc', a.bank_ifsc, 'gst_lookup', a.gst_lookup,
        'partner_type', a.partner_type, 'telephone', a.telephone, 'established_on', a.established_on,
        'bank_name', a.bank_name, 'bank_branch', a.bank_branch, 'bank_address', a.bank_address,
        'working_capital', a.working_capital, 'other_sources_lakhs', a.other_sources_lakhs::text,
        'two_wheelers', a.two_wheelers, 'cars', a.cars, 'other_vehicles', a.other_vehicles,
        'office_area', a.office_area::text, 'godown_area', a.godown_area::text, 'area_unit', a.area_unit,
        'manpower', a.manpower, 'previous_installations', a.previous_installations,
        'sales_executives', a.sales_executives, 'technicians', a.technicians,
        'appointment_place', a.appointment_place,
        -- app_anon reads no territory, so the printed sheet's place comes from here (plan review R-4)
        'district', (SELECT t.name FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
                      WHERE tc.descendant_id = a.territory_id AND t.level = 'district' ORDER BY tc.depth LIMIT 1),
        'state', (SELECT t.name FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
                   WHERE tc.descendant_id = a.territory_id AND t.level = 'state' ORDER BY tc.depth LIMIT 1),
        'deposit', jsonb_build_object('amount_set', a.deposit_set::text, 'amount_due', a.deposit_due::text,
            'status', CASE
                WHEN p.amount IS NOT NULL AND p.amount >= a.deposit_due THEN 'paid'
                WHEN a.deposit_due = 0 AND EXISTS (SELECT 1 FROM dealer_application_deposit_entry e
                                                    WHERE e.application_id = a.id AND e.kind = 'relaxation') THEN 'waived'
                WHEN a.deposit_due > 0 THEN 'pending' ELSE 'not_required' END,
            'paid_amount', p.amount::text, 'paid_on', p.paid_on),""")
_v = _replace(_v, """DECLARE a dealer_application%ROWTYPE; v_session boolean;""",
              """DECLARE a dealer_application%ROWTYPE; v_session boolean; p record;""")
_v = _replace(_v, """    v_session := p_session_hash IS NOT NULL AND a.session_hash = p_session_hash AND a.session_expires_at > now();""",
              """    v_session := p_session_hash IS NOT NULL AND a.session_hash = p_session_hash AND a.session_expires_at > now();
    -- the status as dealer_application_deposit_status() has it; that one checks staff visibility
    SELECT e.amount, e.paid_on INTO p FROM dealer_application_deposit_entry e
     WHERE e.application_id = a.id AND e.kind = 'payment' ORDER BY e.created_at DESC, e.id DESC LIMIT 1;""")
VIEW_078 = _v

# ── documents: frozen once closed, the payment's slip kept, the application locked first ──

APPLY_REMOVE_062 = _f062("dealer_apply_document_remove")
APPLY_REMOVE_078 = """CREATE OR REPLACE FUNCTION dealer_apply_document_remove(p_token_hash text, p_session_hash text, p_doc uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_app uuid;
BEGIN
    v_app := dealer_apply_session(p_token_hash, p_session_hash);
    IF v_app IS NULL THEN RETURN 'no_session'; END IF;
    -- the application before the document, as the payment takes them (plan review B-1, R-1)
    PERFORM 1 FROM dealer_application WHERE id = v_app FOR UPDATE;
    -- a submit that committed while this waited ends the session (code review F-3)
    IF dealer_apply_session(p_token_hash, p_session_hash) IS NULL THEN RETURN 'no_session'; END IF;
    IF EXISTS (SELECT 1 FROM dealer_application_deposit_entry e WHERE e.application_id = v_app AND e.slip_id = p_doc) THEN
        RETURN 'in_use';
    END IF;
    UPDATE record_document SET deleted_at = now()
     WHERE id = p_doc AND record_type = 'dealer_application' AND record_id = v_app
       AND uploaded_by IS NULL AND deleted_at IS NULL;
    IF NOT FOUND THEN RETURN 'not_found'; END IF;
    PERFORM record_document_event(p_doc, 'document.removed');
    RETURN 'ok';
END $fn$"""

REMOVE_061 = _f061("record_document_remove")
_r = _or_replace(REMOVE_061)
_r = _replace(_r, """DECLARE d record_document%ROWTYPE; v_why text;
BEGIN
    SELECT * INTO d FROM record_document WHERE id = p_doc AND deleted_at IS NULL FOR UPDATE;""",
              """DECLARE d record_document%ROWTYPE; v_why text; v_type text; v_record uuid;
BEGIN
    -- FS-071: a dealer application's row before its document, the order the payment
    -- takes them, so the two never deadlock (plan review R-1)
    SELECT record_type, record_id INTO v_type, v_record FROM record_document WHERE id = p_doc AND deleted_at IS NULL;
    IF v_type = 'dealer_application' THEN
        PERFORM 1 FROM dealer_application WHERE id = v_record FOR UPDATE;
    END IF;
    SELECT * INTO d FROM record_document WHERE id = p_doc AND deleted_at IS NULL FOR UPDATE;""")
_r = _replace(_r, """    IF d.uploaded_by IS DISTINCT FROM app_current_user_id()""",
              """    IF d.record_type = 'dealer_application' THEN
        -- frozen once decided or withdrawn, even for the uploader (FS-071 E-2)
        IF v_why = 'DOCCL' THEN
            RAISE EXCEPTION 'the application is closed' USING ERRCODE = 'DOCCL';
        END IF;
        IF EXISTS (SELECT 1 FROM dealer_application_deposit_entry e WHERE e.slip_id = p_doc) THEN
            RAISE EXCEPTION 'a payment names this slip' USING ERRCODE = 'DOCIU';
        END IF;
    END IF;
    IF d.uploaded_by IS DISTINCT FROM app_current_user_id()""")
REMOVE_078 = _r

CREATE_062 = _f062("dealer_application_create")
WRITE_062 = _f062("dealer_application_write")
MISSING_062 = _f062("dealer_application_missing")

FUNCTIONS = [DEPOSIT_STATUS, CAN, WRITE_078, CREATE_078, MISSING_078, DEPOSIT_RECORD, RELAX,
             DECIDE_078, VIEW_078, APPLY_REMOVE_078, REMOVE_078]

OLD_CREATE = "dealer_application_create(text, text, text, uuid, uuid, text, timestamptz)"
NEW_CREATE = "dealer_application_create(text, text, text, uuid, uuid, text, timestamptz, text)"
GRANTED_STAFF = [NEW_CREATE, "dealer_application_deposit_status(uuid)", "dealer_application_can(uuid)",
                 "dealer_application_deposit_record(uuid, numeric, date, text, uuid)",
                 "dealer_application_relax(uuid, numeric, text)"]


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE dealer_application_deposit_entry ENABLE ROW LEVEL SECURITY")
    op.execute(floor.policy_sql("dealer_application_deposit_entry"))
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)

    op.execute(M077._kind_check(KINDS_078))
    op.execute(CHECK_AFTER)
    op.execute(SEED)

    # E-1: the 7-argument create goes, so no caller can make an application without a deposit
    op.execute(f"DROP FUNCTION {OLD_CREATE}")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED_STAFF:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    # E-24: refuse rather than lose a deposit, a distributor or a filled sheet
    filled = " OR ".join(f"{c} IS NOT NULL" for c in DATA_SHEET if c != "area_unit")
    op.execute(f"""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM dealer_application WHERE partner_type <> 'dealer' OR deposit_set <> 0 OR {filled})
           OR EXISTS (SELECT 1 FROM dealer_application_deposit_entry)
           OR EXISTS (SELECT 1 FROM record_document WHERE doc_type = 'deposit_slip') THEN
            RAISE EXCEPTION '078 downgrade: applications carry a distributor, a deposit or the data sheet; remove them first';
        END IF;
    END $$""")
    # the functions that read the settings go back before the settings do (plan review R-7)
    for sig in GRANTED_STAFF:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute(_or_replace(REMOVE_061))
    op.execute(_or_replace(APPLY_REMOVE_062))
    op.execute(_or_replace(VIEW_062))
    op.execute(_or_replace(DECIDE_062))
    op.execute(_or_replace(MISSING_062))
    op.execute(_or_replace(WRITE_062))
    op.execute(CREATE_062)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {OLD_CREATE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {OLD_CREATE} TO {APP_ROLE}")

    keys = ", ".join(f"'{k}'" for k in SETTING_KEYS)
    op.execute(f"DELETE FROM activity_event WHERE kind = 'setting.changed' AND payload ->> 'key' IN ({keys})")
    op.execute(f"DELETE FROM app_setting WHERE key IN ({keys})")
    op.execute(CHECK_BEFORE)
    op.execute(M077._kind_check(KINDS_077))

    op.execute("DELETE FROM activity_event WHERE entity_type = 'dealer_application' AND kind IN "
               "('dealer_application.type_changed', 'dealer_application.deposit_recorded', 'dealer_application.deposit_relaxed')")
    op.execute("DROP TABLE dealer_application_deposit_entry")
    op.execute("ALTER TABLE record_document DROP CONSTRAINT ck_record_document_doc_type")
    op.execute(f"ALTER TABLE record_document ADD CONSTRAINT ck_record_document_doc_type CHECK (doc_type IN {DOC_TYPES_062})")
    op.execute("DROP INDEX IF EXISTS ix_dealer_application_partner_type")
    drops = (["ck_dealer_application_partner_type", "ck_dealer_application_established", "ck_dealer_application_area_unit",
              "ck_dealer_application_deposit"]
             + [f"ck_dealer_application_{c}" for c in [*_TEXTS, *_INTS, *_DECIMALS, *_LISTS]])
    op.execute("ALTER TABLE dealer_application " + ", ".join(f"DROP CONSTRAINT IF EXISTS {c}" for c in drops))
    op.execute("ALTER TABLE dealer_application " + ", ".join(
        f"DROP COLUMN IF EXISTS {c}" for c in ["partner_type", *DATA_SHEET, "deposit_set", "deposit_due"]))
