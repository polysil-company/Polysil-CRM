"""058: group chats (FS-048) on FS-019's conversations.

- `conversation` gains `kind` (direct, group), `name` and `manager_id`; a group has
  no pair. One table, so `message`, its pages and the stamp trigger stay as they are.
- `conversation_member`: who is in a group and each one's read mark. Read through
  an own-rows policy, so it and `conversation_sel` never read each other (edge E-1);
  the other members come from `conversation_members()`.
- Every write goes through a definer that locks the conversation first (edge E-2).
  `message_stamp()` re-checks a group sender after that lock (plan review R-3).
- The acting manager: `manager_id` while active, else the earliest-added active
  member still in (edge E-3). `conversation_manager()` answers members only.

Revision ID: 058_group_chat
Revises: 055_portal_code_ceiling
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "058_group_chat"
down_revision: str | None = "055_portal_code_ceiling"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005
INTAKE_USER_ID = "3f962ae5-f0d3-5583-91b5-5cea037139fc"  # 015
_NOT_PEOPLE = f"'{SYSTEM_USER_ID}', '{INTAKE_USER_ID}'"

_spec = importlib.util.spec_from_file_location(
    "consumer_floor_058", Path(__file__).resolve().parents[3] / "authz" / "consumer_floor.py")
assert _spec is not None and _spec.loader is not None
floor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(floor)

TABLES = [
    "ALTER TABLE conversation ADD COLUMN kind text NOT NULL DEFAULT 'direct' CHECK (kind IN ('direct', 'group')), "
    "ADD COLUMN name text, "
    "ADD COLUMN manager_id uuid REFERENCES app_user(id) ON DELETE SET NULL, "
    "ALTER COLUMN user_a DROP NOT NULL, ALTER COLUMN user_b DROP NOT NULL",
    "ALTER TABLE conversation DROP CONSTRAINT ck_conversation_pair",
    """ALTER TABLE conversation ADD CONSTRAINT ck_conversation_pair CHECK (
    (kind = 'direct' AND user_a IS NOT NULL AND user_b IS NOT NULL AND user_a < user_b
         AND name IS NULL AND manager_id IS NULL)
 OR (kind = 'group' AND user_a IS NULL AND user_b IS NULL
         AND name IS NOT NULL AND length(btrim(name)) BETWEEN 1 AND 80))""",
    "CREATE INDEX ix_conversation_manager ON conversation (manager_id)",
    """CREATE TABLE conversation_member (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    read_at timestamptz,
    added_at timestamptz NOT NULL DEFAULT now(),
    added_by uuid REFERENCES app_user(id) ON DELETE SET NULL,
    left_at timestamptz,
    CONSTRAINT uq_conversation_member UNIQUE (conversation_id, user_id)
)""",
    "CREATE INDEX ix_conversation_member_user ON conversation_member (user_id)",
    "CREATE INDEX ix_conversation_member_added_by ON conversation_member (added_by)",
]

GRANTS: dict[str, str] = {"conversation_member": "SELECT"}

HAND_POLICIES: list[tuple[str, str]] = [
    ("conversation", "CREATE POLICY conversation_sel ON conversation FOR SELECT USING (user_a = (SELECT app_current_user_id()) OR user_b = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM conversation_member m WHERE m.conversation_id = conversation.id AND m.user_id = (SELECT app_current_user_id()) AND m.left_at IS NULL))"),
    # own rows only: it must read no other table, or the two policies recurse (edge E-1)
    ("conversation_member", "CREATE POLICY conversation_member_sel ON conversation_member FOR SELECT USING (user_id = (SELECT app_current_user_id()))"),
]

_STAFF_CHECK = f"""    IF v_me IN ({_NOT_PEOPLE}) OR NOT EXISTS (SELECT 1 FROM app_user u WHERE u.id = v_me AND u.user_type = 'staff'
                     AND u.is_active AND u.deleted_at IS NULL) THEN
        RAISE EXCEPTION 'staff only' USING ERRCODE = 'MSGST';
    END IF;"""

# the people a group may hold: active staff, never the service accounts
_BAD_PEOPLE = f"""SELECT 1 FROM unnest(p_users) AS x(uid)
                WHERE x.uid IN ({_NOT_PEOPLE}) OR NOT EXISTS (
                      SELECT 1 FROM app_user u WHERE u.id = x.uid AND u.user_type = 'staff'
                         AND u.is_active AND u.deleted_at IS NULL)"""

FUNCTIONS = [
    # The acting manager, internal: no membership check (edge E-3, ties by user id E-4)
    """CREATE FUNCTION conversation_acting_manager(p_conversation uuid) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT coalesce(
        (SELECT c.manager_id FROM conversation c
           JOIN conversation_member m ON m.conversation_id = c.id AND m.user_id = c.manager_id AND m.left_at IS NULL
           JOIN app_user u ON u.id = c.manager_id AND u.is_active AND u.deleted_at IS NULL
          WHERE c.id = p_conversation),
        (SELECT m.user_id FROM conversation_member m
           JOIN app_user u ON u.id = m.user_id AND u.is_active AND u.deleted_at IS NULL
          WHERE m.conversation_id = p_conversation AND m.left_at IS NULL
          ORDER BY m.added_at, m.user_id LIMIT 1))
