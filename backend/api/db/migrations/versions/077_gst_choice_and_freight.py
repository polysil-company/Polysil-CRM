"""077: a GST slab chosen per line, and a freight charge (FS-069).

* `quotation_line` and `order_line` gain `hsn_slab` (the product's HSN slab at
  pricing) and `gst_slab_chosen`. `gst_slab` stays the line's slab: the chosen one,
  else the HSN's. A BEFORE INSERT trigger fills `hsn_slab` from `gst_slab` when a
  writer leaves it out, so every existing writer keeps working, the complaint
  replacement definer (060's text, drift-pinned) among them.
* The backfill runs with the line triggers disabled. Sent quotation lines and
  submitted order lines refuse any UPDATE, the owner's included (012, 013), so a
  plain UPDATE fails on any database holding one, and CI's empty database would
  not show it (plan review B-1). 063 set the pattern.
* `quotation` and `sales_order` gain the freight columns. `gross` and `discount`
  stay the goods only; `taxable`, the taxes and `total` include freight, and the
  header identity `taxable = gross - discount + freight` is a CHECK, so a writer
  that forgets freight fails (plan review B-2).
* `gst_rate` accepts the Council's 40 % slab.
* `app_setting` gains the kind `slabs` and the setting `gst_slab_choices`.

Revision ID: 077_gst_choice_and_freight
Revises: 076_quotation_print_block
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic import op

revision: str = "077_gst_choice_and_freight"
down_revision: str | None = "076_quotation_print_block"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# FS-069: the Council's slabs, 40 % from 22 Sep 2025. `api/domain/pricing/tax.py`
# holds the same list.
SLABS_BEFORE = ("0", "0.25", "3", "5", "12", "18", "28")
SLABS = (*SLABS_BEFORE, "40")
_SLAB_LIST = ", ".join(SLABS)

_FREIGHT = ("freight_amount", "freight_slab", "freight_slab_chosen", "freight_cgst",
            "freight_sgst", "freight_igst", "freight_total")
_TYPE_COLUMN = {"quotation": "sales_type", "sales_order": "order_type"}

GRANTS: dict[str, str] = {
    # sales_order is column-granted (013); quotation and the line tables have table grants
    "sales_order": f"INSERT ({', '.join(_FREIGHT)}), UPDATE ({', '.join(_FREIGHT)})",
}

_LINE_TRIGGERS = {
    "quotation_line": ("trg_quotation_line_refuse_sent_edit", "trg_quotation_line_updated_at",
                       "trg_quotation_line_audit"),
    "order_line": ("trg_order_line_refuse_edit", "trg_order_line_updated_at",
                   "trg_order_line_audit"),
}

HSN_SLAB_FILL = """CREATE FUNCTION line_hsn_slab_fill() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_temp AS $fn$
BEGIN
    -- FS-069: a writer that predates the choice leaves hsn_slab out; its line is
    -- the HSN's own slab. A chosen line must say what it was chosen over.
    IF NEW.hsn_slab IS NULL THEN
        IF NEW.gst_slab_chosen THEN
            RAISE EXCEPTION 'a chosen GST slab needs hsn_slab' USING ERRCODE = '23502';
        END IF;
        NEW.hsn_slab := NEW.gst_slab;
    END IF;
    RETURN NEW;
