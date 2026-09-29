"""024: staff messages, one-to-one (FS-019, ADR-036 amended).

- `conversation`: one row per pair of staff (`user_a < user_b`, unique), each
  side's read mark and the last message's time. `app_role` reads its own and
  writes nothing: the marks move only through the definers and the message
  trigger below. A column grant could not stop one side resetting the other's
  mark (plan review B-1, executed).
- `message`: append-only, so no `updated_*` columns and no UPDATE or DELETE grant.
  Its `created_at` is set by the trigger under the conversation's row lock and is
  strictly increasing per conversation in commit order. A read mark is a
  message's own time, so a message that commits late is never counted read
  unseen (plan review B-2, executed).
- Definers: `conversation_open`, `conversation_mark_read`, `conversation_peers`
  (the other person's name, role and office, which an officer cannot read from
  `app_user`: plan review B-3), `messages_staff_directory`.
- No `activity_event`: a message is not a state change of a business record, and
  it would put chat on the lead timeline (FS-019 rule 7).

Revision ID: 024_messages
Revises: 023_notifications
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "024_messages"
down_revision: str | None = "023_notifications"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005
INTAKE_USER_ID = "3f962ae5-f0d3-5583-91b5-5cea037139fc"  # 015

TABLES_SQL = [
    # people are soft-deleted; only tests hard-delete, and their chats go with them
    """CREATE TABLE conversation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_a uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    user_b uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    a_read_at timestamptz,
    b_read_at timestamptz,
    last_message_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_conversation_pair CHECK (user_a < user_b),
    CONSTRAINT uq_conversation_pair UNIQUE (user_a, user_b)
)""",
    "CREATE INDEX ix_conversation_user_b ON conversation (user_b)",   # user_a leads the unique index
    "CREATE TRIGGER trg_conversation_updated_at BEFORE UPDATE ON conversation FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    """CREATE TABLE message (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    sender_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    body text NOT NULL CHECK (length(btrim(body)) BETWEEN 1 AND 2000),
    resource_type text CHECK (resource_type IS NULL OR resource_type = 'lead'),
    resource_id uuid,
    resource_label text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_message_resource CHECK ((resource_type IS NULL) = (resource_id IS NULL)
                                         AND (resource_id IS NULL) = (resource_label IS NULL))
)""",
    "CREATE INDEX ix_message_page ON message (conversation_id, created_at DESC, id DESC)",
    "CREATE INDEX ix_message_sender ON message (sender_id)",
]

HAND_POLICIES: list[tuple[str, str]] = [
    ("conversation", "CREATE POLICY conversation_sel ON conversation FOR SELECT USING (user_a = (SELECT app_current_user_id()) OR user_b = (SELECT app_current_user_id()))"),
    ("message", "CREATE POLICY message_sel ON message FOR SELECT USING (EXISTS (SELECT 1 FROM conversation c WHERE c.id = conversation_id))"),
    ("message", "CREATE POLICY message_ins ON message FOR INSERT WITH CHECK (sender_id = (SELECT app_current_user_id()) AND EXISTS (SELECT 1 FROM conversation c WHERE c.id = conversation_id))"),
]

GRANTS: dict[str, str] = {"conversation": "SELECT", "message": "SELECT, INSERT"}

_NOT_PEOPLE = f"'{SYSTEM_USER_ID}', '{INTAKE_USER_ID}'"

FUNCTIONS = [
    # Sends on one conversation serialise on its row: created_at strictly increases
    # in commit order, and the sender's own mark moves with it (plan review B-2).
    """CREATE FUNCTION message_stamp() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_last timestamptz; v_at timestamptz;
BEGIN
    -- the row lock orders concurrent sends; one clock read, used everywhere
    SELECT last_message_at INTO v_last FROM conversation WHERE id = NEW.conversation_id FOR UPDATE;
    v_at := GREATEST(clock_timestamp(), COALESCE(v_last, '-infinity') + interval '1 microsecond');
    UPDATE conversation
       SET last_message_at = v_at,
           a_read_at = CASE WHEN user_a = NEW.sender_id THEN v_at ELSE a_read_at END,
           b_read_at = CASE WHEN user_b = NEW.sender_id THEN v_at ELSE b_read_at END
     WHERE id = NEW.conversation_id;
    NEW.created_at := v_at;
    RETURN NEW;
