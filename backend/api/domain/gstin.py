"""A GSTIN read from itself (FS-051 rule 7): its shape, its check character, its state
code and the PAN inside it. No network: details from the GST portal need a provider
(GAP-292)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# 2-digit state, 10-character PAN, entity number, the letter Z by default, check character.
# The same shape as channel_partner's CHECK (004).
SHAPE: Final = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][Z][0-9A-Z]$")
PAN_SHAPE: Final = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
_CHARS: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# GST state codes: 01 to 38 for the states and union territories, 97 other territory,
# 99 centre jurisdiction
STATE_CODES: Final = frozenset({f"{i:02d}" for i in range(1, 39)} | {"97", "99"})


def check_character(first14: str) -> str:
    """The mod-36 check character of the first 14 characters: weights 1 and 2
    alternating from the left; each product contributes its quotient and remainder
    by 36; the check is (36 - sum mod 36) mod 36."""
    total = 0
    for i, ch in enumerate(first14):
        value = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += value // 36 + value % 36
    return _CHARS[(36 - total % 36) % 36]


@dataclass(frozen=True)
class GstinFacts:
    gstin: str
    valid: bool
    state_code: str | None
    pan: str | None
    reason: str | None   # why it is not valid; None when it is


def read(raw: str) -> GstinFacts:
    gstin = raw.strip().upper()
    if not SHAPE.match(gstin):
        return GstinFacts(gstin, False, None, None, "not the shape of a GSTIN")
    state, pan = gstin[:2], gstin[2:12]
    if state not in STATE_CODES:
        return GstinFacts(gstin, False, None, pan, "not a GST state code")
    if check_character(gstin[:14]) != gstin[14]:
        return GstinFacts(gstin, False, state, pan, "the check character does not match")
    return GstinFacts(gstin, True, state, pan, None)
