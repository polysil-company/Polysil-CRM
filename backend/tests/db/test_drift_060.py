# ruff: noqa: E501  (embedded SQL)

"""The live `complaint_remedy_replacement` is migration 060's text (FS-049): built from
026's by anchored replacements, so a later edit to either shows here."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db.migration_grants import _load

pytestmark = pytest.mark.db


def _body(stmt: str) -> str:
    tag = "$fn$" if "$fn$" in stmt else "$function$"
    return " ".join(stmt[stmt.index(tag) + len(tag):stmt.rindex(tag)].split())


async def test_the_live_body_is_060s(db: AsyncSession) -> None:
    m = _load("060_replacement_chain")
    assert m is not None
    live = (await db.execute(text(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'complaint_remedy_replacement'"))).scalars().all()
    assert len(live) == 1
    assert _body(live[0]) == _body(m.COMPLAINT_REMEDY_REPLACEMENT_060)
