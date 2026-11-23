"""The email port (ADR-020, FS-078), beside the WhatsApp one.

A provider never raises. It returns the WhatsApp outcome classes, so the drain maps
an email the same way it maps a message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.errors import HeaderParseError
from email.headerregistry import Address
from typing import Protocol

from api.integrations.whatsapp.provider import ProviderResult

SUBJECT_MAX = 150
# One ASCII addr-spec. The same pattern decides eligibility in migration 082
# (`ADDRESS_RE` there); a test holds the two equal (code review F-4). A list, a
# display name or a header never matches (EC-5, ISS-221).
ADDRESS_RE = r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$"
_ADDRESS = re.compile(ADDRESS_RE)


@dataclass(frozen=True)
class Email:
    to: str              # one addr-spec, checked by parse_address
    to_name: str
    subject: str
    text: str
    html: str
    reference: str       # the outbox row id


class EmailProvider(Protocol):
    async def send(self, msg: Email) -> ProviderResult: ...


def parse_address(raw: str | None) -> str | None:
    """Exactly one addr-spec, or None. Stricter than the profile's check on
    purpose: `a@x.com,b@y.com` is stored today (ISS-221) and must mail nobody."""
    s = (raw or "").strip()
    if not _ADDRESS.fullmatch(s):
        return None
    try:
        address = Address(addr_spec=s)
    except (ValueError, IndexError, HeaderParseError):
        return None
    if address.addr_spec != s or not address.username or "." not in address.domain:
        return None
    return s


def one_line(text: str, limit: int = SUBJECT_MAX) -> str:
    """A subject: every line break and run of space collapsed, cut at `limit` (EC-18)."""
    s = " ".join(text.split())
    return s if len(s) <= limit else s[: limit - 3].rstrip() + "..."
