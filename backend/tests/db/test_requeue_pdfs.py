"""scripts/requeue_pdfs.py: only live quotations go back in the render queue."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import importlib.util
import pathlib

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.db import test_migration_012 as m12
from tests.db.conftest import Fixtures

pytestmark = pytest.mark.db

_spec = importlib.util.spec_from_file_location(
    "requeue_pdfs", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "requeue_pdfs.py")
assert _spec and _spec.loader
requeue_pdfs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(requeue_pdfs)


async def test_a_dead_quotation_keeps_its_failed_pdf(db: AsyncSession, ids: Fixtures) -> None:
    """PR 11 review: a re-render queues the share link, so a superseded or rejected
    quotation must not come back and message the farmer late."""
    lead = await m12._lead(db, ids)
    live = await m12._quotation(db, ids, lead, status="sent")
    old = await m12._quotation(db, ids, lead, status="sent")
    rejected = await m12._quotation(db, ids, lead, status="rejected")
    await db.execute(text("UPDATE quotation SET superseded_by_id = CAST(:n AS uuid) WHERE id = CAST(:o AS uuid)"),
                     {"n": live, "o": old})
    await db.execute(text("UPDATE quotation SET pdf_state = 'failed', pdf_attempts = 5 "
                          "WHERE id = ANY(CAST(:q AS uuid[]))"), {"q": [live, old, rejected]})
    quotations, _ = await requeue_pdfs.requeue_rows(db)
    back = {str(r.id) for r in quotations}
    assert live in back
    assert old not in back and rejected not in back
