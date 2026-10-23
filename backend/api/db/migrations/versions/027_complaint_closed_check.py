"""027: the CHECK that names 026's new complaint status (FS-015b §5).

PostgreSQL refuses a new enum value in a CHECK within the transaction that added
it (executed in the plan review: UnsafeNewEnumValueUsage), so it lives here.

Revision ID: 027_complaint_closed_check
Revises: 026_complaint_remedies
"""

from __future__ import annotations

from alembic import op

revision = "027_complaint_closed_check"
down_revision = "026_complaint_remedies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE complaint ADD CONSTRAINT ck_complaint_closed "
               "CHECK ((status = 'closed') = (closed_at IS NOT NULL))")


def downgrade() -> None:
    op.execute("ALTER TABLE complaint DROP CONSTRAINT ck_complaint_closed")
