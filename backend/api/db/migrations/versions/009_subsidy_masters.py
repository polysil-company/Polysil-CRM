"""009 subsidy masters: the tables the calculation engine reads (FS-008)

Masters only. Nothing here stores a calculation; the endpoint is a preview and
FS-009 owns the application that keeps one.

Four things in this migration are not obvious, and each was executed rather than
reasoned about (the plan review's blockers B-4 and B-5):

* `btree_gist` first. `001_foundation` installs pgcrypto, pg_trgm and citext only,
  and every effective-dated table's exclusion constraint mixes equality columns
  with a range. The extension is trusted, so `appuser` can install it without
  being a superuser.
* **Every effective-dated table carries `CHECK (effective_to > effective_from)`.**
  `effective_from = effective_to` builds an *empty* daterange, which an exclusion
  constraint accepts happily and which is in force for no day at all. The loader
  closes a row by writing the successor's `effective_from` into it, so a revision
  landing on a row's own start date would produce exactly that.
* **A nullable discriminator gets two exclusion constraints, one per side of the
  null.** `NULL = NULL` is not a conflict, so a single `system_type WITH =` lets
  two overlapping parameter rows coexist whenever the column is null, which is the
  common case (a parameter that applies to every system). Four casts were executed
  against 16.14 to find the form that works: btree_gist indexes an enum column
  directly but **refuses `enum::text`**, because that cast is not IMMUTABLE (enum
  labels can be renamed); citext is the mirror, with no gist operator for its own
  `=` but an immutable cast to text. So enums and uuids go in bare, citext goes in
  cast, a nullable smallint goes through COALESCE, and a nullable enum splits into
  a pair of partial constraints. The pair subsumes the review's
  `UNIQUE NULLS NOT DISTINCT` suggestion: it refuses a duplicate key *and* an
  overlapping range, where a unique index on `effective_from` alone refuses
  neither.
* **Closing a row is `effective_to`, never `is_active`.** A deactivated row still
  occupies its range and still blocks an overlapping insert. `is_active` hides a
  row from the config endpoint; it does not free the range.

**Every master that moves money is effective-dated**, the category percentage and
the crop's standard lateral spacing included. Neither was, in the spec's first
draft: both carried `is_active` alone, which cannot reproduce a quotation dated
before a revision, and the standard spacing picks the Jantri row as surely as a
rate picks an amount (CLAUDE.md 4.1 rule 10). Their natural keys are therefore
exclusion constraints over the range, not plain uniques.

The rounding policy is two text arrays rather than a row of booleans. Drip rounds
every block cell, Mini Sprinkler rounds exactly one (`'Quo Summary'!I27`, the
insurance) and Sprinkler rounds every block but the inspection, so a boolean per
kind of cell cannot express the middle one (plan review B-1).

Revision ID: 009_subsidy_masters
Revises: 008_message_delivery
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision: str = "009_subsidy_masters"
down_revision: str | None = "008_message_delivery"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

TABLES = (
    "subsidy_scheme", "subsidy_system", "subsidy_category", "unit_cost_matrix", "unit_cost_cell",
    "quantity_matrix", "quantity_matrix_cell", "subsidy_component_rate", "crop_lateral_spacing",
    "subsidy_parameter",
)

# ── grants and hand-written policies, read by tests/db/migration_grants.py ────

CELL_TABLES = ("unit_cost_cell", "quantity_matrix_cell")

# The two cell tables hold the numbers themselves and take no UPDATE. A cell is
# never edited: a revised table is a new matrix with its own effective date, which
# is what CLAUDE.md 4.1 rule 10 means by "never in place". With UPDATE granted, a
# `masters.edit` holder could have tripled a unit cost in force and restated every
# quotation back to the load date (code review F-3, executed).
GRANTS: dict[str, str] = {
    t: ("SELECT, INSERT" if t in CELL_TABLES else "SELECT, INSERT, UPDATE") for t in TABLES
}

# Masters are global: anyone signed in reads them, `masters.edit` writes them. No
# DELETE anywhere, so a price in force cannot be removed out from under a past
# quotation (CLAUDE.md 4.1 rule 10). The engine itself writes nothing; the loader
# runs as the owner, and the INSERT and UPDATE policies exist so FS-009's admin
# screens need no grant migration of their own.
HAND_POLICIES: list[tuple[str, str]] = [
    (t, f"""CREATE POLICY {t}_sel ON {t} FOR SELECT USING ((SELECT app_current_user_id()) IS NOT NULL)""")
    for t in TABLES
] + [
    (t, f"""CREATE POLICY {t}_ins ON {t} FOR INSERT WITH CHECK ((SELECT app_has_permission('masters', 'edit')))""")
    for t in TABLES
] + [
    (t, f"""CREATE POLICY {t}_upd ON {t} FOR UPDATE USING ((SELECT app_has_permission('masters', 'edit')))""")
    for t in TABLES if t not in CELL_TABLES
]

# ── enums ────────────────────────────────────────────────────────────────────

ENUMS: dict[str, tuple[str, ...]] = {
    # Parallel to `mis_system` (006) on purpose: that table is what a lead asked
    # for and carries `automation` and `other`, which have no subsidy calculation.
    "subsidy_system_type": ("drip", "mini_sprinkler", "sprinkler"),
    "subsidy_pipeline_variant": ("full_abcdefg", "field_inspection_only"),
    "subsidy_jantri_variant": ("bilinear_2d", "area_lookup_1d"),
    "subsidy_quantity_source": ("manual", "area_matrix"),
    "subsidy_matrix_variant": ("regular", "seven_year"),
    "subsidy_spacing_rule": ("max_of_standard_and_design", "design"),
    "subsidy_outside_table": ("clamp", "extrapolate"),
    "subsidy_nozzle": ("plastic", "brass"),
    "subsidy_param_unit": ("ratio", "rupees", "hectares", "metres", "flag"),
}

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz"""

