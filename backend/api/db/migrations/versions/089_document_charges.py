"""089: installation and fittings charges on quotations and orders (FS-088).

* `quotation` and `sales_order` gain seven columns per charge, as 077 gave freight,
  with the same three CHECKs each. The columns come from one KINDS tuple, so a
  fourth charge is one entry (rule 17).
* The header identity becomes `taxable = gross - discount + every charge`. NOT
  VALID then VALIDATE, as 077. Old code that writes freight only still satisfies it.
* `sales_order` is column-granted (013, 077), so the new columns are granted here.
* `quotation_public_view(text)` gains each charge in its `totals`, so the public
  page reads them instead of deriving one from the identity (plan review B-1).
  The body is swapped by its live text, as 072 does; the signature does not change.

Revision ID: 089_document_charges
Revises: 088_held_districts
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision: str = "089_document_charges"
down_revision: str | None = "088_held_districts"
branch_labels = None
depends_on = None

APP_ROLE = "app_role"

# api/domain/pricing/tax.py CHARGE_KINDS without freight, which 077 added
KINDS = ("installation", "fittings")
_SUFFIXES = ("amount", "slab", "slab_chosen", "cgst", "sgst", "igst", "total")
_TYPE_COLUMN = {"quotation": "sales_type", "sales_order": "order_type"}
# 077's SLABS
_SLAB_LIST = "0, 0.25, 3, 5, 12, 18, 28, 40"


def columns(kind: str) -> tuple[str, ...]:
    return tuple(f"{kind}_{s}" for s in _SUFFIXES)


ALL_COLUMNS = tuple(c for k in KINDS for c in columns(k))

GRANTS: dict[str, str] = {
    "sales_order": f"INSERT ({', '.join(ALL_COLUMNS)}), UPDATE ({', '.join(ALL_COLUMNS)})",
}

IDENTITY_077 = "taxable = gross - discount + COALESCE(freight_amount, 0)"
IDENTITY = ("taxable = gross - discount + COALESCE(freight_amount, 0)"
            + "".join(f" + COALESCE({k}_amount, 0)" for k in KINDS))

VIEW_SIG = "quotation_public_view(text)"
VIEW_OLD = "'cgst', q.cgst, 'sgst', q.sgst, 'igst', q.igst, 'total', q.total),"
VIEW_NEW = ("'cgst', q.cgst, 'sgst', q.sgst, 'igst', q.igst, 'total', q.total,\n"
            "                                     'freight', q.freight_amount, "
            "'installation', q.installation_amount, 'fittings', q.fittings_amount),")


def _swap(sig: str, old: str, new: str) -> None:
    body = str(op.get_bind().execute(
        text(f"SELECT pg_get_functiondef('{sig}'::regprocedure)")).scalar_one())
    if body.count(old) != 1:
        raise RuntimeError(f"089: {sig} anchor found {body.count(old)} times")
    op.execute(body.replace(old, new))


def _add(table: str, type_col: str, kind: str) -> str:
    cols = columns(kind)
    return f"""ALTER TABLE {table}
        ADD COLUMN {kind}_amount numeric(14,2), ADD COLUMN {kind}_slab numeric(6,3),
        ADD COLUMN {kind}_slab_chosen boolean, ADD COLUMN {kind}_cgst numeric(14,2),
        ADD COLUMN {kind}_sgst numeric(14,2), ADD COLUMN {kind}_igst numeric(14,2),
        ADD COLUMN {kind}_total numeric(14,2),
        ADD CONSTRAINT ck_{table}_{kind}_set CHECK (
            num_nulls({', '.join(cols)}) IN (0, {len(cols)})),
        ADD CONSTRAINT ck_{table}_{kind}_figures CHECK ({kind}_amount IS NULL OR (
            {kind}_amount > 0
            AND {kind}_total = {kind}_amount + {kind}_cgst + {kind}_sgst + {kind}_igst
            AND {kind}_slab IN ({_SLAB_LIST}))),
        ADD CONSTRAINT ck_{table}_{kind}_type CHECK (
            {kind}_amount IS NULL OR {type_col}::text IN ('commercial', 'industrial'))"""


def _identity(table: str, expr: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT ck_{table}_taxable_identity")
    # NOT VALID then VALIDATE: the scan runs without the write lock held
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT ck_{table}_taxable_identity "
               f"CHECK ({expr}) NOT VALID")
    op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT ck_{table}_taxable_identity")


def upgrade() -> None:
    for table, type_col in _TYPE_COLUMN.items():
        for kind in KINDS:
            op.execute(_add(table, type_col, kind))
        _identity(table, IDENTITY)
    for table, verbs in GRANTS.items():
        op.execute(f"GRANT {verbs} ON {table} TO {APP_ROLE}")
    _swap(VIEW_SIG, VIEW_OLD, VIEW_NEW)
    # a re-created function keeps its grants; this is belt and braces (028, 087)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {VIEW_SIG} FROM PUBLIC")


def downgrade() -> None:
    # taxable and total include the charges; dropping the columns would leave them
    # unexplained, and the restored identity would refuse the rows
    checks = " OR ".join(f"EXISTS (SELECT 1 FROM {t} WHERE {k}_amount IS NOT NULL)"
                         for t in _TYPE_COLUMN for k in KINDS)
    op.execute(f"""DO $$ BEGIN
        IF {checks} THEN
            RAISE EXCEPTION '089 downgrade: documents carry installation or fittings; remove them first';
        END IF;
    END $$""")
    _swap(VIEW_SIG, VIEW_NEW, VIEW_OLD)
    op.execute(f"REVOKE EXECUTE ON FUNCTION {VIEW_SIG} FROM PUBLIC")
    for table in _TYPE_COLUMN:
        _identity(table, IDENTITY_077)
        for kind in KINDS:
            for ck in ("set", "figures", "type"):
                op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{kind}_{ck}")
        op.execute(f"ALTER TABLE {table} " + ", ".join(f"DROP COLUMN IF EXISTS {c}" for c in ALL_COLUMNS))