$fn$""",
    # Granted: NULL for a caller who is not in, so it reveals no group (plan review R-2)
    """CREATE FUNCTION conversation_manager(p_conversation uuid) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT conversation_acting_manager(p_conversation)
     WHERE EXISTS (SELECT 1 FROM conversation_member m WHERE m.conversation_id = p_conversation
                     AND m.user_id = app_current_user_id() AND m.left_at IS NULL)
$fn$""",
    # 024's stamp, plus the group branch: re-checked after the lock (plan review R-3)
    """CREATE OR REPLACE FUNCTION message_stamp() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_last timestamptz; v_at timestamptz; v_kind text;
BEGIN
    -- the row lock orders concurrent sends; one clock read, used everywhere
    SELECT last_message_at, kind INTO v_last, v_kind FROM conversation WHERE id = NEW.conversation_id FOR UPDATE;
    v_at := GREATEST(clock_timestamp(), COALESCE(v_last, '-infinity') + interval '1 microsecond');
    IF v_kind = 'group' THEN
        -- the insert policy saw membership on a snapshot older than this lock
        UPDATE conversation_member SET read_at = v_at
         WHERE conversation_id = NEW.conversation_id AND user_id = NEW.sender_id AND left_at IS NULL;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'not a member of this group' USING ERRCODE = 'MSGNF';
        END IF;
        UPDATE conversation SET last_message_at = v_at WHERE id = NEW.conversation_id;
    ELSE
        UPDATE conversation
           SET last_message_at = v_at,
               a_read_at = CASE WHEN user_a = NEW.sender_id THEN v_at ELSE a_read_at END,
               b_read_at = CASE WHEN user_b = NEW.sender_id THEN v_at ELSE b_read_at END
         WHERE id = NEW.conversation_id;
    END IF;
    NEW.created_at := v_at;
    RETURN NEW;
END $fn$""",
    # 024's mark, plus the group branch: the member's own row, not the conversation (E-11)
    """CREATE OR REPLACE FUNCTION conversation_mark_read(p_conversation uuid, p_up_to uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); c conversation%ROWTYPE; v_at timestamptz; v_member uuid;
