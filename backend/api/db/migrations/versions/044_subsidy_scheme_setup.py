"""044: setting up a new state's subsidy scheme (FS-039).

- `subsidy_scheme`: the code is upper case (checked on the text, since citext's
  `~` ignores case), and one active scheme per state (`ux_subsidy_scheme_state`).
  GGRC is linked to the one state coded GJ, where there is exactly one.
- `subsidy_scheme_create()`: the scheme, the template's engine settings and every
  stage and field, in one transaction. No figure is copied (FS-039 rule 2).
- `subsidy_scheme_update()`, `subsidy_stage_rename()`: the admin's edits. Definers,
  for the locks and because `app_role` reads the stage tables only (025).
- `subsidy_scheme_for_lead()`: the active scheme of the lead's state; in legacy mode
  (no active scheme has a state) the single active scheme.
- `subsidy_application_create`: patched from its live text, signature unchanged
  (plan review B-2). It resolves the scheme itself, under the state lock it already
  takes, and refuses a calculation made on another scheme's figures.

Revision ID: 044_subsidy_scheme_setup
Revises: 043_whatsapp_webhook_capture
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "044_subsidy_scheme_setup"
down_revision: str | None = "043_whatsapp_webhook_capture"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

GRANTS: dict[str, str] = {}
HAND_POLICIES: list[tuple[str, str]] = []

# Two schemes may hold no state only in legacy mode, and the two modes never mix:
# checked after the write, under one lock both definers take (delta check 3).
_MODE_LOCK = "PERFORM pg_advisory_xact_lock(hashtext('subsidy_scheme_mode'));"
_MODE_CHECK = """IF EXISTS (SELECT 1 FROM subsidy_scheme WHERE is_active AND state_territory_id IS NULL)
       AND EXISTS (SELECT 1 FROM subsidy_scheme WHERE is_active AND state_territory_id IS NOT NULL) THEN
        RAISE EXCEPTION 'an active scheme has no state; link it first' USING ERRCODE = 'SSCUL';
    END IF;"""

_SYSTEM_COLS = ("system_type, pipeline_variant, jantri_variant, quantity_source, has_head_unit, "
                "supports_group, crop_count_max, rounded_blocks, rounded_lines, spacing_rule, "
                "seven_year_spacing_floor, spacing_outside_table, formula_version, is_active")

FUNCTIONS = [
    f"""CREATE FUNCTION subsidy_scheme_create(p_code text, p_name text, p_state uuid,
                                      p_template text, p_systems text[]) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_t uuid; v_id uuid; v_me uuid := app_current_user_id();
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'masters.edit required' USING ERRCODE = '42501';
    END IF;
    {_MODE_LOCK}
    PERFORM 1 FROM territory WHERE id = p_state AND level = 'state' AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'not a state' USING ERRCODE = 'SSCST';
    END IF;
    -- codes are upper case (the CHECK); citext = text would compare as text, case-sensitively
    SELECT id INTO v_t FROM subsidy_scheme WHERE code = upper(btrim(p_template)) AND is_active;
    IF v_t IS NULL OR NOT EXISTS (SELECT 1 FROM subsidy_stage_def WHERE scheme_id = v_t AND is_active) THEN
        RAISE EXCEPTION 'no such active template with stages' USING ERRCODE = 'SSCTM';
    END IF;
    IF COALESCE(cardinality(p_systems), 0) = 0 OR EXISTS (
            SELECT unnest(p_systems)
            EXCEPT SELECT system_type::text FROM subsidy_system WHERE scheme_id = v_t AND is_active) THEN
        RAISE EXCEPTION 'a system the template lacks' USING ERRCODE = 'SSCSY';
    END IF;

    INSERT INTO subsidy_scheme (code, name, state_territory_id, created_by, updated_by)
    VALUES (upper(btrim(p_code)), btrim(p_name), p_state, v_me, v_me)
    RETURNING id INTO v_id;
    {_MODE_CHECK}

    INSERT INTO subsidy_system (scheme_id, {_SYSTEM_COLS}, created_by, updated_by)
    SELECT v_id, {_SYSTEM_COLS}, v_me, v_me
      FROM subsidy_system WHERE scheme_id = v_t AND is_active AND system_type::text = ANY (p_systems);
    -- every stage and field, inactive ones included, so each pairs_with_key keeps
    -- its partner (edge case 6)
    INSERT INTO subsidy_stage_def (scheme_id, seq, code, name, is_active, created_by, updated_by)
    SELECT v_id, seq, code, name, is_active, v_me, v_me FROM subsidy_stage_def WHERE scheme_id = v_t;
    INSERT INTO subsidy_stage_field (scheme_id, stage_def_id, field_key, label, type, is_required,
                                     pairs_with_key, sort_order, is_active, created_by, updated_by)
    SELECT v_id, nd.id, f.field_key, f.label, f.type, f.is_required, f.pairs_with_key, f.sort_order,
           f.is_active, v_me, v_me
      FROM subsidy_stage_field f
      JOIN subsidy_stage_def od ON od.id = f.stage_def_id
      JOIN subsidy_stage_def nd ON nd.scheme_id = v_id AND nd.code = od.code
     WHERE f.scheme_id = v_t;
    RETURN v_id;
