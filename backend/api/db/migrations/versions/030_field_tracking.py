"""030: field tracking (FS-021, ADR-044).

Duty sessions, background location points, the newest position per person,
visits with photos, consent, an effective-dated policy and a log of every look
at someone else's whereabouts.

- **No ScopeSpec.** The generator writes one table per module, and its write
  branches check the office column, not the person (review B-1). Every table here
  is hand-written on `app_scope('tracking')` and declared in `HAND_POLICIES`.
- **A person writes only their own rows**, whatever their scope: every INSERT
  and UPDATE policy checks `user_id = me`. Reads follow the scope: own `user_id`,
  org subtree `org_unit_id` (stamped from the duty, so a transfer mid-duty does not
  split a day), global.
- **`location_point` has no UPDATE or DELETE grant.** The nightly purge is a
  system definer.
- **Events:** `visit`, `duty_session` and `tracking_consent` join
  `activity_event_sel` (api/authz/activity.py). `lead_timeline()` shows visit
  events to staff only, like tasks (FS-014 B-4). No payload carries a position.
- **Deactivation ends an open duty** (trigger on `app_user`, review EC-5).
- The `tracking` permission rows from RBAC.md §6.1. The board holds none (§6.4).

Revision ID: 030_field_tracking
Revises: 029_notification_fixes
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "030_field_tracking"
down_revision: str | None = "029_notification_fixes"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"
SYSTEM_USER_ID = "26809c63-290b-5bd9-9d6a-a717dc0b32e3"  # 005


def _load(name: str) -> ModuleType:
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"mig_{name}_for_030", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"030: migration {name} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"030: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


ENUMS = [
    "CREATE TYPE duty_end_reason AS ENUM ('user', 'auto', 'consent_withdrawn', 'deactivated')",
    "CREATE TYPE visit_outcome AS ENUM ('met', 'not_available', 'follow_up', 'other')",
]

_LAT = "numeric(9,6) CHECK ({c} BETWEEN -90 AND 90)"
_LNG = "numeric(9,6) CHECK ({c} BETWEEN -180 AND 180)"
_ACC = "numeric(8,1) CHECK ({c} IS NULL OR {c} >= 0)"


def _pos(prefix: str, required: bool) -> str:
    nn = " NOT NULL" if required else ""
    return (f"    {prefix}_lat {_LAT.format(c=prefix + '_lat')}{nn},\n"
            f"    {prefix}_lng {_LNG.format(c=prefix + '_lng')}{nn},\n"
            f"    {prefix}_accuracy_m {_ACC.format(c=prefix + '_accuracy_m')},\n")


TABLES = [
    """CREATE TABLE tracking_policy (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    effective_from timestamptz NOT NULL UNIQUE,
    interval_seconds int NOT NULL CHECK (interval_seconds BETWEEN 15 AND 3600),
    distance_filter_m int NOT NULL CHECK (distance_filter_m BETWEEN 0 AND 5000),
    work_start time NOT NULL,
    work_end time NOT NULL,
    work_days smallint[] NOT NULL CHECK (work_days <@ '{1,2,3,4,5,6,7}'::smallint[] AND cardinality(work_days) BETWEEN 1 AND 7),
    retention_days int NOT NULL CHECK (retention_days BETWEEN 7 AND 3650),
    visit_photo_required boolean NOT NULL DEFAULT false,
    consent_version text NOT NULL CHECK (consent_version ~ '^[A-Za-z0-9._-]{1,20}$'),
    consent_text text NOT NULL CHECK (length(consent_text) BETWEEN 1 AND 10000),
    created_by uuid REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_tracking_policy_hours CHECK (work_end > work_start)
)""",
    """CREATE TABLE tracking_consent (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES app_user(id),
    org_unit_id uuid REFERENCES org_unit(id),
    version text NOT NULL CHECK (version ~ '^[A-Za-z0-9._-]{1,20}$'),
    accepted boolean NOT NULL,
    at timestamptz NOT NULL DEFAULT now()
)""",
    f"""CREATE TABLE duty_session (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app_user(id),
    org_unit_id uuid REFERENCES org_unit(id),
    device_id text NOT NULL CHECK (length(device_id) BETWEEN 8 AND 100),
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    end_reason duty_end_reason,
{_pos('start', False)}{_pos('end', False)}    outside_hours boolean NOT NULL DEFAULT false,
    last_point_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_duty_session_ended CHECK ((ended_at IS NULL) = (end_reason IS NULL)),
    CONSTRAINT ck_duty_session_order CHECK (ended_at IS NULL OR ended_at >= started_at)
)""",
    """CREATE TABLE location_point (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app_user(id),
    org_unit_id uuid REFERENCES org_unit(id),
    duty_id uuid NOT NULL REFERENCES duty_session(id),
    device_id text NOT NULL CHECK (length(device_id) BETWEEN 8 AND 100),
    recorded_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    clock_skew_s int NOT NULL DEFAULT 0,
    lat numeric(9,6) NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng numeric(9,6) NOT NULL CHECK (lng BETWEEN -180 AND 180),
    accuracy_m numeric(8,1) CHECK (accuracy_m IS NULL OR accuracy_m >= 0),
    speed_mps numeric(7,2),
    heading numeric(5,1),
    altitude_m numeric(8,1),
    battery_pct smallint CHECK (battery_pct IS NULL OR battery_pct BETWEEN 0 AND 100),
    is_mock boolean NOT NULL DEFAULT false
)""",
    # a copy, not a reference: the purge must never be blocked by it (review EC-11)
    """CREATE TABLE tracking_latest (
    user_id uuid PRIMARY KEY REFERENCES app_user(id),
    org_unit_id uuid REFERENCES org_unit(id),
    duty_id uuid,
    recorded_at timestamptz NOT NULL,
    lat numeric(9,6) NOT NULL,
    lng numeric(9,6) NOT NULL,
    accuracy_m numeric(8,1),
    battery_pct smallint,
    is_mock boolean NOT NULL DEFAULT false
)""",
    f"""CREATE TABLE visit (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES app_user(id),
    org_unit_id uuid REFERENCES org_unit(id),
    duty_id uuid REFERENCES duty_session(id),
    lead_id uuid REFERENCES lead(id),
    partner_id uuid REFERENCES channel_partner(id),
    task_id uuid REFERENCES task(id),
    place_name text CHECK (place_name IS NULL OR length(btrim(place_name)) BETWEEN 1 AND 200),
    checkin_at timestamptz NOT NULL,
{_pos('checkin', True)}    checkout_at timestamptz,
{_pos('checkout', False)}    outcome visit_outcome,
    note text CHECK (note IS NULL OR length(note) <= 2000),
    auto_closed boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_visit_one_party CHECK (lead_id IS NULL OR partner_id IS NULL),
    CONSTRAINT ck_visit_somewhere CHECK (lead_id IS NOT NULL OR partner_id IS NOT NULL OR place_name IS NOT NULL),
    CONSTRAINT ck_visit_order CHECK (checkout_at IS NULL OR checkout_at >= checkin_at),
    CONSTRAINT ck_visit_open CHECK (checkout_at IS NOT NULL OR (outcome IS NULL AND NOT auto_closed))
)""",
    """CREATE TABLE visit_photo (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    visit_id uuid NOT NULL REFERENCES visit(id),
    storage_key text NOT NULL,
    content_type text NOT NULL,
    filename text CHECK (filename IS NULL OR length(filename) <= 255),
    size_bytes int NOT NULL CHECK (size_bytes > 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    uploaded_by uuid NOT NULL REFERENCES app_user(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_visit_photo_hash UNIQUE (visit_id, sha256)
)""",
    """CREATE TABLE tracking_view_log (
    id bigserial PRIMARY KEY,
    viewer_id uuid NOT NULL REFERENCES app_user(id),
    subject_user_id uuid REFERENCES app_user(id),
    what text NOT NULL CHECK (what IN ('route', 'visits', 'team')),
    viewed_date date,
    viewed_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_tracking_view_log_subject CHECK ((what = 'team') = (subject_user_id IS NULL))
)""",
]

INDEXES = [
    "CREATE INDEX ix_tracking_consent_user ON tracking_consent (user_id, at DESC)",
    "CREATE INDEX ix_tracking_consent_org_unit ON tracking_consent (org_unit_id)",
    "CREATE UNIQUE INDEX uq_duty_session_open ON duty_session (user_id) WHERE ended_at IS NULL",
    "CREATE INDEX ix_duty_session_user ON duty_session (user_id, started_at)",
    "CREATE INDEX ix_duty_session_org_unit ON duty_session (org_unit_id)",
    "CREATE INDEX ix_location_point_user ON location_point (user_id, recorded_at)",
    "CREATE INDEX ix_location_point_recorded ON location_point (recorded_at)",
    "CREATE INDEX ix_location_point_duty ON location_point (duty_id)",
    "CREATE INDEX ix_location_point_org_unit ON location_point (org_unit_id)",
    "CREATE INDEX ix_tracking_latest_org_unit ON tracking_latest (org_unit_id)",
    "CREATE UNIQUE INDEX uq_visit_open ON visit (user_id) WHERE checkout_at IS NULL",
    "CREATE INDEX ix_visit_user ON visit (user_id, checkin_at)",
    "CREATE INDEX ix_visit_org_unit ON visit (org_unit_id)",
    "CREATE INDEX ix_visit_lead ON visit (lead_id)",
    "CREATE INDEX ix_visit_partner ON visit (partner_id)",
    "CREATE INDEX ix_visit_task ON visit (task_id)",
    "CREATE INDEX ix_visit_duty ON visit (duty_id)",
    "CREATE INDEX ix_visit_photo_visit ON visit_photo (visit_id)",
    "CREATE INDEX ix_visit_photo_uploaded_by ON visit_photo (uploaded_by)",
    "CREATE INDEX ix_tracking_view_log_subject ON tracking_view_log (subject_user_id, viewed_at)",
    "CREATE INDEX ix_tracking_view_log_viewer ON tracking_view_log (viewer_id)",
    "CREATE INDEX ix_tracking_policy_created_by ON tracking_policy (created_by)",
]

RLS_TABLES = ("tracking_policy", "tracking_consent", "duty_session", "location_point",
              "tracking_latest", "visit", "visit_photo", "tracking_view_log")

# tests/db/migration_grants.py reads these two, as it does every migration's
GRANTS: dict[str, str] = {
    "tracking_policy": "SELECT, INSERT",
    "tracking_consent": "SELECT, INSERT",
    "duty_session": "SELECT, INSERT, UPDATE (ended_at, end_reason, end_lat, end_lng, end_accuracy_m, last_point_at)",
    "location_point": "SELECT, INSERT",
    "tracking_latest": "SELECT, INSERT, UPDATE (org_unit_id, duty_id, recorded_at, lat, lng, accuracy_m, battery_pct, is_mock)",
    "visit": "SELECT, INSERT, UPDATE (checkout_at, checkout_lat, checkout_lng, checkout_accuracy_m, outcome, note)",
    "visit_photo": "SELECT, INSERT",
    "tracking_view_log": "SELECT, INSERT",
}

_ME = "(SELECT app_current_user_id())"
_SCOPE = "(SELECT app_scope('tracking'))"
_VIEW = "(SELECT app_has_permission('tracking', 'view'))"
_CREATE = "(SELECT app_has_permission('tracking', 'create'))"
_EDIT = "(SELECT app_has_permission('tracking', 'edit'))"
_SUBTREE = "(SELECT descendant_id FROM org_closure WHERE ancestor_id = (SELECT app_current_org_unit()))"
_READ = (f"(({_SCOPE} = 'own' AND user_id = {_ME})\n"
         f"  OR ({_SCOPE} = 'org_subtree' AND org_unit_id IN {_SUBTREE})\n"
         f"  OR ({_SCOPE} = 'global'))")


def _person_table(t: str, *, update: bool) -> list[tuple[str, str]]:
    """A person's tracking rows: read by scope, written only by the person."""
    out = [
        (t, f"CREATE POLICY {t}_sel ON {t} FOR SELECT USING (\n  {_READ}\n)"),
        (t, f"CREATE POLICY {t}_res_perm ON {t} AS RESTRICTIVE FOR SELECT USING (\n  {_VIEW}\n)"),
        (t, f"CREATE POLICY {t}_ins ON {t} FOR INSERT WITH CHECK (\n  user_id = {_ME}\n)"),
        (t, f"CREATE POLICY {t}_ins_perm ON {t} AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_CREATE}\n)"),
    ]
    if update:
        out += [
            (t, f"CREATE POLICY {t}_upd ON {t} FOR UPDATE USING (\n  user_id = {_ME}\n) WITH CHECK (\n  user_id = {_ME}\n)"),
            (t, f"CREATE POLICY {t}_upd_perm ON {t} AS RESTRICTIVE FOR UPDATE USING (\n  {_EDIT}\n)"),
        ]
    return out


# a visit names something the caller can see (rule 8); a dealer through FS-020's
# document arm too
_VISIT_PARENTS = ("(lead_id IS NULL OR EXISTS (SELECT 1 FROM lead p WHERE p.id = lead_id))\n"
                  "  AND (partner_id IS NULL OR EXISTS (SELECT 1 FROM channel_partner p WHERE p.id = partner_id)\n"
                  "       OR partner_on_visible_document(partner_id))\n"
                  "  AND (task_id IS NULL OR EXISTS (SELECT 1 FROM task p WHERE p.id = task_id))")

ACTIVITY_POLICY = """CREATE POLICY activity_event_sel ON activity_event FOR SELECT USING (
  CASE entity_type
    WHEN 'app_user' THEN entity_id = (SELECT app_current_user_id()) OR EXISTS (SELECT 1 FROM app_user u WHERE u.id = entity_id)
    WHEN 'channel_partner' THEN EXISTS (SELECT 1 FROM channel_partner c WHERE c.id = partner_id)
    WHEN 'lead' THEN EXISTS (SELECT 1 FROM lead c WHERE c.id = lead_id)
    WHEN 'org_unit' THEN EXISTS (SELECT 1 FROM org_unit c WHERE c.id = entity_id)
    WHEN 'territory' THEN EXISTS (SELECT 1 FROM territory c WHERE c.id = entity_id)
    WHEN 'quotation' THEN EXISTS (SELECT 1 FROM quotation c WHERE c.id = entity_id)
    WHEN 'sales_order' THEN EXISTS (SELECT 1 FROM sales_order c WHERE c.id = entity_id)
    WHEN 'lead_qr_code' THEN EXISTS (SELECT 1 FROM lead_qr_code c WHERE c.id = entity_id)
    WHEN 'task' THEN EXISTS (SELECT 1 FROM task c WHERE c.id = entity_id)
    WHEN 'meeting_minutes' THEN EXISTS (SELECT 1 FROM meeting_minutes c WHERE c.id = entity_id)
    WHEN 'complaint' THEN EXISTS (SELECT 1 FROM complaint c WHERE c.id = entity_id)
    WHEN 'subsidy_application' THEN EXISTS (SELECT 1 FROM subsidy_application c WHERE c.id = entity_id)
    WHEN 'scheme' THEN EXISTS (SELECT 1 FROM scheme c WHERE c.id = entity_id)
    WHEN 'marketing_order' THEN EXISTS (SELECT 1 FROM marketing_order c WHERE c.id = entity_id)
    WHEN 'reward_rule' THEN EXISTS (SELECT 1 FROM reward_rule c WHERE c.id = entity_id)
    WHEN 'gift' THEN EXISTS (SELECT 1 FROM gift c WHERE c.id = entity_id)
    WHEN 'reward_setting' THEN EXISTS (SELECT 1 FROM reward_setting c WHERE c.id = entity_id)
    WHEN 'visit' THEN EXISTS (SELECT 1 FROM visit c WHERE c.id = entity_id)
    WHEN 'duty_session' THEN EXISTS (SELECT 1 FROM duty_session c WHERE c.id = entity_id)
    WHEN 'tracking_consent' THEN EXISTS (SELECT 1 FROM tracking_consent c WHERE c.id = entity_id)
    ELSE (SELECT app_is_system())
  END
)"""

HAND_POLICIES: list[tuple[str, str]] = [
    # every staff caller reads the policy in force, tracking or not: /me/tracking-config
    # answers tracking_allowed=false from it (review recommendation)
    ("tracking_policy", "CREATE POLICY tracking_policy_sel ON tracking_policy FOR SELECT USING (\n  (SELECT app_current_user_id()) IS NOT NULL AND (SELECT app_current_partner()) IS NULL\n)"),
    ("tracking_policy", f"CREATE POLICY tracking_policy_ins ON tracking_policy FOR INSERT WITH CHECK (\n  (SELECT app_has_permission('masters', 'edit'))\n  AND created_by = {_ME}\n)"),
    # one's own consent is always readable, so the config can say what was accepted
    ("tracking_consent", f"CREATE POLICY tracking_consent_sel ON tracking_consent FOR SELECT USING (\n  user_id = {_ME}\n  OR ({_VIEW} AND {_READ})\n)"),
    ("tracking_consent", f"CREATE POLICY tracking_consent_ins ON tracking_consent FOR INSERT WITH CHECK (\n  user_id = {_ME}\n)"),
    ("tracking_consent", f"CREATE POLICY tracking_consent_ins_perm ON tracking_consent AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_CREATE}\n)"),
    *_person_table("duty_session", update=True),
    *_person_table("location_point", update=False),
    *_person_table("tracking_latest", update=True),
    ("visit", f"CREATE POLICY visit_sel ON visit FOR SELECT USING (\n  {_READ}\n)"),
    ("visit", f"CREATE POLICY visit_res_perm ON visit AS RESTRICTIVE FOR SELECT USING (\n  {_VIEW}\n)"),
    ("visit", f"CREATE POLICY visit_ins ON visit FOR INSERT WITH CHECK (\n  user_id = {_ME}\n  AND {_VISIT_PARENTS}\n)"),
    ("visit", f"CREATE POLICY visit_ins_perm ON visit AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_CREATE}\n)"),
    ("visit", f"CREATE POLICY visit_upd ON visit FOR UPDATE USING (\n  user_id = {_ME}\n) WITH CHECK (\n  user_id = {_ME}\n)"),
    ("visit", f"CREATE POLICY visit_upd_perm ON visit AS RESTRICTIVE FOR UPDATE USING (\n  {_EDIT}\n)"),
    ("visit_photo", "CREATE POLICY visit_photo_sel ON visit_photo FOR SELECT USING (\n  EXISTS (SELECT 1 FROM visit v WHERE v.id = visit_id)\n)"),
    ("visit_photo", f"CREATE POLICY visit_photo_ins ON visit_photo FOR INSERT WITH CHECK (\n  uploaded_by = {_ME}\n  AND EXISTS (SELECT 1 FROM visit v WHERE v.id = visit_id AND v.user_id = {_ME})\n)"),
    ("visit_photo", f"CREATE POLICY visit_photo_ins_perm ON visit_photo AS RESTRICTIVE FOR INSERT WITH CHECK (\n  {_CREATE}\n)"),
    # the log is written by any reader of whereabouts and read only company-wide
    ("tracking_view_log", f"CREATE POLICY tracking_view_log_sel ON tracking_view_log FOR SELECT USING (\n  {_VIEW} AND {_SCOPE} = 'global'\n)"),
    ("tracking_view_log", f"CREATE POLICY tracking_view_log_ins ON tracking_view_log FOR INSERT WITH CHECK (\n  viewer_id = {_ME} AND {_VIEW}\n)"),
    ("activity_event", ACTIVITY_POLICY),
]

# RBAC.md §6.1's tracking row (FS-021 B-2); the board has none (§6.4, GAP-195)
PERMISSIONS = [("field_officer", "own"), ("district_manager", "org_subtree"),
               ("state_manager", "org_subtree"), ("regional_manager", "org_subtree"),
               ("admin_sales", "global"), ("md_ceo", "global")]


def _permission_seed() -> str:
    rows = ", ".join(f"('{code}', '{action}', '{scope}')" for code, scope in PERMISSIONS
                     for action in ("view", "create", "edit"))
    return f"""INSERT INTO role_permission (role_id, module, action, scope)
SELECT r.id, 'tracking', CAST(v.action AS permission_action), CAST(v.scope AS permission_scope)
  FROM (VALUES {rows}) AS v(code, action, scope)
  JOIN role r ON r.code = v.code
ON CONFLICT (role_id, module, action) DO NOTHING"""


# The stand-ins: GAP-191 (hours), GAP-192 (photo), GAP-193 (consent), GAP-194 (retention)
POLICY_SEED = """INSERT INTO tracking_policy (effective_from, interval_seconds, distance_filter_m, work_start,
    work_end, work_days, retention_days, visit_photo_required, consent_version, consent_text)
VALUES ('2026-01-01T00:00:00+05:30', 120, 50, '09:00', '19:00', '{1,2,3,4,5,6}', 90, false, 'v1',
'While you are on duty, this app records your phone''s location in the background and sends it to Polysil. Your manager can see where you are and the route you took that day. Nothing is recorded when you are off duty. Locations are kept for 90 days. Every time someone looks at your route, it is logged. You can withdraw this consent at any time in the app; tracking stops when you do.')"""

FUNCTIONS = [
    # The worker's reads and writes, each guarded on the system principal (review B-4).
    # The worker decides in Python (api/domain/tracking.auto_end); this only applies.
    """CREATE FUNCTION tracking_open_duties()
RETURNS TABLE (id uuid, user_id uuid, started_at timestamptz, last_point_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'system only' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY SELECT d.id, d.user_id, d.started_at, d.last_point_at
                   FROM duty_session d WHERE d.ended_at IS NULL;
END $fn$""",
    f"""CREATE FUNCTION tracking_auto_end(p_id uuid, p_ended_at timestamptz) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE d duty_session%ROWTYPE;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'system only' USING ERRCODE = '42501';
    END IF;
    UPDATE duty_session SET ended_at = GREATEST(started_at, p_ended_at), end_reason = 'auto'
     WHERE id = p_id AND ended_at IS NULL
    RETURNING * INTO d;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
    VALUES ('duty_session', d.id, 'duty.ended', '{SYSTEM_USER_ID}',
            jsonb_build_object('end_reason', 'auto', 'user_id', d.user_id));
    RETURN true;
END $fn$""",
    f"""CREATE FUNCTION visit_auto_close(p_now timestamptz) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v record; n int := 0;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'system only' USING ERRCODE = '42501';
    END IF;
    FOR v IN UPDATE visit SET checkout_at = checkin_at + interval '12 hours', auto_closed = true
              WHERE checkout_at IS NULL AND checkin_at <= p_now - interval '12 hours'
              RETURNING id, lead_id, user_id LOOP
        INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
        VALUES ('visit', v.id, v.lead_id, 'visit.checked_out', '{SYSTEM_USER_ID}',
                jsonb_build_object('auto_closed', true, 'user_id', v.user_id));
        n := n + 1;
    END LOOP;
    RETURN n;
END $fn$""",
    # chunked, so a large backlog never holds one long lock (review EC-11)
    """CREATE FUNCTION location_point_purge(p_batch int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_days int; n int;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'system only' USING ERRCODE = '42501';
    END IF;
    SELECT retention_days INTO v_days FROM tracking_policy
     WHERE effective_from <= now() ORDER BY effective_from DESC LIMIT 1;
    IF v_days IS NULL THEN
        RETURN 0;
    END IF;
    DELETE FROM location_point WHERE id IN (
        SELECT id FROM location_point WHERE recorded_at < now() - make_interval(days => v_days)
         ORDER BY recorded_at LIMIT GREATEST(1, LEAST(p_batch, 50000)));
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $fn$""",
    # review EC-5: a deactivated user's open duty ends with them, whoever deactivates
    """CREATE FUNCTION duty_end_on_deactivate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE d duty_session%ROWTYPE;
BEGIN
    UPDATE duty_session SET ended_at = GREATEST(started_at, now()), end_reason = 'deactivated'
     WHERE user_id = NEW.id AND ended_at IS NULL
    RETURNING * INTO d;
    IF FOUND THEN
        INSERT INTO activity_event (entity_type, entity_id, kind, actor_id, payload)
        VALUES ('duty_session', d.id, 'duty.ended', app_current_user_id(),
                jsonb_build_object('end_reason', 'deactivated', 'user_id', d.user_id));
    END IF;
    RETURN NULL;
END $fn$""",
    "CREATE TRIGGER trg_app_user_duty_end AFTER UPDATE OF is_active ON app_user FOR EACH ROW "
    "WHEN (OLD.is_active AND NOT NEW.is_active) EXECUTE FUNCTION duty_end_on_deactivate()",
]

SYSTEM_ONLY = ["tracking_open_duties()", "tracking_auto_end(uuid, timestamptz)",
               "visit_auto_close(timestamptz)", "location_point_purge(int)"]


def _timeline_before() -> str:
    (f,) = [s for s in _load("019_complaints")._after() if "FUNCTION lead_timeline(" in s]
    return str(f)


def timeline_after() -> str:
    # visits on a lead are for staff, like tasks and minutes (FS-014 B-4)
    return _replace(_timeline_before(),
                    "           AND (entity_type <> 'complaint' OR complaint_visible(entity_id))",
                    "           AND (entity_type <> 'complaint' OR complaint_visible(entity_id))\n"
                    "           AND (entity_type <> 'visit' OR app_current_partner() IS NULL)")


def upgrade() -> None:
    for stmt in ENUMS + TABLES + INDEXES:
        op.execute(stmt)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SEQUENCE tracking_view_log_id_seq TO {APP_ROLE}")
    for t in RLS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    for table, stmt in HAND_POLICIES:
        if table != "activity_event":
            op.execute(stmt)
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    op.execute(ACTIVITY_POLICY)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute(timeline_after())
    op.execute(_permission_seed())
    op.execute(POLICY_SEED)
    # created functions are PUBLIC-executable until this runs (006, 028)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
    for sig in SYSTEM_ONLY:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP POLICY activity_event_sel ON activity_event")
    # 030 runs after session B's chain: the policy before it is 038's
    op.execute(_load("038_marketing_material").ACTIVITY_SEL)
    op.execute(_timeline_before())
    op.execute("DELETE FROM activity_event WHERE entity_type IN ('visit', 'duty_session', 'tracking_consent')")
    op.execute("DELETE FROM role_permission WHERE module = 'tracking'")
    op.execute("DROP TRIGGER IF EXISTS trg_app_user_duty_end ON app_user")
    op.execute("DROP FUNCTION IF EXISTS duty_end_on_deactivate()")
    for sig in SYSTEM_ONLY:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for t in ("tracking_view_log", "visit_photo", "visit", "tracking_latest", "location_point",
              "duty_session", "tracking_consent", "tracking_policy"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("DROP TYPE IF EXISTS visit_outcome")
    op.execute("DROP TYPE IF EXISTS duty_end_reason")
