"""040: lead small gaps (FS-035).

- `lead.dormant_from_stage`: the stage a dormant lead returns to on reopen. The CHECK
  ties it to `stage = 'dormant'`; `trg_lead_dormant_clear` clears it on every move out
  of dormant, so a merge of a dormant loser, a reopen and a loss all satisfy the CHECK
  without each path knowing (plan review B-1).
- `lead_dormant_sweep(now, limit)`: the nightly move to dormant, a plain UPDATE so
  every trigger on `lead` fires as on any stage change. Candidates are locked
  `FOR UPDATE SKIP LOCKED` and the UPDATE re-checks the stage, so a lead a person is
  changing right now is left for tomorrow (plan review B-2).
- `lead_owner_unit(user)`: the sales office of a user the caller may assign a lead
  to, for GAP-061. A line manager cannot read app_user, so this is a definer.
- `dormant_after_days` (60, a stand-in, GAP-339) joins `lead_score_rule`.

Also the PR 11 review of 033 to 039 (findings 1, 4 and the index):
- `partner_visible_to_caller(p)`: 028's pasted partners guard, evaluated over the claim
  inside a definer. A definer bypasses RLS, and an invoker function nested in one runs
  as the owner (ISS-066), so `EXISTS (SELECT ... FROM channel_partner)` there sees every
  dealer. `marketing_order_create()` and `scheme_standing()` now ask this instead, and
  `marketing_order_create()` checks the office against the caller too.
- `scheme_lock_on_use()`: every row that records a scheme's use (a benefit, a credit, a
  ledger row) takes the scheme FOR SHARE first. An edit's BEFORE UPDATE trigger then
  waits for the use to commit and sees it in `scheme_used()` (rule 16). A target change
  takes the scheme FOR UPDATE before its own check.
- `ix_dealer_commission_application`: the commission policy's column, unindexed but
  for a partial unique index (CLAUDE.md 4.1 rule 9).

Revision ID: 040_lead_small_gaps
Revises: 039_subsidy_follow_ups
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "040_lead_small_gaps"
down_revision: str | None = "039_subsidy_follow_ups"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"


def _load(stem: str) -> ModuleType:
    path = next(Path(__file__).parent.glob(f"{stem}_*.py"))
    spec = importlib.util.spec_from_file_location(f"mig_{stem}_for_040", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"040: migration {stem} not found beside it")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _replace(text: str, old: str, new: str) -> str:
    # an exception, not an assert: python -O drops asserts
    if text.count(old) != 1:
        raise RuntimeError(f"040: anchor not found once: {old[:70]!r}")
    return text.replace(old, new)


def _original(stem: str, name: str) -> str:
    """The CREATE FUNCTION text of `name` as migration `stem` wrote it."""
    found = [t for t in _load(stem).FUNCTIONS if f"FUNCTION {name}(" in t]
    if len(found) != 1:
        raise RuntimeError(f"040: {name} not found once in {stem}")
    return found[0]

# Nothing new on any table's grants or policies: lead_qr_code's UPDATE is 015's.
GRANTS: dict[str, str] = {}
HAND_POLICIES: list[tuple[str, str]] = []

OPEN_STAGES = "('new', 'contacted', 'qualified', 'quoted', 'negotiation')"

FUNCTIONS = [
    """CREATE FUNCTION lead_dormant_clear() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    IF NEW.stage IS DISTINCT FROM 'dormant' THEN
        NEW.dormant_from_stage := NULL;
    END IF;
    RETURN NEW;
END $fn$""",

    f"""CREATE FUNCTION lead_dormant_sweep(p_now timestamptz, p_limit int) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_days int; v_cut timestamptz; v_me uuid; r record; v_count int := 0;
