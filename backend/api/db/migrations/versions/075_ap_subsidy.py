"""075: the Andhra Pradesh subsidy scheme (FS-063).

- `subsidy_pipeline_variant` gains `portal_manual` (AP drip: the government portal's
  lines, fittings amount and guided cost, taken as given) and
  `subsidy_jantri_variant` gains `none` (a system with no unit cost table). Nothing
  here casts to the new labels: a value added by ALTER TYPE cannot be used in the
  transaction that adds it, and the loader writes the rows after this commits.
- `ck_subsidy_system_cap_mode` gains `excl_gst`: the cap on MIN(basis, cost before
  GST) with a rupee ceiling, the farmer paying a fraction of the GST.
- `subsidy_application.regular_matrix_id` and `seven_year_matrix_id` drop NOT NULL:
  an AP drip application has no table to point at.

Revision ID: 075_ap_subsidy
Revises: 074_import_batch
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "075_ap_subsidy"
down_revision: str | None = "074_import_batch"
branch_labels = None
depends_on = None

CAP_MODES_OLD = ("ggrc", "incl_gst", "unit_cost_only")
CAP_MODES_NEW = (*CAP_MODES_OLD, "excl_gst")


def _cap_check(modes: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{m}'" for m in modes)
    op.execute("ALTER TABLE subsidy_system DROP CONSTRAINT ck_subsidy_system_cap_mode")
    op.execute(f"ALTER TABLE subsidy_system ADD CONSTRAINT ck_subsidy_system_cap_mode "
               f"CHECK (cap_mode IN ({listed}))")


def upgrade() -> None:
    op.execute("ALTER TYPE subsidy_pipeline_variant ADD VALUE IF NOT EXISTS 'portal_manual'")
    op.execute("ALTER TYPE subsidy_jantri_variant ADD VALUE IF NOT EXISTS 'none'")
    _cap_check(CAP_MODES_NEW)
    op.execute("ALTER TABLE subsidy_application ALTER COLUMN regular_matrix_id DROP NOT NULL")
    op.execute("ALTER TABLE subsidy_application ALTER COLUMN seven_year_matrix_id DROP NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(text(
        "SELECT (SELECT count(*) FROM subsidy_system WHERE cap_mode = 'excl_gst' "
        "OR pipeline_variant::text = 'portal_manual' OR jantri_variant::text = 'none') + "
        "(SELECT count(*) FROM subsidy_application WHERE regular_matrix_id IS NULL "
        "OR seven_year_matrix_id IS NULL)")).scalar_one()
    if used:
        raise RuntimeError("075: AP subsidy rows exist; remove the AP systems and their "
                           "applications before downgrading")
    op.execute("ALTER TABLE subsidy_application ALTER COLUMN seven_year_matrix_id SET NOT NULL")
    op.execute("ALTER TABLE subsidy_application ALTER COLUMN regular_matrix_id SET NOT NULL")
    _cap_check(CAP_MODES_OLD)
    # enum labels stay: PostgreSQL cannot drop one, and nothing uses them after this
