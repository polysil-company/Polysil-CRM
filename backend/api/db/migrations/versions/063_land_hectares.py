# ruff: noqa: E501  (embedded SQL)

"""063: a lead's land in hectares (FS-052, client sheet item 19).

`land_hectares` is stored; `land_acres` becomes a generated column, so every reader
of acres keeps working and only writers change. Existing acres are converted once
(hectares = acres / 2.4710538, two places). The audit trigger records one row per
converted lead with no actor; `updated_at` is left alone (as 050's backfill).

Revision ID: 063_land_hectares
Revises: 061_record_documents
"""

from __future__ import annotations

from alembic import op

revision: str = "063_land_hectares"
down_revision: str | None = "061_record_documents"
branch_labels = None
depends_on = None

ACRES_PER_HECTARE = "2.4710538"
MAX_HECTARES = "40468.56"   # 99999.99 acres, the old limit


def upgrade() -> None:
    op.execute("ALTER TABLE lead ADD COLUMN land_hectares numeric(10,2), "
               f"ADD CONSTRAINT ck_lead_land_hectares CHECK (land_hectares IS NULL OR "
               f"(land_hectares > 0 AND land_hectares <= {MAX_HECTARES}))")
    op.execute("ALTER TABLE lead DISABLE TRIGGER trg_lead_updated_at")
    # a hundredth of an acre rounds to 0.00 ha; the smallest stored value is 0.01
    op.execute(f"UPDATE lead SET land_hectares = GREATEST(round(land_acres / {ACRES_PER_HECTARE}, 2), 0.01) "
               "WHERE land_acres IS NOT NULL")
    op.execute("ALTER TABLE lead ENABLE TRIGGER trg_lead_updated_at")
    op.execute("ALTER TABLE lead DROP COLUMN land_acres")
    op.execute(f"ALTER TABLE lead ADD COLUMN land_acres numeric(10,2) "
               f"GENERATED ALWAYS AS (round(land_hectares * {ACRES_PER_HECTARE}, 2)) STORED")


def downgrade() -> None:
    op.execute("ALTER TABLE lead DROP COLUMN land_acres")
    op.execute("ALTER TABLE lead ADD COLUMN land_acres numeric(10,2), ADD CONSTRAINT ck_lead_land_acres "
               "CHECK (land_acres IS NULL OR (land_acres > 0 AND land_acres <= 99999.99))")
    op.execute("ALTER TABLE lead DISABLE TRIGGER trg_lead_updated_at")
    op.execute(f"UPDATE lead SET land_acres = round(land_hectares * {ACRES_PER_HECTARE}, 2) "
               "WHERE land_hectares IS NOT NULL")
    op.execute("ALTER TABLE lead ENABLE TRIGGER trg_lead_updated_at")
    op.execute("ALTER TABLE lead DROP COLUMN land_hectares")