BEGIN
    SELECT * INTO c FROM conversation WHERE conversation.id = p_conversation;
    IF NOT FOUND THEN RETURN false; END IF;
    IF c.kind = 'group' THEN
        SELECT m.id INTO v_member FROM conversation_member m
         WHERE m.conversation_id = p_conversation AND m.user_id = v_me AND m.left_at IS NULL FOR UPDATE;
        IF NOT FOUND THEN RETURN false; END IF;
    ELSE
        SELECT * INTO c FROM conversation WHERE conversation.id = p_conversation AND v_me IN (user_a, user_b) FOR UPDATE;
        IF NOT FOUND THEN RETURN false; END IF;
    END IF;
    IF p_up_to IS NULL THEN
        v_at := c.last_message_at;
    ELSE
        SELECT m.created_at INTO v_at FROM message m WHERE m.id = p_up_to AND m.conversation_id = p_conversation;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'not a message of this conversation' USING ERRCODE = 'MSGUP';
        END IF;
    END IF;
    IF v_at IS NULL THEN RETURN true; END IF;
    IF c.kind = 'group' THEN
        UPDATE conversation_member SET read_at = GREATEST(read_at, v_at) WHERE id = v_member;
    ELSE
        UPDATE conversation
           SET a_read_at = CASE WHEN user_a = v_me THEN GREATEST(a_read_at, v_at) ELSE a_read_at END,
               b_read_at = CASE WHEN user_b = v_me THEN GREATEST(b_read_at, v_at) ELSE b_read_at END
         WHERE conversation.id = p_conversation;
    END IF;
    RETURN true;
END $fn$""",
    f"""CREATE FUNCTION group_create(p_name text, p_users uuid[]) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_id uuid; v_users uuid[];
BEGIN
{_STAFF_CHECK}
    SELECT coalesce(array_agg(DISTINCT x), '{{}}') INTO v_users FROM unnest(p_users) AS x WHERE x IS DISTINCT FROM v_me;
    p_users := v_users;
    IF cardinality(p_users) < 1 OR EXISTS ({_BAD_PEOPLE}) THEN
        RAISE EXCEPTION 'not someone you can message' USING ERRCODE = 'MSGPT';
    END IF;
    IF cardinality(p_users) > 49 THEN
        RAISE EXCEPTION 'a group holds at most 50' USING ERRCODE = 'MSGFL';
    END IF;
    INSERT INTO conversation (kind, name, manager_id) VALUES ('group', btrim(p_name), v_me) RETURNING id INTO v_id;
    INSERT INTO conversation_member (conversation_id, user_id, added_by)
    SELECT v_id, x, v_me FROM unnest(array_prepend(v_me, p_users)) AS x;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('conversation', v_id, 'conversation.group_created', v_me,
            jsonb_build_object('name', btrim(p_name), 'members', to_jsonb(p_users)));
    RETURN v_id;
END $fn$""",
    f"""CREATE FUNCTION group_add(p_conversation uuid, p_users uuid[]) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_in int; v_new uuid[];
BEGIN
{_STAFF_CHECK}
    -- the conversation first, always (edge E-2): this lock serialises the cap
    PERFORM 1 FROM conversation WHERE id = p_conversation AND kind = 'group' FOR UPDATE;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM conversation_member WHERE conversation_id = p_conversation
                                   AND user_id = v_me AND left_at IS NULL) THEN
        RAISE EXCEPTION 'not a group you are in' USING ERRCODE = 'MSGNF';
    END IF;
    IF cardinality(p_users) < 1 THEN
        RAISE EXCEPTION 'not someone you can message' USING ERRCODE = 'MSGPT';
    END IF;
    -- only the people not already in are checked: a member who has since left the
    -- company is ignored, as the spec says, not a reason to refuse the batch
    SELECT coalesce(array_agg(DISTINCT x), '{{}}') INTO v_new FROM unnest(p_users) AS x
     WHERE NOT EXISTS (SELECT 1 FROM conversation_member m WHERE m.conversation_id = p_conversation
                         AND m.user_id = x AND m.left_at IS NULL);
    p_users := v_new;
    IF EXISTS ({_BAD_PEOPLE}) THEN
        RAISE EXCEPTION 'not someone you can message' USING ERRCODE = 'MSGPT';
    END IF;
    SELECT count(*) INTO v_in FROM conversation_member WHERE conversation_id = p_conversation AND left_at IS NULL;
    IF v_in + cardinality(v_new) > 50 THEN
        RAISE EXCEPTION 'a group holds at most 50' USING ERRCODE = 'MSGFL';
    END IF;
    IF cardinality(v_new) = 0 THEN RETURN; END IF;
    -- added back: added_at and added_by renewed, the read mark kept (rule 8)
    INSERT INTO conversation_member (conversation_id, user_id, added_by)
    SELECT p_conversation, x, v_me FROM unnest(v_new) AS x
    ON CONFLICT (conversation_id, user_id) DO UPDATE
       SET left_at = NULL, added_at = now(), added_by = EXCLUDED.added_by;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('conversation', p_conversation, 'conversation.member_added', v_me,
            jsonb_build_object('members', to_jsonb(v_new)));
