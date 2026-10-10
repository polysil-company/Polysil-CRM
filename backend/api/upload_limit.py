"""The size cap on complaint attachment uploads (FS-015 rule 10, plan review B-2).

FastAPI reads the whole form before any handler or dependency runs, and
Starlette spools file parts to disk with no cap, so a handler cannot refuse a
large body early. This ASGI middleware can:

- a `Content-Length` over the cap is answered `413` before a byte is read;
- without a length, `receive` is wrapped and the byte count checked as it
  arrives. Past the cap it raises `BodyTooLarge`, an `HTTPException`, which
  FastAPI re-raises out of its form parsing (routing.py: "If a middleware raises
  an HTTPException, it should be raised again") and `body_too_large_handler`
  answers in the envelope.

It must sit inside `request_context` (registered first in `create_app`). Outside
that `BaseHTTPMiddleware`, which reads the body through its own task group, the
exception reached FastAPI wrapped and was answered as a 400 parse error.

Caddy's `request_body { max_size 12MB }` is the outer belt; the dev box has no
Caddy, so this is the only one there.

FS-038 adds the WhatsApp webhook paths at 64 KB, on both public mounts and for
every method, so each path pattern carries its own limit and message.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.domain.complaints import MAX_UPLOAD_BYTES

# the file itself may be up to 10 MB; the multipart framing around it is not
BODY_LIMIT = MAX_UPLOAD_BYTES + 64 * 1024
WEBHOOK_LIMIT = 64 * 1024
_UPLOAD_MESSAGE = "Up to 10 MB."
_WEBHOOK_MESSAGE = "Up to 64 KB."

# (path, methods or None for any, limit, message)
_LIMITS: list[tuple[re.Pattern[str], frozenset[str] | None, int, str]] = [
    # complaint attachments (FS-015), subsidy documents (FS-009) and visit photos (FS-021)
    (re.compile(r"^/api/v1/(complaints/[^/]+/attachments|subsidy-applications/[^/]+/documents"
                r"|visits/[^/]+/photos)/?$"), frozenset({"POST"}), BODY_LIMIT, _UPLOAD_MESSAGE),
    # FS-038 rule 4: 11za's webhook calls, on both public mounts
    (re.compile(r"^(/api/v1)?/public/webhooks/whatsapp/"), None, WEBHOOK_LIMIT, _WEBHOOK_MESSAGE),
]


def _envelope(message: str) -> dict[str, Any]:
    code = "attachment_too_large" if message == _UPLOAD_MESSAGE else "body_too_large"
    return {"error": {"code": code, "message": message}}


class BodyTooLarge(HTTPException):
    def __init__(self, message: str = _UPLOAD_MESSAGE) -> None:
        super().__init__(status_code=413, detail=message)


async def body_too_large_handler(_: Request, exc: Exception) -> JSONResponse:
    message = exc.detail if isinstance(exc, BodyTooLarge) else _UPLOAD_MESSAGE
    return JSONResponse(status_code=413, content=_envelope(str(message)))


def _limit_for(scope: Scope) -> tuple[int, str] | None:
    path, method = scope.get("path", ""), scope.get("method")
    for pattern, methods, limit, message in _LIMITS:
        if (methods is None or method in methods) and pattern.match(path):
            return limit, message
    return None


class UploadLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        found = _limit_for(scope) if scope["type"] == "http" else None
        if found is None:
            await self.app(scope, receive, send)
            return
        limit, message = found
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > limit:
            await _refuse(send, message)
            return
        seen = 0

        async def counted() -> Message:
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise BodyTooLarge(message)
            return msg

        await self.app(scope, counted, send)


async def _refuse(send: Send, message: str) -> None:
    body = json.dumps(_envelope(message)).encode()
    headers: list[Any] = [(b"content-type", b"application/json"),
                          (b"content-length", str(len(body)).encode()),
                          (b"connection", b"close")]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})
