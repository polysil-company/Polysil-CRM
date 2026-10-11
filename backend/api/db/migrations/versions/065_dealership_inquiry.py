"""065: a dealership enquiry type (FS-053, closes GAP-294).

A prospective dealer is a lead of type `dealership`. It is won without a
quotation, and winning it starts a dealer application (FS-051) from the lead.
`ALTER TYPE ... ADD VALUE` cannot be used in the transaction that adds it; nothing
here does.

Revision ID: 065_dealership_inquiry
Revises: 064_amend_after_void
"""

from __future__ import annotations

from alembic import op

revision: str = "065_dealership_inquiry"
down_revision: str | None = "064_amend_after_void"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE inquiry_type ADD VALUE IF NOT EXISTS 'dealership'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value; leads of this type move to commercial
    op.execute("UPDATE lead SET inquiry_type = 'commercial' "
               "WHERE inquiry_type::text = 'dealership'")
