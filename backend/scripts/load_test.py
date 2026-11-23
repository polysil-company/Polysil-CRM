"""A load run against staging (test build-out 7). Never production.

    python scripts/deploy_staging.py --target staging load [--users 300] [--seconds 120]

The deploy tool opens the SSH tunnel and passes the staging check account in the
environment, as `verify` does, so no password is typed or printed here. Every
virtual user signs in with that one account's token (one sign-in, so the login
lockout is not what is measured), then loops over the screens people open most,
weighted as a working day would weight them, with a short think time.

It reports, per route and overall: requests, errors (5xx and timeouts), and the
50th, 95th and 99th percentile in milliseconds. It fails (exit 1) when more than
1 % of requests error or the overall p95 passes the budget. The budget is ours
(ADR-023 sizing: about 200 at once): 1,500 ms at p95 for reads.
"""

# ruff: noqa: E501  (report lines)

from __future__ import annotations

import argparse
import asyncio
import os
import random
import statistics
import sys
import time
from collections import defaultdict

import httpx

# path, query, weight: what a field officer and a manager open in a day
MIX: list[tuple[str, dict[str, str], int]] = [
    ("/api/v1/dashboard/overview", {}, 6),
    ("/api/v1/leads", {}, 8),
    ("/api/v1/leads", {"q": "pa"}, 2),
    ("/api/v1/notifications", {}, 5),
    ("/api/v1/auth/me", {}, 2),
    ("/api/v1/planner", {}, 4),
    ("/api/v1/tasks", {}, 3),
    ("/api/v1/quotations", {}, 4),
    ("/api/v1/orders", {}, 3),
    ("/api/v1/customers", {}, 2),
    ("/api/v1/complaints", {}, 2),
    ("/api/v1/products", {}, 2),
    ("/api/v1/partners", {}, 1),
    ("/api/v1/lookups/lead-sources", {}, 1),
    ("/api/v1/reports/lead-conversion", {}, 1),
    ("/api/v1/reports/follow-ups", {}, 1),
]
P95_BUDGET_MS = 1500.0
ERROR_BUDGET = 0.01
TIMEOUT = 30.0


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))]


async def _user(client: httpx.AsyncClient, token: str, stop: float, results: dict[str, list[float]],
                errors: dict[str, int], statuses: dict[int, int], think: float) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    paths = [m[0] + ("?" + "&".join(f"{k}={v}" for k, v in m[1].items()) if m[1] else "") for m in MIX]
    weights = [m[2] for m in MIX]
    await asyncio.sleep(random.uniform(0, think * 2))   # stagger the start
    while time.monotonic() < stop:
        path = random.choices(paths, weights)[0]
        started = time.monotonic()
        try:
            r = await client.get(path, headers=headers)
            ms = (time.monotonic() - started) * 1000
            statuses[r.status_code] += 1
            if r.status_code >= 500:
                errors[path] += 1
            else:
                results[path].append(ms)
        except (httpx.TimeoutException, httpx.TransportError):
            errors[path] += 1
            statuses[0] += 1
        await asyncio.sleep(random.uniform(think / 2, think * 1.5))


async def run(base: str, email: str, password: str, users: int, seconds: int, think: float) -> int:
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(base_url=base, timeout=TIMEOUT, limits=limits) as client:
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            print(f"  sign-in failed: {login.status_code}")
            return 1
        token = login.json()["data"]["access_token"]
        results: dict[str, list[float]] = defaultdict(list)
        errors: dict[str, int] = defaultdict(int)
        statuses: dict[int, int] = defaultdict(int)
        stop = time.monotonic() + seconds
        print(f"  {users} users for {seconds} s, think time about {think} s")
        await asyncio.gather(*(_user(client, token, stop, results, errors, statuses, think)
                               for _ in range(users)))
    every = [ms for v in results.values() for ms in v]
    total = len(every) + sum(errors.values())
    failed = sum(errors.values())
    print(f"\n  {total} requests, {total / seconds:.1f} a second, {failed} errors "
          f"({100 * failed / max(total, 1):.2f} %)")
    print(f"  status codes: {dict(sorted(statuses.items()))}  (0 is a timeout or a dropped connection)")
    print(f"  overall p50 {_pct(every, 50):.0f} ms, p95 {_pct(every, 95):.0f} ms, p99 {_pct(every, 99):.0f} ms\n")
    print(f"  {'route':52} {'n':>6} {'err':>5} {'p50':>7} {'p95':>7} {'p99':>7}")
    for path in sorted(results, key=lambda p: -_pct(results[p], 95)):
        v = results[path]
        print(f"  {path[:52]:52} {len(v):>6} {errors.get(path, 0):>5} {_pct(v, 50):>7.0f} "
              f"{_pct(v, 95):>7.0f} {_pct(v, 99):>7.0f}")
    if every:
        print(f"\n  mean {statistics.mean(every):.0f} ms")
    ok = failed / max(total, 1) <= ERROR_BUDGET and _pct(every, 95) <= P95_BUDGET_MS
    print(f"\n  {'PASS' if ok else 'FAIL'}: budget is at most {ERROR_BUDGET:.0%} errors and p95 "
          f"at most {P95_BUDGET_MS:.0f} ms")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--think", type=float, default=2.0, help="seconds between a user's requests")
    args = parser.parse_args(argv)
    if os.environ.get("LIVE_TARGET") != "staging":
        print("  load runs against staging only")
        return 2
    return asyncio.run(run(os.environ["LIVE_BASE_URL"], os.environ["LIVE_CHECK_EMAIL"],
                           os.environ["LIVE_CHECK_PASSWORD"], args.users, args.seconds, args.think))


if __name__ == "__main__":
    sys.exit(main())
