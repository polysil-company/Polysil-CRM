"""074: Excel import batches (FS-062).

- `import_batch`: one uploaded sheet, its parsed rows, the person's column matches
  and the last check. Private to its uploader: every policy is `created_by` is the
  caller. Purged seven days after upload by the worker.
  - No audit trigger: each status change would copy the rows (several MB) into
    `audit_log` (plan review C-6).
  - No `updated_at`, `updated_by`, `deleted_at` or `external_id`: a batch is
    short-lived and private, and a discard clears its rows at once.
- `partner_codes_taken(citext[])`: which of the given partner codes are taken,
  across the company. A definer, because partners outside the caller's area are
  hidden by RLS and the unique index is company-wide (FS-062 EC-11). It reveals no
  more than an insert's unique violation already does. A closed partner's code is
  free, as the partial unique index says (004).
- `import_batch_purge(timestamptz)`: the worker's retention delete. A definer,
  because the owner-only policy hides every batch from the system principal.
  Refuses any caller but the system principal, like `lead_intake_purge`.

Revision ID: 074_import_batch
Revises: 073_price_list_sales_type
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "074_import_batch"
down_revision: str | None = "073_price_list_sales_type"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_074", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

KINDS = ("partners", "price_list_items", "lines")
STATUSES = ("uploaded", "checked", "committed", "discarded")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


TABLES = [
    f"""CREATE TABLE import_batch (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind text NOT NULL CHECK (kind IN ({_in(KINDS)})),
    target_id uuid REFERENCES price_list(id) ON DELETE CASCADE,
    file_name text NOT NULL CHECK (length(file_name) BETWEEN 1 AND 255),
    file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{{64}}$'),
    sheet text,
    sheets jsonb NOT NULL DEFAULT '[]'::jsonb,
    header_row int NOT NULL CHECK (header_row >= 1),
    headers jsonb NOT NULL,
    rows jsonb,
    row_count int NOT NULL CHECK (row_count >= 0),
    mapping jsonb,
    options jsonb,
    check_result jsonb,
    status text NOT NULL DEFAULT 'uploaded' CHECK (status IN ({_in(STATUSES)})),
    committed_at timestamptz,
    created_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_import_batch_target CHECK ((kind = 'price_list_items') = (target_id IS NOT NULL)),
    CONSTRAINT ck_import_batch_committed CHECK ((status = 'committed') = (committed_at IS NOT NULL)),
    CONSTRAINT ck_import_batch_rows CHECK (status = 'discarded' OR rows IS NOT NULL)
)""",
    "CREATE INDEX ix_import_batch_created_by ON import_batch (created_by, created_at DESC)",
    "CREATE INDEX ix_import_batch_created_at ON import_batch (created_at)",
    "CREATE INDEX ix_import_batch_target ON import_batch (target_id) WHERE target_id IS NOT NULL",
]

GRANTS: dict[str, str] = {"import_batch": "SELECT, INSERT, UPDATE"}

_OWN = "created_by = (SELECT app_current_user_id())"
HAND_POLICIES: list[tuple[str, str]] = [
    ("import_batch", f"CREATE POLICY import_batch_sel ON import_batch FOR SELECT USING ({_OWN})"),
    ("import_batch", f"CREATE POLICY import_batch_ins ON import_batch FOR INSERT WITH CHECK ({_OWN})"),
    ("import_batch", f"CREATE POLICY import_batch_upd ON import_batch FOR UPDATE USING ({_OWN}) WITH CHECK ({_OWN})"),
]

FUNCTIONS = [
    """CREATE FUNCTION partner_codes_taken(p_codes citext[]) RETURNS SETOF text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT cp.code::text FROM channel_partner cp
     WHERE cp.code = ANY(p_codes) AND cp.deleted_at IS NULL
$fn$""",
    """CREATE FUNCTION import_batch_purge(p_cut timestamptz) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal purges' USING ERRCODE = '42501';
    END IF;
    DELETE FROM import_batch WHERE created_at < p_cut;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $fn$""",
]

GRANTED = ["partner_codes_taken(citext[])", "import_batch_purge(timestamptz)"]


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE import_batch ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(floor.policy_sql("import_batch"))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in reversed(GRANTED):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TABLE IF EXISTS import_batch")
