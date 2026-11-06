"""017: discount approval on quotations (FS-013).

A quotation whose effective discount is above its owner's limit cannot be sent
until one manager with a high enough limit approves it. The quotation's status
does not change (RBAC.md 5.2d): the gate is on send.

- `approval_request.lines_hash`: the figures the request was opened on. The
  decision refuses `figures_changed` when they moved, and the send gate accepts an
  approval only while they still match. It lives on the request, which `app_role`
  cannot write, so no column grant on `quotation` is needed (EC-8).
- `approval_threshold.unit`: `pct` for quotation rows, `inr` otherwise, generated
  from `doc_type` so the two cannot disagree (plan review R-1).
- The engine's quotation arms, patched into the live text of 013's functions (and
  016's, for the two it already patched): the chain is one step, the refusal and
  the stall read the quotation, the decision locks the lead, then the quotation,
  then the request and the step, and the outcome changes no status.
- Definers for the service: `quotation_discount_limit`, `quotation_send_gate`,
  `quotation_request_approval`, `quotation_approval_cancel`.
- Stand-in quotation limits, inserted where the roles exist (staging); the demo
  seed inserts them on a fresh database (ISS-098). Question 6.8, GAP-105.

Revision ID: 017_quotation_discount_approval
Revises: 016_order_messages
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "017_quotation_discount_approval"
down_revision: str | None = "016_order_messages"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# the ladder a quotation climbs, lowest first (FS-013 rule 3)
LADDER = ("district_manager", "state_manager", "regional_manager", "admin_sales")

# stand-ins (question 6.8); a null limit is no limit
STAND_IN_LIMITS = {"field_officer": "5", "district_manager": "10", "state_manager": "15",
                   "regional_manager": "20", "admin_sales": None}

TABLES = [
    "ALTER TABLE approval_request ADD COLUMN lines_hash text",
    # why the discount is asked for: staff read it from the request, never from an
    # event a dealer's timeline carries (cross-vendor review P1)
    "ALTER TABLE approval_request ADD COLUMN remark text CHECK (remark IS NULL OR length(remark) <= 1000)",
    """ALTER TABLE approval_threshold
    ADD COLUMN unit text GENERATED ALWAYS AS (CASE WHEN doc_type = 'quotation' THEN 'pct' ELSE 'inr' END) STORED,
    ADD CONSTRAINT ck_approval_threshold_pct CHECK (doc_type <> 'quotation' OR max_amount IS NULL OR max_amount <= 100)""",
    # a discount limit of 0 means no discount without approval (code review)
    "ALTER TABLE approval_threshold DROP CONSTRAINT ck_approval_threshold_amount",
    """ALTER TABLE approval_threshold ADD CONSTRAINT ck_approval_threshold_amount
    CHECK (max_amount IS NULL OR max_amount > 0 OR (doc_type = 'quotation' AND max_amount = 0))""",
]

HAND_POLICIES: list[tuple[str, str]] = [
    # a quotation's request is read by whoever sees the quotation
    ("approval_request", """CREATE POLICY approval_request_sel ON approval_request FOR SELECT USING (
  CASE doc_type
    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order d WHERE d.id = entity_id)
    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation d WHERE d.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""),
]

