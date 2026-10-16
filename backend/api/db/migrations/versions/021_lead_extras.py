"""021: crops and land on a lead, the lead list's sort indexes, and the people a
lead's assignment events name (FS-016).

- `crop`: an admin list like `lead_source` (006): everyone signed in reads,
  `masters.edit` adds and switches off, nothing deletes (ADR-033). Seeded from a
  literal list: the crops the subsidy workbooks name, computed once. The
  workbooks arrive by a loader after the migrations, and not at all in CI, so
  the migration must not read them (plan review B-1).
- `lead.crops` (codes) and `lead.land_acres`.
- Three indexes for the new sort orders (EC-1).
- `lead_event_people(lead)`: the names of the people a lead's `lead.assigned`
  events refer to, for whoever sees the lead. `people_names()` names only the
  current people on a document, so a previous owner or a handed-over leaver had
  no name (plan review B-2).

Revision ID: 021_lead_extras
Revises: 020_complaint_fixes
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "021_lead_extras"
down_revision: str | None = "020_complaint_fixes"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# (code, name): the workbook's spelling kept; the code is the name in lower case
# with anything not a letter or digit turned to "_" (EC-12). "Select Crop here",
# the workbook's placeholder row, is left out. GAP-156: the client's list replaces it.
CROPS: list[tuple[str, str]] = [
    ("aloevera", "Aloevera"), ("amla", "Amla"), ("ardusoa", "Ardusoa"), ("banana", "Banana"),
    ("ber", "Ber"), ("bhindi", "Bhindi"), ("bitter_gourd", "Bitter Gourd"),
    ("bottle_gourd", "Bottle Gourd"), ("brinjal", "Brinjal"), ("cabbage", "Cabbage"),
    ("capsicum", "Capsicum"), ("cashewnut", "Cashewnut"), ("castor", "Castor"),
    ("cauliflower", "Cauliflower"), ("chillies", "Chillies"), ("citrus", "Citrus"),
    ("coconut", "Coconut"), ("corriander", "Corriander"), ("cotton", "Cotton"),
    ("cowpea", "Cowpea"), ("cucumber", "Cucumber"), ("cumin", "Cumin"),
    ("custard_apple", "Custard Apple"), ("date_palm", "Date Palm"),
    ("dragon_fruit", "Dragon Fruit"), ("drumstick", "Drumstick"), ("eucalyptus", "Eucalyptus"),
    ("fennel", "Fennel"), ("fenugreek", "Fenugreek"), ("galardia", "Galardia"),
    ("garlic", "Garlic"), ("ginger", "Ginger"), ("green_gram", "Green Gram"),
    ("groundnut", "Groundnut"), ("guar", "Guar"), ("guava", "Guava"),
    ("indian_bean", "Indian Bean"), ("jamun", "Jamun"), ("jasmine", "Jasmine"), ("kolu", "Kolu"),
    ("lady_finger", "Lady Finger"), ("lemon", "Lemon"), ("maize", "Maize"), ("mango", "Mango"),
    ("marygold", "Marygold"), ("mehogni", "Mehogni"), ("melia_dubia", "Melia Dubia"),
    ("oil_palm", "Oil Palm"), ("onion", "Onion"), ("orange", "Orange"),
    ("palmarosa", "Palmarosa"), ("papaya", "Papaya"), ("parval", "Parval"),
    ("pointed_gourd", "Pointed Gourd"), ("pomegranate", "Pomegranate"), ("pomelo", "Pomelo"),
    ("potato", "Potato"), ("pumpkin", "Pumpkin"), ("redgram_pigeonpea", "Redgram/Pigeonpea"),
    ("ridgegourd", "Ridgegourd"), ("rose", "Rose"), ("sakar_teti", "Sakar Teti"),
    ("sandalwood", "Sandalwood"), ("sapota", "Sapota"), ("saru", "Saru"),
    ("sesamum", "Sesamum"), ("small_gourd", "Small Gourd"), ("smoothgourd", "Smoothgourd"),
    ("spine_gourd", "Spine Gourd"), ("strawberry", "Strawberry"), ("sugarcane", "Sugarcane"),
    ("suran", "Suran"), ("teak", "Teak"), ("tindola", "Tindola"), ("tomato", "Tomato"),
    ("turmeric", "Turmeric"), ("watermelon", "Watermelon"), ("wheat", "Wheat"),
]

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id)"""

