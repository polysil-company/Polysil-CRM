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

Revision ID: 040_lead_small_gaps
Revises: 039_subsidy_follow_ups
"""

from __future__ import annotations

from alembic import op

revision: str = "040_lead_small_gaps"
down_revision: str | None = "039_subsidy_follow_ups"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

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
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_lead_dormant_clear ON lead")
    op.execute("DROP FUNCTION IF EXISTS lead_dormant_clear()")
    op.execute("DROP FUNCTION IF EXISTS lead_dormant_sweep(timestamptz, int)")
    op.execute("DROP FUNCTION IF EXISTS lead_owner_unit(uuid)")
    op.execute("DELETE FROM lead_score_rule WHERE key = 'dormant_after_days'")
    op.execute("ALTER TABLE lead DROP CONSTRAINT IF EXISTS ck_lead_dormant_from")
    op.execute("ALTER TABLE lead DROP COLUMN IF EXISTS dormant_from_stage")
