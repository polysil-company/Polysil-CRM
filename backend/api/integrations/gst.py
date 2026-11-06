"""GSTIN details from a GST data provider (FS-053, closes GAP-292's fetch half).

The government portal has no free API. gstinapi.in gives 100 free lookups a month
(no card): GET https://gstinapi.in/v1/gstin/{gstin} with an `x-api-key` header,
answering legal_name, trade_name, status, address and state_code. With no key the
lookup is `unavailable` and the form asks for the names, as before.

A found GSTIN is cached in Redis for 30 days, so the free quota is spent once per
GSTIN, not once per click. A provider error is `unavailable`, never a 500: the
applicant can always type the names.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from typing import Any

import httpx
import structlog

from api.config import Settings
from api.integrations import cache

log = structlog.get_logger()

CACHE_TTL = timedelta(days=30)
NOT_FOUND_TTL = timedelta(days=1)
_BASE = "https://gstinapi.in/v1/gstin/"


async def fetch(gstin: str, settings: Settings) -> tuple[str, dict[str, Any]]:
    """(lookup, details): lookup is found, not_found or unavailable."""
    key = settings.gstinapi_key.get_secret_value() if settings.gstinapi_key else ""
    if settings.gst_provider != "gstinapi" or not key:
        return "unavailable", {}
    cache_key = f"gst:{gstin}"
    try:
        cached = await cache.read_bundle(cache_key)
    except Exception:
        cached = None
    if cached is not None:
        return ("not_found", {}) if cached.get("not_found") else ("found", cached)
    try:
        async with httpx.AsyncClient(timeout=settings.gst_lookup_timeout) as client:
            r = await client.get(_BASE + gstin, headers={"x-api-key": key})
    except Exception as exc:
        log.warning("gst.lookup_failed", kind=type(exc).__name__)
        return "unavailable", {}
    if r.status_code == 404:
        with contextlib.suppress(Exception):   # code review F-8: the quota is 100 a month
            await cache.cache_bundle(cache_key, {"not_found": True}, NOT_FOUND_TTL)
        return "not_found", {}
    if r.status_code != 200:
        # the body is not logged: it may echo the key
        log.warning("gst.lookup_refused", status=r.status_code)
        return "unavailable", {}
    try:
        body = r.json()
    except ValueError:
        return "unavailable", {}
    if not isinstance(body, dict) or not body.get("legal_name"):
        return "not_found", {}
    details = {k: (str(body[k]) if body.get(k) is not None else None)
               for k in ("legal_name", "trade_name", "status", "address", "state_code")}
    with contextlib.suppress(Exception):   # a cache failure costs only a later lookup
        await cache.cache_bundle(cache_key, details, CACHE_TTL)
    return "found", details