BEGIN
    IF NOT app_is_system() THEN
        RAISE EXCEPTION 'only the system principal sweeps leads' USING ERRCODE = '42501';
    END IF;
    SELECT round(value)::int INTO v_days FROM lead_score_rule
     WHERE key = 'dormant_after_days' AND deleted_at IS NULL;
    IF v_days IS NULL OR v_days <= 0 THEN
        RETURN 0;
    END IF;
    v_cut := p_now - make_interval(days => v_days);
    v_me := app_current_user_id();
    FOR r IN
        SELECT l.id, l.stage::text AS stage FROM lead l
         WHERE l.stage IN {OPEN_STAGES} AND l.deleted_at IS NULL
           AND l.last_activity_at < v_cut
           -- a person's event is activity; the System's (a quotation expiring) is not
           AND NOT EXISTS (SELECT 1 FROM activity_event ae
                            WHERE ae.lead_id = l.id AND ae.occurred_at >= v_cut
                              AND ae.actor_id IS DISTINCT FROM v_me)
           -- a follow-up booked or an answer awaited is not neglect (GAP-340)
           AND NOT EXISTS (SELECT 1 FROM task t WHERE t.lead_id = l.id AND t.status = 'open')
           AND NOT EXISTS (SELECT 1 FROM quotation q
                            WHERE q.lead_id = l.id AND q.deleted_at IS NULL
                              AND q.superseded_by_id IS NULL
                              AND q.status IN ('sent', 'viewed', 'negotiation'))
         ORDER BY l.last_activity_at, l.id
         LIMIT p_limit
         FOR UPDATE OF l SKIP LOCKED
    LOOP
        UPDATE lead SET stage = 'dormant', dormant_from_stage = stage
         WHERE id = r.id AND stage IN {OPEN_STAGES} AND deleted_at IS NULL;
        IF FOUND THEN
            INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload)
            VALUES ('lead', r.id, r.id, 'lead.stage_changed', v_me,
                    jsonb_build_object('from', r.stage, 'to', 'dormant', 'reason', 'no_activity',
                                       'days', v_days, 'actor_name', 'System'));
            v_count := v_count + 1;
        END IF;
    END LOOP;
    RETURN v_count;
END $fn$""",

    """CREATE FUNCTION lead_owner_unit(p_user uuid) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v uuid;
BEGIN
    -- the same gate assign already passes: a user the caller may not assign reads nothing
    IF NOT authz_user_assignable('leads', p_user) THEN
        RETURN NULL;
    END IF;
    SELECT ou.id INTO v FROM app_user u JOIN org_unit ou ON ou.id = u.org_unit_id
     WHERE u.id = p_user AND ou.territory_id IS NOT NULL;
    RETURN v;