TABLES_SQL = [
    f"""CREATE TABLE crop (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE CHECK (code::text ~ '^[a-z0-9_]+$'),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 100),
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    deleted_at timestamptz,
    external_id text,
    source_system text NOT NULL DEFAULT 'crm',
    synced_at timestamptz
)""",
    "CREATE TRIGGER trg_crop_updated_at BEFORE UPDATE ON crop FOR EACH ROW EXECUTE FUNCTION set_updated_at()",
    "CREATE TRIGGER trg_crop_audit AFTER INSERT OR UPDATE OR DELETE ON crop FOR EACH ROW EXECUTE FUNCTION audit_row()",
    # codes, not ids: stable and readable in a report. The element checks are the
    # database's belt; the service stores the list's own code (EC-8)
    """ALTER TABLE lead
    ADD COLUMN crops citext[] NOT NULL DEFAULT '{}',
    ADD COLUMN land_acres numeric(10,2),
    ADD CONSTRAINT ck_lead_crops CHECK (cardinality(crops) <= 10 AND array_position(crops, NULL) IS NULL
                                        AND NOT ('' = ANY(crops))),
    ADD CONSTRAINT ck_lead_land_acres CHECK (land_acres IS NULL OR (land_acres > 0 AND land_acres <= 99999.99))""",
]

# the sort orders of GET /leads, each served without a sort step (EC-1)
INDEXES = [
    "CREATE INDEX ix_lead_farmer_name_lower ON lead (lower(farmer_name), id)",
    "CREATE INDEX ix_lead_value_asc ON lead (estimated_value ASC NULLS LAST, id ASC)",
    "CREATE INDEX ix_lead_value_desc ON lead (estimated_value DESC NULLS LAST, id DESC)",
]

HAND_POLICIES: list[tuple[str, str]] = [
    ("crop", "CREATE POLICY crop_sel ON crop FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)"),
    ("crop", "CREATE POLICY crop_ins ON crop FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
    ("crop", "CREATE POLICY crop_upd ON crop FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit'))) WITH CHECK ((SELECT app_has_permission('masters', 'edit')))"),
]

GRANTS: dict[str, str] = {"crop": "SELECT, INSERT, UPDATE"}

FUNCTIONS = [
    # Whoever sees a lead sees the people on it (see-the-lead-see-everything), and
    # that includes the people its assignment history names. Only this lead's
    # events and those of leads merged into it, as lead_timeline() reads them.
    """CREATE FUNCTION lead_event_people(p_lead_id uuid)
RETURNS TABLE (id uuid, name text, is_partner boolean)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    WITH ev AS (
        SELECT e.payload FROM activity_event e
         WHERE lead_visible(p_lead_id) AND e.kind = 'lead.assigned'
           AND (e.lead_id = p_lead_id
                OR e.lead_id IN (SELECT l.id FROM lead l WHERE l.merged_into_id = p_lead_id))
    ), refs AS (
        SELECT DISTINCT k, (ev.payload ->> k)::uuid AS ref
          FROM ev, unnest(ARRAY['owner_user_id', 'previous_owner_user_id', 'assigned_partner_id']) AS k
         -- one malformed old payload must not break the lead's history (code review F-1)
         WHERE ev.payload ->> k ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    )
    SELECT u.id, u.full_name, false FROM app_user u
     WHERE u.id IN (SELECT ref FROM refs WHERE k <> 'assigned_partner_id')
    UNION ALL
    -- a dealer is not told which competing dealer held the lead before: partner
    -- names only within the reader's own partner tree (code review F-3a)
    SELECT p.id, p.name, true FROM channel_partner p
     WHERE p.id IN (SELECT ref FROM refs WHERE k = 'assigned_partner_id')
       AND ((SELECT app_current_partner()) IS NULL
            OR p.id IN (SELECT descendant_id FROM partner_closure
                         WHERE ancestor_id = (SELECT app_current_partner())))
$fn$""",
]

GRANTED = ["lead_event_people(uuid)"]


def upgrade() -> None:
    for stmt in TABLES_SQL + INDEXES:
        op.execute(stmt)
    values = ", ".join(f"('{code}', '{name}', {i * 10})" for i, (code, name) in enumerate(CROPS, 1))
    op.execute(f"INSERT INTO crop (code, name, sort_order) VALUES {values}")
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    op.execute("ALTER TABLE crop ENABLE ROW LEVEL SECURITY")
    for _, stmt in HAND_POLICIES:
        op.execute(stmt)
    for stmt in FUNCTIONS:
        op.execute(stmt)
    for sig in GRANTED:
        op.execute(f"GRANT EXECUTE ON FUNCTION {sig} TO {APP_ROLE}")
    # new functions are PUBLIC-executable until this runs (006, cross-vendor B-6)
    op.execute("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    for sig in GRANTED:
        op.execute(f"DROP FUNCTION IF EXISTS {sig}")
    for stmt in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {stmt.split()[2]}")
    op.execute("ALTER TABLE lead DROP CONSTRAINT IF EXISTS ck_lead_land_acres, "
               "DROP CONSTRAINT IF EXISTS ck_lead_crops, DROP COLUMN IF EXISTS land_acres, "
               "DROP COLUMN IF EXISTS crops")
    op.execute("DROP TABLE IF EXISTS crop")
