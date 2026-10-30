"""029: the bell clears a decided approval, and says what was decided (ISS-108).

Found in the 2 Oct demo re-walk (R-9). Three changes to the bell functions, as 026
(complaint refunds) left them:

1. **A decided step clears its bell.** `notify_settle()` marks every unread
   `approval_requested` notification on the document read when the step is
   decided (approve or reject), and when the request ends without a decision:
   the order is cancelled, the discount request is cancelled by an edit or a
   delete, or a complaint remedy is withdrawn (`ENDED`). It runs before the next step is notified, so the new step's
   notifications stay unread. One pending request per document (013), so every
   older `approval_requested` on the document is stale by then.
2. **A discount says how much.** "Discount of 8% on QT/... waits for your
   approval". The figure is `approval_request.amount`, the effective percent the
   request was raised at (017). No article, so "an 8%" never reads "a 8%".
3. **A rejection says "was not approved"**, for orders and discounts. The engine's
   word is "returned"; users say "rejected". The `kind` codes do not change
   (`order_returned`, `discount_returned`), so the frontend's mapping holds.

Notifications already stale are marked read once, here.

Revision ID: 029_notification_fixes
Revises: 039_subsidy_follow_ups (session B's chain merged first, PR 52)
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "029_notification_fixes"
down_revision: str | None = "039_subsidy_follow_ups"
branch_labels = None
depends_on = None


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_029", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"029: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"029: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _m026() -> ModuleType:
    return _load("026_complaint_remedies")


def _live(name: str) -> str:
    """The live text: 023's function as 026 patched it, already CREATE OR REPLACE."""
    (body,) = [f for f in _m026()._bell_patched() if f"FUNCTION {name}(" in f]
    return str(body)


# "8%", "12.5%": two places at most, trailing zeros dropped
_PCT = "trim_scale(round({x}, 2))::text || '%'"

# The ways a request ends without a decision: an order cancelled, a discount
# request cancelled by an edit or a delete, a remedy withdrawn (a refund's request
# is cancelled), and a replacement order cancelled with it (026).
ENDED = ("order.cancelled", "quotation.approval_cancelled", "complaint.remedy_withdrawn",
         "order.replacement_cancelled")

KINDS_026 = (*_m026()._load("023").KINDS, *_m026().NEW_KINDS)
if set(ENDED) & set(KINDS_026):
    raise RuntimeError("029: an ended kind already has an arm; settle would never run")
KINDS = (*KINDS_026, *ENDED)

SETTLE = """CREATE FUNCTION notify_settle(p_type text, p_entity uuid) RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    UPDATE notification SET read_at = now()
     WHERE kind = 'approval_requested' AND resource_type = p_type AND resource_id = p_entity
       AND read_at IS NULL
$fn$"""

INDEX = ("CREATE INDEX ix_notification_waiting ON notification (resource_id) "
         "WHERE kind = 'approval_requested' AND read_at IS NULL")

# Stale today: no pending request on the document, or a step of the pending one
# decided after the notification was written. Strictly after: the next step's
# notifications share the deciding transaction's now().
BACKFILL = """UPDATE notification n SET read_at = now()
 WHERE n.kind = 'approval_requested' AND n.read_at IS NULL
   AND (NOT EXISTS (SELECT 1 FROM approval_request r
                     WHERE r.doc_type = n.resource_type AND r.entity_id = n.resource_id
                       AND r.status = 'pending')
        OR EXISTS (SELECT 1 FROM approval_request r JOIN approval_step s ON s.request_id = r.id
                    WHERE r.doc_type = n.resource_type AND r.entity_id = n.resource_id
                      AND r.status = 'pending' AND s.decided_at > n.created_at))"""


def step_after() -> str:
    f = _live("notify_step")
    f = _replace(f, "v_title := 'A discount on ' || v_label || ' waits for your approval';",
                 "v_title := CASE WHEN r.amount IS NULL THEN 'A discount' ELSE 'Discount of ' || "
                 + _PCT.format(x="r.amount") + " END || ' on ' || v_label || ' waits for your approval';")
    return f


def event_after() -> str:
    f = _live("notify_from_event")
    f = _replace(f, """        WHEN 'approval.decided' THEN
            -- only an approve moves the chain on; a reject returns it (review B-1)
            IF""", """        WHEN 'approval.decided' THEN
            -- the decided step's bell clears first, so the next step's stays (ISS-108)
            PERFORM notify_settle(e.entity_type, e.entity_id);
            -- only an approve moves the chain on; a reject returns it (review B-1)
            IF""")
    f = _replace(f, """        WHEN 'order.approved', 'order.returned',""",
                 "        WHEN " + ", ".join(f"'{k}'" for k in ENDED) + """ THEN
            -- a request ended without a decision: nobody is waited on now
            PERFORM notify_settle(e.entity_type, e.entity_id);
        WHEN 'order.approved', 'order.returned',""")
    f = _replace(f, "THEN ' was approved' ELSE ' was returned' END;\n",
                 "THEN ' was approved' ELSE ' was not approved' END;\n")
    f = _replace(f, """                    'The discount on ' || v_label || CASE WHEN e.kind = 'quotation.approval_approved' THEN ' was approved' ELSE ' was returned' END,""",
                 """                    CASE WHEN v_req.amount IS NULL THEN 'The discount' ELSE 'Discount of ' || """
                 + _PCT.format(x="v_req.amount") + """ END
                    || ' on ' || v_label || CASE WHEN e.kind = 'quotation.approval_approved' THEN ' was approved' ELSE ' was not approved' END,""")
    return f


def _trigger(kinds: tuple[str, ...]) -> str:
    # 026's trigger: a paid refund's close stays quiet
    return str(_m026()._trigger(kinds, quiet_refund_close=True))


def upgrade() -> None:
    op.execute(INDEX)
    op.execute(SETTLE)
    op.execute(step_after())
    op.execute(event_after())
    op.execute("DROP TRIGGER trg_notify_from_event ON activity_event")
    op.execute(_trigger(KINDS))
    op.execute(BACKFILL)
    # a created or re-created function is PUBLIC-executable by default (028, CI PR 50)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_notify_from_event ON activity_event")
    op.execute(_trigger(KINDS_026))
    for name in ("notify_step", "notify_from_event"):
        op.execute(_live(name))
    op.execute("DROP FUNCTION notify_settle(text, uuid)")
    op.execute("DROP INDEX ix_notification_waiting")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
