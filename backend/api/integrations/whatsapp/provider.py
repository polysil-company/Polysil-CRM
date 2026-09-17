"""The provider port (ADR-020), as FS-007 shapes it.

A provider never raises for a business failure and never for a transport failure
either: it returns an outcome the worker maps onto the row. The worker stays free
of provider knowledge, and the provider stays free of the database.
"""

from __future__ import annotations

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


def scrub(text: str, secrets: Iterable[str]) -> str:
    """Rule 5: every secret and every value sent is replaced by substring, then the
    text is bounded. Applied to every error a provider returns and to every line
    the live scripts print."""
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out[:ERROR_MAX]


def mask(recipient: str) -> str:
    """Enough to correlate a delivery failure, not enough to be a phone list."""
    return f"{recipient[:4]}…{recipient[-2:]}" if len(recipient) > 6 else "…"
