"""064: amending an order that had a dispatch voided is refused with a clear 409
(ISS-122).

A voided dispatch keeps its lines, and they point at the order's lines. An amend
let the order go back to draft, and the next lines edit then failed on that
reference: a 500. The voided dispatch is the record of what was sent and taken
back, so it stays, and the amend is refused: cancel and re-create the order.

Revision ID: 064_amend_after_void
Revises: 062_dealer_recruitment
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "064_amend_after_void"
down_revision: str | None = "062_dealer_recruitment"
branch_labels = None
depends_on = None

# Edited in the LIVE text, not rebuilt from 041: 045 swapped amended_from_gross into
# order_amend, and a rebuild from 041 dropped it (code review F-1).
_ANCHOR = """    IF EXISTS (SELECT 1 FROM dispatch WHERE sales_order_id = p_order_id AND voided_at IS NULL) THEN
        RAISE EXCEPTION 'the order has shipped' USING ERRCODE = 'ORDDS';
    END IF;
"""
_BLOCK = """    -- ISS-122: a voided dispatch still names the order's lines
    IF EXISTS (SELECT 1 FROM dispatch WHERE sales_order_id = p_order_id AND voided_at IS NOT NULL) THEN
        RAISE EXCEPTION 'a voided dispatch holds the lines' USING ERRCODE = 'ORDVD';
    END IF;
"""


def _swap(old: str, new: str) -> None:
    body = str(op.get_bind().execute(text(
        "SELECT pg_get_functiondef('order_amend(uuid, text, text)'::regprocedure)")).scalar_one())
    if body.count(old) != 1:
        raise RuntimeError(f"064: order_amend anchor found {body.count(old)} times")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    _swap(_ANCHOR, _ANCHOR + _BLOCK)


def downgrade() -> None:
    _swap(_ANCHOR + _BLOCK, _ANCHOR)