END $fn$""",

    f"""CREATE FUNCTION subsidy_scheme_update(p_code text, p_name text, p_active boolean, p_state uuid)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE s subsidy_scheme%ROWTYPE; v_state uuid;
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'masters.edit required' USING ERRCODE = '42501';
    END IF;
    {_MODE_LOCK}
    SELECT * INTO s FROM subsidy_scheme WHERE code = upper(btrim(p_code)) AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no such scheme' USING ERRCODE = 'SSCNF';
    END IF;
    IF p_state IS NOT NULL THEN
        IF s.state_territory_id IS NOT NULL THEN
            RAISE EXCEPTION 'the scheme already has a state' USING ERRCODE = 'SSCSF';
        END IF;
        PERFORM 1 FROM territory WHERE id = p_state AND level = 'state' AND deleted_at IS NULL FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'not a state' USING ERRCODE = 'SSCST';
        END IF;
    END IF;
    v_state := COALESCE(p_state, s.state_territory_id);
    IF v_state IS NOT NULL AND p_state IS NULL THEN
        -- serialise a reactivation against an application create on the state
        PERFORM 1 FROM territory WHERE id = v_state FOR UPDATE;
    END IF;
    UPDATE subsidy_scheme
       SET name = COALESCE(btrim(p_name), name), is_active = COALESCE(p_active, is_active),
           state_territory_id = v_state, updated_by = app_current_user_id()
     WHERE id = s.id;
    {_MODE_CHECK}
    RETURN s.id;
