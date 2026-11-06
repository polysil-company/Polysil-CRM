"""057: farmers rate from the portal (FS-060).

- `rating.entered_via`: staff, portal or dealer. Stored, because staff below a
  global users scope cannot read a consumer's app_user row (plan review B-1).
  Backfilled from `rated_by`: no consumer rating exists before this migration.
- `rating_record()`: a consumer arm, built from 051's text by anchored replacements.
  It branches before the visibility and permission checks, which no consumer passes,
  and admits only documents `portal_rating_docs()` returns. Installation and service
  only. The event payload of a portal rating carries `via` and the farmer's name.
- `portal_rating_docs()`: the orders and complaints the portal lists for the
  signed-in farmer, by the predicates of 052's `portal_orders()` and
  `portal_complaints()`. Internal: no grant.
- `portal_rate()`: the portal's write. The number to an id among his documents,
  then `rating_record()`.
- `portal_ratings()`: the customer ratings on his documents; his own comments only.

Revision ID: 057_portal_ratings
Revises: 072_subsidised_quotations
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "057_portal_ratings"
down_revision: str | None = "072_subsidised_quotations"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_057", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"057: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rating_record_051() -> str:
    m051 = _load("051")
    return str(next(f for f in m051.FUNCTIONS if "FUNCTION rating_record(" in f))  # type: ignore[attr-defined]


# (old, new): each `old` occurs exactly once, or as often as `count` says
_SWAPS: list[tuple[str, str, int]] = [
    ("    v_lead uuid; v_doc_partner uuid; v_comment text; v_id uuid; v_status text;\n",
     "    v_lead uuid; v_doc_partner uuid; v_comment text; v_id uuid; v_status text;\n"
     "    v_via text; v_customer uuid;\n", 1),
    ("    IF v_type = 'staff' THEN\n"
     "        v_by := 'customer';\n"
     "    ELSIF v_type = 'partner_user' AND v_partner IS NOT NULL THEN\n"
     "        v_by := 'dealer';\n",
     "    IF v_type = 'staff' THEN\n"
     "        v_by := 'customer'; v_via := 'staff';\n"
     "    ELSIF v_type = 'consumer' THEN\n"
     "        -- FS-060: the farmer himself, only while the portal is on\n"
     "        v_customer := portal_customer();\n"
     "        IF v_customer IS NULL THEN\n"
     "            RAISE EXCEPTION 'portal off' USING ERRCODE = '42501';\n"
     "        END IF;\n"
     "        v_by := 'customer'; v_via := 'portal';\n"
     "    ELSIF v_type = 'partner_user' AND v_partner IS NOT NULL THEN\n"
     "        v_by := 'dealer'; v_via := 'dealer';\n", 1),
    ("    IF p_target IN ('installation', 'product') THEN\n",
     "    -- FS-060 rule 1: a farmer rates installation and service, never a product\n"
     "    IF v_via = 'portal' AND p_target NOT IN ('installation', 'service') THEN\n"
     "        RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';\n"
     "    END IF;\n"
     "    IF p_target IN ('installation', 'product') THEN\n", 1),
    ("        IF NOT order_visible(p_order) THEN\n",
     "        -- a farmer's documents are the portal's, decided before any staff check (EC-1)\n"
     "        IF (v_via = 'portal' AND NOT EXISTS (SELECT 1 FROM portal_rating_docs() d\n"
     "                                             WHERE d.kind = 'order' AND d.id = p_order))\n"
     "           OR (v_via <> 'portal' AND NOT order_visible(p_order)) THEN\n", 1),
    ("        IF NOT complaint_visible(p_complaint) THEN\n",
     "        IF (v_via = 'portal' AND NOT EXISTS (SELECT 1 FROM portal_rating_docs() d\n"
     "                                             WHERE d.kind = 'complaint' AND d.id = p_complaint))\n"
     "           OR (v_via <> 'portal' AND NOT complaint_visible(p_complaint)) THEN\n", 1),
    ("        IF v_by = 'customer' AND NOT app_has_permission(",
     "        IF v_via = 'staff' AND NOT app_has_permission(", 2),
    ("                            rated_by, score, comment, entered_by)\n",
     "                            rated_by, score, comment, entered_by, entered_via)\n", 1),
    ("                v_by, p_score, v_comment, v_me)\n",
     "                v_by, p_score, v_comment, v_me, v_via)\n", 1),
    ("                               'rated_by', v_by, 'product_id', p_product));\n",
     "                               'rated_by', v_by, 'product_id', p_product)\n"
     "            -- a portal rating names the farmer for staff timelines; a dealer's\n"
     "            -- timeline strips actor_name and hides this kind's actor (FS-060 R-1)\n"
     "            || CASE WHEN v_via = 'portal' THEN jsonb_build_object(\n"
     "                   'via', 'portal',\n"
     "                   'actor_name', (SELECT c.name FROM customer c WHERE c.id = v_customer))\n"
     "               ELSE '{}'::jsonb END);\n", 1),
]


def rating_record_057() -> str:
    body = _rating_record_051()
    for old, new, count in _SWAPS:
        found = body.count(old)
        if found != count:
            raise RuntimeError(f"057: expected {count} of {old[:50]!r} in 051's rating_record, found {found}")
        body = body.replace(old, new)
    return body.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


COLUMN = [
    "ALTER TABLE rating ADD COLUMN entered_via text",
    "UPDATE rating SET entered_via = CASE rated_by WHEN 'dealer' THEN 'dealer' ELSE 'staff' END",
    "ALTER TABLE rating ALTER COLUMN entered_via SET NOT NULL, "
    "ADD CONSTRAINT ck_rating_entered_via CHECK (entered_via IN ('staff', 'portal', 'dealer'))",
]

PORTAL_RATING_DOCS = """CREATE FUNCTION portal_rating_docs() RETURNS TABLE (kind text, id uuid, doc_no text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- exactly what portal_orders() and portal_complaints() list (052)
    SELECT 'order', o.id, o.order_no::text FROM sales_order o
     WHERE o.lead_id IN (SELECT portal_leads(portal_customer(), true))
       AND o.deleted_at IS NULL AND o.order_no IS NOT NULL
    UNION ALL
    SELECT 'complaint', c.id, c.complaint_no::text FROM complaint c
     WHERE c.deleted_at IS NULL AND c.complaint_no IS NOT NULL AND c.status <> 'draft'
       AND (c.lead_id IN (SELECT portal_leads(portal_customer(), true))
            OR c.sales_order_id IN (SELECT o.id FROM sales_order o
                                     WHERE o.lead_id IN (SELECT portal_leads(portal_customer(), true))))
       AND NOT EXISTS (SELECT 1 FROM sales_order o WHERE o.id = c.sales_order_id AND o.partner_id IS NOT NULL)
$fn$"""

PORTAL_RATINGS = """CREATE FUNCTION portal_ratings(p_only uuid DEFAULT NULL) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(jsonb_agg(x ORDER BY x->>'created_at' DESC), '[]') FROM (
        SELECT jsonb_build_object(
                   'target', r.target,
                   'order_no', CASE WHEN d.kind = 'order' THEN d.doc_no END,
                   'complaint_no', CASE WHEN d.kind = 'complaint' THEN d.doc_no END,
                   'score', r.score,
                   -- his own words only; a staff note is not the farmer's (EC-2)
                   'comment', CASE WHEN r.entered_via = 'portal' AND r.entered_by = app_current_user_id()
                                   THEN r.comment END,
                   'entered_via', CASE WHEN r.entered_via = 'portal' THEN 'portal' ELSE 'staff' END,
                   'created_at', to_char(r.created_at AT TIME ZONE 'Asia/Kolkata',
                                         'YYYY-MM-DD"T"HH24:MI:SS"+05:30"')) AS x
          FROM rating r
          JOIN portal_rating_docs() d
            ON (d.kind = 'order' AND r.target = 'installation' AND d.id = r.sales_order_id)
            OR (d.kind = 'complaint' AND r.target = 'service' AND d.id = r.complaint_id)
         WHERE r.rated_by = 'customer' AND (p_only IS NULL OR r.id = p_only)
         ORDER BY r.created_at DESC LIMIT 200) s
$fn$"""

PORTAL_RATE = """CREATE FUNCTION portal_rate(p_target text, p_order_no text, p_complaint_no text,
                            p_score integer, p_comment text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_order uuid; v_complaint uuid; v_id uuid;
BEGIN
    -- the portal switched off mid-request reads as portal_off, not "not permitted" (EC-11)
    IF portal_customer() IS NULL THEN
        RAISE EXCEPTION 'portal off' USING ERRCODE = '42501';
    END IF;
    IF p_target = 'installation' THEN
        IF p_order_no IS NULL OR p_complaint_no IS NOT NULL THEN
            RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';
        END IF;
        SELECT d.id INTO v_order FROM portal_rating_docs() d
         WHERE d.kind = 'order' AND d.doc_no::citext = btrim(p_order_no)::citext;
        IF v_order IS NULL THEN
            RAISE EXCEPTION 'order not found' USING ERRCODE = 'RTGNF';
        END IF;
    ELSIF p_target = 'service' THEN
        IF p_complaint_no IS NULL OR p_order_no IS NOT NULL THEN
            RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';
        END IF;
        SELECT d.id INTO v_complaint FROM portal_rating_docs() d
         WHERE d.kind = 'complaint' AND d.doc_no::citext = btrim(p_complaint_no)::citext;
        IF v_complaint IS NULL THEN
            RAISE EXCEPTION 'complaint not found' USING ERRCODE = 'RTGNF';
        END IF;
    ELSE
        RAISE EXCEPTION 'target' USING ERRCODE = 'RTGTG';
    END IF;
    v_id := rating_record(p_target, v_order, v_complaint, NULL, p_score, p_comment);
    RETURN portal_ratings(v_id) -> 0;
END $fn$"""

GRANTED = ["portal_rate(text, text, text, integer, text)", "portal_ratings(uuid)"]
INTERNAL = ["portal_rating_docs()"]


def upgrade() -> None:
    for stmt in COLUMN:
        op.execute(stmt)
    op.execute(PORTAL_RATING_DOCS)
    op.execute(rating_record_057())
    op.execute(PORTAL_RATINGS)
    op.execute(PORTAL_RATE)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute(_rating_record_051().replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    for sig in INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    # a farmer's own ratings cannot be represented without the column
    op.execute("DELETE FROM activity_event WHERE kind = 'rating.recorded' AND payload ->> 'via' = 'portal'")
    op.execute("DELETE FROM rating WHERE entered_via = 'portal'")
    op.execute("ALTER TABLE rating DROP COLUMN IF EXISTS entered_via")
