"""011 effective-dated masters cannot be edited in place (FS-008, FS-010)

Three holes a cross-vendor review found in 009 and 010, all of the same shape:
the rule was written in the service and nothing below the service enforced it.

* **Every dated master still granted UPDATE on its value columns.** 009 withheld
  UPDATE from the two cell tables and stopped there, so an `app_role` caller with
  `masters.edit` could change `subsidy_category.pct`, a parameter's value, a
  component's rate or a crop's standard spacing without creating a revision. No
  constraint and no audit trigger refuses that, and after the service's 60-second
  cache expires every past calculation quietly uses the new figure. CLAUDE.md 4.1
  rule 10 says masters are never edited in place; this is where that becomes true.

  UPDATE has to stay, because closing a row **is** an update: `effective_to` is
  how a revision supersedes its predecessor. So the grant is unchanged and a
  trigger freezes the columns that carry meaning, leaving the lifecycle ones
  alone.

* **A published price list could go back to draft.** `status = 'draft',
  published_at = NULL` satisfies the CHECK and the UPDATE policy, and the
  draft-only item policies then allow deleting and replacing rates a quotation
  was already built on. Withholding UPDATE on `price_list_item` was supposed to
  make published rates immutable, and this route walked around it.

* **Two function hygiene rules were missed, and the suite caught both.** A new
  function's ACL is null, which means EXECUTE to PUBLIC, so the pre-auth role
  could call the triggers' functions; and a pinned `search_path` has to name
  `pg_temp` explicitly and last, or a temp table made by the owner shadows the
  real one. 010's `app_current_partner_tier` has the same `search_path` gap and
  is replaced here, forward-only, because 010 has already run on staging.

* **The exclusion constraints compared citext identity case-sensitively.**
  `btree_gist` has no operator class for citext, so 009 cast to text - and the
  cast is also a downgrade to case-sensitive equality. `Mango` and `MANGO` could
  therefore hold different spacings over the same dates, while the service
  lowercases both into one dictionary key and silently keeps whichever row it read
  last. Executed on 16.14: both rows insert. `lower(x::text)` is immutable, keeps
  the gist operator class, and restores the identity the column declares.

Revision ID: 011_master_immutability
Revises: 010_products_and_pricing
"""
# ruff: noqa: E501

from __future__ import annotations

from alembic import op

revision: str = "011_master_immutability"
down_revision: str | None = "010_products_and_pricing"
branch_labels = None
depends_on = None

# The columns of each dated master that carry meaning: its identity, its value and
# the day it starts. Everything absent is lifecycle - `effective_to`, `is_active`,
# `deleted_at`, the audit columns, and the display fields that print nowhere an
# auditor reads.
#
# `effective_from` is frozen with the values on purpose. Moving a row's start date
# is not a correction, it is a restatement: every document priced between the old
# start and the new one was priced from a row that now says it was not in force.
FROZEN: dict[str, tuple[str, ...]] = {
    "subsidy_category": ("scheme_id", "system_type", "code", "pct", "variant",
                         "per_ha_cap", "gsdma_pct", "effective_from"),
    "subsidy_parameter": ("scheme_id", "system_type", "key", "value", "unit",
                          "effective_from"),
    "subsidy_component_rate": ("scheme_id", "system_type", "component_code", "pipe_size_mm",
                               "nozzle", "uom", "rate", "effective_from"),
    "crop_lateral_spacing": ("scheme_id", "crop", "standard_spacing", "effective_from"),
    "gst_rate": ("hsn_code", "rate", "effective_from"),
    "product_hsn": ("product_id", "hsn_code", "effective_from"),
}

