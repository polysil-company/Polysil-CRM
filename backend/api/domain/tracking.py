"""Field tracking (FS-021): the rules that need no database.

Coordinates are WGS84 degrees as floats. They are positions, not money, and the
database stores them as numeric(9,6). Days are Indian calendar days. The stand-in
figures are the policy's defaults (GAP-191, GAP-194); the live values come from
`tracking_policy`, so each is a parameter here, not a constant read inside.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

IST: Final = dt.timezone(dt.timedelta(hours=5, minutes=30))

EARTH_RADIUS_M: Final = 6_371_008.8
FUTURE_SKEW: Final = dt.timedelta(minutes=5)
DUTY_GRACE: Final = dt.timedelta(minutes=2)
ROUTE_ACCURACY_M: Final = 100.0          # rule 13: worse fixes are left out of the route
MAX_SPEED_MPS: Final = 150 / 3.6         # rule 13: a faster jump is GPS noise
STOP_RADIUS_M: Final = 150.0
STOP_MIN: Final = dt.timedelta(minutes=10)
IDLE_AFTER_HOURS: Final = dt.timedelta(minutes=30)       # rule 4: idle this long after hours
AUTO_END_MAX: Final = dt.timedelta(hours=14)             # rule 4
VISIT_AUTO_CLOSE: Final = dt.timedelta(hours=12)         # rule 7
PHOTO_AFTER_CHECKOUT: Final = dt.timedelta(minutes=30)
STALE_AFTER: Final = dt.timedelta(minutes=15)

REJECT_REASONS: Final = ("off_duty", "future", "too_old", "bad_coordinates", "unknown_duty")


@dataclass(frozen=True)
class Fix:
    at: dt.datetime
    lat: float
    lng: float
    accuracy_m: float | None = None


@dataclass(frozen=True)
class Stop:
    start: dt.datetime
    end: dt.datetime
    lat: float
    lng: float

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class Hours:
    """The working week: days are ISO weekdays, 1 Monday to 7 Sunday, in IST."""
    start: dt.time
    end: dt.time
    days: frozenset[int]


def day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """The IST day as a half-open instant range [start, end)."""
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=IST)
    return start, start + dt.timedelta(days=1)


def coordinates_ok(lat: float, lng: float) -> bool:
    """In range and not the (0, 0) a phone reports before its first fix."""
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return False
    return not (lat == 0.0 and lng == 0.0)


def haversine_m(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def point_problem(*, recorded_at: dt.datetime, lat: float, lng: float, now: dt.datetime,
                  retention: dt.timedelta,
                  duty: Sequence[tuple[dt.datetime, dt.datetime | None]]) -> str | None:
    """Why a point is refused, or None. `duty` is the caller's sessions that could
    hold it. An open one runs to `now` plus the clock skew allowed, so a phone a
    few minutes fast is not off duty. The order is the order a person would fix
    things in: a broken fix first, then the clock, then the duty."""
    if recorded_at.tzinfo is None:
        raise ValueError("recorded_at must carry an offset")
    if not coordinates_ok(lat, lng):
        return "bad_coordinates"
    if recorded_at > now + FUTURE_SKEW:
        return "future"
    if recorded_at < now - retention:
        return "too_old"
    for started, ended in duty:
        end = ended + DUTY_GRACE if ended is not None else now + FUTURE_SKEW
        if started - DUTY_GRACE <= recorded_at <= end:
            return None
    return "off_duty"


def route_fixes(fixes: Sequence[Fix], *, max_accuracy_m: float = ROUTE_ACCURACY_M,
                max_speed_mps: float = MAX_SPEED_MPS) -> tuple[list[Fix], int]:
    """The fixes a route draws, oldest first, and how many were left out: worse
    than the accuracy bound, or a jump faster than the speed bound from the last
    kept fix. Two fixes at one instant keep the first."""
    kept: list[Fix] = []
    dropped = 0
    for f in sorted(fixes, key=lambda x: x.at):
        if f.accuracy_m is not None and f.accuracy_m > max_accuracy_m:
            dropped += 1
            continue
        if kept:
            last = kept[-1]
            secs = (f.at - last.at).total_seconds()
            if secs <= 0:
                dropped += 1
                continue
            if haversine_m(last.lat, last.lng, f.lat, f.lng) / secs > max_speed_mps:
                dropped += 1
                continue
        kept.append(f)
    return kept, dropped


def distance_m(fixes: Sequence[Fix]) -> float:
    """Path length over fixes already filtered and in order."""
    return sum(haversine_m(a.lat, a.lng, b.lat, b.lng) for a, b in pairwise(fixes))


def stops(fixes: Sequence[Fix], *, radius_m: float = STOP_RADIUS_M,
          min_duration: dt.timedelta = STOP_MIN) -> list[Stop]:
    """Runs of fixes that stay within `radius_m` of the run's first fix for at
    least `min_duration`. The stop's position is the run's mean. Fixes in order."""
    out: list[Stop] = []
    i, n = 0, len(fixes)
    while i < n:
        anchor = fixes[i]
        j = i
        while j + 1 < n and haversine_m(anchor.lat, anchor.lng,
                                        fixes[j + 1].lat, fixes[j + 1].lng) <= radius_m:
            j += 1
        if fixes[j].at - anchor.at >= min_duration:
            run = fixes[i:j + 1]
            out.append(Stop(anchor.at, fixes[j].at, sum(f.lat for f in run) / len(run),
                            sum(f.lng for f in run) / len(run)))
            i = j + 1
        else:
            i += 1
    return out


def outside_hours(at: dt.datetime, hours: Hours) -> bool:
    local = at.astimezone(IST)
    if local.isoweekday() not in hours.days:
        return True
    return not (hours.start <= local.time() < hours.end)


def hours_end_after(at: dt.datetime, hours: Hours) -> dt.datetime:
    """The first end of a working day strictly after `at`, in IST. A start at 20:00
    looks to the next working day's end, not to the one already past."""
    day = at.astimezone(IST).date()
    for _ in range(8):
        end = dt.datetime.combine(day, hours.end, tzinfo=IST)
        if day.isoweekday() in hours.days and end > at:
            return end
        day += dt.timedelta(days=1)
    raise ValueError("a working week needs at least one day")


