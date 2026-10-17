"""One cell as text, and text as the value a field wants (FS-062 EC-9, EC-20).

Excel stores numbers as binary floats. A rate shown as 1234.50 can be held as
1234.4999999999998, and `str(1e16)` is `'1e+16'`. So a float goes through
`repr()` (the shortest text that round-trips), into `Decimal`, quantized to nine
places and printed without an exponent. No arithmetic is ever done on the float.

A cell formatted as a percentage holds a fraction: 10 % is stored as 0.1. It is
read as shown.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation

MAX_CELL_CHARS = 1000
_NINE = Decimal("1e-9")
# zero-width space, non-joiner, joiner, word joiner, byte-order mark
_ZERO_WIDTH = dict.fromkeys((0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF))
# no-break, figure and narrow no-break spaces, tab, CR, LF
_SPACES = re.compile("[" + "".join(map(chr, (0xA0, 0x2007, 0x202F, 9, 13, 10))) + "]+")


def clean_text(value: str) -> str:
    """Outer spaces trimmed, zero-width characters dropped, odd spaces made plain."""
    return _SPACES.sub(" ", value.translate(_ZERO_WIDTH)).strip()


def _float_text(value: float, *, percent: bool) -> str:
    d = Decimal(repr(value))
    if percent:
        d *= 100
    d = d.quantize(_NINE).normalize() if abs(d) < Decimal("1e15") else d
    out = format(d, "f")
    return "0" if out in ("-0", "") else out


def cell_text(value: object, number_format: str | None = None) -> str:
    """Any value openpyxl hands back, as the text the matching screen shows."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        # GAP-476: a code typed 0101 in a number cell arrives as 101; nothing recovers it
        if number_format and "%" in number_format:
            return str(value * 100)
        return str(value)
    if isinstance(value, float):
        return _float_text(value, percent=bool(number_format and "%" in number_format))
    if isinstance(value, dt.datetime):
        if value.time() == dt.time(0, 0):
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dt.time):
        return value.isoformat(timespec="minutes")
    return clean_text(str(value))[:MAX_CELL_CHARS]


class CellError(ValueError):
    """The text is not the value the field wants. The message is the API's."""


def to_decimal(text: str, *, places: int, minimum: Decimal | None = None,
               maximum: Decimal | None = None, exclusive_min: bool = False) -> Decimal:
    """Rupees and quantities. `,` `₹` `Rs` and spaces go; more decimals than
    `places` is refused, never rounded: it is the client's number."""
    t = text.replace(",", "").replace("₹", "").replace(" ", "")
    if t.lower().startswith("rs."):
        t = t[3:]
    elif t.lower().startswith("rs"):
        t = t[2:]
    if t.endswith("%"):
        t = t[:-1]
    try:
        d = Decimal(t)
    except InvalidOperation as exc:
        raise CellError(f"{text!r} is not a number") from exc
    if not d.is_finite():
        raise CellError(f"{text!r} is not a number")
    exponent = d.normalize().as_tuple().exponent
    if isinstance(exponent, int) and -exponent > places:
        raise CellError(f"at most {places} decimal places" if places else "a whole number")
    if minimum is not None and (d <= minimum if exclusive_min else d < minimum):
        raise CellError(f"must be {'more than' if exclusive_min else 'at least'} {minimum}")
    if maximum is not None and d > maximum:
        raise CellError(f"must be at most {maximum}")
    return d.quantize(Decimal(1).scaleb(-places)) if places else d.to_integral_value()


_YES = {"yes", "y", "true", "1", "registered", "haan", "ha"}
_NO = {"no", "n", "false", "0", "unregistered", "not registered", "nahi"}


def to_bool(text: str) -> bool:
    t = text.strip().lower()
    if t in _YES:
        return True
    if t in _NO:
        return False
    raise CellError(f"{text!r} is not yes or no")


def key(text: str) -> str:
    """Comparison form for names: case, spaces, dots and hyphens ignored."""
    return re.sub(r"[\s.\-_/]+", "", text.casefold())


# Excel keeps a carriage return, a newline or a tab inside a cell as these literal
# escapes; openpyxl hands them back as text. The catalogue loader strips them too.
_ESCAPES = re.compile(r"_x000[DA9]_", re.IGNORECASE)
_RUNS = re.compile(r"\s+")


def name_key(text: str) -> str:
    """Comparison form for product names and codes (FS-067 rule 5): Excel escapes
    gone, every run of whitespace one space, trimmed, case ignored. Unlike `key`,
    dots and hyphens stay: `PE-100` and `PE100` are different products."""
    return _RUNS.sub(" ", _ESCAPES.sub("", text)).strip().casefold()


# a Python repr: '...' or "...", with backslash escapes inside
_QUOTED = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_DIGITS = re.compile(r"\d{6,}")


def redact(message: str) -> str:
    """An error message with the cell it quotes taken out (FS-067 rule 9): kept after
    a discard, it must not hold a mobile or a name from a misfiled sheet."""
    return _DIGITS.sub("…", _QUOTED.sub("'…'", message))
