"""020: fixes to 019 from the PR 25 review.

- `complaint_sla_policy_set` refuses a start date before today (IST). A past start
  closed the target in force early, and a resubmit then restated the targets of
  complaints first submitted in that window (rule 10: masters never restate the past).
- `complaint_add_working_hours` and `complaint_due` are STRICT, and the first
  refuses negative hours. A NULL argument looped until the statement timeout.
- The two partial indexes on `complaint.lead_id` and `complaint.sales_order_id`
  duplicated the generated ones.

Forward only: 019 is applied on staging.

Revision ID: 020_complaint_fixes
Revises: 019_complaints
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "020_complaint_fixes"
down_revision: str | None = "019_complaints"
branch_labels = None
depends_on = None


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_020", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"020: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"020: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _before() -> dict[str, str]:
    """The three functions this migration replaces, as 019 left them."""
    fns = _load("019_complaints").FUNCTIONS
    out = {}
    for name in ("complaint_add_working_hours", "complaint_due", "complaint_sla_policy_set"):
        out[name] = next(f for f in fns if f.startswith(f"CREATE FUNCTION {name}("))
    return out


def _after() -> dict[str, str]:
    f = _before()
    f["complaint_add_working_hours"] = _replace(
        f["complaint_add_working_hours"],
        "LANGUAGE plpgsql IMMUTABLE SET",
        "LANGUAGE plpgsql IMMUTABLE STRICT SET")
    f["complaint_add_working_hours"] = _replace(
        f["complaint_add_working_hours"],
        "BEGIN\n    LOOP\n",
        "BEGIN\n    IF p_hours < 0 THEN\n"
        "        RAISE EXCEPTION 'hours must not be negative' USING ERRCODE = '22023';\n"
        "    END IF;\n    LOOP\n")
    f["complaint_due"] = _replace(
        f["complaint_due"],
        "LANGUAGE sql IMMUTABLE SET",
        "LANGUAGE sql IMMUTABLE STRICT SET")
    f["complaint_sla_policy_set"] = _replace(
        f["complaint_sla_policy_set"],
        "    PERFORM pg_advisory_xact_lock(5, hashtext('complaint_sla_policy'));\n",
        "    IF p_from < (now() AT TIME ZONE 'Asia/Kolkata')::date THEN\n"
        "        RAISE EXCEPTION 'a target cannot start in the past' USING ERRCODE = 'CMPPD';\n"
        "    END IF;\n"
        "    PERFORM pg_advisory_xact_lock(5, hashtext('complaint_sla_policy'));\n")
    return f


def _or_replace(stmt: str) -> str:
    return _replace(stmt, "CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ")


def upgrade() -> None:
    for stmt in _after().values():
        op.execute(_or_replace(stmt))
    op.execute("DROP INDEX IF EXISTS ix_complaint_lead")
    op.execute("DROP INDEX IF EXISTS ix_complaint_order")
    # CREATE OR REPLACE keeps the grants; this keeps PUBLIC off, as every migration does
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    # CREATE OR REPLACE cannot drop STRICT: re-create the 019 bodies with it off
    for stmt in _before().values():
        body = _or_replace(stmt)
        body = body.replace("IMMUTABLE SET", "IMMUTABLE CALLED ON NULL INPUT SET")
        op.execute(body)
    op.execute("CREATE INDEX ix_complaint_lead ON complaint (lead_id) WHERE lead_id IS NOT NULL")
    op.execute("CREATE INDEX ix_complaint_order ON complaint (sales_order_id) WHERE sales_order_id IS NOT NULL")