END $fn$""",
]


# ── the PR 11 review of 033 to 039 ──────────────────────────────────────────

def _visible_fn() -> str:
    guard = _load("028").PARTNERS_GUARD
    return f"""CREATE FUNCTION partner_visible_to_caller(p_partner uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    -- 028's partners guard, pasted: the caller's own reach, not the owner's (ISS-066)
    SELECT EXISTS (SELECT 1 FROM channel_partner WHERE id = p_partner AND {guard})
$fn$"""


_MKT_PARTNER_OLD = """           AND (v_caller_partner IS NOT NULL OR EXISTS (SELECT 1 FROM channel_partner WHERE id = v_partner));"""
_MKT_PARTNER_NEW = """           AND (v_caller_partner IS NOT NULL OR partner_visible_to_caller(v_partner));"""
_MKT_OFFICE_OLD = """    IF NOT EXISTS (SELECT 1 FROM org_unit WHERE id = p_office) THEN
        RAISE EXCEPTION 'no office' USING ERRCODE = 'MKTVL';
    END IF;"""
_MKT_OFFICE_NEW = """    IF NOT EXISTS (SELECT 1 FROM org_unit WHERE id = p_office) THEN
        RAISE EXCEPTION 'no office' USING ERRCODE = 'MKTVL';
    END IF;
    -- the office is the caller's, or the one over the dealer's territory (rule 6; PR 11 review)
    IF app_current_org_unit() IS NOT NULL AND v_caller_partner IS NULL THEN
        IF NOT EXISTS (SELECT 1 FROM org_closure WHERE ancestor_id = app_current_org_unit()
                        AND descendant_id = p_office) THEN
            RAISE EXCEPTION 'the office is not yours' USING ERRCODE = '42501';
        END IF;
    ELSIF v_territory IS NULL OR NOT (
            EXISTS (SELECT 1 FROM org_unit ou JOIN territory_closure tc ON tc.ancestor_id = ou.territory_id
                     WHERE ou.id = p_office AND tc.descendant_id = v_territory)
         OR NOT EXISTS (SELECT 1 FROM org_unit ou JOIN territory_closure tc ON tc.ancestor_id = ou.territory_id
                         WHERE tc.descendant_id = v_territory)) THEN
        RAISE EXCEPTION 'the office does not cover the dealer' USING ERRCODE = '42501';
    END IF;"""

_STANDING_OLD = """    IF s.id IS NULL OR NOT EXISTS (SELECT 1 FROM channel_partner WHERE id = p_partner) THEN"""
_STANDING_NEW = """    IF NOT app_has_permission('schemes', 'view') OR s.id IS NULL
       OR NOT partner_visible_to_caller(p_partner) THEN"""

_TARGET_OLD = """BEGIN
    IF scheme_used(coalesce(NEW.scheme_id, OLD.scheme_id)) THEN"""
_TARGET_NEW = """BEGIN
    -- the scheme first, so a use being written commits before this check (rule 16)
    PERFORM 1 FROM scheme WHERE id = coalesce(NEW.scheme_id, OLD.scheme_id) FOR UPDATE;
    IF scheme_used(coalesce(NEW.scheme_id, OLD.scheme_id)) THEN"""

SCHEME_LOCK_FN = """CREATE FUNCTION scheme_lock_on_use() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    -- rule 16: an edit's trigger waits for this use to commit, then sees it
    PERFORM 1 FROM scheme WHERE id = NEW.scheme_id FOR SHARE;
    RETURN NEW;
END $fn$"""

USE_TABLES = ("scheme_benefit", "scheme_entitlement", "reward_ledger")


def _replaced() -> list[str]:
    mkt = _original("038", "marketing_order_create")
    mkt = _replace(_replace(mkt, _MKT_PARTNER_OLD, _MKT_PARTNER_NEW), _MKT_OFFICE_OLD, _MKT_OFFICE_NEW)
    standing = _replace(_original("033", "scheme_standing"), _STANDING_OLD, _STANDING_NEW)
    target = _replace(_original("033", "refuse_used_scheme_target"), _TARGET_OLD, _TARGET_NEW)
    return [_replace(t, "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION") for t in (mkt, standing, target)]


def _restored() -> list[str]:
    return [_replace(_original(stem, name), "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
            for stem, name in (("038", "marketing_order_create"), ("033", "scheme_standing"),
                               ("033", "refuse_used_scheme_target"))]


def upgrade() -> None:
    op.execute("ALTER TABLE lead ADD COLUMN dormant_from_stage lead_stage")
    # Nothing has ever moved a lead to dormant, so no row needs a backfill; refuse to
    # run if one exists, rather than guess where it came from.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM lead WHERE stage = 'dormant') THEN
            RAISE EXCEPTION '040: dormant leads exist with no from-stage; set them first';
        END IF;
    END $$""")
    op.execute("ALTER TABLE lead ADD CONSTRAINT ck_lead_dormant_from "
               "CHECK ((stage = 'dormant') = (dormant_from_stage IS NOT NULL))")
    op.execute("INSERT INTO lead_score_rule (key, value) VALUES ('dormant_after_days', 60) "
               "ON CONFLICT (key) DO NOTHING")
    for stmt in FUNCTIONS:
        op.execute(stmt)
    op.execute("CREATE TRIGGER trg_lead_dormant_clear BEFORE UPDATE OF stage ON lead "
               "FOR EACH ROW EXECUTE FUNCTION lead_dormant_clear()")
    op.execute(f"GRANT EXECUTE ON FUNCTION lead_dormant_sweep(timestamptz, int) TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION lead_owner_unit(uuid) TO {APP_ROLE}")
    # the PR 11 review
    op.execute(_visible_fn())
    op.execute(f"GRANT EXECUTE ON FUNCTION partner_visible_to_caller(uuid) TO {APP_ROLE}")
    for stmt in _replaced():
        op.execute(stmt)
    op.execute(SCHEME_LOCK_FN)
    for table in USE_TABLES:
        op.execute(f"CREATE TRIGGER trg_{table}_scheme_lock BEFORE INSERT ON {table} FOR EACH ROW "
                   "WHEN (NEW.scheme_id IS NOT NULL) EXECUTE FUNCTION scheme_lock_on_use()")
    op.execute("CREATE INDEX ix_dealer_commission_application ON dealer_commission (application_id)")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_dealer_commission_application")
    for table in USE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_scheme_lock ON {table}")
    op.execute("DROP FUNCTION IF EXISTS scheme_lock_on_use()")
    for stmt in _restored():
        op.execute(stmt)
    op.execute("DROP FUNCTION IF EXISTS partner_visible_to_caller(uuid)")
    op.execute("DROP TRIGGER IF EXISTS trg_lead_dormant_clear ON lead")
    op.execute("DROP FUNCTION IF EXISTS lead_dormant_clear()")
    op.execute("DROP FUNCTION IF EXISTS lead_dormant_sweep(timestamptz, int)")
    op.execute("DROP FUNCTION IF EXISTS lead_owner_unit(uuid)")
    op.execute("DELETE FROM lead_score_rule WHERE key = 'dormant_after_days'")
    op.execute("ALTER TABLE lead DROP CONSTRAINT IF EXISTS ck_lead_dormant_from")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS dormant_from_stage")
