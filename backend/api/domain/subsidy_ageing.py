"""The six ageing figures of the client's Application-Process-Flow, rows 107 to 112
(FS-009a). Pure: the service hands in the dates the stage entries hold."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Final

# figure -> (start field, end field). `@full_fp` is the application's own column.
FIGURES: Final[dict[str, tuple[str, str]]] = {
    "today_to_supply": ("supply", "@full_fp"),
    "inward_to_submission": ("app_inward", "submission"),
    "wo_to_tpa_received": ("wo_received", "tpa_received"),
    "tpa_cleared_to_inspection_sent": ("tpa_cleared", "inspection_sent"),
    "inspection_sent_to_tr": ("inspection_sent", "tr_date"),
    "fp_submitted_to_full_fp": ("fp_submitted", "@full_fp"),
}

FIELDS: Final = tuple(sorted({k for pair in FIGURES.values() for k in pair
                              if not k.startswith("@")}))


@dataclass(frozen=True)
class Figure:
    days: int | None
    running: bool
    start: dt.date | None
    end: dt.date | None


def ageing(dates: dict[str, dt.date | None], full_fp: dt.date | None, stopped_on: dt.date | None,
           today: dt.date) -> dict[str, Figure]:
    """Each figure: null days when the start is not recorded; an open interval counts
    to `stopped_on` (a cancelled application) or today and says it is running
    (GAP-332)."""
    out: dict[str, Figure] = {}
    for name, (start_key, end_key) in FIGURES.items():
        start = dates.get(start_key)
        end = full_fp if end_key == "@full_fp" else dates.get(end_key)
        if start is None:
            out[name] = Figure(None, False, None, end)
        elif end is not None:
            out[name] = Figure((end - start).days, False, start, end)
        else:
            until = stopped_on or today
            out[name] = Figure((until - start).days, stopped_on is None, start, None)
    return out