END $fn$""",
    "CREATE TRIGGER trg_message_stamp BEFORE INSERT ON message FOR EACH ROW EXECUTE FUNCTION message_stamp()",
    # Find or open the pair. Staff only, active, not the service accounts, not yourself.
    f"""CREATE FUNCTION conversation_open(p_participant uuid) RETURNS TABLE (id uuid, created boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_a uuid; v_b uuid; v_id uuid;
BEGIN
    -- the service accounts are not people, as callers either (code review F-2)
    IF v_me IN ({_NOT_PEOPLE}) OR NOT EXISTS (SELECT 1 FROM app_user u WHERE u.id = v_me AND u.user_type = 'staff'
                     AND u.is_active AND u.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'staff only' USING ERRCODE = '42501';
    END IF;
    IF p_participant = v_me OR p_participant IN ({_NOT_PEOPLE}) OR NOT EXISTS (
        SELECT 1 FROM app_user u WHERE u.id = p_participant AND u.user_type = 'staff'
           AND u.is_active AND u.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'not someone you can message' USING ERRCODE = 'MSGPT';
    END IF;
    v_a := least(v_me, p_participant); v_b := greatest(v_me, p_participant);
    INSERT INTO conversation (user_a, user_b) VALUES (v_a, v_b)
    ON CONFLICT (user_a, user_b) DO NOTHING RETURNING conversation.id INTO v_id;
    IF v_id IS NOT NULL THEN
        RETURN QUERY SELECT v_id, true;
        RETURN;
    END IF;
    RETURN QUERY SELECT c.id, false FROM conversation c WHERE c.user_a = v_a AND c.user_b = v_b;
END $fn$""",
    # Only the caller's own side, only forwards, and only to a message of this
    # conversation: what the reader's screen showed (plan review B-2).
    """CREATE FUNCTION conversation_mark_read(p_conversation uuid, p_up_to uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); c conversation%ROWTYPE; v_at timestamptz;
BEGIN
    SELECT * INTO c FROM conversation WHERE conversation.id = p_conversation AND v_me IN (user_a, user_b) FOR UPDATE;
    IF NOT FOUND THEN RETURN false; END IF;
    IF p_up_to IS NULL THEN
        v_at := c.last_message_at;
    ELSE
        SELECT m.created_at INTO v_at FROM message m WHERE m.id = p_up_to AND m.conversation_id = p_conversation;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'not a message of this conversation' USING ERRCODE = 'MSGUP';
        END IF;
    END IF;
    IF v_at IS NULL THEN RETURN true; END IF;
    UPDATE conversation
       SET a_read_at = CASE WHEN user_a = v_me THEN GREATEST(a_read_at, v_at) ELSE a_read_at END,
           b_read_at = CASE WHEN user_b = v_me THEN GREATEST(b_read_at, v_at) ELSE b_read_at END
     WHERE conversation.id = p_conversation;
    RETURN true;
END $fn$""",
    # The other person in each of my conversations, including one who has left,
    # which an officer cannot read from app_user (plan review B-3).
    """CREATE FUNCTION conversation_peers()
RETURNS TABLE (conversation_id uuid, id uuid, full_name text, role_name text, org_unit_name text, is_active boolean, my_read_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT c.id, u.id, u.full_name::text, r.name::text, ou.name::text,
           u.is_active AND u.deleted_at IS NULL,
           CASE WHEN c.user_a = app_current_user_id() THEN c.a_read_at ELSE c.b_read_at END
      FROM conversation c
      JOIN app_user u ON u.id = CASE WHEN c.user_a = app_current_user_id() THEN c.user_b ELSE c.user_a END
      LEFT JOIN role r ON r.id = u.role_id
      LEFT JOIN org_unit ou ON ou.id = u.org_unit_id
     WHERE app_current_user_id() IN (c.user_a, c.user_b)
$fn$""",
    # Every active staff member, for staff callers only (FS-019 rule 2, GAP-165).
    f"""CREATE FUNCTION messages_staff_directory(p_q text, p_limit int)
RETURNS TABLE (id uuid, full_name text, role_name text, org_unit_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT u.id, u.full_name::text, r.name::text, ou.name::text
      FROM app_user u
      LEFT JOIN role r ON r.id = u.role_id
      LEFT JOIN org_unit ou ON ou.id = u.org_unit_id
     WHERE EXISTS (SELECT 1 FROM app_user me WHERE me.id = app_current_user_id() AND me.user_type = 'staff'
                     AND me.id NOT IN ({_NOT_PEOPLE}))
       AND u.user_type = 'staff' AND u.is_active AND u.deleted_at IS NULL
       AND u.id <> app_current_user_id() AND u.id NOT IN ({_NOT_PEOPLE})
       AND (p_q IS NULL OR u.full_name ILIKE '%' || replace(replace(replace(p_q, '\\', '\\\\'), '%', '\\%'), '_', '\\_') || '%')
     ORDER BY u.full_name, u.id
     LIMIT greatest(1, least(coalesce(p_limit, 50), 100))
$fn$""",
]

GRANTED = ["conversation_open(uuid)", "conversation_mark_read(uuid, uuid)", "conversation_peers()",
           "messages_staff_directory(text, int)"]
INTERNAL = ["message_stamp()"]


def upgrade() -> None:
    for stmt in TABLES_SQL:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    for table in ("conversation", "message"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_message_stamp ON message")
    for sig in GRANTED + INTERNAL:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP TABLE IF EXISTS message")
    op.execute("DROP TABLE IF EXISTS conversation")
