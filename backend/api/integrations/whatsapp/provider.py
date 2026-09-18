"""The provider port (ADR-020), as FS-007 shapes it.

A provider never raises for a business failure and never for a transport failure
either: it returns an outcome the worker maps onto the row. The worker stays free
of provider knowledge, and the provider stays free of the database.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

ERROR_MAX = 500
_DIGITS = re.compile(r"\D")


class Outcome(StrEnum):
    ACCEPTED = "accepted"      # the body says success; provider_msg_id may be None
    TRANSIENT = "transient"    # transport, 429, 5xx, a token error: uncharged, the breaker
    REFUSED = "refused"        # the provider refused this message; charged
    PERMANENT = "permanent"    # refused, and retrying cannot help


@dataclass(frozen=True)
class OutboundMessage:
    channel: str
    recipient: str                 # as stored on the row
    template_key: str
    payload: dict[str, object]
    reference: str                 # the outbox row id, sent as `tags` for correlation


@dataclass(frozen=True)
class ProviderResult:
    outcome: Outcome
    provider_msg_id: str | None = None
    error: str | None = None       # scrubbed of the token and every value sent (rule 5)


class MessageProvider(Protocol):
    async def send(self, msg: OutboundMessage) -> ProviderResult: ...

    async def list_templates(self) -> list[dict[str, object]]: ...


def to_sendto(recipient: str) -> str | None:
    """Rule 9: digits only, country code first, no plus, whatever form the row
    carries. None for anything that is not a phone number."""
    digits = _DIGITS.sub("", recipient)
    if not 10 <= len(digits) <= 15 or digits.startswith("0"):
        return None
    return digits


def _forms(secret: str) -> list[str]:
    """The secret as it may appear in a body: as typed, JSON-escaped (a provider
    that writes `/` as `\\/`, or non-ASCII as `\\uXXXX`), and URL-escaped. A base64
    token carries slashes, so the literal form alone missed a real echo
    (cross-vendor review of the code, P1)."""
    forms = [secret]
    escaped = json.dumps(secret, ensure_ascii=True)[1:-1]
    if escaped != secret:
        forms.append(escaped)
    if "/" in secret:
        forms.append(secret.replace("/", "\\/"))
        forms.append(secret.replace("/", "%2F"))
    return forms


def scrub(text: str, secrets: Iterable[str]) -> str:
    """Rule 5: every secret and every value sent is replaced by substring, in every
    form it may take, then the text is bounded. Applied to every error a provider
    returns and to every line the live scripts print."""
    out = text
    for secret in secrets:
        if not secret:
            continue
        for form in _forms(secret):
            out = out.replace(form, "***")
    return out[:ERROR_MAX]


def scrub_body(text: str, secrets: Iterable[str]) -> str:
    """A response body for diagnostics: decoded when it is JSON, every string
    value scrubbed, re-serialised; the raw text scrubbed otherwise. Decoding first
    is what catches an escape the raw text hides."""
    try:
        decoded = json.loads(text) if text else None
    except ValueError:
        decoded = None
    if isinstance(decoded, (dict, list)):
        def walk(v: object) -> object:
            if isinstance(v, str):
                return scrub(v, secrets)
            if isinstance(v, dict):
                return {str(k): walk(x) for k, x in v.items()}
            if isinstance(v, list):
                return [walk(x) for x in v]
            return v
        return scrub(json.dumps(walk(decoded), ensure_ascii=False), secrets)
    return scrub(text, secrets)


def mask(recipient: str) -> str:
    """Enough to correlate a delivery failure, not enough to be a phone list."""
    return f"{recipient[:4]}…{recipient[-2:]}" if len(recipient) > 6 else "…"
