"""FS-038 step one: keep each call 11za makes to the webhook URLs, as it arrived.

Nothing here interprets a call. The raw bytes are the record; the decoded text
and the parsed JSON are conveniences for reading the rows, so each is built so
that no body, however odd, can fail the insert (edge cases EC-5, EC-6).
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import re
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings

# header values worth hiding even from the superuser who reads these rows: a
# provider credential, if 11za sends one, is kept by name only (review Q-1)
_SENSITIVE = re.compile(r"authorization|cookie|token|key|secret|password", re.IGNORECASE)

log = structlog.get_logger(__name__)


class WebhookStoreError(Exception):
    """The insert failed. The route catches it and answers the 500 itself, so no
    exception reaches Starlette: uvicorn prints any exception that does, and a
    DBAPIError's text holds the statement's parameters, the farmer's number and
    words. `from None` alone is not enough: SQLAlchemy re-attaches the database
    error as the cause while the request's transaction unwinds (code review F-1,
    rule 7, executed)."""


def secret_matches(settings: Settings, given: str) -> bool:
    """Bytes, not str: `compare_digest` raises on a non-ASCII str (EC-3)."""
    configured = settings.whatsapp_webhook_secret
    if configured is None:
        return False
    return hmac.compare_digest(given.encode("utf-8"), configured.get_secret_value().encode("utf-8"))


def header_pairs(raw: list[tuple[bytes, bytes]]) -> list[list[str]]:
    """Every header in order, repeats kept, sensitive values masked by name."""
    out: list[list[str]] = []
    for name_b, value_b in raw:
        name = name_b.decode("latin-1")
        value = value_b.decode("latin-1")
        if _SENSITIVE.search(name):
            value = f"<masked, {len(value)} chars>"
        out.append([name, value.replace("\x00", "�")])
    return out


def parse_ip(value: str | None) -> str | None:
    """`_client_ip` returns text; `host:port` or `unknown` would fail the inet cast (EC-9)."""
    if not value:
        return None
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    # Python accepts a scope id (fe80::1%eth0); Postgres inet does not (review F-7)
    return None if getattr(ip, "scope_id", None) else str(ip)


def body_text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace").replace("\x00", "�")


def body_json(raw: bytes) -> str | None:
    """The body as jsonb text, or None when Postgres could not hold it."""
    try:
        parsed: Any = json.loads(raw)
        dumped = json.dumps(parsed, allow_nan=False, ensure_ascii=False)
    except (ValueError, RecursionError, UnicodeDecodeError):
        return None
    if "\\u0000" in dumped or "\x00" in dumped:
        return None
    try:
        # a lone surrogate (an emoji cut in half by a UTF-16 runtime) parses in
        # Python and fails both the encode and jsonb (review F-2)
        dumped.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return dumped


async def record(db: AsyncSession, *, kind: str, method: str, ip: str | None,
                 headers: list[tuple[bytes, bytes]], raw: bytes) -> None:
    try:
        # a savepoint, so a failure leaves the request's transaction clean and the
        # route can answer the 500 itself (see WebhookStoreError)
        async with db.begin_nested():
            await db.execute(text(
                "SELECT whatsapp_webhook_record(:kind, :method, CAST(:ip AS inet), "
                "CAST(:headers AS jsonb), :raw, :text, CAST(:body AS jsonb))"),
                {"kind": kind, "method": method, "ip": parse_ip(ip),
                 "headers": json.dumps(header_pairs(headers), ensure_ascii=False),
                 "raw": raw, "text": body_text(raw), "body": body_json(raw)})
    except Exception as exc:
        # any failure, not only DBAPIError: an encode error in the driver carries
        # the parameter too. The class and the SQLSTATE are enough to act on.
        orig = exc.orig if isinstance(exc, DBAPIError) else None
        log.error("whatsapp_webhook.store_failed", kind=kind, error=type(exc).__name__,
                  sqlstate=str(getattr(orig, "sqlstate", "") or ""))
        raise WebhookStoreError() from None
