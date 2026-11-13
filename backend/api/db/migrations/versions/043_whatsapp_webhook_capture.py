"""043: WhatsApp webhook capture (FS-038, step one).

- `whatsapp_webhook_event`: each call 11za makes to the webhook URLs, as it
  arrived. RLS on, no policy and no grant for either role; only the definers
  below touch it (the `lead_intake_challenge` shape, 015).
- `whatsapp_webhook_record()`: the insert, granted to `app_anon`, because the
  caller is 11za and holds no session.
- `whatsapp_webhook_purge(cut)`: System only, called by the nightly retention
  purge beside `lead_intake_purge`.

Revision ID: 043_whatsapp_webhook_capture
Revises: 048_complaint_escalation
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "043_whatsapp_webhook_capture"
down_revision: str | None = "048_complaint_escalation"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
ANON_ROLE = "app_anon"

GRANTS: dict[str, str] = {}
HAND_POLICIES: list[tuple[str, str]] = []

TABLE = """CREATE TABLE whatsapp_webhook_event (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind text NOT NULL CHECK (kind IN ('inbound', 'status')),
    method text NOT NULL CHECK (method IN ('GET', 'HEAD', 'POST')),
    received_at timestamptz NOT NULL DEFAULT now(),
    source_ip inet,
    headers jsonb NOT NULL CHECK (jsonb_typeof(headers) = 'array'),
    body_raw bytea NOT NULL CHECK (octet_length(body_raw) <= 65536),
    body_text text NOT NULL,
    body jsonb
)"""

FUNCTIONS = [
    """CREATE FUNCTION whatsapp_webhook_record(p_kind text, p_method text, p_ip inet, p_headers jsonb,
                                        p_body_raw bytea, p_body_text text, p_body jsonb)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid;
BEGIN
    INSERT INTO whatsapp_webhook_event (kind, method, source_ip, headers, body_raw, body_text, body)
    VALUES (p_kind, p_method, p_ip, p_headers, p_body_raw, p_body_text, p_body)
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$""",

    """CREATE FUNCTION whatsapp_webhook_purge(p_cut timestamptz) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_n int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal purges' USING ERRCODE = '42501';
    END IF;
    DELETE FROM whatsapp_webhook_event WHERE received_at < p_cut;
    GET DIAGNOSTICS v_n = ROW_COUNT;
    RETURN v_n;
END $fn$""",
]

ANON_SIGS = ["whatsapp_webhook_record(text, text, inet, jsonb, bytea, text, jsonb)"]
ROLE_SIGS = ["whatsapp_webhook_purge(timestamptz)"]


def upgrade() -> None:
    op.execute(TABLE)
    op.execute("CREATE INDEX ix_whatsapp_webhook_event_received ON whatsapp_webhook_event (received_at)")
    op.execute("ALTER TABLE whatsapp_webhook_event ENABLE ROW LEVEL SECURITY")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in ANON_SIGS + ROLE_SIGS:
        op.execute(f"REVOKE ALL ON FUNCTION {sig} FROM PUBLIC")
    for sig in ANON_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {ANON_ROLE}")
    for sig in ROLE_SIGS:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in ANON_SIGS + ROLE_SIGS:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TABLE IF EXISTS whatsapp_webhook_event")
