"""081: indexes for the sales forecast and insights (FS-079 §5, plan review S-4, S-5, Q2).

Indexes only, no table or policy change.

- `ix_quotation_live_value`: the newest live quotation of a lead, in the order rule 8
  picks it (`sent_at DESC NULLS LAST, id DESC`). Its predicate matches the query's
  uncast `status IN (...)`; a cast to text would not use it (plan review S-3).
- `ix_quotation_accepted_at`, `ix_quotation_rejected_at`: the quotation insights
  window on the decision date (rule 15).
- `ix_activity_event_stage_changed`: the won leads' stage events (rule 3).

Revision ID: 081_forecast_indexes
Revises: 080_lead_reopen_links
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "081_forecast_indexes"
down_revision: str | None = "080_lead_reopen_links"
branch_labels = None
depends_on = None

INDEXES = {
    "ix_quotation_live_value": (
        "CREATE INDEX ix_quotation_live_value ON quotation (lead_id, sent_at DESC NULLS LAST, id DESC) "
        "WHERE superseded_by_id IS NULL AND deleted_at IS NULL "
        "AND status IN ('sent', 'viewed', 'negotiation')"),
    "ix_quotation_accepted_at": (
        "CREATE INDEX ix_quotation_accepted_at ON quotation (accepted_at) "
        "WHERE accepted_at IS NOT NULL AND deleted_at IS NULL"),
    "ix_quotation_rejected_at": (
        "CREATE INDEX ix_quotation_rejected_at ON quotation (rejected_at) "
        "WHERE rejected_at IS NOT NULL AND deleted_at IS NULL"),
    "ix_activity_event_stage_changed": (
        "CREATE INDEX ix_activity_event_stage_changed ON activity_event (lead_id) "
        "WHERE kind = 'lead.stage_changed'"),
}


def upgrade() -> None:
    for stmt in INDEXES.values():
        op.execute(stmt)


def downgrade() -> None:
    for name in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
