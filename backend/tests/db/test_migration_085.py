"""085: `import_batch.kind` takes `products` and still refuses an unknown kind."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.db

INSERT = ("INSERT INTO import_batch (kind, file_name, file_sha256, header_row, headers, rows, row_count, created_by) "
          "VALUES (:k, 'x.csv', repeat('0', 64), 1, '[]', '[]', 0, "
          "(SELECT id FROM app_user ORDER BY created_at LIMIT 1))")


async def test_products_is_a_kind_and_an_unknown_one_is_refused(db: AsyncSession) -> None:
    await db.execute(text(INSERT), {"k": "products"})
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(text(INSERT), {"k": "suppliers"})
