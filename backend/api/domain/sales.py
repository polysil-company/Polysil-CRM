"""When an order counts as a sale (FS-026).

One company setting picks the date. Each date is null exactly when the order must
not count in that mode: `approved_at` is cleared when an approved order is amended,
`fully_dispatched_at` is null outside dispatched and closed short, and
`order_paid_at()` is null until what is owed is covered. So a report needs only the
common exclusions and a window on the mode's date.
"""

from __future__ import annotations

from typing import Final, Literal

Mode = Literal["submission", "approval", "dispatch", "payment"]
MODES: Final[tuple[Mode, ...]] = ("submission", "approval", "dispatch", "payment")
DEFAULT: Final[Mode] = "approval"

# the order column, or the SQL function, that dates a sale in each mode
DATE_OF: Final[dict[Mode, str]] = {
    "submission": "submitted_at",
    "approval": "approved_at",
    "dispatch": "fully_dispatched_at",
    "payment": "order_paid_at",
}


def mode_of(value: object) -> Mode:
    """The setting's value as a mode; an unknown one is refused, never guessed."""
    for mode in MODES:
        if value == mode:
            return mode
    raise ValueError(f"unknown sale_counted_at mode: {value!r}")