def auto_end(started_at: dt.datetime, last_point_at: dt.datetime | None, now: dt.datetime,
             hours: Hours) -> dt.datetime | None:
    """The end time the worker gives an open duty, or None to leave it open (rule 4,
    review B-8). Ended when idle for 30 minutes after the first working-day end
    that follows the start, or 14 hours after the start. The end is the last
    point's time, so evening work that keeps sending is never cut off."""
    last = max(started_at, last_point_at) if last_point_at is not None else started_at
    cap = started_at + AUTO_END_MAX
    if now >= cap:
        return min(last, cap)
    if now >= hours_end_after(started_at, hours) and now - last >= IDLE_AFTER_HOURS:
        return last
    return None


def corrected_at(at: dt.datetime, sent_at: dt.datetime | None, now: dt.datetime) -> dt.datetime:
    """A phone-stamped time on the server's clock (code review F-1). With `sent_at`,
    a skew over 5 minutes shifts `at` by it, as a batch shifts its points. Never
    later than now: a fast phone without `sent_at` starts duty now, not in the future."""
    if sent_at is not None and abs(now - sent_at) > FUTURE_SKEW:
        at = at + (now - sent_at)
    return min(at, now)


def stale(last_seen_at: dt.datetime | None, on_duty: bool, now: dt.datetime) -> bool:
    """On duty and silent for 15 minutes. Off duty is never stale."""
    return on_duty and (last_seen_at is None or now - last_seen_at >= STALE_AFTER)


ROUTE_DRAW_MAX: Final = 2000


def thin(fixes: Sequence[Fix], limit: int = ROUTE_DRAW_MAX) -> list[Fix]:
    """At most `limit` fixes for drawing, evenly spaced by index, keeping the first
    and the last. Distance and stops are computed before thinning (review EC-10)."""
    n = len(fixes)
    if n <= limit:
        return list(fixes)
    if limit < 2:
        raise ValueError("thin needs room for the first and last fix")
    step = (n - 1) / (limit - 1)
    return [fixes[round(i * step)] for i in range(limit)]