END $fn$"""


def _066_check() -> str:
    path = Path(__file__).with_name("066_int_setting_whole.py")
    spec = importlib.util.spec_from_file_location("mig_066_for_077", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return str(mod.AFTER)


CHECK_BEFORE = _066_check()
_ANCHOR = """    ELSE
        IF jsonb_typeof(NEW.value) <> 'array' THEN
            RAISE EXCEPTION 'setting %: a list of role codes', NEW.key USING ERRCODE = 'SETVL';"""
if CHECK_BEFORE.count(_ANCHOR) != 1:
    raise RuntimeError("077: anchor not found once in app_setting_check")
CHECK_AFTER = CHECK_BEFORE.replace(_ANCHOR, f"""    ELSIF NEW.kind = 'slabs' THEN
        -- FS-069: GST slabs as decimal strings, each a slab in force, none twice
        IF jsonb_typeof(NEW.value) <> 'array' OR jsonb_array_length(NEW.value) = 0 THEN
            RAISE EXCEPTION 'setting %: a list of GST slabs', NEW.key USING ERRCODE = 'SETVL';
        END IF;
        FOR e IN SELECT x FROM jsonb_array_elements(NEW.value) x LOOP
            -- nested, not OR: SQL does not promise the cast runs after the shape test
            IF jsonb_typeof(e) <> 'string' OR (e #>> '{{}}') !~ '^[0-9]+(\\.[0-9]+)?$' THEN
                RAISE EXCEPTION 'setting %: % is not a GST slab', NEW.key, e USING ERRCODE = 'SETVL';
            END IF;
            IF (e #>> '{{}}')::numeric NOT IN ({_SLAB_LIST}) THEN
                RAISE EXCEPTION 'setting %: % is not a GST slab', NEW.key, e USING ERRCODE = 'SETVL';
            END IF;
        END LOOP;
        IF (SELECT count(DISTINCT (x #>> '{{}}')::numeric) FROM jsonb_array_elements(NEW.value) x)
           <> jsonb_array_length(NEW.value) THEN
            RAISE EXCEPTION 'setting %: a slab is listed twice', NEW.key USING ERRCODE = 'SETVL';
        END IF;
{_ANCHOR}""")

SEED = """INSERT INTO app_setting (key, kind, value, allowed, min, max, description) VALUES
('gst_slab_choices', 'slabs', '["0", "5", "18", "40"]', NULL, NULL, NULL,
 'The GST slabs a commercial or industrial line, and freight, may be set to.')
ON CONFLICT (key) DO NOTHING"""


def _kind_check(kinds: str) -> str:
    return ("ALTER TABLE app_setting DROP CONSTRAINT app_setting_kind_check, "
            f"ADD CONSTRAINT app_setting_kind_check CHECK (kind IN ({kinds}))")


def _slab_check(slabs: tuple[str, ...]) -> str:
    return ("ALTER TABLE gst_rate DROP CONSTRAINT ck_gst_rate_slab, "
            f"ADD CONSTRAINT ck_gst_rate_slab CHECK (rate IN ({', '.join(slabs)}))")


def upgrade() -> None:
    op.execute(_slab_check(SLABS))

    # ── lines ──
    for table, triggers in _LINE_TRIGGERS.items():
        op.execute(f"ALTER TABLE {table} ADD COLUMN hsn_slab numeric(6,3), "
                   f"ADD COLUMN gst_slab_chosen boolean NOT NULL DEFAULT false")
        for trg in triggers:
            op.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trg}")
        op.execute(f"UPDATE {table} SET hsn_slab = gst_slab")
        for trg in triggers:
            op.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trg}")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN hsn_slab SET NOT NULL, "
                   f"ADD CONSTRAINT ck_{table}_gst_chosen CHECK (gst_slab_chosen = (gst_slab <> hsn_slab))")
    op.execute(HSN_SLAB_FILL)
    # a new function is EXECUTE to PUBLIC; a trigger function needs no caller grant
    op.execute("REVOKE EXECUTE ON FUNCTION line_hsn_slab_fill() FROM PUBLIC")
    for table in _LINE_TRIGGERS:
        # named to sort before the refuse trigger, which reads nothing of these columns
        op.execute(f"CREATE TRIGGER trg_{table}_a_hsn_slab BEFORE INSERT ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION line_hsn_slab_fill()")

    # ── headers ──
    for table, type_col in _TYPE_COLUMN.items():
        op.execute(f"""ALTER TABLE {table}
            ADD COLUMN freight_amount numeric(14,2), ADD COLUMN freight_slab numeric(6,3),
            ADD COLUMN freight_slab_chosen boolean, ADD COLUMN freight_cgst numeric(14,2),
            ADD COLUMN freight_sgst numeric(14,2), ADD COLUMN freight_igst numeric(14,2),
            ADD COLUMN freight_total numeric(14,2),
            ADD CONSTRAINT ck_{table}_freight_set CHECK (
                num_nulls({', '.join(_FREIGHT)}) IN (0, {len(_FREIGHT)})),
            ADD CONSTRAINT ck_{table}_freight_figures CHECK (freight_amount IS NULL OR (
                freight_amount > 0
                AND freight_total = freight_amount + freight_cgst + freight_sgst + freight_igst
                AND freight_slab IN ({_SLAB_LIST}))),
            ADD CONSTRAINT ck_{table}_freight_type CHECK (
                freight_amount IS NULL OR {type_col}::text IN ('commercial', 'industrial'))""")
        # NOT VALID then VALIDATE: the scan runs without the write lock held
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_taxable_identity CHECK ("
                   f"taxable = gross - discount + COALESCE(freight_amount, 0)) NOT VALID")
        op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT ck_{table}_taxable_identity")
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")

    # ── the setting ──
    op.execute(_kind_check("'choice', 'int', 'roles', 'bands', 'slabs'"))
    op.execute(CHECK_AFTER)
    op.execute(SEED)


def downgrade() -> None:
    # taxable and total include freight; dropping the columns would leave them
    # unexplained, and the identity CHECK would fail the next upgrade
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM quotation WHERE freight_amount IS NOT NULL)
           OR EXISTS (SELECT 1 FROM sales_order WHERE freight_amount IS NOT NULL) THEN
            RAISE EXCEPTION '077 downgrade: documents carry freight; remove it first';
        END IF;
    END $$""")
    op.execute("DELETE FROM activity_event WHERE kind = 'setting.changed' "
               "AND payload ->> 'key' = 'gst_slab_choices'")
    op.execute("DELETE FROM app_setting WHERE key = 'gst_slab_choices'")
    op.execute(CHECK_BEFORE)
    op.execute(_kind_check("'choice', 'int', 'roles', 'bands'"))
    for table in _TYPE_COLUMN:
        for ck in ("freight_set", "freight_figures", "freight_type", "taxable_identity"):
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{ck}")
        op.execute(f"ALTER TABLE {table} " + ", ".join(f"DROP COLUMN IF EXISTS {c}" for c in _FREIGHT))
    for table in _LINE_TRIGGERS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_a_hsn_slab ON {table}")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_gst_chosen, "
                   f"DROP COLUMN IF EXISTS hsn_slab, DROP COLUMN IF EXISTS gst_slab_chosen")
    op.execute("DROP FUNCTION IF EXISTS line_hsn_slab_fill()")
    # a 40 % rate row would break the old check; the downgrade refuses rather than
    # deleting a tax record
    op.execute(_slab_check(SLABS_BEFORE))