END $fn$""",

    """CREATE FUNCTION subsidy_stage_rename(p_scheme text, p_code text, p_name text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_id uuid;
BEGIN
    IF NOT app_has_permission('masters', 'edit') THEN
        RAISE EXCEPTION 'masters.edit required' USING ERRCODE = '42501';
    END IF;
    UPDATE subsidy_stage_def d SET name = btrim(p_name), updated_by = app_current_user_id()
      FROM subsidy_scheme s
     WHERE s.id = d.scheme_id AND s.code = upper(btrim(p_scheme)) AND s.deleted_at IS NULL AND d.code = p_code
    RETURNING d.id INTO v_id;
    IF v_id IS NULL THEN
        RAISE EXCEPTION 'no such stage' USING ERRCODE = 'SSCNF';
    END IF;
    RETURN v_id;
END $fn$""",

    # The state is read as subsidy_application_create reads it. A caller that
    # already holds the state's share lock (the create) gets the same answer the
    # lock protects.
    """CREATE FUNCTION subsidy_scheme_for_lead(p_lead uuid) RETURNS uuid
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
DECLARE v_terr uuid; v_state uuid; v_id uuid;
BEGIN
    IF NOT lead_visible(p_lead) THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'SAPNF';
    END IF;
    SELECT territory_id INTO v_terr FROM lead WHERE id = p_lead AND deleted_at IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'lead not found' USING ERRCODE = 'SAPNF';
    END IF;
    SELECT t.id INTO v_state
      FROM territory_closure tc JOIN territory t ON t.id = tc.ancestor_id
     WHERE tc.descendant_id = v_terr AND t.level = 'state'
     ORDER BY tc.depth ASC LIMIT 1;
    IF v_state IS NULL THEN
        RAISE EXCEPTION 'no coded state' USING ERRCODE = 'SAPSC';
    END IF;
    SELECT id INTO v_id FROM subsidy_scheme
     WHERE is_active AND deleted_at IS NULL AND state_territory_id = v_state;
    IF v_id IS NOT NULL THEN
        RETURN v_id;
    END IF;
    -- legacy mode: no active scheme names a state, and exactly one is active
    IF NOT EXISTS (SELECT 1 FROM subsidy_scheme WHERE is_active AND state_territory_id IS NOT NULL) THEN
        SELECT CASE WHEN count(*) = 1 THEN (array_agg(id))[1] END INTO v_id
          FROM subsidy_scheme WHERE is_active AND deleted_at IS NULL;
    END IF;
    RETURN v_id;
END $fn$""",
]

GRANTED = [
    "subsidy_scheme_create(text, text, uuid, text, text[])",
    "subsidy_scheme_update(text, text, boolean, uuid)",
    "subsidy_stage_rename(text, text, text)",
    "subsidy_scheme_for_lead(uuid)",
]

# subsidy_application_create: the GGRC lookup goes; the scheme is resolved after the
# state's share lock, and the first stage is the scheme's lowest active one.
_CREATE_OLD_1 = """    SELECT id INTO v_scheme FROM subsidy_scheme WHERE code = 'GGRC';
    SELECT id INTO v_stage FROM subsidy_stage_def WHERE scheme_id = v_scheme AND seq = 4;
"""
_CREATE_NEW_1 = """    -- FS-039: the scheme is resolved below, under the state's share lock
"""
_CREATE_OLD_2 = """    v_no := subsidy_allocate_no(v_state, p_fy);
"""
_CREATE_NEW_2 = """    -- FS-039: the lead's state's scheme, and the calculation must be made on its figures
    v_scheme := subsidy_scheme_for_lead(p_lead);
    IF v_scheme IS NULL THEN
        RAISE EXCEPTION 'no subsidy scheme for the lead''s state' USING ERRCODE = 'SAPSN';
    END IF;
    PERFORM 1 FROM subsidy_scheme
     WHERE id = v_scheme AND is_active
       -- a request without the key is the schema's default, GGRC (CalculateRequest.scheme)
       AND code = upper(COALESCE(p_request->>'scheme', 'GGRC')) FOR SHARE;
    -- a matrix of another scheme means the figures are that scheme's. An id that is
    -- no matrix at all is left alone: the column has no foreign key, and a fixed
    -- calculation in the tests carries made-up ids
    IF NOT FOUND OR EXISTS (SELECT 1 FROM unit_cost_matrix
                             WHERE id IN (p_regular, p_seven) AND scheme_id <> v_scheme) THEN
        RAISE EXCEPTION 'the calculation is not on the lead''s scheme' USING ERRCODE = 'SAPSX';
    END IF;
    -- resolved again now the scheme row is held: a link or a new scheme committed
    -- while this waited on the lock shows here (code review F-7)
    IF subsidy_scheme_for_lead(p_lead) IS DISTINCT FROM v_scheme THEN
        RAISE EXCEPTION 'the lead''s scheme changed' USING ERRCODE = 'SAPSX';
    END IF;
    SELECT id INTO v_stage FROM subsidy_stage_def
     WHERE scheme_id = v_scheme AND is_active ORDER BY seq LIMIT 1;
    IF v_stage IS NULL THEN
        RAISE EXCEPTION 'the scheme has no active stage' USING ERRCODE = 'SAPNG';
    END IF;
    v_no := subsidy_allocate_no(v_state, p_fy);
"""

BACKFILL = """UPDATE subsidy_scheme SET state_territory_id = (
        SELECT id FROM territory WHERE level = 'state' AND code = 'GJ' AND deleted_at IS NULL)
 WHERE code = 'GGRC' AND state_territory_id IS NULL
   AND (SELECT count(*) FROM territory WHERE level = 'state' AND code = 'GJ' AND deleted_at IS NULL) = 1"""


def _live(name: str) -> str:
    defs = op.get_bind().execute(text(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = :n"), {"n": name}).scalars().all()
    if len(defs) != 1:
        raise RuntimeError(f"044: expected one function {name}, found {len(defs)}")
    return str(defs[0])


def _swap(name: str, pairs: list[tuple[str, str]]) -> None:
    body = _live(name)
    for old, new in pairs:
        if body.count(old) != 1:
            raise RuntimeError(f"044: {name}: anchor found {body.count(old)} times, expected 1")
        body = body.replace(old, new)
    op.execute(body)


def upgrade() -> None:
    op.execute("ALTER TABLE subsidy_scheme ADD CONSTRAINT ck_subsidy_scheme_code "
               "CHECK (code::text ~ '^[A-Z0-9_]{2,20}$')")
    op.execute("CREATE UNIQUE INDEX ux_subsidy_scheme_state ON subsidy_scheme (state_territory_id) "
               "WHERE is_active AND state_territory_id IS NOT NULL")
    op.execute(BACKFILL)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    _swap("subsidy_application_create",
          [(_CREATE_OLD_1, _CREATE_NEW_1), (_CREATE_OLD_2, _CREATE_NEW_2)])
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    _swap("subsidy_application_create",
          [(_CREATE_NEW_2, _CREATE_OLD_2), (_CREATE_NEW_1, _CREATE_OLD_1)])
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    op.execute("DROP INDEX IF EXISTS ux_subsidy_scheme_state")
    op.execute("ALTER TABLE subsidy_scheme DROP CONSTRAINT IF EXISTS ck_subsidy_scheme_code")
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")
