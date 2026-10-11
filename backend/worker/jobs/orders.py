"""The order PDF (FS-012 rule 6): rendered once, on approval, by the worker.

The quotation render's shape (`worker/jobs/quotations.py`): the claim commits
before the render and charges the attempt; the render and the upload run outside
any transaction; `order_render_done()` or `order_render_failed()` closes the lease
in its own transaction, conditional on the lease token. The renderer, the filters
and the claim decoding are the quotation's.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from sqlalchemy import text

from api.config import Settings, get_settings
from api.db.session import async_session_factory
from api.domain import orders as domain
from api.services.clock import today_ist
from api.storage import Storage, get_storage
from worker.jobs.outbox import enter_as_principal
from worker.jobs.quotations import (
    _env,
    decode_claim,
    discount_columns,
    discount_tiers,
    render_pdf,
    renderer_available,
)

log = structlog.get_logger(__name__)


def render_html(doc: dict[str, Any]) -> str:
    """Money and rates arrive as strings the filters format; the template does no
    arithmetic. No approver names and no remarks (rule 9): the claim strips them."""
    o = doc["order"]
    tiers = discount_tiers(doc["lines"])
    return _env.get_template("order.html").render(
        o=o, lines=doc["lines"], tiers=tiers, discount_cols=discount_columns(tiers),
        is_provisional=bool(o.get("is_provisional")),
        intra_state=bool(o.get("intra_state")), rendered_on=today_ist().strftime("%d %b %Y"))


def render_document(doc: dict[str, Any], settings: Settings) -> tuple[bytes, str]:
    html = render_html(doc)
    if settings.pdf_renderer == "html":
        return html.encode("utf-8"), "text/html; charset=utf-8"
    problem = renderer_available()
    if problem:
        raise RuntimeError(f"the PDF renderer is unavailable: {problem}")
    return render_pdf(html), "application/pdf"


async def _call(settings: Settings, sql: str, params: dict[str, Any]) -> Any:
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        return (await session.execute(text(sql), params)).scalar_one()


async def render_one(settings: Settings, storage: Storage) -> str | None:
    """Claim, render, upload, close. None when nothing was due."""
    doc = await _call(settings, "SELECT order_render_claim(make_interval(mins => :m))",
                      {"m": settings.pdf_lease_minutes})
    if doc is None:
        return None
    doc = decode_claim(doc)
    order_id, lease = str(doc["order"]["id"]), str(doc["lease_token"])
    try:
        # synchronous libraries, off the loop that drains the sign-in codes
        data, content_type = await asyncio.to_thread(render_document, doc, settings)
        key = domain.pdf_storage_key(order_id, lease)
        await asyncio.to_thread(storage.put, key, data, content_type)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("order.render_failed", order=order_id, attempt=doc.get("attempt"),
                  error=error[:300])
        await _call(settings, "SELECT order_render_failed(CAST(:id AS uuid), "
                              "CAST(:lease AS uuid), :err)",
                    {"id": order_id, "lease": lease, "err": error})
        return "failed"
    if not await _call(settings, "SELECT order_render_done(CAST(:id AS uuid), "
                                 "CAST(:lease AS uuid), :key)",
                       {"id": order_id, "lease": lease, "key": key}):
        log.warning("order.render_stale", order=order_id, orphan=key)
        return "stale"
    log.info("order.rendered", order=order_id, key=key, renderer=content_type)
    return "ready"


_ticking = False


async def order_render_due(ctx: dict[str, Any], *, batch: int = 20) -> int:
    """Every five seconds, offset from the quotation tick: what is pending, up to
    `batch`, within the render budget. One tick at a time in this process."""
    global _ticking
    if _ticking:
        return 0
    _ticking = True
    try:
        settings = get_settings()
        storage: Storage = ctx.get("storage") or get_storage(settings)
        started = time.monotonic()
        handled = 0
        while handled < batch and time.monotonic() - started < settings.pdf_render_budget:
            if await render_one(settings, storage) is None:
                break
            handled += 1
        return handled
    finally:
        _ticking = False
