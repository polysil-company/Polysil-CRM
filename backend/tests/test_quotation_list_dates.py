"""The quotation list's date filter (no database)."""

from __future__ import annotations

import datetime as dt

from api.services.quotations import _parse_date


def test_the_list_date_filter_is_the_ist_day() -> None:
    """PR #10 review: a UTC midnight left out a quotation made at 03:00 IST and let
    in one made at 23:30 IST the evening before."""
    start = _parse_date("2027-01-15", "from")
    assert start == dt.datetime(2027, 1, 14, 18, 30, tzinfo=dt.UTC)
    made_at_3am_ist = dt.datetime(2027, 1, 14, 21, 30, tzinfo=dt.UTC)
    made_last_evening_ist = dt.datetime(2027, 1, 14, 18, 0, tzinfo=dt.UTC)
    assert made_at_3am_ist >= start and made_last_evening_ist < start
