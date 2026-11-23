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
import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.config import Settings, get_settings
from api.db.session import async_session_factory
from api.domain import orders as domain
from api.domain import quotations as quotation_domain
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


_OUTCOMES = {"approved": "Approved", "rejected": "Returned for changes",
             "cancelled": "Withdrawn", "pending": "Waiting"}
_env.filters["outcome"] = lambda v: _OUTCOMES.get(str(v), str(v).replace("_", " ").capitalize())


def render_html(doc: dict[str, Any], *, internal: bool = False) -> str:
    """Money and rates arrive as strings the filters format; the template does no
    arithmetic. The customer copy has no approver names and no remarks (rule 9):
    the claim keeps them out of `order`, and only the internal copy (FS-091) is
    given the claim's `internal` key."""
    o = doc["order"]
    tiers = discount_tiers(doc["lines"])
    return _env.get_template("order.html").render(
        o=o, lines=doc["lines"], tiers=tiers, discount_cols=discount_columns(tiers),
        # FS-069 rule 16, FS-088 rule 11: each charge is a row of its own, so the rows
        # add up to the total
        charges=quotation_domain.charge_rows(o),
        is_provisional=bool(o.get("is_provisional")),
        intra_state=bool(o.get("intra_state")), rendered_on=today_ist().strftime("%d %b %Y"),
        internal=(doc.get("internal") or {"approvals": []}) if internal else None)


def render_document(doc: dict[str, Any], settings: Settings, *,
                    internal: bool = False) -> tuple[bytes, str]:
    html = render_html(doc, internal=internal)
    if settings.pdf_renderer == "html":
        return html.encode("utf-8"), "text/html; charset=utf-8"
    problem = renderer_available()
    if problem:
        raise RuntimeError(f"the PDF renderer is unavailable: {problem}")
    return render_pdf(html), "application/pdf"


def _render_and_store(doc: dict[str, Any], settings: Settings, storage: Storage,
                      order_id: str, lease: str) -> tuple[str | None, str | None, str]:
    """Mode `both`: the customer copy, then the internal one. An internal copy that
    fails does not hold back the dealer's: the customer copy is published, the
    internal key is None, and claim branch 2 retries it (FS-091 rule 8, plan review
    R-4). Mode `internal`: an order already ready owes only its internal copy; the
    customer copy is not rendered again (EC-1), and its key is None."""
    content_type = "application/pdf"
    key = None
    if doc.get("mode", "both") == "both":
        data, content_type = render_document(doc, settings)
        key = domain.pdf_storage_key(order_id, lease)
        storage.put(key, data, content_type)
    internal_key: str | None = domain.internal_pdf_storage_key(order_id, lease,
                                                                uuid.uuid4().hex)
    try:
        internal, content_type = render_document(doc, settings, internal=True)
        storage.put(internal_key, internal, content_type)  # type: ignore[arg-type]
    except Exception as exc:
        if key is None:
            raise
        log.warning("order.internal_copy_failed", order=order_id,
                    error=f"{type(exc).__name__}: {exc}"[:300])
        internal_key = None
    return key, internal_key, content_type


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
        key, internal_key, content_type = await asyncio.to_thread(
            _render_and_store, doc, settings, storage, order_id, lease)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("order.render_failed", order=order_id, attempt=doc.get("attempt"),
                  mode=doc.get("mode"), error=error[:300])
        await _call(settings, "SELECT order_render_failed(CAST(:id AS uuid), "
                              "CAST(:lease AS uuid), :err)",
                    {"id": order_id, "lease": lease, "err": error})
        return "failed"
    try:
        published = await _call(settings, "SELECT order_render_done(CAST(:id AS uuid), "
                                          "CAST(:lease AS uuid), :key, :internal)",
                                {"id": order_id, "lease": lease, "key": key,
                                 "internal": internal_key})
    except DBAPIError as exc:
        # plan review R-1: the deploy starts this worker before 092 is applied, and
        # the four-argument done does not exist yet (42883). The lease lapses and the
        # order is claimed again once the migration lands. Anything else is a real
        # fault and propagates (code review F-1).
        if _sqlstate(exc) != "42883":
            raise
        log.warning("order.render_done_unavailable", order=order_id, error=str(exc)[:300])
        return "failed"
    if not published:
        log.warning("order.render_stale", order=order_id, orphan=key,
                    orphan_internal=internal_key)
        return "stale"
    log.info("order.rendered", order=order_id, key=key, internal_key=internal_key,
             mode=doc.get("mode"), renderer=content_type)
    return "ready"


def _sqlstate(exc: DBAPIError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


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
