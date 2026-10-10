"""FS-021 domain: distance, the route filter, stops, point checks, working hours."""

from __future__ import annotations

import datetime as dt
import math
import random
from itertools import pairwise

import pytest

from api.domain import tracking as t

T0 = dt.datetime(2026, 10, 5, 9, 0, tzinfo=t.IST)          # a Monday
HOURS = t.Hours(dt.time(9, 0), dt.time(19, 0), frozenset({1, 2, 3, 4, 5, 6}))
RETENTION = dt.timedelta(days=90)
AHMEDABAD = (23.0225, 72.5714)


def _walk(seed: int, n: int, step_s: int = 60) -> list[t.Fix]:
    """A plausible track: a random walk at walking-to-driving speeds."""
    rng = random.Random(seed)
    lat, lng = AHMEDABAD
    out = []
    for i in range(n):
        out.append(t.Fix(T0 + dt.timedelta(seconds=i * step_s), lat, lng, rng.uniform(3, 60)))
        bearing = rng.uniform(0, 2 * math.pi)
        metres = rng.uniform(0, 600)     # at most 36 km/h over a minute
        lat += metres * math.cos(bearing) / 111_320
        lng += metres * math.sin(bearing) / (111_320 * math.cos(math.radians(lat)))
    return out


# ── distance ────────────────────────────────────────────────────────────────

def test_haversine_known_distance() -> None:
    # Ahmedabad to Vadodara, about 100 km as the crow flies
    d = t.haversine_m(23.0225, 72.5714, 22.3072, 73.1812)
    assert 98_000 < d < 102_000


@pytest.mark.parametrize("seed", range(500))
def test_haversine_is_a_metric_on_random_triples(seed: int) -> None:
    rng = random.Random(seed)
    pts = [(rng.uniform(-80, 80), rng.uniform(-179, 179)) for _ in range(3)]
    a, b, c = pts
    ab, ba = t.haversine_m(*a, *b), t.haversine_m(*b, *a)
    assert ab >= 0 and math.isclose(ab, ba, rel_tol=1e-9, abs_tol=1e-6)
    assert t.haversine_m(*a, *a) == 0
    assert t.haversine_m(*a, *c) <= ab + t.haversine_m(*b, *c) + 1e-6


@pytest.mark.parametrize("seed", range(300))
def test_distance_never_shrinks_when_a_fix_is_added(seed: int) -> None:
    fixes = _walk(seed, 40)
    assert t.distance_m(fixes[:-1]) <= t.distance_m(fixes) + 1e-9


def test_distance_of_zero_or_one_fix_is_zero() -> None:
    assert t.distance_m([]) == 0
    assert t.distance_m([t.Fix(T0, *AHMEDABAD)]) == 0


# ── the route filter ────────────────────────────────────────────────────────

def test_inaccurate_fixes_and_jumps_are_dropped() -> None:
    lat, lng = AHMEDABAD
    fixes = [t.Fix(T0, lat, lng, 10),
             t.Fix(T0 + dt.timedelta(minutes=1), lat + 0.001, lng, 500),     # inaccurate
             t.Fix(T0 + dt.timedelta(minutes=2), lat + 1.0, lng, 10),        # 111 km in a minute
             t.Fix(T0 + dt.timedelta(minutes=3), lat + 0.002, lng, 10)]
    kept, dropped = t.route_fixes(fixes)
    assert [f.at for f in kept] == [fixes[0].at, fixes[3].at] and dropped == 2


def test_two_fixes_at_one_instant_keep_the_first() -> None:
    a = t.Fix(T0, *AHMEDABAD, 5)
    b = t.Fix(T0, AHMEDABAD[0] + 0.0001, AHMEDABAD[1], 5)
    kept, dropped = t.route_fixes([a, b])
    assert kept == [a] and dropped == 1


@pytest.mark.parametrize("seed", range(300))
def test_route_filter_keeps_order_and_counts_every_fix(seed: int) -> None:
    fixes = _walk(seed, 60)
    random.Random(seed).shuffle(fixes)
    kept, dropped = t.route_fixes(fixes)
    assert len(kept) + dropped == len(fixes)
    assert all(a.at < b.at for a, b in pairwise(kept))
    assert all((f.accuracy_m or 0) <= t.ROUTE_ACCURACY_M for f in kept)


# ── stops ───────────────────────────────────────────────────────────────────

def _dwell(start: dt.datetime, minutes: int, lat: float, lng: float) -> list[t.Fix]:
    return [t.Fix(start + dt.timedelta(minutes=m), lat + 0.0001 * (m % 3), lng)
            for m in range(minutes + 1)]


def test_a_dwell_of_ten_minutes_is_a_stop_and_nine_is_not() -> None:
    assert len(t.stops(_dwell(T0, 10, *AHMEDABAD))) == 1
    assert t.stops(_dwell(T0, 9, *AHMEDABAD)) == []


