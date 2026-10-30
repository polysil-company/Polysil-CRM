"""034: reports: a lead's won and lost dates, and the report indexes (FS-024).

The lead had no won or lost date (GAP-158), so lost leads and wins could not be
windowed without scanning the event log (review B-5). `won_at` and `lost_at` are
set by one BEFORE UPDATE trigger on every stage change, which covers every path:
the API's transition, the quotation acceptance definer (012), the subsidy definer
(025), a reopen. Existing leads are backfilled from `lead.stage_changed` events,
the latest winning.

The reports themselves are live aggregates in the service (ADR-021 point 3 amended):
nothing else is stored.

Revision ID: 034_reports
Revises: 032_stock
"""



from __future__ import annotations

from alembic import op

revision: str = "034_reports"
down_revision: str | None = "032_stock"
branch_labels = None
depends_on = None

COLUMNS = [
    "ALTER TABLE lead ADD COLUMN won_at timestamptz",
    "ALTER TABLE lead ADD COLUMN lost_at timestamptz",
]

FUNCTIONS = [
    """CREATE FUNCTION lead_stage_dates() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.stage = 'won' AND OLD.stage <> 'won' THEN
        NEW.won_at := now();
    ELSIF NEW.stage <> 'won' AND OLD.stage = 'won' THEN
        NEW.won_at := NULL;
    END IF;
    IF NEW.stage = 'lost' AND OLD.stage <> 'lost' THEN
        NEW.lost_at := now();
    ELSIF NEW.stage <> 'lost' AND OLD.stage = 'lost' THEN
        NEW.lost_at := NULL;   -- a reopen
    END IF;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_lead_stage_dates BEFORE UPDATE OF stage ON lead FOR EACH ROW "
    "WHEN (OLD.stage IS DISTINCT FROM NEW.stage) EXECUTE FUNCTION lead_stage_dates()",
]

# the latest event that moved the lead into its current won or lost stage
BACKFILL = [
    """UPDATE lead l SET won_at = e.at
  FROM (SELECT lead_id, max(occurred_at) AS at FROM activity_event
         WHERE kind = 'lead.stage_changed' AND payload ->> 'to' = 'won' GROUP BY lead_id) e
 WHERE l.id = e.lead_id AND l.stage = 'won'""",
    """UPDATE lead l SET lost_at = e.at
  FROM (SELECT lead_id, max(occurred_at) AS at FROM activity_event
         WHERE kind = 'lead.stage_changed' AND payload ->> 'to' = 'lost' GROUP BY lead_id) e
 WHERE l.id = e.lead_id AND l.stage = 'lost'""",
    # a won or lost lead with no event (seeded or imported): its last update stands in
    "UPDATE lead SET won_at = updated_at WHERE stage = 'won' AND won_at IS NULL",
    "UPDATE lead SET lost_at = updated_at WHERE stage = 'lost' AND lost_at IS NULL",
]

INDEXES = [
    "CREATE INDEX ix_lead_lost_at ON lead (lost_at) WHERE stage = 'lost'",
    "CREATE INDEX ix_lead_won_at ON lead (won_at) WHERE stage = 'won'",
    "CREATE INDEX ix_task_open_due ON task (due_at) WHERE status = 'open'",
]


def upgrade() -> None:
    for stmt in COLUMNS + FUNCTIONS + BACKFILL + INDEXES:
        op.execute(stmt)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_lead_stage_dates ON lead")
    op.execute("DROP FUNCTION IF EXISTS lead_stage_dates()")
    for name in ("ix_task_open_due", "ix_lead_won_at", "ix_lead_lost_at"):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS lost_at")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS won_at")
