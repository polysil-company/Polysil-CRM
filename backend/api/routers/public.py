"""/public (FS-005 4): the farmer's link, as app_anon.

No session, no cookie, no Authorization. Both quotation endpoints reach the
database only through the two definer functions granted to app_anon (the
pre-auth surface is ten functions, asserted by the suite); the token is the
whole credential. `/public/files/{sig}` exists for the local storage adapter
only and serves a file the API itself signed for ten minutes.
"""

from __future__ import annotations

import datetime as dt
from datetime import timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Path, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from api.config import get_settings
from api.deps import AnonSession
from api.domain.quotations import limiter_key
from api.errors import NotFoundError
from api.integrations import cache
from api.routers.auth import _client_ip
from api.schemas.auth import Envelope, ErrorResponse
from api.schemas.leads import UUID_RE
from api.schemas.public_leads import (
    PublicLeadCreate,
    PublicLeadForm,
    PublicLeadResult,
    PublicTerritory,
    VerifyRequest,
    VerifySent,
)
from api.schemas.quotations import PublicQuotation
from api.services import public_leads as lead_capture
from api.services import quotations as service
from api.storage import LocalStorage, filename_from_query, get_storage

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/public", tags=["public"])

Token = Annotated[str, Path(min_length=20, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]

_ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "Unknown link."},
}

# 60 a minute per link and per source address (FS-005 4). The limit protects the
# PDF's cost, not the token's secrecy, so when Redis is unreachable the endpoint
# serves and logs rather than failing a customer-facing link (edge case 18).
PDF_BURST = 60
PDF_WINDOW = timedelta(minutes=1)


async def _over_limit(token: str, request: Request) -> bool:
    key = limiter_key(token)
    ip = _client_ip(request) or "unknown"
    try:
        per_link = await cache.hit_rate_limit(f"q:pdf:{key}", PDF_BURST, PDF_WINDOW)
        per_ip = await cache.hit_rate_limit(f"q:pdf:ip:{ip}", PDF_BURST, PDF_WINDOW)
    except Exception as exc:  # Redis down: serve, and say so
        log.warning("public.limiter_unavailable", kind=type(exc).__name__)
        return False
    return per_link or per_ip


@router.get("/q/{token}", response_model=Envelope[PublicQuotation], responses=_ERRORS)
async def public_quotation(token: Token, db: AnonSession) -> Envelope[PublicQuotation]:
    """What the farmer's link shows before the PDF: the number, the seller, the
    validity, the total, and whether the document is expired or superseded. **No
    name, no mobile, no address, no lines.** Show a "View quotation" button that
    opens `pdf_url` in a new tab; do not fetch the PDF on page load, because
    messengers fetch a link's landing page to draw a preview the moment the
    message is sent, and that must not count as a view.
    """
    return Envelope(data=await service.public_view(db, token))


@router.get("/q/{token}/pdf", status_code=302,
            responses={**_ERRORS, 409: {"model": ErrorResponse,
                                        "description": "The PDF is not ready yet."},
                       429: {"model": ErrorResponse, "description": "Too many opens."}})
async def public_quotation_pdf(token: Token, request: Request, db: AnonSession) -> Response:
    """Records the view (the first open moves the quotation to `viewed`; later
    opens only count), then redirects to the PDF: a URL valid for ten minutes.
    Superseded and expired documents still open. `409 pdf_pending` while the
    worker has not finished.
    """
    if await _over_limit(token, request):
        body = ('{"error": {"code": "rate_limited", '
                '"message": "Too many opens; try again in a minute."}}')
        return Response(status_code=429, content=body, media_type="application/json")
    url = await service.public_open(db, token, request.headers.get("user-agent"),
                                    get_storage(get_settings()))
    return RedirectResponse(url, status_code=302)


@router.get("/files/{sig}", responses=_ERRORS, include_in_schema=False)
async def local_file(sig: Annotated[str, Path(max_length=1024)],
                     name: Annotated[str | None, Query()] = None) -> Response:
    """The local storage adapter's signed URL (dev box only). Not part of the
    contract: on staging and production the PDF is a presigned R2 URL."""
    storage = get_storage(get_settings())
    if not isinstance(storage, LocalStorage):
        raise NotFoundError("Not served here.")
    key = storage.verify(sig, now=dt.datetime.now(tz=dt.UTC))
    if key is None:
        raise NotFoundError("The link has expired.")
    data, content_type = storage.get(key)
    filename = filename_from_query(name)
    return Response(content=data, media_type=content_type,
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


# ── the public lead form (FS-003a) ───────────────────────────────────────────

_LEAD_ERRORS: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "An unknown or inactive QR code."},
    422: {"model": ErrorResponse, "description": "A field, or `invalid_code`."},
    429: {"model": ErrorResponse, "description": "Too many codes for this number or address."},
}


@router.get("/lead-form", response_model=Envelope[PublicLeadForm], responses=_LEAD_ERRORS)
async def lead_form(db: AnonSession, qr: Annotated[str | None, Query(
        max_length=12, description="The code from the page URL, if the farmer scanned one."
)] = None) -> Envelope[PublicLeadForm]:
    """What the enquiry page needs before the farmer types: the QR code's label and
    campaign (show "Enquiry through Shah Irrigation" at the top), the states, the
    irrigation systems and the inquiry types. Districts and talukas come from
    `GET /public/territories?parent_id=`."""
    return Envelope(data=await lead_capture.form(db, qr))


@router.get("/territories", response_model=Envelope[list[PublicTerritory]],
            responses=_LEAD_ERRORS)
async def public_territories(db: AnonSession, parent_id: Annotated[str, Query(
        pattern=UUID_RE, description="A state for its districts, a district for its talukas."
)]) -> Envelope[list[PublicTerritory]]:
    """The children of one territory, name and id only, at most 200."""
    return Envelope(data=await lead_capture.territories(db, parent_id))


@router.post("/leads/verify", status_code=202, response_model=Envelope[VerifySent],
             responses=_LEAD_ERRORS)
async def lead_verify(body: VerifyRequest, request: Request,
                      db: AnonSession) -> Envelope[VerifySent]:
    """Send the farmer a six-digit WhatsApp code for this mobile. The body is the
    same whether or not the number is known to Polysil. Offer "send again" after
    `resend_after` seconds; a new code replaces the old one."""
    return Envelope(data=await lead_capture.request_code(db, body.mobile, _client_ip(request)))


@router.post("/leads", status_code=201, response_model=Envelope[PublicLeadResult],
             responses={**_LEAD_ERRORS,
                        200: {"model": Envelope[PublicLeadResult],
                              "description": "Already enquired today, or a retry: the "
                                             "earlier inquiry number."}})
async def public_lead(body: PublicLeadCreate) -> Response:
    """Create the lead once the code matches. Show the farmer the `inquiry_no`
    either way; the acknowledgement also goes by WhatsApp, but it can be held back
    (one a day per number), so the page is the place they read it. A retry after a
    lost response returns the same number. `invalid_code` covers a wrong, expired
    or used-up code: offer to send a new one."""
    status, result = await lead_capture.submit(body)
    return JSONResponse(status_code=status, content={"data": result.model_dump(mode="json")})