def test_two_dwells_with_a_drive_between_are_two_stops() -> None:
    first = _dwell(T0, 20, *AHMEDABAD)
    drive = [t.Fix(T0 + dt.timedelta(minutes=21 + i), AHMEDABAD[0] + 0.01 * (i + 1), AHMEDABAD[1])
             for i in range(5)]
    second = _dwell(T0 + dt.timedelta(minutes=27), 15, AHMEDABAD[0] + 0.06, AHMEDABAD[1])
    found = t.stops(first + drive + second)
    assert [s.minutes for s in found] == [20, 15]
    assert t.haversine_m(found[0].lat, found[0].lng, *AHMEDABAD) < 50


@pytest.mark.parametrize("seed", range(300))
def test_stops_never_overlap_and_each_lasts_ten_minutes(seed: int) -> None:
    fixes, _ = t.route_fixes(_walk(seed, 120, step_s=30))
    found = t.stops(fixes)
    assert all(s.end - s.start >= t.STOP_MIN for s in found)
    assert all(a.end < b.start for a, b in pairwise(found))


# ── a point's checks ────────────────────────────────────────────────────────

def _problem(at: dt.datetime, *, lat: float = AHMEDABAD[0], lng: float = AHMEDABAD[1],
             duty: list[tuple[dt.datetime, dt.datetime | None]] | None = None,
             now: dt.datetime = T0 + dt.timedelta(hours=3)) -> str | None:
    return t.point_problem(recorded_at=at, lat=lat, lng=lng, now=now, retention=RETENTION,
                           duty=duty if duty is not None else [(T0, None)])


@pytest.mark.parametrize(("lat", "lng"), [(0.0, 0.0), (91.0, 72.0), (23.0, 181.0), (math.nan, 72.0),
                                          (23.0, math.inf), (-90.1, 0.5)])
def test_bad_coordinates(lat: float, lng: float) -> None:
    assert _problem(T0 + dt.timedelta(minutes=5), lat=lat, lng=lng) == "bad_coordinates"


def test_the_clock_checks() -> None:
    now = T0 + dt.timedelta(hours=3)
    assert _problem(now + dt.timedelta(minutes=5)) is None, "5 minutes of skew, open duty too"
    assert _problem(now + dt.timedelta(minutes=6)) == "future"
    old = now - RETENTION - dt.timedelta(seconds=1)
    assert _problem(old, duty=[(old - dt.timedelta(hours=1), None)]) == "too_old"


def test_off_duty_with_two_minutes_grace() -> None:
    end = T0 + dt.timedelta(hours=2)
    duty: list[tuple[dt.datetime, dt.datetime | None]] = [(T0, end)]
    assert _problem(T0 - dt.timedelta(minutes=2), duty=duty) is None
    assert _problem(T0 - dt.timedelta(minutes=3), duty=duty) == "off_duty"
    assert _problem(end + dt.timedelta(minutes=2), duty=duty) is None
    assert _problem(end + dt.timedelta(minutes=3), duty=duty) == "off_duty"
    assert _problem(T0, duty=[]) == "off_duty"


def test_a_naive_time_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        _problem(dt.datetime(2026, 10, 5, 9, 0))


@pytest.mark.parametrize("seed", range(1000))
def test_point_checks_agree_with_a_direct_reading(seed: int) -> None:
    rng = random.Random(seed)
    now = T0 + dt.timedelta(hours=10)
    duty: list[tuple[dt.datetime, dt.datetime | None]] = []
    s = T0
    for _ in range(rng.randint(0, 3)):
        s += dt.timedelta(minutes=rng.randint(0, 120))
        e = s + dt.timedelta(minutes=rng.randint(1, 180))
        duty.append((s, e if rng.random() < 0.8 else None))
        s = e
    at = T0 + dt.timedelta(seconds=rng.randint(-3600, 12 * 3600))
    got = _problem(at, duty=duty, now=now)
    inside = any(a - t.DUTY_GRACE <= at <= (b + t.DUTY_GRACE if b else now + t.FUTURE_SKEW)
                 for a, b in duty)
    if at > now + t.FUTURE_SKEW:
        assert got == "future"
    else:
        assert got == (None if inside else "off_duty")


# ── working hours and the automatic end ─────────────────────────────────────

def test_outside_hours() -> None:
    assert not t.outside_hours(T0, HOURS)
    assert t.outside_hours(T0 - dt.timedelta(minutes=1), HOURS)
    assert t.outside_hours(T0.replace(hour=19), HOURS), "the end is exclusive"
    assert t.outside_hours(T0 + dt.timedelta(days=6), HOURS), "Sunday"
    utc = T0.astimezone(dt.UTC)
    assert not t.outside_hours(utc, HOURS), "judged in IST whatever the offset"


