"""010 products, price lists and tax rates (FS-010)

The masters a quotation prices from. No quotation table here; that is FS-005.

Five things in this migration are not obvious, and each was executed rather than
reasoned about (the plan review's blockers B-1, B-8, B-10 and its R-2, R-5):

* **The tier rule is a RESTRICTIVE policy, not a permissive one.** Written as a
  single permissive clause, a staff caller has no partner, so
  `channel_tier = app_current_partner_tier()` is NULL for every tier row and
  staff resolve nothing but the base list. That breaks the pricing endpoint the
  moment a tier list exists. Permissive policies also OR together, so a later
  feature adding one would defeat the rule entirely. `RBAC.md` §6.3 says
  "restrictive" for exactly this reason.
* **`app_current_partner_tier()` exists so the policy can hoist it.** Called as
  `(SELECT app_current_partner_tier())` it evaluates once per statement: 3.4 ms
  against 136 ms over five thousand rows. A new function's ACL is null, which
  means EXECUTE to PUBLIC, so the REVOKE below is not optional.
* **The four exclusion constraints are four, not two, and they are deferrable.**
  `price_list` has two nullable scope columns, so there are four null patterns;
  a pair split on one column accepts two overlapping rows on the other's null,
  executed. Deferrable because publishing closes a predecessor and publishes a
  successor in one transaction, and doing it in the other order raises.
* **`is_active` stays.** ADR-033 mandates it beside effective dating, and 009 kept
  it on all ten subsidy masters with the semantics that matter: it hides a row
  from a picker and it does not free the range. Resolution never reads it.
* **`price_list_item` takes no UPDATE at all**, and its DELETE is granted at
  table level and restricted by policy to a draft's items. A delete against a
  published list therefore removes zero rows *silently* rather than raising, so
  the 409 the API promises comes from the service's status check, not from here.

Revision ID: 010_products_and_pricing
Revises: 009_subsidy_masters
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision: str = "010_products_and_pricing"
down_revision: str | None = "009_subsidy_masters"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

TABLES = ("product_category", "uom", "product", "product_hsn", "gst_rate",
          "price_list", "price_list_item", "seller_gstin")

# ── grants and hand-written policies, read by tests/db/migration_grants.py ────

GRANTS: dict[str, str] = {
    "product_category": "SELECT, INSERT, UPDATE",
    "uom": "SELECT, INSERT, UPDATE",
    "product": "SELECT, INSERT, UPDATE",
    "product_hsn": "SELECT, INSERT, UPDATE",
    "gst_rate": "SELECT, INSERT, UPDATE",
    "seller_gstin": "SELECT, INSERT, UPDATE",
    "price_list": "SELECT, INSERT, UPDATE",
    # A draft's rates are replaced wholesale, so this one table takes DELETE. The
    # policy below narrows it to drafts; the grant cannot.
    "price_list_item": "SELECT, INSERT, DELETE",
}

_PRODUCTS_READ = "(SELECT app_current_user_id()) IS NOT NULL"
_PRODUCTS_EDIT = "(SELECT app_has_permission('products', 'edit'))"
_PRICING_EDIT = "(SELECT app_has_permission('pricing', 'edit'))"
# The tier a partner caller is entitled to. NULL for staff, which is why the
# clause below is restrictive and starts by letting a non-partner through.
_TIER_OK = ("(SELECT app_current_partner()) IS NULL "
            "OR channel_tier IS NULL "
            "OR channel_tier = (SELECT app_current_partner_tier())")
_ITEM_TIER_OK = ("(SELECT app_current_partner()) IS NULL OR EXISTS ("
                 "SELECT 1 FROM price_list pl WHERE pl.id = price_list_id "
                 "AND (pl.channel_tier IS NULL "
                 "OR pl.channel_tier = (SELECT app_current_partner_tier())))")
_ITEM_DRAFT = ("EXISTS (SELECT 1 FROM price_list pl WHERE pl.id = price_list_id "
               "AND pl.status = 'draft')")

_CATALOGUE = ("product_category", "uom", "product", "product_hsn", "gst_rate", "seller_gstin")

HAND_POLICIES: list[tuple[str, str]] = [
    *[(t, f"""CREATE POLICY {t}_sel ON {t} FOR SELECT USING ({_PRODUCTS_READ})""")
      for t in _CATALOGUE],
    *[(t, f"""CREATE POLICY {t}_ins ON {t} FOR INSERT WITH CHECK ({_PRODUCTS_EDIT})""")
      for t in _CATALOGUE],
    *[(t, f"""CREATE POLICY {t}_upd ON {t} FOR UPDATE USING ({_PRODUCTS_EDIT})""")
      for t in _CATALOGUE],
    # price_list: one permissive read for anyone signed in, one RESTRICTIVE clause
    # that a later permissive policy cannot OR past.
    ("price_list", f"""CREATE POLICY price_list_sel ON price_list FOR SELECT USING ({_PRODUCTS_READ})"""),
    ("price_list", f"""CREATE POLICY price_list_tier ON price_list AS RESTRICTIVE FOR SELECT USING ({_TIER_OK})"""),
    ("price_list", f"""CREATE POLICY price_list_ins ON price_list FOR INSERT WITH CHECK ({_PRICING_EDIT})"""),
    ("price_list", f"""CREATE POLICY price_list_upd ON price_list FOR UPDATE USING ({_PRICING_EDIT})"""),
    ("price_list_item", f"""CREATE POLICY price_list_item_sel ON price_list_item FOR SELECT USING ({_PRODUCTS_READ})"""),
    ("price_list_item", f"""CREATE POLICY price_list_item_tier ON price_list_item AS RESTRICTIVE FOR SELECT USING ({_ITEM_TIER_OK})"""),
    ("price_list_item", f"""CREATE POLICY price_list_item_ins ON price_list_item FOR INSERT WITH CHECK ({_PRICING_EDIT} AND {_ITEM_DRAFT})"""),
    ("price_list_item", f"""CREATE POLICY price_list_item_del ON price_list_item FOR DELETE USING ({_PRICING_EDIT} AND {_ITEM_DRAFT})"""),
]

# ── enums ────────────────────────────────────────────────────────────────────
#
# `channel_tier` is not here: migration 004 created it and its comment says it is
# shared with this table.

ENUMS: dict[str, tuple[str, ...]] = {
    "quotation_category": ("head", "field", "both"),
    "price_list_status": ("draft", "published"),
}

AUDIT = """created_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid        REFERENCES app_user(id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    updated_by    uuid        REFERENCES app_user(id),
    deleted_at    timestamptz,
    external_id   text,
    source_system text        NOT NULL DEFAULT 'crm',
    synced_at     timestamptz"""

# The fields a product may still carry our stand-in value for. `rate` is not one:
# that provenance belongs to the price list, which has its own flag.
PROVISIONAL_FIELDS = ("hsn_code", "gst_slab", "mrp", "pack_multiple")

# The slabs in force. A Council change is a migration, deliberately: it is a
# legal event and it should not be a data entry away.
GST_SLABS = ("0", "0.25", "3", "5", "12", "18", "28")

# Spaces, tab, carriage return, newline, and the non-breaking space. Plain
# `btrim(x)` trims only the first of those, and six of the client's 1,094 rows end
# in a tab or a carriage return; 009's own seeds carry non-breaking spaces.
TRIM_CHARS = r"E' \t\r\n\u00a0'"


def _arr(values: tuple[str, ...]) -> str:
    return "ARRAY[" + ",".join(f"'{v}'" for v in values) + "]::text[]"


def _trimmed(column: str) -> str:
    return f"CHECK ({column} = btrim({column}, {TRIM_CHARS}))"


TABLES_SQL: tuple[str, ...] = (
    f"""CREATE TABLE product_category (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE,
    name text NOT NULL,
    sort_order int NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_product_category_trimmed {_trimmed('code')}
)""",
    f"""CREATE TABLE uom (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code citext NOT NULL UNIQUE,
    name text NOT NULL,
    decimals smallint NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_uom_decimals CHECK (decimals BETWEEN 0 AND 3),
    CONSTRAINT ck_uom_trimmed {_trimmed('code')}
)""",
    f"""CREATE TABLE product (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    item_code citext,
    description citext NOT NULL,
    source_description text,
    source_row int,
    source_file text,
    product_category_id uuid NOT NULL REFERENCES product_category(id),
    quotation_category quotation_category NOT NULL,
    uom_id uuid NOT NULL REFERENCES uom(id),
    mrp numeric(14,2),
    pack_multiple numeric(10,3),
    is_subsidy_eligible boolean NOT NULL DEFAULT true,
    provisional_fields text[] NOT NULL DEFAULT '{{}}',
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT uq_product_description UNIQUE (description),
    CONSTRAINT ck_product_trimmed {_trimmed('description')},
    CONSTRAINT ck_product_description_length CHECK (length(description) BETWEEN 3 AND 200),
    CONSTRAINT ck_product_item_code_trimmed CHECK (item_code IS NULL OR item_code = btrim(item_code, {TRIM_CHARS})),
    CONSTRAINT ck_product_mrp CHECK (mrp IS NULL OR mrp > 0),
    CONSTRAINT ck_product_pack_multiple CHECK (pack_multiple IS NULL OR pack_multiple > 0),
    CONSTRAINT ck_product_provisional CHECK (provisional_fields <@ {_arr(PROVISIONAL_FIELDS)})
)""",
    f"""CREATE TABLE product_hsn (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid NOT NULL REFERENCES product(id),
    hsn_code text NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_product_hsn_code CHECK (hsn_code ~ '^[0-9]{{4,8}}$'),
    CONSTRAINT ck_product_hsn_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_product_hsn EXCLUDE USING gist (
        product_id WITH =, daterange(effective_from, effective_to, '[)') WITH &&)
)""",
    f"""CREATE TABLE gst_rate (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    hsn_code text NOT NULL,
    rate numeric(6,3) NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    {AUDIT},
    CONSTRAINT ck_gst_rate_code CHECK (hsn_code ~ '^[0-9]{{4,8}}$'),
    CONSTRAINT ck_gst_rate_slab CHECK (rate IN ({', '.join(GST_SLABS)})),
    CONSTRAINT ck_gst_rate_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ex_gst_rate EXCLUDE USING gist (
        hsn_code WITH =, daterange(effective_from, effective_to, '[)') WITH &&)
)""",
    f"""CREATE TABLE price_list (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    state_territory_id uuid REFERENCES territory(id),
    channel_tier channel_tier,
    status price_list_status NOT NULL DEFAULT 'draft',
    published_at timestamptz,
    effective_from date NOT NULL,
    effective_to date,
    is_active boolean NOT NULL DEFAULT true,
    is_provisional boolean NOT NULL DEFAULT false,
    source_note text,
    {AUDIT},
    CONSTRAINT ck_price_list_range CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ck_price_list_published CHECK ((status = 'published') = (published_at IS NOT NULL))
)""",
    """CREATE TABLE price_list_item (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    price_list_id uuid NOT NULL REFERENCES price_list(id) ON DELETE CASCADE,
    product_id uuid NOT NULL REFERENCES product(id),
    rate numeric(14,2) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_price_list_item UNIQUE (price_list_id, product_id),
    CONSTRAINT ck_price_list_item_rate CHECK (rate > 0)
)""",
    f"""CREATE TABLE seller_gstin (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    gstin citext NOT NULL UNIQUE,
    legal_name text NOT NULL,
    trade_name text,
    state_territory_id uuid NOT NULL REFERENCES territory(id),
    address text,
    is_default boolean NOT NULL DEFAULT false,
    is_active boolean NOT NULL DEFAULT true,
    effective_from date NOT NULL,
    effective_to date,
    {AUDIT},
    CONSTRAINT ck_seller_gstin_format CHECK (gstin ~ '^[0-9]{{2}}[A-Z]{{5}}[0-9]{{4}}[A-Z][0-9A-Z]{{3}}$'),
    CONSTRAINT ck_seller_gstin_range CHECK (effective_to IS NULL OR effective_to > effective_from)
)""",
)

# The four null patterns of the two scope columns. A pair split on one column
# accepts two overlapping rows on the other's null, executed on 16.14. Published
# rows only, so drafts never collide; deferrable so one transaction can close a
# predecessor and publish a successor in either order.
_RANGE = "daterange(effective_from, effective_to, '[)') WITH &&"
EXCLUSIONS: tuple[str, ...] = (
    f"""ALTER TABLE price_list ADD CONSTRAINT ex_price_list_both EXCLUDE USING gist (
        state_territory_id WITH =, channel_tier WITH =, {_RANGE})
        WHERE (status = 'published' AND state_territory_id IS NOT NULL AND channel_tier IS NOT NULL)
        DEFERRABLE INITIALLY IMMEDIATE""",
    f"""ALTER TABLE price_list ADD CONSTRAINT ex_price_list_state EXCLUDE USING gist (
        state_territory_id WITH =, {_RANGE})
        WHERE (status = 'published' AND state_territory_id IS NOT NULL AND channel_tier IS NULL)
        DEFERRABLE INITIALLY IMMEDIATE""",
    f"""ALTER TABLE price_list ADD CONSTRAINT ex_price_list_tier EXCLUDE USING gist (
        channel_tier WITH =, {_RANGE})
        WHERE (status = 'published' AND state_territory_id IS NULL AND channel_tier IS NOT NULL)
        DEFERRABLE INITIALLY IMMEDIATE""",
    f"""ALTER TABLE price_list ADD CONSTRAINT ex_price_list_base EXCLUDE USING gist ({_RANGE})
        WHERE (status = 'published' AND state_territory_id IS NULL AND channel_tier IS NULL)
        DEFERRABLE INITIALLY IMMEDIATE""",
)

INDEXES: tuple[str, ...] = (
    """CREATE INDEX ix_product_category_lookup ON product (product_category_id, description) WHERE is_active""",
    """CREATE INDEX ix_product_quotation_category ON product (quotation_category) WHERE is_active""",
    """CREATE INDEX ix_product_search ON product USING gin (description gin_trgm_ops)""",
    """CREATE UNIQUE INDEX uq_product_item_code ON product (item_code) WHERE item_code IS NOT NULL""",
    """CREATE INDEX ix_product_hsn_lookup ON product_hsn (product_id, effective_from DESC)""",
    """CREATE INDEX ix_gst_rate_lookup ON gst_rate (hsn_code, effective_from DESC)""",
    """CREATE INDEX ix_price_list_resolve ON price_list (state_territory_id, channel_tier, effective_from DESC) WHERE status = 'published'""",
    """CREATE INDEX ix_price_list_tier ON price_list (channel_tier) WHERE status = 'published'""",
    """CREATE INDEX ix_price_list_item_product ON price_list_item (product_id, price_list_id)""",
    # Two defaults would make the tax split nondeterministic on the same order.
    """CREATE UNIQUE INDEX uq_seller_gstin_default ON seller_gstin (is_default) WHERE is_default AND deleted_at IS NULL""",
)

TRIGGERS: tuple[str, ...] = tuple(
    stmt
    for t in TABLES if t != "price_list_item"
    for stmt in (
        f"""CREATE TRIGGER trg_{t}_updated_at BEFORE UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION set_updated_at()""",
        f"""CREATE TRIGGER trg_{t}_audit AFTER INSERT OR UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION audit_row()""",
    )
)
# A rate has no updated_at to maintain: it is written once and never edited.
TRIGGERS = (*TRIGGERS,
            """CREATE TRIGGER trg_price_list_item_audit AFTER INSERT OR UPDATE OR DELETE ON price_list_item FOR EACH ROW EXECUTE FUNCTION audit_row()""")

# ── the helper the tier policy hoists ────────────────────────────────────────

PARTNER_TIER_FN = """CREATE FUNCTION app_current_partner_tier() RETURNS channel_tier
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
    SELECT p.price_tier
      FROM channel_partner p
     WHERE p.id = app_current_partner()
$fn$"""

# ── seeds ────────────────────────────────────────────────────────────────────

CATEGORIES = (
    ("DRIP COMPONENTS", 1), ("HDPE PIPES", 2), ("EMITTING PIPE", 3),
    ("HDPE SPRINKLER SYSTEM", 4), ("PVC FITTINGS", 5), ("PVC PIPES", 6),
    ("MINI SPRINKLER COMPONENTS", 7), ("PLAIN LATERAL", 8), ("SPRINKLER COMPONENTS", 9),
    ("Marketing", 10),
)
# code, name, decimals. The decimals are enforced: 1.5 of NOS. is a refusal.
UOMS = (("NOS.", "Numbers", 0), ("MTR", "Metres", 3), ("Set.", "Sets", 0), ("ML", "Millilitres", 0))

# The codes that actually apply to this catalogue, and the slabs the client's own
# BOQ workbooks use: 5 % on material, 18 % on service. Stand-ins, and marked as
# such on every product until the client confirms them (GAP-089).
HSN_SLABS = (
    ("3917", "5"),    # plastic tubes, pipes and hoses: laterals, HDPE and PVC pipe
    ("3926", "5"),    # other plastic articles: fittings, connectors, end plugs
    ("8424", "5"),    # mechanical spraying appliances: sprinklers, emitters, filters
    ("8413", "5"),    # pumps for liquids
    ("8481", "5"),    # taps, cocks, valves
    ("6305", "18"),   # sacks and bags of man-made textile: the marketing bags
    ("6601", "18"),   # umbrellas
    ("9608", "18"),   # pens
    ("4820", "18"),   # diaries and notebooks
    ("4911", "5"),    # printed matter: brochures and literature
    ("6505", "5"),    # caps
    ("9995", "18"),   # services, the rate the BOQ workbooks use for installation
)
EFFECTIVE_FROM = "2026-04-01"   # the financial year the client's workbooks belong to


def _hand(table: str) -> None:
    for t, stmt in HAND_POLICIES:
        if t == table:
            op.execute(stmt)


def upgrade() -> None:
    for name, values in ENUMS.items():
        labels = ", ".join(f"'{v}'" for v in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")

    for stmt in TABLES_SQL:
        op.execute(stmt)
    for stmt in EXCLUSIONS:
        op.execute(stmt)
    for stmt in INDEXES:
        op.execute(stmt)
    for stmt in TRIGGERS:
        op.execute(stmt)

    # A new function's ACL is null, which means EXECUTE to PUBLIC. Every migration
    # from 003 on pairs the create with this revoke; without it the pre-auth role
    # could read a partner's tier.
    op.execute(PARTNER_TIER_FN)
    op.execute("REVOKE EXECUTE ON FUNCTION app_current_partner_tier() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_current_partner_tier() TO {APP_ROLE}")

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        _hand(table)
        op.execute(f"GRANT {GRANTS[table]} ON {table} TO {APP_ROLE}")

    for code, order in CATEGORIES:
        op.execute("INSERT INTO product_category (code, name, sort_order) VALUES "
                   f"('{code}', '{code}', {order})")
    for code, name, decimals in UOMS:
        op.execute(f"INSERT INTO uom (code, name, decimals) VALUES ('{code}', '{name}', {decimals})")
    for hsn, rate in HSN_SLABS:
        op.execute("INSERT INTO gst_rate (hsn_code, rate, effective_from) VALUES "
                   f"('{hsn}', {rate}, DATE '{EFFECTIVE_FROM}')")

    # One registration, Gujarat, so the seller's state is a lookup from the start
    # rather than a constant that becomes a signature change (GAP-088). The number
    # is a placeholder with a valid checksum shape; the client's real one replaces
    # it through the admin path.
    op.execute(f"""INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, is_default,
        effective_from)
    SELECT '24AAAAA0000A1Z5', 'Polysil Irrigation Systems Limited', t.id, true,
           DATE '{EFFECTIVE_FROM}'
    FROM territory t WHERE t.level = 'state' AND t.code = 'GJ'""")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app_current_partner_tier()")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
