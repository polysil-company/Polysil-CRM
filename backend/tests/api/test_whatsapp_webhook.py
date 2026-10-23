"""FS-038: 11za's webhook calls are kept as they arrived, behind the path secret,
and the secret never reaches a log."""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
import structlog
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import Settings, get_settings
from api.redact import AccessLogRedact, redact_path

pytestmark = pytest.mark.db

Sessions = Callable[[], AsyncSession]
SECRET = "fs038-" + base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("=")
BASE = "/api/v1/public/webhooks/whatsapp"


@pytest_asyncio.fixture
async def secret(monkeypatch: pytest.MonkeyPatch, sessions: Sessions) -> AsyncIterator[str]:
    monkeypatch.setattr(get_settings(), "whatsapp_webhook_secret", SecretStr(SECRET))
    yield SECRET
    s = sessions()
    await s.execute(text("DELETE FROM whatsapp_webhook_event WHERE body_text LIKE '%fs038%' "
                         "OR headers::text LIKE '%fs038%'"))
    await s.commit()
    await s.close()


async def _rows(sessions: Sessions, marker: str) -> list[dict]:
    s = sessions()
    rows = (await s.execute(text(
        "SELECT kind, method, host(source_ip) AS ip, headers, body_raw, body_text, body "
        "FROM whatsapp_webhook_event WHERE headers::text LIKE :m ORDER BY received_at"),
        {"m": f"%{marker}%"})).mappings().all()
    await s.close()
    return [dict(r) for r in rows]


def _h(marker: str, **extra: str) -> dict[str, str]:
    return {"x-fs038-marker": marker, **extra}


async def test_both_kinds_are_kept_with_headers_and_bytes(client: httpx.AsyncClient, secret: str,
                                                          sessions: Sessions) -> None:
    body = {"from": "919876543210", "text": {"body": "fs038 drip quote please"}}
    for kind in ("inbound", "status"):
        r = await client.post(f"{BASE}/{secret}/{kind}", json=body,
                              headers=_h(f"both-{kind}", cookie="a=b", authtoken="provider-credential"))
        assert r.status_code == 200 and r.json() == {"ok": True}, r.text
        (row,) = await _rows(sessions, f"both-{kind}")
        assert (row["kind"], row["method"], row["body"]) == (kind, "POST", body)
        assert json.loads(bytes(row["body_raw"])) == body
        headers = dict(row["headers"])
        assert headers["cookie"].startswith("<masked") and headers["authtoken"] == "<masked, 19 chars>"


async def test_get_head_and_an_empty_post_are_kept(client: httpx.AsyncClient, secret: str,
                                                   sessions: Sessions) -> None:
    for method in ("GET", "HEAD", "POST"):
        r = await client.request(method, f"{BASE}/{secret}/inbound", headers=_h(f"probe-{method}"))
        assert r.status_code == 200, (method, r.text)
        (row,) = await _rows(sessions, f"probe-{method}")
        assert row["method"] == method and bytes(row["body_raw"]) == b"" and row["body"] is None


@pytest.mark.parametrize("raw", [
    b"not json at all fs038",
    b"\x1f\x8b\x08\x00fs038-gzip\xff\xfe",
    b'{"t": "a\x00b fs038"}',
    b'{"t": "a\\u0000b", "m": "fs038"}',
    b'{"n": 1e999, "m": "fs038"}',
    b"[" * 30000 + b"fs038",
    b'{"t": "hello \ud83d", "m": "fs038"}',
], ids=["text", "gzip", "nul", "escaped-nul", "infinity", "deep", "lone-surrogate"])
async def test_odd_bodies_are_kept_raw_and_never_fail(client: httpx.AsyncClient, secret: str,
                                                      sessions: Sessions, raw: bytes) -> None:
    marker = f"odd-{abs(hash(raw)) % 10**9}"
    r = await client.post(f"{BASE}/{secret}/inbound", content=raw,
                          headers=_h(marker, **{"content-type": "application/json"}))
    assert r.status_code == 200, r.text
    (row,) = await _rows(sessions, marker)
    assert bytes(row["body_raw"]) == raw and row["body"] is None and "\x00" not in row["body_text"]


@pytest.mark.parametrize("probe", ["short", "ગુજરાતી-" * 8, "x" * 300, SECRET[:-1] + "!"],
                         ids=["short", "gujarati", "long", "near-miss"])
async def test_a_wrong_secret_is_a_404_and_nothing_is_kept(client: httpx.AsyncClient, secret: str,
                                                           sessions: Sessions, probe: str) -> None:
    r = await client.post(f"{BASE}/{probe}/inbound", json={"m": "fs038"}, headers=_h(f"wrong-{len(probe)}"))
    assert r.status_code == 404 and "fields" not in r.json().get("error", {}), r.text
    assert await _rows(sessions, f"wrong-{len(probe)}") == []