FUNCTIONS = [
    # The figures an approval covers (FS-013 5, EC-10): each line's priced inputs
    # and taxable value in line order, and the header's money. Terms, validity and
    # the party's text are outside it.
    """CREATE FUNCTION quotation_lines_hash(p_id uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT md5(
        COALESCE((SELECT string_agg(concat_ws('|', l.product_id, l.qty, l.rate, l.discount_pct,
                                              l.discount2_pct, l.discount3_pct, l.gst_rate_id, l.taxable),
                                    ';' ORDER BY l.line_no)
                    FROM quotation_line l WHERE l.quotation_id = p_id), '')
        || '#' ||
        COALESCE((SELECT concat_ws('|', q.partner_id, q.price_effective_date, q.gross, q.discount,
                                   q.taxable, q.total)
                    FROM quotation q WHERE q.id = p_id), ''))
$fn$""",
    # Rule 2a: discount / gross in percent, two places, half up; 0 on a zero gross.
    """CREATE FUNCTION quotation_effective_pct(p_gross numeric, p_discount numeric) RETURNS numeric
LANGUAGE sql IMMUTABLE SET search_path = public, pg_temp AS $fn$
    SELECT CASE WHEN COALESCE(p_gross, 0) = 0 THEN 0::numeric
                ELSE round(COALESCE(p_discount, 0) * 100 / p_gross, 2) END
$fn$""",
    # Rule 2: the owner's limit. The owner's role's row, nearest up the territory
    # tree, else the company-wide row. No row: 0 for any role but Admin-Sales and
    # the MD, who have no limit. No owner: 0. Returns null for no limit.
    """CREATE FUNCTION quotation_owner_limit(p_id uuid) RETURNS numeric
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_role uuid; v_code text; v_territory uuid; v_found boolean := false; v_limit numeric;
BEGIN
    SELECT u.role_id, r.code::text, q.territory_id INTO v_role, v_code, v_territory
      FROM quotation q
      LEFT JOIN app_user u ON u.id = q.owner_user_id
      LEFT JOIN role r ON r.id = u.role_id
     WHERE q.id = p_id;
    IF v_role IS NULL THEN
        RETURN 0;
    END IF;
    SELECT true, t.max_amount INTO v_found, v_limit
      FROM approval_threshold t
      LEFT JOIN territory_closure tc ON tc.ancestor_id = t.territory_id AND tc.descendant_id = v_territory
     WHERE t.doc_type = 'quotation' AND t.role_id = v_role AND t.deleted_at IS NULL
       AND (t.territory_id IS NULL OR tc.descendant_id IS NOT NULL)
     ORDER BY (t.territory_id IS NULL), tc.depth ASC
     LIMIT 1;
    IF COALESCE(v_found, false) THEN
        RETURN v_limit;
    END IF;
    RETURN CASE WHEN v_code IN ('admin_sales', 'md_ceo') THEN NULL ELSE 0 END;
END $fn$""",
    # EC-7: officers cannot read the threshold rows, so the detail asks this.
    """CREATE FUNCTION quotation_discount_limit(p_id uuid)
RETURNS TABLE (owner_limit_pct numeric, effective_pct numeric, approval_required boolean)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE q quotation%ROWTYPE; v_limit numeric;
BEGIN
    IF NOT quotation_visible(p_id) THEN
        RAISE EXCEPTION 'quotation not found' USING ERRCODE = 'QTNF0';
    END IF;
    SELECT * INTO q FROM quotation WHERE id = p_id;
    v_limit := quotation_owner_limit(p_id);
    RETURN QUERY SELECT v_limit, quotation_effective_pct(q.gross, q.discount),
        -- exact, no rounding (rule 2a)
        v_limit IS NOT NULL AND COALESCE(q.discount, 0) * 100 > v_limit * COALESCE(q.gross, 0);
END $fn$""",
    # Plan review B-3: what send may do. none_needed | required | pending |
    # approved | void (approved, then the figures moved) | returned.
    """CREATE FUNCTION quotation_send_gate(p_id uuid) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_required boolean; v_req approval_request%ROWTYPE;
BEGIN
    SELECT approval_required INTO v_required FROM quotation_discount_limit(p_id);
    IF NOT v_required THEN
        RETURN 'none_needed';
    END IF;
    SELECT * INTO v_req FROM approval_request
     WHERE doc_type = 'quotation' AND entity_id = p_id
     ORDER BY created_at DESC, id DESC LIMIT 1;
    IF NOT FOUND OR v_req.status = 'cancelled' THEN
        RETURN 'required';
    END IF;
    IF v_req.status = 'pending' THEN
        RETURN 'pending';
    END IF;
    IF v_req.status = 'rejected' THEN
        RETURN 'returned';
    END IF;
    RETURN CASE WHEN v_req.lines_hash = quotation_lines_hash(p_id) THEN 'approved' ELSE 'void' END;
END $fn$""",
    # FS-013 5: the only way a quotation request opens. The lead first, then the
    # quotation: the lock order send and revise take (FS-005).
    """CREATE FUNCTION quotation_request_approval(p_id uuid, p_remark text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE
    q quotation%ROWTYPE; v_limit numeric; v_pct numeric; v_required boolean;
    v_chain uuid[]; v_request uuid;
BEGIN
    IF NOT app_has_permission('quotations', 'edit') OR NOT quotation_visible(p_id) THEN
        RAISE EXCEPTION 'not permitted on this quotation' USING ERRCODE = '42501';
    END IF;
    PERFORM 1 FROM lead WHERE id = (SELECT lead_id FROM quotation WHERE id = p_id) FOR UPDATE;
    SELECT * INTO q FROM quotation WHERE id = p_id AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'quotation not found' USING ERRCODE = 'QTNF0';
    END IF;
    IF q.status <> 'draft' THEN
        RAISE EXCEPTION 'the quotation is %', q.status USING ERRCODE = 'QTNDR';
    END IF;
    SELECT owner_limit_pct, effective_pct, approval_required INTO v_limit, v_pct, v_required
      FROM quotation_discount_limit(p_id);
    IF NOT v_required THEN
        RAISE EXCEPTION 'approval_not_required' USING ERRCODE = 'APRNR';
    END IF;
    IF EXISTS (SELECT 1 FROM approval_request WHERE doc_type = 'quotation' AND entity_id = p_id
                                                  AND status = 'pending') THEN
        RAISE EXCEPTION 'this quotation already has an open approval' USING ERRCODE = 'APRPD';
    END IF;
    -- the exact ratio, not the rounded display figure: 20.004 % is not covered by
    -- a 20 % limit (OCR review of FS-013, rule 2a)
    v_chain := approval_chain('quotation', q.discount * 100 / NULLIF(q.gross, 0), q.territory_id,
                              approval_owner_level(q.owner_user_id));
    IF COALESCE(array_length(v_chain, 1), 0) = 0 THEN
        RAISE EXCEPTION 'no_approver' USING ERRCODE = 'APRNA';
    END IF;
    INSERT INTO approval_request (doc_type, entity_id, requested_by, amount, territory_id, lines_hash,
                                  remark)
    VALUES ('quotation', p_id, app_current_user_id(), v_pct, q.territory_id, quotation_lines_hash(p_id),
            NULLIF(btrim(COALESCE(p_remark, '')), ''))
    RETURNING id INTO v_request;
    INSERT INTO approval_step (request_id, seq, approver_role_id) VALUES (v_request, 1, v_chain[1]);
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('quotation', p_id, q.lead_id, 'quotation.approval_requested', app_current_user_id(),
            jsonb_build_object('effective_pct', v_pct, 'request_id', v_request));
    RETURN v_request;
END $fn$""",
    # Plan review B-2: an edit or a delete cancels the pending request, so an
    # approval is never for other figures (EC-1, rule 5a).
    """CREATE FUNCTION quotation_approval_cancel(p_id uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_lead uuid; v_n int;
BEGIN
    IF NOT app_has_permission('quotations', 'edit') OR NOT quotation_visible(p_id) THEN
        RAISE EXCEPTION 'not permitted on this quotation' USING ERRCODE = '42501';
    END IF;
    UPDATE approval_request SET status = 'cancelled', decided_at = now()
     WHERE doc_type = 'quotation' AND entity_id = p_id AND status = 'pending';
    GET DIAGNOSTICS v_n = ROW_COUNT;
    IF v_n = 0 THEN
        RETURN false;
    END IF;
    SELECT lead_id INTO v_lead FROM quotation WHERE id = p_id;
    INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
    VALUES ('quotation', p_id, v_lead, 'quotation.approval_cancelled', app_current_user_id(), '{}');
    RETURN true;
END $fn$""",
]

