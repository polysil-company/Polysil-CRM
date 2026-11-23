"""The clock, in the timezone the business runs in.

One place, because two engines need it and neither may import the other, and
because the mistake this prevents is easy and silent.

**Never `current_date` in SQL, and never `date.today()`.** The server runs UTC.
Between 00:00 and 05:30 India time a UTC box is still on yesterday, so a rule
that refuses a date "after today" refuses the date the user is looking at, every
morning, for five and a half hours. FS-008 hit this while writing the rule and
the comment has lived in the subsidy service since; it is here now so the pricing
engine cannot rediscover it.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def today_ist() -> dt.date:
    """Today, where the client is."""
    return dt.datetime.now(tz=IST).date()


def now_ist() -> dt.datetime:
    return dt.datetime.now(tz=IST)