async def test_unset_secret_is_a_404_and_an_unknown_kind_too(client: httpx.AsyncClient, secret: str,
                                                             monkeypatch: pytest.MonkeyPatch,
                                                             sessions: Sessions) -> None:
    r = await client.post(f"{BASE}/{secret}/other", json={}, headers=_h("kind-other"))
    assert r.status_code == 404
    monkeypatch.setattr(get_settings(), "whatsapp_webhook_secret", None)
    r = await client.post(f"{BASE}/{secret}/inbound", json={}, headers=_h("unset"))
    assert r.status_code == 404
    assert await _rows(sessions, "kind-other") == [] and await _rows(sessions, "unset") == []


async def test_the_body_cap_is_64_kb(client: httpx.AsyncClient, secret: str, sessions: Sessions) -> None:
    r = await client.post(f"{BASE}/{secret}/inbound", content=b"a" * (64 * 1024), headers=_h("cap-exact"))
    assert r.status_code == 200
    r = await client.post(f"{BASE}/{secret}/inbound", content=b"a" * (64 * 1024 + 1), headers=_h("cap-over"))
    assert r.status_code == 413 and r.json()["error"]["code"] == "body_too_large"

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(66):
            yield b"a" * 1024

    r = await client.post(f"{BASE}/{secret}/inbound", content=chunks(), headers=_h("cap-chunked"))
    assert r.status_code == 413
    assert await _rows(sessions, "cap-over") == [] and await _rows(sessions, "cap-chunked") == []


async def test_the_legacy_root_mount_answers_too(client: httpx.AsyncClient, secret: str,
                                                 sessions: Sessions) -> None:
    r = await client.post(f"/public/webhooks/whatsapp/{secret}/status", json={}, headers=_h("root-mount"))
    assert r.status_code == 200
    assert len(await _rows(sessions, "root-mount")) == 1


async def test_a_database_failure_logs_neither_the_secret_nor_the_body(
        secret: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Code review F-1: a real statement failure, and the exception uvicorn prints
    after the 500, not only structlog. A DBAPIError's text carries the parameters."""
    from api.main import app
    from api.services import whatsapp_webhook

    real_text = whatsapp_webhook.text
    monkeypatch.setattr(whatsapp_webhook, "text",
                        lambda sql: real_text(sql.replace("whatsapp_webhook_record", "fs038_no_such_fn")))
    # raise_app_exceptions=True: any exception that escaped the app would be
    # raised here, and that exception is what uvicorn prints with its traceback
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
    with structlog.testing.capture_logs() as logs:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(f"{BASE}/{secret}/inbound",
                                  content=b'{"from": "919800038038", "text": "fs038-private words"}')
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error", r.text
    for leak in (secret, "fs038-private", "919800038038"):
        assert leak not in r.text, leak
        assert leak not in json.dumps(logs, default=str), leak
    assert any(e.get("event") == "whatsapp_webhook.store_failed" and e.get("sqlstate") == "42883"
               for e in logs), logs


def test_redact_path_covers_both_mounts_and_near_misses() -> None:
    for path in (f"/api/v1/public/webhooks/whatsapp/{SECRET}/inbound",
                 f"/public/webhooks/whatsapp/{SECRET}/status",
                 f"/api/v1/public/webhooks/whatsapp/{SECRET}",
                 f"/api/v1/public/webhooks/whatsapp/{SECRET}/inbound?x=1",
                 "/api/v1/public/webhooks/whatsapp/wrong-guess/inbound"):
        out = redact_path(path)
        assert SECRET not in out and "wrong-guess" not in out and "<redacted>" in out, out
    assert redact_path("/api/v1/leads/123") == "/api/v1/leads/123"


def test_the_uvicorn_access_record_is_redacted() -> None:
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1,
                               '%s - "%s %s HTTP/%s" %d',
                               ("203.0.113.5:4411", "POST",
                                f"/api/v1/public/webhooks/whatsapp/{SECRET}/inbound", "1.1", 200), None)
    assert AccessLogRedact().filter(record)
    assert SECRET not in record.getMessage() and "<redacted>" in record.getMessage()
    # create_app installs it; uvicorn configures logging before it imports the app,
    # so the filter is not wiped
    import api.main  # noqa: F401

    assert any(isinstance(f, AccessLogRedact) for f in logging.getLogger("uvicorn.access").filters)


def test_a_short_secret_refuses_to_start() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        Settings(whatsapp_webhook_secret="too-short")  # type: ignore[call-arg]
    assert Settings(whatsapp_webhook_secret="").whatsapp_webhook_secret is None  # type: ignore[call-arg]