END $fn$""",
    f"""CREATE FUNCTION group_leave(p_conversation uuid, p_user uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_manager uuid;
BEGIN
{_STAFF_CHECK}
    PERFORM 1 FROM conversation WHERE id = p_conversation AND kind = 'group' FOR UPDATE;
    IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM conversation_member WHERE conversation_id = p_conversation
                                   AND user_id = v_me AND left_at IS NULL) THEN
        RAISE EXCEPTION 'not a group you are in' USING ERRCODE = 'MSGNF';
    END IF;
    IF p_user IS DISTINCT FROM v_me AND conversation_acting_manager(p_conversation) IS DISTINCT FROM v_me THEN
        RAISE EXCEPTION 'only the manager removes others' USING ERRCODE = '42501';
    END IF;
    UPDATE conversation_member SET left_at = now()
     WHERE conversation_id = p_conversation AND user_id = p_user AND left_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'not a member' USING ERRCODE = 'MSGNM';
    END IF;
    -- the manager leaving hands over to the earliest-added active member still in
    SELECT manager_id INTO v_manager FROM conversation WHERE id = p_conversation;
    IF v_manager = p_user THEN
        UPDATE conversation SET manager_id = (
            SELECT m.user_id FROM conversation_member m
              JOIN app_user u ON u.id = m.user_id AND u.is_active AND u.deleted_at IS NULL
             WHERE m.conversation_id = p_conversation AND m.left_at IS NULL
             ORDER BY m.added_at, m.user_id LIMIT 1)
         WHERE id = p_conversation;
    END IF;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('conversation', p_conversation,
            CASE WHEN p_user = v_me THEN 'conversation.member_left' ELSE 'conversation.member_removed' END,
            v_me, jsonb_build_object('member', p_user));