# 014's people_names(), extended: a quotation's approvers and its requesters are
# named for staff who see the quotation, as an order's approvers already are; a
# partner still learns none of them (question 15.14, cross-vendor review P2)
_PEOPLE_OLD = """         OR ((SELECT app_current_partner()) IS NULL
             AND (EXISTS (SELECT 1 FROM approval_step s JOIN approval_request r ON r.id = s.request_id
                           WHERE s.approver_user_id = u.id AND r.doc_type = 'sales_order'
                             AND order_visible(r.entity_id))"""
_PEOPLE_NEW = """         OR ((SELECT app_current_partner()) IS NULL
             AND (EXISTS (SELECT 1 FROM approval_step s JOIN approval_request r ON r.id = s.request_id
                           WHERE s.approver_user_id = u.id AND r.doc_type = 'sales_order'
                             AND order_visible(r.entity_id))
               OR EXISTS (SELECT 1 FROM approval_request r
                           LEFT JOIN approval_step s ON s.request_id = r.id
                           WHERE r.doc_type = 'quotation'
                             AND (s.approver_user_id = u.id OR r.requested_by = u.id)
                             AND quotation_visible(r.entity_id))"""


def _people_names(extended: bool) -> str:
    body = next(f for f in _load("014_document_people").FUNCTIONS
                if f.lstrip().startswith("CREATE FUNCTION people_names("))
    if extended:
        body = _replace(body, _PEOPLE_OLD, _PEOPLE_NEW)
    return body.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


