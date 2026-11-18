"""073: price lists scoped to a sale type (FS-061).

- `price_list.sales_type`: commercial, industrial or subsidised; null is a general
  list that applies to every sale type. Text with a CHECK, so a fourth value is a
  constraint swap rather than an enum migration. Existing lists stay general
  (GAP-470).
- The four overlap exclusions from 010 become two. They had one per null pattern
  of (state, tier); a third nullable key would need eight. `coalesce` folds a null
  state and a null sale type into a key of their own. The tier cannot be folded:
  its cast to text is not immutable (`enum_out` is STABLE), and any enum value
  used as a stand-in is a real tier (`farmer`, GAP-091). So the split is on the
  tier alone. Same meaning as before: two published lists collide when their
  dates overlap and state, tier and sale type are each equal, null equal to null.
- `refuse_published_price_list_edit()`: a published list's sale type is fixed,
  like its state and tier (FS-061 section 5).

Revision ID: 073_price_list_sales_type
Revises: 057_portal_ratings
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op

revision: str = "073_price_list_sales_type"
down_revision: str | None = "057_portal_ratings"
branch_labels = None
depends_on = None

NO_STATE = "'00000000-0000-0000-0000-000000000000'::uuid"
_RANGE = "daterange(effective_from, effective_to, '[)') WITH &&"
_KEYS = f"(coalesce(state_territory_id, {NO_STATE})) WITH =, (coalesce(sales_type, '')) WITH ="

EXCLUSIONS: tuple[str, ...] = (
    f"""ALTER TABLE price_list ADD CONSTRAINT ex_price_list_tiered EXCLUDE USING gist (
        {_KEYS}, channel_tier WITH =, {_RANGE})
        WHERE (status = 'published' AND channel_tier IS NOT NULL)
        DEFERRABLE INITIALLY IMMEDIATE""",
    f"""ALTER TABLE price_list ADD CONSTRAINT ex_price_list_untiered EXCLUDE USING gist (
        {_KEYS}, {_RANGE})
        WHERE (status = 'published' AND channel_tier IS NULL)
        DEFERRABLE INITIALLY IMMEDIATE""",
)

OLD_NAMES = ("ex_price_list_both", "ex_price_list_state", "ex_price_list_tier", "ex_price_list_base")

TRIGGER_FN = """
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
       OR NEW.sales_type IS DISTINCT FROM OLD.sales_type
       OR NEW.effective_from IS DISTINCT FROM OLD.effective_from
       OR NEW.is_provisional IS DISTINCT FROM OLD.is_provisional THEN
        RAISE EXCEPTION
            'a published price list''s scope and start date are fixed. Only effective_to may move.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$
"""

TRIGGER_FN_011 = TRIGGER_FN.replace(
    "       OR NEW.sales_type IS DISTINCT FROM OLD.sales_type\n", "")


def upgrade() -> None:
    op.execute("ALTER TABLE price_list ADD COLUMN sales_type text")
    op.execute("ALTER TABLE price_list ADD CONSTRAINT ck_price_list_sales_type "
               "CHECK (sales_type IN ('commercial', 'industrial', 'subsidised'))")
    for name in OLD_NAMES:
        op.execute(f"ALTER TABLE price_list DROP CONSTRAINT {name}")
    for sql in EXCLUSIONS:
        op.execute(sql)
    op.execute(TRIGGER_FN)


def downgrade() -> None:
    # 010's four exclusions, verbatim.
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    path = next(Path(__file__).parent.glob("010_*.py"))
    spec = spec_from_file_location("mig_010_for_073", path)
    assert spec is not None and spec.loader is not None
    m010 = module_from_spec(spec)
    spec.loader.exec_module(m010)

    op.execute(TRIGGER_FN_011)
    op.execute("ALTER TABLE price_list DROP CONSTRAINT ex_price_list_tiered")
    op.execute("ALTER TABLE price_list DROP CONSTRAINT ex_price_list_untiered")
    # A typed list has no meaning without the column; refuse rather than drop it.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM price_list WHERE sales_type IS NOT NULL) THEN
            RAISE EXCEPTION 'typed price lists exist; delete or close them before downgrading 073';
        END IF; END $$""")
    for sql in m010.EXCLUSIONS:
        op.execute(sql)
    op.execute("ALTER TABLE price_list DROP CONSTRAINT ck_price_list_sales_type")
    op.execute("ALTER TABLE price_list DROP COLUMN sales_type")