def test_the_hours_end_is_the_first_one_after_the_start() -> None:
    assert t.hours_end_after(T0, HOURS) == T0.replace(hour=19)
    tomorrow = T0.replace(hour=19) + dt.timedelta(days=1)
    assert t.hours_end_after(T0.replace(hour=20), HOURS) == tomorrow
    saturday_night = T0.replace(hour=20) + dt.timedelta(days=5)
    monday = T0.replace(hour=19) + dt.timedelta(days=7)
    assert t.hours_end_after(saturday_night, HOURS) == monday, "Sunday is skipped"
    with pytest.raises(ValueError):
        t.hours_end_after(T0, t.Hours(dt.time(9), dt.time(19), frozenset()))


def test_evening_work_that_keeps_sending_is_not_cut_off() -> None:
    """Review B-8: the old rule ended every duty at 19:30."""
    at_2100 = T0.replace(hour=21)
    assert t.auto_end(T0, at_2100 - dt.timedelta(minutes=5), at_2100, HOURS) is None
    quiet_since = T0.replace(hour=20, minute=10)
    assert t.auto_end(T0, quiet_since, at_2100, HOURS) == quiet_since, "ends at the last point"


def test_idle_before_the_hours_end_is_left_open() -> None:
    lunch = T0.replace(hour=13)
    assert t.auto_end(T0, T0.replace(hour=12), lunch, HOURS) is None


def test_no_points_at_all_ends_at_the_start() -> None:
    now = T0.replace(hour=19, minute=31)
    assert t.auto_end(T0, None, now, HOURS) == T0


def test_the_fourteen_hour_cap() -> None:
    now = T0 + dt.timedelta(hours=14)
    last = now - dt.timedelta(minutes=1)
    assert t.auto_end(T0, last, now, HOURS) == last
    later = now + dt.timedelta(hours=2)
    assert t.auto_end(T0, later, later, HOURS) == now, "never past the cap"


def test_a_night_start_waits_for_the_next_days_end() -> None:
    night = T0.replace(hour=22)
    assert t.auto_end(night, None, night + dt.timedelta(hours=2), HOURS) is None


@pytest.mark.parametrize("seed", range(500))
def test_auto_end_never_precedes_the_start_or_passes_the_cap(seed: int) -> None:
    rng = random.Random(seed)
    start = T0 + dt.timedelta(minutes=rng.randint(-24 * 60, 24 * 60))
    last = None if rng.random() < 0.2 else start + dt.timedelta(minutes=rng.randint(-10, 16 * 60))
    now = start + dt.timedelta(minutes=rng.randint(0, 20 * 60))
    if last is not None and last > now:
        last = now
    end = t.auto_end(start, last, now, HOURS)
    if end is not None:
        assert start <= end <= start + t.AUTO_END_MAX
        assert end <= now
    if now >= start + t.AUTO_END_MAX:
        assert end is not None, "the cap always ends it"


def test_stale_only_on_duty() -> None:
    now = T0 + dt.timedelta(hours=1)
    assert t.stale(now - dt.timedelta(minutes=15), True, now)
    assert not t.stale(now - dt.timedelta(minutes=14), True, now)
    assert not t.stale(None, False, now)
    assert t.stale(None, True, now)


def test_day_bounds_are_ist() -> None:
    start, end = t.day_bounds(dt.date(2026, 10, 5))
    assert start.astimezone(dt.UTC) == dt.datetime(2026, 10, 4, 18, 30, tzinfo=dt.UTC)
    assert end - start == dt.timedelta(days=1)


@pytest.mark.parametrize(("n", "limit"), [(0, 2000), (5, 2000), (2000, 2000), (2001, 2000),
                                          (10_000, 2000), (3, 2), (99_999, 500)])
def test_thinning_keeps_ends_order_and_the_limit(n: int, limit: int) -> None:
    fixes = [t.Fix(T0 + dt.timedelta(seconds=i), *AHMEDABAD) for i in range(n)]
    out = t.thin(fixes, limit)
    assert len(out) == min(n, limit)
    if n:
        assert out[0] is fixes[0] and out[-1] is fixes[-1]
    assert all(a.at < b.at for a, b in pairwise(out))


def test_a_phone_stamped_time_is_put_on_the_server_clock() -> None:
    """Code review F-1: duty and visit times are corrected as points are."""
    now = T0 + dt.timedelta(hours=1)
    fast = dt.timedelta(minutes=10)
    assert t.corrected_at(now + fast, now + fast, now) == now, "a fast phone with sent_at"
    assert t.corrected_at(now - fast, now - fast, now) == now, "a slow phone with sent_at"
    assert t.corrected_at(now + fast, None, now) == now, "never in the future"
    early = now - dt.timedelta(hours=3)
    assert t.corrected_at(early, None, now) == early, "an offline time without sent_at stands"
    assert t.corrected_at(early, now - dt.timedelta(minutes=4), now) == early, "small skew ignored"
