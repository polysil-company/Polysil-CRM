"""The quotation worker (FS-005 5.2): the render lease and the nightly expiry.

**Three transactions per document, and no network call inside any of them.**
`quotation_render_claim()` leases one row and commits, charging the attempt; the
render and the upload happen outside any transaction; `quotation_render_done()`
or `quotation_render_failed()` closes the lease in a transaction of its own,
conditional on the lease token so a stale worker finishing after its lease was
reclaimed writes nothing. A worker that dies mid-render leaves a lease that
expires, and the next tick reclaims the row with the charge already recorded.
That is the shape `worker/jobs/outbox.py` earned the hard way, with a lease in
place of a held lock (cross-vendor B-5).

Every transaction enters as the system principal (FS-002 5.6). The system
principal holds no module permissions, so every access goes through a definer
guarded on `app_is_system()`; nothing here reads `quotation` directly.

The renderer is probed at startup and logged, never refused: a missing PDF
library fails jobs with a recorded `pdf_error`, not the CRM (edge case 20).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import functools
import json
import pathlib
from decimal import Decimal
from typing import Any

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import text

from api.config import Settings, get_settings
from api.db.session import async_session_factory
from api.domain import quotations as domain
from api.services.clock import IST, today_ist
from api.storage import Storage, get_storage
from worker.jobs.outbox import enter_as_principal

log = structlog.get_logger(__name__)

TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                   autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)


# ── rendering ────────────────────────────────────────────────────────────────

def _money(v: Any) -> str:
    return f"{Decimal(str(v)):.2f}"


def _pct(v: Any) -> str:
    return f"{Decimal(str(v)):.3f}"


def _date(v: Any) -> str:
    """A date as given, or a timestamp on the IST calendar: `sent_at` is stored
    in UTC, and a send at 00:30 IST is the day before in UTC (rule 10)."""
    if not v:
        return ""
    s = str(v)
    if len(s) > 10:
        stamp = dt.datetime.fromisoformat(s)
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(IST)
        return stamp.date().strftime("%d %b %Y")
    return dt.date.fromisoformat(s).strftime("%d %b %Y")


_env.filters.update(money=_money, pct=_pct, date=_date)


def render_html(doc: dict[str, Any]) -> str:
    """The document as HTML. Money and rates arrive as strings the filters format;
    the template does no arithmetic (FS-005 5.3)."""
    q = doc["quotation"]
    lines = doc["lines"]
    return _env.get_template("quotation.html").render(
        q=q, lines=lines, is_provisional=bool(q.get("is_provisional")),
        intra_state=bool(q.get("intra_state")), rendered_on=today_ist().strftime("%d %b %Y"))


@functools.cache
def renderer_available() -> str | None:
    """None when WeasyPrint imports, else why not. Cached: the answer does not
    change while the process lives, and the import is expensive."""
    try:
        import weasyprint  # noqa: F401
    except Exception as exc:  # OSError on a missing native library, ImportError otherwise
        return f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
    return None


def render_pdf(html: str) -> bytes:
    import weasyprint

    return bytes(weasyprint.HTML(string=html).write_pdf())


def render_document(doc: dict[str, Any], settings: Settings) -> tuple[bytes, str]:
    """The bytes and their content type. `pdf_renderer = html` is the dev box's
    fallback and settings refuse it anywhere else."""
    html = render_html(doc)
    if settings.pdf_renderer == "html":
        return html.encode("utf-8"), "text/html; charset=utf-8"
    problem = renderer_available()
    if problem:
        raise RuntimeError(f"the PDF renderer is unavailable: {problem}")
    return render_pdf(html), "application/pdf"


# ── the render job ───────────────────────────────────────────────────────────

def decode_claim(doc: Any) -> dict[str, Any]:
    """The claim's jsonb with every number a Decimal: json's default float would
    put the money path through IEEE-754 (rule 4). A dict from a codec is re-read
    the same way, so both shapes decode alike."""
    raw = doc if isinstance(doc, str) else json.dumps(doc)
    return dict(json.loads(raw, parse_float=Decimal))


async def _claim(settings: Settings) -> dict[str, Any] | None:
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        doc = (await session.execute(
            text("SELECT quotation_render_claim(make_interval(mins => :m))"),
            {"m": settings.pdf_lease_minutes})).scalar_one()
    if doc is None:
        return None
    return decode_claim(doc)


async def _done(settings: Settings, quotation_id: str, lease: str, key: str, link: str) -> bool:
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        return bool((await session.execute(
            text("SELECT quotation_render_done(CAST(:id AS uuid), CAST(:lease AS uuid), "
                 ":key, :link)"),
            {"id": quotation_id, "lease": lease, "key": key, "link": link})).scalar_one())


async def _failed(settings: Settings, quotation_id: str, lease: str, error: str) -> bool:
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        return bool((await session.execute(
            text("SELECT quotation_render_failed(CAST(:id AS uuid), CAST(:lease AS uuid), :err)"),
            {"id": quotation_id, "lease": lease, "err": error})).scalar_one())


async def render_one(settings: Settings, storage: Storage) -> str | None:
    """Claim, render, upload, close. Returns the outcome, or None when nothing was
    due."""
    doc = await _claim(settings)
    if doc is None:
        return None
    q = doc["quotation"]
    quotation_id, lease = str(q["id"]), str(doc["lease_token"])
    try:
        # WeasyPrint and boto3 are synchronous; on the loop they would stall the
        # outbox drain that sends sign-in codes (cross-vendor A-5)
        data, content_type = await asyncio.to_thread(render_document, doc, settings)
        key = domain.storage_key(quotation_id, int(q["version"]), lease)
        await asyncio.to_thread(storage.put, key, data, content_type)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.error("quotation.render_failed", quotation=quotation_id,
                  attempt=doc.get("attempt"), error=error[:300])
        await _failed(settings, quotation_id, lease, error)
        return "failed"
    link = domain.share_url(settings.public_web_url, str(q["share_token"]))
    if not await _done(settings, quotation_id, lease, key, link):
        # a stale lease: someone else reclaimed and finished it. This attempt's
        # object sits under its own key and nothing points at it.
        log.warning("quotation.render_stale", quotation=quotation_id, orphan=key)
        return "stale"
    log.info("quotation.rendered", quotation=quotation_id, key=key, renderer=content_type)
    return "ready"


async def quotation_render_due(ctx: dict[str, Any], *, batch: int = 20) -> int:
    """Every five seconds: render what is pending, one document per lease, up to
    `batch` in one tick. Twelve a minute is a field team's pace, not a bulk send's."""
    settings = get_settings()
    storage: Storage = ctx.get("storage") or get_storage(settings)
    handled = 0
    while handled < batch:
        outcome = await render_one(settings, storage)
        if outcome is None:
            break
        handled += 1
    return handled


# ── the nightly expiry ───────────────────────────────────────────────────────

async def quotation_expire(ctx: dict[str, Any]) -> int:
    """00:05 IST. The date is today_ist() passed in: current_date is UTC on this
    box and would expire everything a day late (FS-005 rule 10)."""
    settings = get_settings()
    async with async_session_factory() as session, session.begin():
        await enter_as_principal(session, settings)
        count = int((await session.execute(
            text("SELECT quotation_expire_due(:today)"), {"today": today_ist()})).scalar_one())
    if count:
        log.info("quotation.expired", count=count)
    return count
