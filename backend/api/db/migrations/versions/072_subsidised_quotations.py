"""072: subsidised quotations (FS-057).

- `quotation_subsidy`: one calculator answer for one category on a subsidised
  quotation. Read through the parent quotation; written by the definers only.
- `quotation_subsidy_set()`: the quotation locked, draft and subsidised only.
- `quotation_subsidy_copy()`: a revision carries its source's block (the app
  role cannot write the table).
- The worker's render claim and the public link view gain a `subsidy` key, by
  live text.

Revision ID: 072_subsidised_quotations
Revises: 071_state_subsidy_formulas
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "072_subsidised_quotations"
down_revision: str | None = "071_state_subsidy_formulas"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_072", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

TABLES = [
    """CREATE TABLE quotation_subsidy (
    quotation_id uuid PRIMARY KEY REFERENCES quotation(id) ON DELETE CASCADE,
    scheme_code text NOT NULL,
    system_type text NOT NULL,
    category_code text NOT NULL,
    category_name text NOT NULL,
    category_pct numeric(6,2) NOT NULL,
    calculation_request jsonb NOT NULL,
    calculation jsonb NOT NULL,
    total_cost numeric(14,2) NOT NULL CHECK (total_cost >= 0),
    flat_charge numeric(14,2) NOT NULL DEFAULT 0 CHECK (flat_charge >= 0),
    subsidy numeric(14,2) NOT NULL CHECK (subsidy >= 0),
    farmer_share numeric(14,2) NOT NULL CHECK (farmer_share >= 0),
    formula_version text NOT NULL,
    as_of date NOT NULL,
    updated_by uuid NOT NULL REFERENCES app_user(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_quotation_subsidy_within CHECK (subsidy <= total_cost + flat_charge)
)""",
]

GRANTS: dict[str, str] = {"quotation_subsidy": "SELECT"}

_Q_VIEW = "(SELECT app_has_permission('quotations', 'view'))"
_PARENT = "EXISTS (SELECT 1 FROM quotation q WHERE q.id = quotation_id)"

HAND_POLICIES: list[tuple[str, str]] = [
    ("quotation_subsidy", f"CREATE POLICY quotation_subsidy_sel ON quotation_subsidy FOR SELECT USING (\n  {_PARENT}\n)"),
    ("quotation_subsidy", f"CREATE POLICY quotation_subsidy_res_perm ON quotation_subsidy AS RESTRICTIVE FOR SELECT USING (\n  {_Q_VIEW}\n)"),
]

FUNCTIONS = [
    """CREATE FUNCTION quotation_subsidy_set(p_quotation uuid, p_scheme text, p_system text,
        p_code text, p_name text, p_pct numeric, p_request jsonb, p_calc jsonb, p_total numeric,
        p_flat numeric, p_subsidy numeric, p_share numeric, p_version text, p_as_of date)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE q quotation%ROWTYPE; v_me uuid := app_current_user_id();
BEGIN
    IF NOT app_has_permission('quotations', 'edit') OR app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'quotations.edit required' USING ERRCODE = '42501';
    END IF;
    IF NOT quotation_visible(p_quotation) THEN
        RAISE EXCEPTION 'quotation not found' USING ERRCODE = 'QSBNF';
    END IF;
    SELECT * INTO q FROM quotation WHERE id = p_quotation FOR UPDATE;
    IF q.status <> 'draft' THEN
        RAISE EXCEPTION 'the quotation is %', q.status USING ERRCODE = 'QSBND';
    END IF;
    IF q.sales_type::text <> 'subsidised' THEN
        RAISE EXCEPTION 'not a subsidised quotation' USING ERRCODE = 'QSBTY';
    END IF;
    INSERT INTO quotation_subsidy (quotation_id, scheme_code, system_type, category_code, category_name,
        category_pct, calculation_request, calculation, total_cost, flat_charge, subsidy, farmer_share,
        formula_version, as_of, updated_by, updated_at)
    VALUES (p_quotation, p_scheme, p_system, p_code, p_name, p_pct, p_request, p_calc, p_total, p_flat,
            p_subsidy, p_share, p_version, p_as_of, v_me, now())
    ON CONFLICT (quotation_id) DO UPDATE SET scheme_code = EXCLUDED.scheme_code,
        system_type = EXCLUDED.system_type, category_code = EXCLUDED.category_code,
        category_name = EXCLUDED.category_name, category_pct = EXCLUDED.category_pct,
        calculation_request = EXCLUDED.calculation_request, calculation = EXCLUDED.calculation,
        total_cost = EXCLUDED.total_cost, flat_charge = EXCLUDED.flat_charge, subsidy = EXCLUDED.subsidy,
        farmer_share = EXCLUDED.farmer_share, formula_version = EXCLUDED.formula_version,
        as_of = EXCLUDED.as_of, updated_by = v_me, updated_at = now();
    -- no money in the event: a dealer can read the lead's timeline (rule 17 of FS-054)
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('quotation', p_quotation, q.lead_id, 'quotation.subsidy_set', v_me,
            jsonb_build_object('scheme', p_scheme, 'system_type', p_system, 'category', p_code,
                               'actor_name', COALESCE((SELECT full_name FROM app_user WHERE id = v_me), '')));
END $fn$""",
    """CREATE FUNCTION quotation_subsidy_copy(p_from uuid, p_to uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id();
BEGIN
    IF NOT app_has_permission('quotations', 'edit') OR app_current_partner() IS NOT NULL THEN
        RAISE EXCEPTION 'quotations.edit required' USING ERRCODE = '42501';
    END IF;
    -- the revision is the source's next version on the same quote number
    IF NOT EXISTS (SELECT 1 FROM quotation t JOIN quotation f ON f.id = p_from
                    WHERE t.id = p_to AND t.supersedes_id = f.id AND t.status = 'draft'
                      AND quotation_visible(p_from)) THEN
        RAISE EXCEPTION 'not a revision of that quotation' USING ERRCODE = 'QSBNF';
    END IF;
    INSERT INTO quotation_subsidy (quotation_id, scheme_code, system_type, category_code, category_name,
        category_pct, calculation_request, calculation, total_cost, flat_charge, subsidy, farmer_share,
        formula_version, as_of, updated_by, updated_at)
    SELECT p_to, scheme_code, system_type, category_code, category_name, category_pct, calculation_request,
           calculation, total_cost, flat_charge, subsidy, farmer_share, formula_version, as_of, v_me, now()
      FROM quotation_subsidy WHERE quotation_id = p_from
    ON CONFLICT (quotation_id) DO NOTHING;
    RETURN FOUND;
END $fn$""",
]
GRANTED = ["quotation_subsidy_set(uuid, text, text, text, text, numeric, jsonb, jsonb, numeric, numeric, numeric, numeric, text, date)",
           "quotation_subsidy_copy(uuid, uuid)"]

# the worker's document and the farmer's link, by live text
CLAIM_SIG = "quotation_render_claim"
CLAIM_OLD = "'quotation', to_jsonb(q) - ARRAY['pdf_lease_token'],"
CLAIM_NEW = (CLAIM_OLD + "\n        'subsidy', (SELECT to_jsonb(s) - ARRAY['calculation', 'calculation_request', 'updated_by'] "
             "FROM quotation_subsidy s WHERE s.quotation_id = q.id),")
VIEW_SIG = "quotation_public_view(text)"
VIEW_OLD = "'sales_type', q.sales_type,"
VIEW_NEW = (VIEW_OLD + "\n        'subsidy', (SELECT jsonb_build_object('scheme', s.scheme_code, 'category', s.category_name, "
            "'total_cost', s.total_cost + s.flat_charge, 'subsidy', s.subsidy, 'farmer_share', s.farmer_share) "
            "FROM quotation_subsidy s WHERE s.quotation_id = q.id),")


def _swap(sig: str, old: str, new: str) -> None:
    reg = f"'{sig}'::regproc" if "(" not in sig else f"'{sig}'::regprocedure"
    body = str(op.get_bind().execute(text(f"SELECT pg_get_functiondef({reg})")).scalar_one())
    if body.count(old) != 1:
        raise RuntimeError(f"072: {sig} anchor found {body.count(old)} times")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for table in GRANTS:
        op.execute(floor.policy_sql(table))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    _swap(CLAIM_SIG, CLAIM_OLD, CLAIM_NEW)
    _swap(VIEW_SIG, VIEW_OLD, VIEW_NEW)


def downgrade() -> None:
    _swap(VIEW_SIG, VIEW_NEW, VIEW_OLD)
    _swap(CLAIM_SIG, CLAIM_NEW, CLAIM_OLD)
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE kind = 'quotation.subsidy_set'")
    op.execute("DROP TABLE IF EXISTS quotation_subsidy")