# `to_jsonb` rather than a column list per table: one function, and adding a name
# to FROZEN is then the whole change. SQLSTATE 23514 so it reaches the API as the
# same class of refusal as a CHECK, which is what it is.
REFUSE_VALUE_EDIT = """
CREATE OR REPLACE FUNCTION refuse_value_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
DECLARE
    frozen text;
    was jsonb := to_jsonb(OLD);
    now_ jsonb := to_jsonb(NEW);
BEGIN
    FOREACH frozen IN ARRAY TG_ARGV LOOP
        IF was -> frozen IS DISTINCT FROM now_ -> frozen THEN
            RAISE EXCEPTION
                '% is effective-dated: % cannot be edited in place. Close this row by setting effective_to and insert a revision.',
                TG_TABLE_NAME, frozen
                USING ERRCODE = '23514';
        END IF;
    END LOOP;
    RETURN NEW;
END $$
"""

REFUSE_UNPUBLISH = """
CREATE OR REPLACE FUNCTION refuse_published_price_list_edit() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $$
BEGIN
    -- A draft is freely editable. That is what drafts are for, and it is the whole
    -- reason publication is a separate step.
    IF OLD.status <> 'published' THEN
        RETURN NEW;
    END IF;
    IF NEW.status <> 'published' OR NEW.published_at IS DISTINCT FROM OLD.published_at THEN
        RAISE EXCEPTION
            'a published price list cannot return to draft. Create a new list effective from the day the new rates start, and publish that.'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.state_territory_id IS DISTINCT FROM OLD.state_territory_id
       OR NEW.channel_tier IS DISTINCT FROM OLD.channel_tier
       OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
       OR NEW.is_provisional IS DISTINCT FROM OLD.is_provisional THEN
        RAISE EXCEPTION
            'a published price list''s scope and start date are fixed. Only effective_to may move.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$
"""

# The four constraints whose equality was case-sensitive on a case-insensitive
# column. Each is dropped and rebuilt on `lower(x::text)`; a database already
# holding two rows that differ only in case fails here, loudly, which is the
# right moment to find out.
RECASE: tuple[tuple[str, str, str, str], ...] = (
    ("subsidy_category", "ex_subsidy_category",
     "scheme_id WITH =, system_type WITH =, (lower(code::text)) WITH =, "
     "daterange(effective_from, effective_to, '[)') WITH &&", ""),
    ("crop_lateral_spacing", "ex_crop_lateral_spacing",
     "scheme_id WITH =, (lower(crop::text)) WITH =, "
     "daterange(effective_from, effective_to, '[)') WITH &&", ""),
    ("subsidy_parameter", "ex_subsidy_parameter_all_systems",
     "scheme_id WITH =, (lower(key::text)) WITH =, "
     "daterange(effective_from, effective_to, '[)') WITH &&", "system_type IS NULL"),
    ("subsidy_parameter", "ex_subsidy_parameter_one_system",
     "scheme_id WITH =, system_type WITH =, (lower(key::text)) WITH =, "
     "daterange(effective_from, effective_to, '[)') WITH &&", "system_type IS NOT NULL"),
    ("subsidy_component_rate", "ex_subsidy_component_rate_sized",
     "scheme_id WITH =, system_type WITH =, (lower(component_code::text)) WITH =, "
     "(COALESCE(pipe_size_mm, (-1)::smallint)) WITH =, "
     "daterange(effective_from, effective_to, '[)') WITH &&", "nozzle IS NULL"),
    ("subsidy_component_rate", "ex_subsidy_component_rate_nozzle",
     "scheme_id WITH =, system_type WITH =, (lower(component_code::text)) WITH =, nozzle WITH =, "
     "(COALESCE(pipe_size_mm, (-1)::smallint)) WITH =, "
     "daterange(effective_from, effective_to, '[)') WITH &&", "nozzle IS NOT NULL"),
)

