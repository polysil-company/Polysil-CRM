"""071: subsidy formulas for CG, RJ and UP (FS-056).

- Two pipelines (`gst_inclusive`, `unit_cost_only`) and two table shapes
  (`size_area_2d`, `label_anchor_linear`) join the enums. Nothing here casts to
  the new labels: a value added by ALTER TYPE cannot be used in the transaction
  that adds it, and the loader writes the rows after this commits.
- `subsidy_system.cap_mode`: how the category subsidy caps (ggrc, incl_gst,
  unit_cost_only). Loader-only, as `pipeline_variant` is.
- `unit_cost_cell.row_label`: a label table's row (CG and RJ drip: '1.2 x 0.60').
  A set-size table keeps the size in `lateral_spacing` (stated limit).
- `subsidy_scheme_create` copies `cap_mode` too, edited on its live text.
- `subsidy_parameter.value` widens to six places: UP's insurance rate is 0.169 %
  (0.00169), which four places stored as 0.0017.

Revision ID: 071_state_subsidy_formulas
Revises: 069_subsidy_completion
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "071_state_subsidy_formulas"
down_revision: str | None = "069_subsidy_completion"
branch_labels = None
depends_on = None

CAP_MODES = ("ggrc", "incl_gst", "unit_cost_only")
CREATE_SIG = "subsidy_scheme_create(text, text, uuid, text, text[])"
COLS_OLD = "spacing_outside_table, formula_version, is_active"
COLS_NEW = "spacing_outside_table, formula_version, is_active, cap_mode"


def _swap(old: str, new: str) -> None:
    body = str(op.get_bind().execute(text(
        f"SELECT pg_get_functiondef('{CREATE_SIG}'::regprocedure)")).scalar_one())
    if body.count(old) != 2:
        raise RuntimeError(f"071: subsidy_scheme_create column list found {body.count(old)} times, wanted 2")
    op.execute(body.replace(old, new))


def upgrade() -> None:
    for value in ("gst_inclusive", "unit_cost_only"):
        op.execute(f"ALTER TYPE subsidy_pipeline_variant ADD VALUE IF NOT EXISTS '{value}'")
    for value in ("size_area_2d", "label_anchor_linear"):
        op.execute(f"ALTER TYPE subsidy_jantri_variant ADD VALUE IF NOT EXISTS '{value}'")
    modes = ", ".join(f"'{m}'" for m in CAP_MODES)
    op.execute(f"ALTER TABLE subsidy_system ADD COLUMN cap_mode text NOT NULL DEFAULT 'ggrc' "
               f"CONSTRAINT ck_subsidy_system_cap_mode CHECK (cap_mode IN ({modes}))")
    op.execute("ALTER TABLE unit_cost_cell ADD COLUMN row_label text "
               "CONSTRAINT ck_unit_cost_cell_label CHECK (row_label IS NULL OR length(btrim(row_label)) BETWEEN 1 AND 60)")
    op.execute("DROP INDEX uq_unit_cost_cell")
    op.execute("CREATE UNIQUE INDEX uq_unit_cost_cell ON unit_cost_cell (matrix_id, "
               "COALESCE(lateral_spacing, -1::numeric), COALESCE(row_label, ''), area_breakpoint)")
    _swap(COLS_OLD, COLS_NEW)
    op.execute("ALTER TABLE subsidy_parameter ALTER COLUMN value TYPE numeric(16,6)")


def downgrade() -> None:
    op.execute("ALTER TABLE subsidy_parameter ALTER COLUMN value TYPE numeric(14,4)")
    _swap(COLS_NEW, COLS_OLD)
    op.execute("DELETE FROM unit_cost_cell WHERE row_label IS NOT NULL")
    op.execute("DROP INDEX uq_unit_cost_cell")
    op.execute("CREATE UNIQUE INDEX uq_unit_cost_cell ON unit_cost_cell (matrix_id, "
               "COALESCE(lateral_spacing, -1::numeric), area_breakpoint)")
    op.execute("ALTER TABLE unit_cost_cell DROP COLUMN row_label")
    op.execute("ALTER TABLE subsidy_system DROP COLUMN cap_mode")
    # enum labels stay: PostgreSQL cannot drop one, and nothing uses them after this