INTERNAL = ["quotation_lines_hash(uuid)", "quotation_owner_limit(uuid)"]
GRANTED = ["quotation_discount_limit(uuid)", "quotation_send_gate(uuid)",
           "quotation_request_approval(uuid, text)", "quotation_approval_cancel(uuid)",
           "quotation_effective_pct(numeric, numeric)"]


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_017", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"017: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    # an exception, not an assert: python -O drops asserts (FS-012 code review F-8)
    if text.count(old) != 1:
        raise RuntimeError(f"017: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _live() -> dict[str, str]:
    """The text of each engine function as it stands after 016: 016's for the two
    it patched, 013's for the rest. Each as CREATE OR REPLACE."""
    m016 = _load("016_order_messages")
    out: dict[str, str] = {}
    for name in ("approval_chain", "approval_step_stalled", "approval_refusal",
                 "apply_approval_outcome", "record_decision"):
        out[name] = m016._original(name).replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    create, advance, _refuse = m016._patched()
    out["create_approval_request"] = create
    out["advance_approval"] = advance
    return out


def _patched() -> list[str]:
    f = _live()
    ladder = ", ".join(f"'{c}'" for c in LADDER)
    f["approval_chain"] = _replace(f["approval_chain"], "BEGIN\n    FOR r IN SELECT id, level FROM role\n", f"""BEGIN
    -- FS-013 rule 3: one step, the lowest ladder role above the owner whose limit
    -- covers the discount; no Accounts or Dispatch step
    IF p_doc_type = 'quotation' THEN
        FOR r IN SELECT id, level, code::text AS code_text FROM role
                  WHERE code IN ({ladder}) AND deleted_at IS NULL AND NOT is_functional AND NOT is_portal
                  ORDER BY level LOOP
            CONTINUE WHEN r.level <= p_owner_level;
            v_found := false;
            SELECT true, t.max_amount INTO v_found, v_ceiling
              FROM approval_threshold t
              LEFT JOIN territory_closure tc
                ON tc.ancestor_id = t.territory_id AND tc.descendant_id = p_territory_id
             WHERE t.doc_type = 'quotation' AND t.role_id = r.id AND t.deleted_at IS NULL
               AND (t.territory_id IS NULL OR tc.descendant_id IS NOT NULL)
             ORDER BY (t.territory_id IS NULL), tc.depth ASC
             LIMIT 1;
            IF NOT COALESCE(v_found, false) AND r.code_text = 'admin_sales' THEN
                -- the top of the ladder, uncapped without a row (EC-3)
                RETURN ARRAY[r.id];
            END IF;
            IF COALESCE(v_found, false) AND (v_ceiling IS NULL OR p_amount <= v_ceiling) THEN
                RETURN ARRAY[r.id];
            END IF;
        END LOOP;
        RETURN '{{}}';
    END IF;
    FOR r IN SELECT id, level FROM role
""")
    f["approval_step_stalled"] = _replace(
        f["approval_step_stalled"],
        "    SELECT owner_org_unit_id, owner_user_id, created_by INTO v_org, v_owner, v_creator\n      FROM sales_order WHERE id = v_req.entity_id;\n",
        """    IF v_req.doc_type = 'quotation' THEN
        SELECT owner_org_unit_id, owner_user_id, created_by INTO v_org, v_owner, v_creator
          FROM quotation WHERE id = v_req.entity_id;
    ELSE
        SELECT owner_org_unit_id, owner_user_id, created_by INTO v_org, v_owner, v_creator
          FROM sales_order WHERE id = v_req.entity_id;
    END IF;
""")
    f["approval_refusal"] = _replace(
        f["approval_refusal"],
        """    IF v_req.doc_type <> 'sales_order' THEN
        RETURN 'not_your_step';
    END IF;
    SELECT owner_user_id, created_by INTO v_owner, v_creator FROM sales_order WHERE id = v_req.entity_id;
    IF v_me = v_req.requested_by OR v_me IS NOT DISTINCT FROM v_owner OR v_me IS NOT DISTINCT FROM v_creator THEN
        RETURN 'self_approval';
    END IF;
    IF NOT order_visible(v_req.entity_id) OR NOT app_has_permission('sales_orders', 'approve') THEN
        RETURN 'not_your_step';
    END IF;
""",
        """    IF v_req.doc_type = 'quotation' THEN
        SELECT owner_user_id, created_by INTO v_owner, v_creator FROM quotation WHERE id = v_req.entity_id;
    ELSIF v_req.doc_type = 'sales_order' THEN
        SELECT owner_user_id, created_by INTO v_owner, v_creator FROM sales_order WHERE id = v_req.entity_id;
    ELSE
        RETURN 'not_your_step';
    END IF;
    IF v_me = v_req.requested_by OR v_me IS NOT DISTINCT FROM v_owner OR v_me IS NOT DISTINCT FROM v_creator THEN
        RETURN 'self_approval';
    END IF;
    IF v_req.doc_type = 'quotation' THEN
        IF NOT quotation_visible(v_req.entity_id) OR NOT app_has_permission('quotations', 'approve') THEN
            RETURN 'not_your_step';
        END IF;
    ELSIF NOT order_visible(v_req.entity_id) OR NOT app_has_permission('sales_orders', 'approve') THEN
        RETURN 'not_your_step';
    END IF;
""")
    f["create_approval_request"] = _replace(
        f["create_approval_request"],
        """    IF p_doc_type <> 'sales_order' THEN
        RAISE EXCEPTION 'approval for % is not built yet', p_doc_type USING ERRCODE = '0A000';
    END IF;
""",
        """    IF p_doc_type = 'quotation' THEN
        RETURN quotation_request_approval(p_entity_id, NULL);
    END IF;
    IF p_doc_type <> 'sales_order' THEN
        RAISE EXCEPTION 'approval for % is not built yet', p_doc_type USING ERRCODE = '0A000';
    END IF;
""")
    # the quotation's figures are held by the request's hash; no status moves
    f["apply_approval_outcome"] = _replace(
        f["apply_approval_outcome"],
        "BEGIN\n    IF p_doc_type <> 'sales_order' THEN",
        "BEGIN\n    IF p_doc_type = 'quotation' THEN\n        RETURN;\n    END IF;\n    IF p_doc_type <> 'sales_order' THEN")
    f["advance_approval"] = _replace(
        f["advance_approval"],
        "    SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_req.entity_id;\n",
        """    IF v_req.doc_type = 'quotation' THEN
        SELECT lead_id INTO v_lead FROM quotation WHERE id = v_req.entity_id;
        IF v_rejected > 0 THEN
            UPDATE approval_request SET status = 'rejected', decided_at = now() WHERE id = p_request_id;
            INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
            VALUES ('quotation', v_req.entity_id, v_lead, 'quotation.approval_returned', app_current_user_id(),
                    jsonb_build_object('effective_pct', v_req.amount));
            RETURN 'rejected';
        END IF;
        IF v_approved < v_total THEN
            RETURN 'pending';
        END IF;
        UPDATE approval_request SET status = 'approved', decided_at = now() WHERE id = p_request_id;
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('quotation', v_req.entity_id, v_lead, 'quotation.approval_approved', app_current_user_id(),
                jsonb_build_object('effective_pct', v_req.amount));
        RETURN 'approved';
    END IF;
    SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_req.entity_id;
""")
    rd = f["record_decision"]
    # the lead first, then the quotation (plan review B-1: locked directly, since a
    # Regional Manager holds no leads.edit for lead_lock_for_quotation())
    rd = _replace(rd, """    IF v_doc_type = 'sales_order' THEN
        SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_entity FOR UPDATE;
    END IF;
""", """    IF v_doc_type = 'sales_order' THEN
        SELECT lead_id INTO v_lead FROM sales_order WHERE id = v_entity FOR UPDATE;
    ELSIF v_doc_type = 'quotation' THEN
        SELECT lead_id INTO v_lead FROM quotation WHERE id = v_entity;
        PERFORM 1 FROM lead WHERE id = v_lead FOR UPDATE;
        PERFORM 1 FROM quotation WHERE id = v_entity FOR UPDATE;
    END IF;
""")
    # EC-1: an approval is for the figures the request was opened on
    rd = _replace(rd, """    IF v_req.status <> 'pending' THEN
        RAISE EXCEPTION 'request_closed' USING ERRCODE = 'APRCL';
    END IF;
""", """    IF v_req.status <> 'pending' THEN
        RAISE EXCEPTION 'request_closed' USING ERRCODE = 'APRCL';
    END IF;
    IF v_doc_type = 'quotation' AND NOT EXISTS (SELECT 1 FROM quotation WHERE id = v_entity
                                                   AND status = 'draft' AND deleted_at IS NULL) THEN
        RAISE EXCEPTION 'request_closed' USING ERRCODE = 'APRCL';
    END IF;
    IF v_doc_type = 'quotation' AND quotation_lines_hash(v_entity) IS DISTINCT FROM v_req.lines_hash THEN
        RAISE EXCEPTION 'figures_changed' USING ERRCODE = 'APRFC';
    END IF;
""")
    rd = _replace(rd, "    VALUES ('sales_order', v_entity, v_lead, 'approval.decided', v_actor,",
                  "    VALUES (CASE WHEN v_doc_type = 'quotation' THEN 'quotation' ELSE 'sales_order' END,\n            v_entity, v_lead, 'approval.decided', v_actor,")
    f["record_decision"] = rd
    return list(f.values())


def _limits_sql() -> str:
    rows = ", ".join(f"('{code}', {('NULL' if v is None else v)})" for code, v in STAND_IN_LIMITS.items())
    return f"""INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount)
SELECT 'quotation', r.id, NULL, v.max_amount
  FROM (VALUES {rows}) AS v(code, max_amount)
  JOIN role r ON r.code = v.code
ON CONFLICT (doc_type, role_id, territory_id) DO NOTHING"""


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in INTERNAL + GRANTED:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    for stmt in _patched():
        op.execute(stmt)
    op.execute("DROP POLICY approval_request_sel ON approval_request")
    op.execute(HAND_POLICIES[0][1])
    op.execute(_people_names(extended=True))
    # where the roles exist (staging); the seed covers a fresh database (ISS-098)
    op.execute(_limits_sql())


def downgrade() -> None:
    for stmt in _live().values():
        op.execute(stmt)
    op.execute(_people_names(extended=False))
    op.execute("DROP POLICY approval_request_sel ON approval_request")
    op.execute(next(s for t, s in _load("013_orders_approvals_dispatch").HAND_POLICIES
                    if t == "approval_request"))
    op.execute("DELETE FROM approval_step WHERE request_id IN (SELECT id FROM approval_request WHERE doc_type = 'quotation')")
    op.execute("DELETE FROM approval_request WHERE doc_type = 'quotation'")
    op.execute("DELETE FROM approval_threshold WHERE doc_type = 'quotation'")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("ALTER TABLE approval_threshold DROP CONSTRAINT IF EXISTS ck_approval_threshold_pct")
    op.execute("ALTER TABLE approval_threshold DROP CONSTRAINT ck_approval_threshold_amount")
    op.execute("ALTER TABLE approval_threshold ADD CONSTRAINT ck_approval_threshold_amount "
               "CHECK (max_amount IS NULL OR max_amount > 0)")
    op.execute("ALTER TABLE approval_threshold DROP COLUMN IF EXISTS unit")
    op.execute("ALTER TABLE approval_request DROP COLUMN IF EXISTS lines_hash")
    op.execute("ALTER TABLE approval_request DROP COLUMN IF EXISTS remark")