# What 009 wrote, so the downgrade puts it back exactly.
RECASE_ORIGINAL: dict[str, tuple[str, str]] = {
    "ex_subsidy_category": (
        "scheme_id WITH =, system_type WITH =, (code::text) WITH =, "
        "daterange(effective_from, effective_to, '[)') WITH &&", ""),
    "ex_crop_lateral_spacing": (
        "scheme_id WITH =, (crop::text) WITH =, "
        "daterange(effective_from, effective_to, '[)') WITH &&", ""),
    "ex_subsidy_parameter_all_systems": (
        "scheme_id WITH =, (key::text) WITH =, "
        "daterange(effective_from, effective_to, '[)') WITH &&", "system_type IS NULL"),
    "ex_subsidy_parameter_one_system": (
        "scheme_id WITH =, system_type WITH =, (key::text) WITH =, "
        "daterange(effective_from, effective_to, '[)') WITH &&", "system_type IS NOT NULL"),
    "ex_subsidy_component_rate_sized": (
        "scheme_id WITH =, system_type WITH =, (component_code::text) WITH =, "
        "(COALESCE(pipe_size_mm, (-1)::smallint)) WITH =, "
        "daterange(effective_from, effective_to, '[)') WITH &&", "nozzle IS NULL"),
    "ex_subsidy_component_rate_nozzle": (
        "scheme_id WITH =, system_type WITH =, (component_code::text) WITH =, nozzle WITH =, "
        "(COALESCE(pipe_size_mm, (-1)::smallint)) WITH =, "
        "daterange(effective_from, effective_to, '[)') WITH &&", "nozzle IS NOT NULL"),
}


def _where(predicate: str) -> str:
    return f" WHERE ({predicate})" if predicate else ""


def _args(columns: tuple[str, ...]) -> str:
    return ", ".join(f"'{c}'" for c in columns)


# 010 pinned this one to `public` alone. `pg_temp` is searched first when it is
# not named, so a temp `channel_partner` made by the owner would answer instead of
# the real table - the closure `tests/db/test_policies_005.py` proves both ways.
# Forward-only: 010 has run on staging, so this is a replacement, not an edit.
REPIN_PARTNER_TIER = """CREATE OR REPLACE FUNCTION app_current_partner_tier() RETURNS channel_tier
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $fn$
    SELECT p.price_tier
      FROM channel_partner p
     WHERE p.id = app_current_partner()
$fn$"""

NEW_FUNCTIONS = ("refuse_value_edit()", "refuse_published_price_list_edit()")


def upgrade() -> None:
    op.execute(REFUSE_VALUE_EDIT)
    op.execute(REFUSE_UNPUBLISH)
    op.execute(REPIN_PARTNER_TIER)
    # A new function's ACL is null, which means EXECUTE to PUBLIC. A trigger does
    # not check EXECUTE on its own function - the privilege was checked when the
    # trigger was created - so revoking costs nothing and keeps the surface at the
    # eight pre-auth functions the suite asserts.
    for fn in NEW_FUNCTIONS:
        op.execute(f"REVOKE EXECUTE ON FUNCTION {fn} FROM PUBLIC")

    for table, columns in FROZEN.items():
        # BEFORE, so the refusal happens instead of the write rather than after it,
        # and the audit trigger never records an edit that did not happen.
        op.execute(f"""CREATE TRIGGER trg_{table}_frozen BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION refuse_value_edit({_args(columns)})""")

    op.execute("""CREATE TRIGGER trg_price_list_published BEFORE UPDATE ON price_list
        FOR EACH ROW EXECUTE FUNCTION refuse_published_price_list_edit()""")

    for table, name, elements, predicate in RECASE:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                   f"EXCLUDE USING gist ({elements}){_where(predicate)}")


def downgrade() -> None:
    for table, name, _, _predicate in RECASE:
        elements, predicate = RECASE_ORIGINAL[name]
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                   f"EXCLUDE USING gist ({elements}){_where(predicate)}")
    op.execute("DROP TRIGGER IF EXISTS trg_price_list_published ON price_list")
    for table in FROZEN:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_frozen ON {table}")
    op.execute("DROP FUNCTION IF EXISTS refuse_published_price_list_edit()")
    op.execute("DROP FUNCTION IF EXISTS refuse_value_edit()")
    # `app_current_partner_tier` keeps its pinned search_path. A downgrade undoes
    # this migration's own work; it does not put a security gap back.