END $fn$""",
    f"""CREATE FUNCTION group_rename(p_conversation uuid, p_name text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_me uuid := app_current_user_id(); v_kind text;
BEGIN
{_STAFF_CHECK}
    SELECT kind INTO v_kind FROM conversation WHERE id = p_conversation FOR UPDATE;
    IF NOT FOUND OR (v_kind = 'group' AND NOT EXISTS (
            SELECT 1 FROM conversation_member WHERE conversation_id = p_conversation
               AND user_id = v_me AND left_at IS NULL))
       OR (v_kind = 'direct' AND NOT EXISTS (
            SELECT 1 FROM conversation WHERE id = p_conversation AND v_me IN (user_a, user_b))) THEN
        RAISE EXCEPTION 'not a conversation you are in' USING ERRCODE = 'MSGNF';
    END IF;
    IF v_kind = 'direct' THEN
        RAISE EXCEPTION 'only a group has a name' USING ERRCODE = 'MSGDR';
    END IF;
    IF conversation_acting_manager(p_conversation) IS DISTINCT FROM v_me THEN
        RAISE EXCEPTION 'only the manager renames' USING ERRCODE = '42501';
    END IF;
    UPDATE conversation SET name = btrim(p_name) WHERE id = p_conversation;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('conversation', p_conversation, 'conversation.renamed', v_me, jsonb_build_object('name', btrim(p_name)));
END $fn$""",
    # Per group I am in: name, current member count, acting manager, my mark (plan review R-1)
    """CREATE FUNCTION conversation_groups()
RETURNS TABLE (conversation_id uuid, name text, member_count int, manager_id uuid, my_read_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT c.id, c.name,
           (SELECT count(*)::int FROM conversation_member x WHERE x.conversation_id = c.id AND x.left_at IS NULL),
           conversation_acting_manager(c.id), m.read_at
      FROM conversation_member m JOIN conversation c ON c.id = m.conversation_id AND c.kind = 'group'
     WHERE m.user_id = app_current_user_id() AND m.left_at IS NULL
$fn$""",
    # Everyone who has been in a group I am in; nothing for anyone else
    """CREATE FUNCTION conversation_members(p_conversation uuid)
RETURNS TABLE (id uuid, full_name text, role_name text, org_unit_name text, is_active boolean,
               added_at timestamptz, left_at timestamptz, is_manager boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT u.id, u.full_name::text, r.name::text, ou.name::text, u.is_active AND u.deleted_at IS NULL,
           m.added_at, m.left_at, u.id = conversation_acting_manager(p_conversation)
      FROM conversation_member m
      JOIN app_user u ON u.id = m.user_id
      LEFT JOIN role r ON r.id = u.role_id
      LEFT JOIN org_unit ou ON ou.id = u.org_unit_id
     WHERE m.conversation_id = p_conversation
       AND EXISTS (SELECT 1 FROM conversation_member me WHERE me.conversation_id = p_conversation
                     AND me.user_id = app_current_user_id() AND me.left_at IS NULL)
     ORDER BY m.left_at IS NOT NULL, m.added_at, u.full_name
$fn$""",
]

GRANTED = ["conversation_manager(uuid)", "group_create(text, uuid[])", "group_add(uuid, uuid[])",
           "group_leave(uuid, uuid)", "group_rename(uuid, text)", "conversation_groups()",
           "conversation_members(uuid)"]
INTERNAL = ["conversation_acting_manager(uuid)"]

# 024's bodies, for the downgrade
_m024_spec = importlib.util.spec_from_file_location("m024_for_058", Path(__file__).with_name("024_messages.py"))
assert _m024_spec is not None and _m024_spec.loader is not None
_m024 = importlib.util.module_from_spec(_m024_spec)
_m024_spec.loader.exec_module(_m024)


def upgrade() -> None:
    for stmt in TABLES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE conversation_member ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY conversation_sel ON conversation")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    op.execute(floor.policy_sql("conversation_member"))
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED + INTERNAL:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {sig} FROM PUBLIC")
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    for sig in reversed(GRANTED + INTERNAL):
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DELETE FROM activity_event WHERE entity_type = 'conversation'")
    op.execute("DELETE FROM conversation WHERE kind = 'group'")
    stamp = next(f for f in _m024.FUNCTIONS if f.startswith("CREATE FUNCTION message_stamp("))
    mark = next(f for f in _m024.FUNCTIONS if f.startswith("CREATE FUNCTION conversation_mark_read("))
    op.execute(stamp.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute(mark.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1))
    op.execute("DROP POLICY conversation_sel ON conversation")
    op.execute(next(stmt for t, stmt in _m024.HAND_POLICIES if t == "conversation"))
    op.execute("DROP TABLE conversation_member")
    op.execute("ALTER TABLE conversation DROP CONSTRAINT ck_conversation_pair")
    op.execute("ALTER TABLE conversation ADD CONSTRAINT ck_conversation_pair CHECK (user_a < user_b)")
    op.execute("ALTER TABLE conversation ALTER COLUMN user_a SET NOT NULL, ALTER COLUMN user_b SET NOT NULL")
    op.execute("ALTER TABLE conversation DROP COLUMN manager_id, DROP COLUMN name, DROP COLUMN kind")
