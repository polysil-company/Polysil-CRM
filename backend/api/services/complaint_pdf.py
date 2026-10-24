"""A complaint as a PDF (FS-074, BE-031), made when asked for.

- Every read happens first, as the caller sees it: `get_complaint` and the timeline,
  both already reduced for a dealer. Then the render and the upload, and nothing
  touches the database after them (EC-7).
- The page prints fixed words per event kind, never a payload or an id (EC-1), times
  in IST (EC-12), "Not visible to you" for a link out of scope (EC-11), and no
  printing time or live SLA flag, so an unchanged complaint gives the same file
  (EC-6).
- Stored under `complaint-pdf/`, apart from the evidence photos under `complaints/`
  (EC-2, GAP-527), keyed by the HTML's sha256.
- At most two renders at once in a process, shared with the data sheet (EC-4).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import re
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.authz.predicate import Caller
from api.config import get_settings
from api.errors import NotFoundError, ServiceUnavailableError
from api.pdf import env, logo, logo_only_fetcher, render_pdf, render_slot, renderer_available
from api.schemas import complaints as sch
from api.schemas.quotations import PdfLink
from api.services import complaints
from api.storage import Storage

log = structlog.get_logger()

IST = ZoneInfo("Asia/Kolkata")
MAX_EVENTS = 1000
_PAGE = 100
_STORAGE_DOWN = "File storage is not available right now. Try again in a few minutes."
_BIDI = re.compile("[‪-‮⁦-⁩]")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

# One phrase per event kind. An unknown kind prints as itself, never its payload.
WORDS: dict[str, str] = {
    "complaint.created": "Complaint raised",
    "complaint.updated": "Details changed",
    "complaint.attachment_added": "File added",
    "complaint.attachment_removed": "File removed",
    "complaint.submitted": "Submitted",
    "complaint.registered": "Registered",
    "complaint.returned": "Returned for correction",
    "complaint.approved": "Checked and sent to QC",
    "complaint.qc_approved": "QC accepted the complaint",
    "complaint.qc_rejected": "QC rejected the complaint",
    "complaint.remedy_chosen": "Remedy chosen",
    "complaint.remedy_withdrawn": "Remedy withdrawn",
    "complaint.refund_requested": "Refund requested",
    "complaint.refund_rejected": "Refund rejected",
    "complaint.refund_paid": "Refund paid",
    "complaint.replacement_ordered": "Replacement ordered",
    "complaint.replacement_cancelled": "Replacement cancelled",
    "complaint.escalated": "Escalated",
    "complaint.cancelled": "Cancelled",
    "complaint.closed": "Closed",
    "complaint.reopened": "Reopened",
}


def when(value: str | None) -> str:
    """A timestamp in IST, `dd Mon yyyy, HH:MM`; a plain date as it is (EC-12)."""
    if not value:
        return ""
    if len(value) == 10:
        return dt.date.fromisoformat(value).strftime("%d %b %Y")
    return dt.datetime.fromisoformat(value).astimezone(IST).strftime("%d %b %Y, %H:%M")


def clean_name(name: str) -> str:
    return _BIDI.sub("", name)


def filename(complaint_no: str, extension: str) -> str:
    """`Poly/Comp./2026-27/GJ/01` becomes `Complaint-Poly-Comp.-2026-27-GJ-01.pdf`
    (plan review R-3): a slash cannot go in a download name."""
    return f"Complaint-{_UNSAFE.sub('-', complaint_no).strip('-')}.{extension}"


async def history(db: AsyncSession, caller: Caller, complaint_id: str) -> tuple[list[Any], int]:
    """Oldest first, up to MAX_EVENTS, and how many earlier ones were left out (EC-3).
    The timeline pages newest first, so the newest MAX_EVENTS are the ones kept."""
    events: list[Any] = []
    cursor: str | None = None
    while len(events) < MAX_EVENTS:
        page = await complaints.timeline(db, caller, complaint_id, limit=_PAGE, cursor=cursor)
        events.extend(page.data)
        cursor = page.meta.next_cursor
        if cursor is None:
            break
    omitted = 0
    if cursor is not None:
        total: int = (await db.execute(text(
            "SELECT count(*) FROM activity_event WHERE entity_type = 'complaint' "
            "AND entity_id = CAST(:c AS uuid) "
            "AND NOT (CAST(:portal AS boolean) AND kind = 'complaint.escalated')"),
            {"c": complaint_id, "portal": caller.partner_id is not None})).scalar_one()
        omitted = max(int(total) - len(events), 0)
    events = events[:MAX_EVENTS]
    events.reverse()
    return events, omitted


def _previous_round(c: sch.Complaint) -> bool:
    """FS-074 EC-9: reopened, and the verdict or remedy shown is older than the
    reopening, so it belongs to the round before. Once the new round has its own
    verdict, the earlier one is in the history only (plan review B-1)."""
    if not c.reopened_at:
        return False
    reopened = dt.datetime.fromisoformat(c.reopened_at)
    stamps = [x for x in ((c.quality.at if c.quality else None),
                          (c.remedy.chosen_at if c.remedy else None)) if x]
    return any(dt.datetime.fromisoformat(s) < reopened for s in stamps)


def html(c: sch.Complaint, events: list[Any], omitted: int) -> str:
    rows = [{"when": when(e.occurred_at),
             "what": WORDS.get(e.kind, e.kind),
             "who": e.actor.full_name if e.actor else ""} for e in events]
    return env.get_template("complaint.html").render(
        c=c, logo=logo(), when=when, events=rows, omitted=omitted,
        previous_round=_previous_round(c),
        files=[clean_name(a.filename) for a in c.attachments])


async def pdf_link(db: AsyncSession, caller: Caller, complaint_id: str,
                   storage: Storage) -> PdfLink:
    c = await complaints.get_complaint(db, caller, complaint_id)
    if c.pdf_state != "ready" or not c.complaint_no:
        raise NotFoundError("No PDF: the complaint is a draft.")
    html_mode = get_settings().pdf_renderer == "html"
    # the renderer before the reads it would waste (plan review R-7)
    if not html_mode and renderer_available():
        raise ServiceUnavailableError("PDFs cannot be made right now.", code="pdf_unavailable")
    events, omitted = await history(db, caller, complaint_id)
    page = html(c, events, omitted)
    digest = hashlib.sha256(page.encode("utf-8")).hexdigest()
    extension, content_type = (("html", "text/html; charset=utf-8") if html_mode
                               else ("pdf", "application/pdf"))
    key = f"complaint-pdf/{c.id}/{digest}.{extension}"
    with render_slot():
        body = (page.encode("utf-8") if html_mode
                else await asyncio.to_thread(render_pdf, page, logo_only_fetcher()))
        try:
            await asyncio.to_thread(storage.put, key, body, content_type)
        except Exception as exc:   # network errors are not RuntimeError (plan review R-6)
            log.warning("complaint.storage_unavailable", reason=type(exc).__name__)
            raise ServiceUnavailableError(_STORAGE_DOWN, code="storage_unavailable") from exc
    name = filename(c.complaint_no, extension)
    try:
        url, expires = storage.presign_get(key, filename=name)
    except Exception as exc:
        log.warning("complaint.storage_unavailable", reason=type(exc).__name__)
        raise ServiceUnavailableError(_STORAGE_DOWN, code="storage_unavailable") from exc
    return PdfLink(url=url, expires_at=expires.isoformat(), filename=name)
