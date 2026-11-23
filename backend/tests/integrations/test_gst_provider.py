"""FS-053: the GST data provider, against a fake transport. Nothing here calls out."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from api.config import get_settings
from api.integrations import gst


class _Cache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def read_bundle(self, key: str) -> Any:
        return self.store.get(key)

    async def cache_bundle(self, key: str, bundle: Any, ttl: Any) -> None:
        self.store[key] = bundle


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"n": 0, "status": 200, "body": {
        "gstin": "27AAPFU0939F1ZV", "legal_name": "PATEL AGRO", "trade_name": "Patel Agro Centre",
        "status": "Active", "address": "Main Road, Pune", "state_code": "27"}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        calls["key"] = request.headers.get("x-api-key")
        return httpx.Response(calls["status"], json=calls["body"])

    real = httpx.AsyncClient

    def client(*a: Any, **k: Any) -> httpx.AsyncClient:
        k.pop("transport", None)
        return real(transport=httpx.MockTransport(handler), timeout=k.get("timeout"))

    monkeypatch.setattr(gst.httpx, "AsyncClient", client)
    monkeypatch.setattr(gst, "cache", _Cache())
    s = get_settings()
    monkeypatch.setattr(s, "gst_provider", "gstinapi")
    monkeypatch.setattr(s, "gstinapi_key", __import__("pydantic").SecretStr("gak_test"))
    return calls


async def test_found_is_cached_so_the_quota_is_spent_once(fake: dict[str, Any]) -> None:
    got, details = await gst.fetch("27AAPFU0939F1ZV", get_settings())
    assert got == "found" and details["legal_name"] == "PATEL AGRO" and fake["key"] == "gak_test"
    again, _ = await gst.fetch("27AAPFU0939F1ZV", get_settings())
    assert again == "found" and fake["n"] == 1


@pytest.mark.parametrize(("status", "expected"),
                         [(404, "not_found"), (429, "unavailable"), (500, "unavailable")])
async def test_refusals_never_raise(fake: dict[str, Any], status: int, expected: str) -> None:
    fake["status"] = status
    got, details = await gst.fetch("29AAGCB7383J1Z4", get_settings())
    assert (got, details) == (expected, {})


async def test_no_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "gst_provider", "none")
    assert await gst.fetch("27AAPFU0939F1ZV", s) == ("unavailable", {})


async def test_not_found_is_remembered_so_a_wrong_gstin_spends_once(fake: dict[str, Any]) -> None:
    """Code review F-8: the free quota is 100 a month and the public form can retry."""
    fake["status"] = 404
    for _ in range(3):
        got, details = await gst.fetch("29AAGCB7383J1Z4", get_settings())
        assert (got, details) == ("not_found", {})
    assert fake["n"] == 1