# The block keys and line kinds `api/domain/subsidy/money.py` accepts. A row whose
# array holds anything else would round a cell the engine does not know about, so
# the check is here rather than in the loader.
BLOCK_KEYS = ("a_plus_b", "gst_ab", "gst_c", "total_abc_gst", "insurance", "gst_d", "inspection",
              "gst_e", "education_split", "sump", "dbt", "cost_of_mis", "gst_totals", "total_gst",
              "total_incl_gst")
LINE_KINDS = ("head", "field", "installation", "transport")

# Sprinkler has no head unit, no insurance, no education and no sump, so it names
# only the blocks it actually asks for. Declaring more would round a cell the
# workbook leaves alone the day someone asks for it (code review F-11). These are
# spelled out rather than imported from `api.domain.subsidy.money`: a migration
# that reads application code changes meaning when that code changes, and the
# drift test in tests/db/test_migration_009.py is what keeps the two in step.
SPRINKLER_BLOCKS = ("gst_ab", "dbt", "gst_e", "cost_of_mis", "gst_totals", "total_gst",
                    "total_incl_gst")


def _arr(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ",".join(f"'{v}'" for v in values) + "]::text[]"


TABLES_SQL: tuple[str, ...] = (
    f"""CREATE TABLE subsidy_scheme (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE,
    name text NOT NULL,
    state_territory_id uuid REFERENCES territory(id),
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT}
)""",
    f"""CREATE TABLE subsidy_system (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type subsidy_system_type NOT NULL,
    pipeline_variant subsidy_pipeline_variant NOT NULL,
    jantri_variant subsidy_jantri_variant NOT NULL,
    quantity_source subsidy_quantity_source NOT NULL,
    has_head_unit boolean NOT NULL,
    supports_group boolean NOT NULL,
    crop_count_max int NOT NULL,
    rounded_blocks text[] NOT NULL DEFAULT '{{}}',
    rounded_lines text[] NOT NULL DEFAULT '{{}}',
    spacing_rule subsidy_spacing_rule NOT NULL,
    seven_year_spacing_floor numeric(6,2),
    spacing_outside_table subsidy_outside_table NOT NULL DEFAULT 'clamp',
    formula_version text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT uq_subsidy_system UNIQUE (scheme_id, system_type),
    CONSTRAINT ck_subsidy_system_crop_count CHECK (crop_count_max > 0),
    CONSTRAINT ck_subsidy_system_blocks CHECK (rounded_blocks <@ {_arr(BLOCK_KEYS)}),
    CONSTRAINT ck_subsidy_system_lines CHECK (rounded_lines <@ {_arr(LINE_KINDS)})
)""",
    f"""CREATE TABLE subsidy_category (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type subsidy_system_type NOT NULL,
    code citext NOT NULL,
    name text NOT NULL,
    pct numeric(6,3) NOT NULL,
    variant subsidy_matrix_variant NOT NULL,
    per_ha_cap numeric(14,2),
    gsdma_pct numeric(6,3),
    sort_order int NOT NULL DEFAULT 0,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_subsidy_category_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_subsidy_category EXCLUDE USING gist (
        scheme_id WITH =, system_type WITH =, (code::text) WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&),
    CONSTRAINT ck_subsidy_category_pct CHECK (pct > 0 AND pct <= 100),
    CONSTRAINT ck_subsidy_category_gsdma CHECK (gsdma_pct IS NULL OR (gsdma_pct > 0 AND gsdma_pct <= 100)),
    CONSTRAINT ck_subsidy_category_cap CHECK (per_ha_cap IS NULL OR per_ha_cap > 0)
)""",
    f"""CREATE TABLE unit_cost_matrix (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type subsidy_system_type NOT NULL,
    variant subsidy_matrix_variant NOT NULL,
    dimensionality smallint NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    source text NOT NULL,
    {AUDIT},
    CONSTRAINT ck_unit_cost_matrix_dim CHECK (dimensionality IN (1, 2)),
    CONSTRAINT ck_unit_cost_matrix_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_unit_cost_matrix EXCLUDE USING gist (
        scheme_id WITH =, system_type WITH =, variant WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&)
)""",
    """CREATE TABLE unit_cost_cell (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id uuid NOT NULL REFERENCES unit_cost_matrix(id) ON DELETE CASCADE,
    lateral_spacing numeric(6,2),
    area_breakpoint numeric(10,3) NOT NULL,
    unit_cost numeric(14,4) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_unit_cost_cell_cost CHECK (unit_cost >= 0),
    CONSTRAINT ck_unit_cost_cell_area CHECK (area_breakpoint > 0),
    CONSTRAINT ck_unit_cost_cell_spacing CHECK (lateral_spacing IS NULL OR lateral_spacing > 0)
)""",
    f"""CREATE TABLE quantity_matrix (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type subsidy_system_type NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    source text NOT NULL,
    {AUDIT},
    CONSTRAINT ck_quantity_matrix_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_quantity_matrix EXCLUDE USING gist (
        scheme_id WITH =, system_type WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&)
)""",
    """CREATE TABLE quantity_matrix_cell (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matrix_id uuid NOT NULL REFERENCES quantity_matrix(id) ON DELETE CASCADE,
    component_code citext NOT NULL,
    area_breakpoint numeric(10,3) NOT NULL,
    qty numeric(10,2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_quantity_matrix_cell_qty CHECK (qty >= 0),
    CONSTRAINT ck_quantity_matrix_cell_area CHECK (area_breakpoint > 0)
)""",
    f"""CREATE TABLE subsidy_component_rate (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type subsidy_system_type NOT NULL,
    component_code citext NOT NULL,
    description text NOT NULL,
    uom text NOT NULL,
    pipe_size_mm smallint,
    nozzle subsidy_nozzle,
    rate numeric(14,2) NOT NULL,
    source_cell text NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_subsidy_component_rate_rate CHECK (rate >= 0),
    CONSTRAINT ck_subsidy_component_rate_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_subsidy_component_rate_sized EXCLUDE USING gist (
        scheme_id WITH =, system_type WITH =, (component_code::text) WITH =,
        (COALESCE(pipe_size_mm, (-1)::smallint)) WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&) WHERE (nozzle IS NULL),
    CONSTRAINT ex_subsidy_component_rate_nozzle EXCLUDE USING gist (
        scheme_id WITH =, system_type WITH =, (component_code::text) WITH =, nozzle WITH =,
        (COALESCE(pipe_size_mm, (-1)::smallint)) WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&) WHERE (nozzle IS NOT NULL)
)""",
    f"""CREATE TABLE crop_lateral_spacing (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    crop citext NOT NULL,
    standard_spacing numeric(6,2) NOT NULL,
    sort_order int NOT NULL DEFAULT 0,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_crop_lateral_spacing_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_crop_lateral_spacing EXCLUDE USING gist (
        scheme_id WITH =, (crop::text) WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&),
    CONSTRAINT ck_crop_lateral_spacing_trimmed CHECK (crop = btrim(crop)),
    CONSTRAINT ck_crop_lateral_spacing_value CHECK (standard_spacing >= 0)
)""",
    f"""CREATE TABLE subsidy_parameter (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scheme_id uuid NOT NULL REFERENCES subsidy_scheme(id),
    system_type subsidy_system_type,
    key citext NOT NULL,
    value numeric(14,4) NOT NULL,
    unit subsidy_param_unit NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_subsidy_parameter_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_subsidy_parameter_all_systems EXCLUDE USING gist (
        scheme_id WITH =, (key::text) WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&) WHERE (system_type IS NULL),
    CONSTRAINT ex_subsidy_parameter_one_system EXCLUDE USING gist (
        scheme_id WITH =, system_type WITH =, (key::text) WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&) WHERE (system_type IS NOT NULL)
)""",
)

# Every policy-referenced column is indexed (CLAUDE.md 4.1 rule 9); these policies
# reference no column, so the indexes here are the ones the resolution query uses:
# one lookup per master by scheme, system and the date in force.
INDEXES: tuple[str, ...] = (
    """CREATE INDEX ix_subsidy_system_scheme ON subsidy_system (scheme_id, system_type) WHERE is_active""",
    """CREATE INDEX ix_subsidy_category_scheme ON subsidy_category (scheme_id, system_type, effective_from DESC, sort_order) WHERE is_active""",
    """CREATE INDEX ix_unit_cost_matrix_lookup ON unit_cost_matrix (scheme_id, system_type, variant, effective_from DESC)""",
    """CREATE INDEX ix_unit_cost_cell_matrix ON unit_cost_cell (matrix_id, lateral_spacing, area_breakpoint)""",
    """CREATE UNIQUE INDEX uq_unit_cost_cell ON unit_cost_cell (matrix_id, COALESCE(lateral_spacing, -1), area_breakpoint)""",
    """CREATE INDEX ix_quantity_matrix_lookup ON quantity_matrix (scheme_id, system_type, effective_from DESC)""",
    """CREATE UNIQUE INDEX uq_quantity_matrix_cell ON quantity_matrix_cell (matrix_id, component_code, area_breakpoint)""",
    """CREATE INDEX ix_subsidy_component_rate_lookup ON subsidy_component_rate (scheme_id, system_type, component_code, effective_from DESC)""",
    """CREATE INDEX ix_crop_lateral_spacing_scheme ON crop_lateral_spacing (scheme_id, crop, effective_from DESC) WHERE is_active""",
    """CREATE INDEX ix_subsidy_parameter_lookup ON subsidy_parameter (scheme_id, key, effective_from DESC)""",
)

TRIGGERS: tuple[str, ...] = tuple(
    stmt
    for t in TABLES if t not in CELL_TABLES
    for stmt in (
        f"""CREATE TRIGGER trg_{t}_updated_at BEFORE UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
        f"""CREATE TRIGGER trg_{t}_audit AFTER INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    )
) + tuple(
    # The cells have no updated_at to maintain, but a load still leaves a trace.
    f"""CREATE TRIGGER trg_{t}_audit AFTER INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION audit_row()"""
    for t in CELL_TABLES
)

# ── seeds ────────────────────────────────────────────────────────────────────
#
# Everything the workbooks keep as text or inside a formula. The matrices, the
# quantity table and the 79 crop spacings come from `scripts/load_subsidy_masters.py`,
# which needs the workbooks; these do not.

SCHEME_CODE = "GGRC"
EFFECTIVE_FROM = "2026-06-13"   # the date the three workbooks carry in their file names

SEEDS: tuple[str, ...] = (
    f"""INSERT INTO subsidy_scheme (code, name) VALUES ('{SCHEME_CODE}', 'Gujarat Green Revolution Company')""",
    # Drip rounds every block and no line; Mini rounds one block and two kinds of
    # line; Sprinkler rounds every block but the inspection, and its lines.
    f"""INSERT INTO subsidy_system (scheme_id, system_type, pipeline_variant, jantri_variant, quantity_source,
        has_head_unit, supports_group, crop_count_max, rounded_blocks, rounded_lines, spacing_rule,
        seven_year_spacing_floor, formula_version)
    SELECT s.id, v.system_type::subsidy_system_type, v.pipeline::subsidy_pipeline_variant,
           v.jantri::subsidy_jantri_variant, v.qty::subsidy_quantity_source,
           v.head, v.grp, v.crops, v.blocks, v.lines, v.spacing::subsidy_spacing_rule, v.floor, 'ggrc-2026-06-13'
    FROM subsidy_scheme s, (VALUES
        ('drip', 'full_abcdefg', 'bilinear_2d', 'manual', true, true, 2,
         {_arr(BLOCK_KEYS)}, '{{}}'::text[], 'max_of_standard_and_design', 1.2::numeric),
        ('mini_sprinkler', 'full_abcdefg', 'bilinear_2d', 'manual', true, true, 1,
         ARRAY['insurance']::text[], ARRAY['field','installation']::text[], 'max_of_standard_and_design', 8::numeric),
        ('sprinkler', 'field_inspection_only', 'area_lookup_1d', 'area_matrix', false, false, 1,
         {_arr(SPRINKLER_BLOCKS)}, ARRAY['field','transport']::text[], 'design', NULL)
    ) AS v(system_type, pipeline, jantri, qty, head, grp, crops, blocks, lines, spacing, floor)
    WHERE s.code = '{SCHEME_CODE}'""",
)

# Drip 'Quo Summary'!N29:N36, Mini L33:L40 with the GSDMA percent of Q43:Q48,
# Sprinkler 'Farmer Share Calculation'!A6:A11 and A19:A20. Every `per_ha_cap` is
# null: the printed table applies none, and which row each of the capped table's
# six labels means is unconfirmed (GAP-084).
_CATEGORIES: tuple[tuple[str, str, str, str, str, str | None], ...] = (
    ("drip", "small_farmer", "Small Farmer 70 %", "70", "regular", None),
    ("drip", "darkzone_small_farmer", "Darkzone Small Farmer 80%", "80", "regular", None),
    ("drip", "big_farmer", "Big Farmer 70 %", "70", "regular", None),
    ("drip", "darkzone_big_farmer", "Darkzone Big Farmer 70 %", "70", "regular", None),
    ("drip", "sc_st", "SC+ST 85 %", "85", "regular", None),
    ("drip", "darkzone_sc_st", "Darkzone + SC/ST 90%", "90", "regular", None),
    ("drip", "seven_year_small", "7 Year Small farmer", "55", "seven_year", None),
    ("drip", "seven_year_big", "7 Year Big Farmer", "45", "seven_year", None),
    ("mini_sprinkler", "small_farmer", "Small Farmer 70 %", "70", "regular", "10"),
    ("mini_sprinkler", "darkzone_small_farmer", "Darkzone Small Farmer 80%", "80", "regular", "10"),
    ("mini_sprinkler", "big_farmer", "Big Farmer 70 %", "70", "regular", "10"),
    ("mini_sprinkler", "darkzone_big_farmer", "Darkzone Big Farmer 70 %", "70", "regular", "10"),
    ("mini_sprinkler", "sc_st", "SC+ST 85 %", "85", "regular", "5"),
    ("mini_sprinkler", "darkzone_sc_st", "Darkzone + SC/ST 90%", "90", "regular", "5"),
    ("mini_sprinkler", "seven_year_small", "7 Year Small farmer 55 %", "55", "seven_year", None),
    ("mini_sprinkler", "seven_year_big", "7 Year Big Farmer 45%", "45", "seven_year", None),
    ("sprinkler", "small_farmer", "Small Farmer 70%", "70", "regular", None),
    ("sprinkler", "darkzone_small_farmer", "Small Farmer+Darkzone 80%", "80", "regular", None),
    ("sprinkler", "big_farmer", "General Farmer 70%", "70", "regular", None),
    ("sprinkler", "darkzone_big_farmer", "General Farmer+Darkzone 70%", "70", "regular", None),
    ("sprinkler", "sc_st", "SC+ST (TRIBAL) Farmer 85 %", "85", "regular", None),
    ("sprinkler", "darkzone_sc_st", "SC+ST (TRIBAL)+Dark Zone Farmer 90 %", "90", "regular", None),
    ("sprinkler", "seven_year_small", "Small Farmer 55%", "55", "seven_year", None),
    ("sprinkler", "seven_year_big", "Big Farmer 45%", "45", "seven_year", None),
)

# key, system (null: every system), value, unit. An absent key is an error at load
# time, never a silent zero, so Drip's "no inspection floor" is a row of 0.
_PARAMETERS: tuple[tuple[str, str | None, str, str], ...] = (
    ("education_amount", None, "1000", "rupees"),
    ("insurance_rate", None, "0.0028", "ratio"),
    ("inspection_rate", None, "0.004", "ratio"),
    ("gst_material_half", None, "0.025", "ratio"),
    ("gst_service_half", None, "0.09", "ratio"),
    ("seven_year_area_min", None, "0.2", "hectares"),
    ("seven_year_area_max", None, "5", "hectares"),
    ("max_area_scaling", None, "1", "flag"),
    ("inspection_floor", "drip", "0", "rupees"),
    ("inspection_floor", "mini_sprinkler", "200", "rupees"),
    ("inspection_floor", "sprinkler", "200", "rupees"),
    ("min_area_prorate", "drip", "0", "flag"),
    ("min_area_prorate", "mini_sprinkler", "1", "flag"),
    ("min_area_prorate", "sprinkler", "0", "flag"),
    ("gsdma_max_area", "mini_sprinkler", "2", "hectares"),
    ("exact_area_match_required", "sprinkler", "1", "flag"),
    ("pipe_size_band_ha", "sprinkler", "2.0", "hectares"),
)

# Rule 20: what the Sprinkler BOQ keeps inside its formulas. Two descriptions carry
# the workbook's own line break and non-breaking space; they are the identity of
# the item in the quantity table, so they are stored exactly as the cells hold them.
_NL, _NBSP = chr(10), chr(160)
_RATES: tuple[tuple[str, str | None, str | None, str, str, str, str], ...] = (
    ("pipe", "75", None, "583.12", "HDPE 17425 SPRINKLER PIPE 75 MM X 2.5 KG WITH SS C CLAMP COUPLER", "Mtr.", "BOQ!I16"),
    ("pipe", "90", None, "691.62", "HDPE 17425 SPRINKLER PIPE 90 MM X 2.5 KG WITH SS C CLAMP COUPLER", "Mtr.", "BOQ!I16"),
    ("coupler", "75", None, "391.49", "Sprinkler Coupler with Foot Batten" + _NL + "Assembly Quick Action 75MM", "No.", "BOQ!I17"),
    ("coupler", "90", None, "410.23", "Sprinkler Coupler with Foot Batten" + _NL + "Assembly Quick Action 90MM", "No.", "BOQ!I17"),
    ("nozzle", None, "plastic", "104.17", "Sprinkler Nozzles (1.7 to 2.8 kg/cm2) 5 to 40 Litre/Minute Capacity(Plastic)", "No.", "'Farmer Share Calculation'!T3"),
    ("nozzle", None, "brass", "299.23", "Sprinkler Nozzles (1.7 to 2.8 kg/cm2) 5 to 40 Litre/Minute Capacity(Brass)", "No.", "'Farmer Share Calculation'!T2"),
    ("riser", "75", None, "90.15", "Riser Pipe 20mm Diameter x 75 cm Long", "No.", "BOQ!I19"),
    ("riser", "90", None, "90.15", "Riser Pipe 20mm Diameter x 75 cm Long", "No.", "BOQ!I19"),
    ("pcn", "75", None, "269.04", "SPRINKLER PCN (NIPPLE) 75MM WITH SS C CLAMP", "No.", "BOQ!I20"),
    ("pcn", "90", None, "334", "SPRINKLER PCN (NIPPLE) 90MM WITH SS C CLAMP", "No.", "BOQ!I20"),
    ("bend", "75", None, "282.63", "SPRINKLER BEND 75MM" + _NBSP + " WITH SS C CLAMP", "No.", "BOQ!I21"),
    ("bend", "90", None, "294.71", "SPRINKLER BEND 90MM" + _NBSP + " WITH SS C CLAMP", "No.", "BOQ!I21"),
    ("tee", "75", None, "303.75", "SPRINKLER TEE 75MM WITH SS C CLAMP", "Mtr.", "BOQ!I22"),
    ("tee", "90", None, "340.21", "SPRINKLER TEE 90MM WITH SS C CLAMP", "Mtr.", "BOQ!I22"),
    ("end_plug", "75", None, "110.97", "SPRINKLER END PLUG 75MM (FOR SPR. C CLAMP PIPE)", "No.", "BOQ!I23"),
    ("end_plug", "90", None, "127.18", "SPRINKLER END PLUG 90MM (FOR SPR. C CLAMP PIPE)", "No.", "BOQ!I23"),
    ("transport", None, None, "506.45", "Secondary Transportation for SIS", "Set", "BOQ!I25"),
)


def _q(value: str | None) -> str:
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def _seed_rows() -> tuple[str, ...]:
    cats = ",".join(
        f"({_q(st)}, {_q(code)}, {_q(name)}, {pct}, {_q(variant)}, {gsdma or 'NULL'}, {i})"
        for i, (st, code, name, pct, variant, gsdma) in enumerate(_CATEGORIES)
    )
    params = ",".join(
        f"({_q(system)}, {_q(key)}, {value}, {_q(unit)})"
        for key, system, value, unit in _PARAMETERS
    )
    rates = ",".join(
        f"({_q(code)}, {size or 'NULL'}, {_q(nozzle)}, {rate}, {_q(desc)}, {_q(uom)}, {_q(cell)})"
        for code, size, nozzle, rate, desc, uom, cell in _RATES
    )
    return (
        f"""INSERT INTO subsidy_category (scheme_id, system_type, code, name, pct, variant, gsdma_pct,
        sort_order, effective_from)
    SELECT s.id, v.st::subsidy_system_type, v.code, v.name, v.pct, v.variant::subsidy_matrix_variant,
           v.gsdma, v.sort_order, DATE '{EFFECTIVE_FROM}'
    FROM subsidy_scheme s, (VALUES {cats}) AS v(st, code, name, pct, variant, gsdma, sort_order)
    WHERE s.code = '{SCHEME_CODE}'""",
        f"""INSERT INTO subsidy_parameter (scheme_id, system_type, key, value, unit, effective_from)
    SELECT s.id, v.st::subsidy_system_type, v.key, v.value, v.unit::subsidy_param_unit, DATE '{EFFECTIVE_FROM}'
    FROM subsidy_scheme s, (VALUES {params}) AS v(st, key, value, unit)
    WHERE s.code = '{SCHEME_CODE}'""",
        f"""INSERT INTO subsidy_component_rate (scheme_id, system_type, component_code, pipe_size_mm, nozzle,
        rate, description, uom, source_cell, effective_from)
    SELECT s.id, 'sprinkler'::subsidy_system_type, v.code, v.size::smallint, v.nozzle::subsidy_nozzle,
           v.rate, v.descr, v.uom, v.cell, DATE '{EFFECTIVE_FROM}'
    FROM subsidy_scheme s, (VALUES {rates}) AS v(code, size, nozzle, rate, descr, uom, cell)
    WHERE s.code = '{SCHEME_CODE}'""",
    )


def _hand(table: str) -> None:
    for t, stmt in HAND_POLICIES:
        if t == table:
            op.execute(stmt)


def upgrade() -> None:
    # 001 installs pgcrypto, pg_trgm and citext only. btree_gist is trusted, so a
    # non-superuser owner with CREATE on the database can install it.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    for name, values in ENUMS.items():
        labels = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")

    for stmt in TABLES_SQL:
        op.execute(stmt)
    for stmt in INDEXES:
        op.execute(stmt)
    for stmt in TRIGGERS:
        op.execute(stmt)

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _hand(table)
        op.execute(f"GRANT {GRANTS[table]} ON {table} TO {APP_ROLE}")

    for stmt in SEEDS:
        op.execute(stmt)
    for stmt in _seed_rows():
        op.execute(stmt)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
