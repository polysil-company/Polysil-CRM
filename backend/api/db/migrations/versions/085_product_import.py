"""085: a `products` import kind (FS-083).

`import_batch.kind` gains `products`. The check was unnamed in 074, so Postgres
named it `import_batch_kind_check`.

Revision ID: 085_product_import
Revises: 084_lead_follows_office
"""

from __future__ import annotations

from alembic import op

revision: str = "085_product_import"
down_revision: str | None = "084_lead_follows_office"
branch_labels = None
depends_on = None

OLD = ("partners", "price_list_items", "lines")
NEW = (*OLD, "products")


def _check(kinds: tuple[str, ...]) -> None:
    values = ", ".join(f"'{k}'" for k in kinds)
    op.execute("ALTER TABLE import_batch DROP CONSTRAINT import_batch_kind_check")
    op.execute(f"ALTER TABLE import_batch ADD CONSTRAINT import_batch_kind_check "
               f"CHECK (kind IN ({values}))")


def upgrade() -> None:
    _check(NEW)


def downgrade() -> None:
    # a committed product batch would break the old check; it is history, so it goes
    op.execute("DELETE FROM import_batch WHERE kind = 'products'")
    _check(OLD)
