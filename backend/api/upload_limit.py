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
# complaint attachments (FS-015) and subsidy documents (FS-009)
_PATH = re.compile(
    r"^/api/v1/(complaints/[^/]+/attachments|subsidy-applications/[^/]+/documents)/?$")
_BODY = {"error": {"code": "attachment_too_large", "message": "Up to 10 MB."}}


class BodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413, detail="Up to 10 MB.")


async def body_too_large_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(status_code=413, content=_BODY)


class UploadLimit:
    def __init__(self, app: ASGIApp, limit: int = BODY_LIMIT) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope.get("method") != "POST"
                or not _PATH.match(scope.get("path", ""))):
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.limit:
            await _refuse(send)
            return
        seen = 0

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise BodyTooLarge()
            return message

        await self.app(scope, counted, send)


async def _refuse(send: Send) -> None:
    body = json.dumps(_BODY).encode()
    headers: list[Any] = [(b"content-type", b"application/json"),
                          (b"content-length", str(len(body)).encode()),
                          (b"connection", b"close")]
    await send({"type": "http.response.start", "status": 413, "headers": headers})
    await send({"type": "http.response.body", "body": body})
