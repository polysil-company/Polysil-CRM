"""090: the approval ladder for industrial orders (FS-089).

* `approval_threshold.doc_type` gains `industrial_order`, seeded company-wide:
  State Manager up to 5,00,000, Regional Manager up to 25,00,000, MD no ceiling
  (rule 2, GAP-593).
* `approval_chain()` reads its manager list by doc type: `industrial_order` climbs
  State Manager, Regional Manager, MD. The loop, the owner-level drop, and the
  Accounts and Dispatch steps are the sales order's. The quotation and complaint
  branches are untouched.
* `create_approval_request()` asks for the industrial ladder on an industrial
  order, and refuses one whose MD step nobody can take (rule 7). That uses
  `approval_step_stalled`, the queue's own test (plan review B-2).

Both functions are patched by their live text, as 041 and 045 do: 016, 017, 026,
041 and 045 have each changed them since 013 wrote them.

Revision ID: 090_industrial_order_ladder
Revises: 089_document_charges
"""



from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "090_industrial_order_ladder"
down_revision: str | None = "089_document_charges"
branch_labels = None
depends_on = None

DOC_TYPES_BEFORE = "'sales_order', 'quotation', 'complaint'"
DOC_TYPES = "'sales_order', 'quotation', 'complaint', 'industrial_order'"

# rule 2: (role code, ceiling)
SEED = (("state_manager", "500000"), ("regional_manager", "2500000"), ("md_ceo", None))

CHAIN = "approval_chain(text, numeric, uuid, integer)"
CHAIN_OLD = "WHERE code IN ('district_manager', 'state_manager', 'regional_manager')"
CHAIN_NEW = ("WHERE code = ANY(CASE WHEN p_doc_type = 'industrial_order' "
             "THEN ARRAY['state_manager', 'regional_manager', 'md_ceo'] "
             "ELSE ARRAY['district_manager', 'state_manager', 'regional_manager'] END)")

REQUEST = "create_approval_request(text, uuid)"
REQUEST_CALL_OLD = "v_chain := approval_chain(p_doc_type, CASE WHEN v_order.order_type = 'sample'"
REQUEST_CALL_NEW = ("v_chain := approval_chain(CASE WHEN v_order.order_type = 'industrial' "
                    "THEN 'industrial_order' ELSE p_doc_type END, "
                    "CASE WHEN v_order.order_type = 'sample'")
REQUEST_NOTIFY_OLD = "    PERFORM order_notify_step(v_request);"
REQUEST_NOTIFY_NEW = """    -- FS-089 rule 7: nobody ranks above the MD to take a stalled MD step
    IF EXISTS (SELECT 1 FROM approval_step s JOIN role r ON r.id = s.approver_role_id
                WHERE s.request_id = v_request AND r.code = 'md_ceo'
                  AND approval_step_stalled(s.id)) THEN
        RAISE EXCEPTION 'no active MD can approve this order' USING ERRCODE = 'ORDNA';
    END IF;
    PERFORM order_notify_step(v_request);"""


def _swap(sig: str, pairs: list[tuple[str, str]]) -> None:
    body = str(op.get_bind().execute(
        text(f"SELECT pg_get_functiondef('{sig}'::regprocedure)")).scalar_one())
    for old, new in pairs:
        if body.count(old) != 1:
            raise RuntimeError(f"090: {sig} anchor {old[:40]!r} found {body.count(old)} times")
        body = body.replace(old, new)
    op.execute(body)


def _doc_type_check(types: str) -> None:
    op.execute("ALTER TABLE approval_threshold DROP CONSTRAINT ck_approval_threshold_doc_type")
    op.execute(f"ALTER TABLE approval_threshold ADD CONSTRAINT ck_approval_threshold_doc_type "
               f"CHECK (doc_type IN ({types}))")


def upgrade() -> None:
    _doc_type_check(DOC_TYPES)
    for role, ceiling in SEED:
        op.execute(
            "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
            f"SELECT 'industrial_order', r.id, NULL, {ceiling or 'NULL'} FROM role r "
            f"WHERE r.code = '{role}' AND r.deleted_at IS NULL "
            "ON CONFLICT (doc_type, role_id, territory_id) DO NOTHING")
    _swap(CHAIN, [(CHAIN_OLD, CHAIN_NEW)])
    _swap(REQUEST, [(REQUEST_CALL_OLD, REQUEST_CALL_NEW), (REQUEST_NOTIFY_OLD, REQUEST_NOTIFY_NEW)])


def downgrade() -> None:
    _swap(REQUEST, [(REQUEST_NOTIFY_NEW, REQUEST_NOTIFY_OLD), (REQUEST_CALL_NEW, REQUEST_CALL_OLD)])
    _swap(CHAIN, [(CHAIN_NEW, CHAIN_OLD)])
    op.execute("DELETE FROM approval_threshold WHERE doc_type = 'industrial_order'")
    _doc_type_check(DOC_TYPES_BEFORE)
