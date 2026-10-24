# ruff: noqa: E501  (request bodies inline)

"""FS-074 (BE-031): a complaint's PDF, made when asked for. Most tests run the
`html` renderer mode and read the stored page, so they hold on a box without
WeasyPrint's libraries; one renders a real PDF where they exist (CI)."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api import pdf
from api.pdf import renderer_available
from api.services import complaint_pdf
from api.storage import UnconfiguredStorage
from tests.api import test_complaints as ct
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class _Keep:
    """A storage that keeps what it is given, so the test reads the page."""

    name = "keep"

    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.files[key] = (data, content_type)

    def presign_get(self, key: str, *, filename: str, disposition: str = "inline") -> tuple[str, dt.datetime]:
        return f"https://files.test/{key}", dt.datetime.now(tz=dt.UTC) + dt.timedelta(minutes=10)


@pytest.fixture
def kept(monkeypatch: pytest.MonkeyPatch) -> _Keep:
    store = _Keep()
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: store)
    monkeypatch.setattr(complaint_pdf, "get_settings", lambda: type("S", (), {"pdf_renderer": "html"})())
    return store


async def _submitted(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], **over: Any) -> dict[str, Any]:
    c = await ct._create(client, shop, h, **over)
    r = await ct._post(client, h, f"/{c['id']}/submit")
    assert r.status_code == 200, r.text
    return dict(r.json()["data"])


async def _page(client: httpx.AsyncClient, h: dict[str, str], cid: str, store: _Keep) -> tuple[httpx.Response, str]:
    r = await client.get(f"{V1}/complaints/{cid}/pdf", headers=h)
    if r.status_code != 200:
        return r, ""
    key = r.json()["data"]["url"].removeprefix("https://files.test/")
    return r, store.files[key][0].decode("utf-8")


# ── when there is one ───────────────────────────────────────────────────────

async def test_a_draft_has_none_and_a_submitted_one_is_ready(client: httpx.AsyncClient, shop: Shop,
                                                              kept: _Keep) -> None:
    fo = await ct._as(client, shop, "field_officer")
    draft = await ct._create(client, shop, fo)
    assert draft["pdf_state"] == "none"
    assert (await client.get(f"{V1}/complaints/{draft['id']}/pdf", headers=fo)).status_code == 404
    c = await _submitted(client, shop, fo)
    assert c["pdf_state"] == "ready"
    listed = (await client.get(f"{V1}/complaints", headers=fo)).json()["data"]
    assert {x["id"]: x["pdf_state"] for x in listed}[c["id"]] == "ready"
    r, page = await _page(client, fo, c["id"], kept)
    assert r.status_code == 200, r.text
    link = r.json()["data"]
    assert link["url"].startswith("https://files.test/complaint-pdf/") and link["expires_at"]
    assert link["filename"] == complaint_pdf.filename(c["complaint_no"], "html")
    assert "/" not in link["filename"] and link["filename"].startswith("Complaint-Poly-Comp.-")
    assert c["complaint_no"] in page and "Laterals cracking within two months" in page
    assert "Submitted" in page and "DC-4471" in page


async def test_a_draft_cancelled_before_submit_has_none(client: httpx.AsyncClient, shop: Shop, kept: _Keep) -> None:
    """EC-5: it never had a number."""
    fo = await ct._as(client, shop, "field_officer")
    c = await ct._create(client, shop, fo)
    r = await ct._post(client, fo, f"/{c['id']}/cancel", {"reason": "Raised by mistake"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["pdf_state"] == "none"
    assert (await client.get(f"{V1}/complaints/{c['id']}/pdf", headers=fo)).status_code == 404


# ── what it holds ───────────────────────────────────────────────────────────

async def test_text_is_escaped_and_no_id_is_printed(client: httpx.AsyncClient, shop: Shop, kept: _Keep) -> None:
    """EC-8 and EC-1."""
    fo = await ct._as(client, shop, "field_officer")
    c = await _submitted(client, shop, fo, description='<img src="http://x/a.png"><style>@import "http://x"</style> ખેડૂત')
    _, page = await _page(client, fo, c["id"], kept)
    assert "&lt;img" in page and '<img src="http://x' not in page and "ખેડૂત" in page
    assert not UUID.search(page)


async def test_an_unchanged_complaint_gives_one_file(client: httpx.AsyncClient, shop: Shop, kept: _Keep) -> None:
    """EC-6: nothing printed changes with the clock."""
    fo = await ct._as(client, shop, "field_officer")
    c = await _submitted(client, shop, fo)
    first, _ = await _page(client, fo, c["id"], kept)
    second, _ = await _page(client, fo, c["id"], kept)
    assert first.json()["data"]["url"] == second.json()["data"]["url"] and len(kept.files) == 1


async def test_a_dealer_never_sees_an_escalation(client: httpx.AsyncClient, shop: Shop, sessions: Sessions,
                                                 kept: _Keep) -> None:
    """EC-1, plan review R-4: not on the complaint's timeline, not on the lead's, not
    in the PDF. Staff see it."""
    fo = await ct._as(client, shop, "field_officer")
    c = await _submitted(client, shop, fo, partner_id=shop.partner)
    s = sessions()
    await s.execute(text(
        "INSERT INTO activity_event (entity_type, entity_id, kind, payload) "
        "VALUES ('complaint', CAST(:c AS uuid), 'complaint.escalated', '{\"target\": \"response\"}')"),
        {"c": c["id"]})
    await s.commit()
    await s.close()
    dealer, mobile = await ct._dealer(client, shop, sessions)
    try:
        theirs = [e["kind"] for e in (await client.get(f"{V1}/complaints/{c['id']}/timeline", headers=dealer)).json()["data"]]
        ours = [e["kind"] for e in (await client.get(f"{V1}/complaints/{c['id']}/timeline", headers=fo)).json()["data"]]
        assert "complaint.escalated" not in theirs and "complaint.escalated" in ours
        _, dealer_page = await _page(client, dealer, c["id"], kept)
        _, staff_page = await _page(client, fo, c["id"], kept)
        assert dealer_page and "Escalated" not in dealer_page and "Escalated" in staff_page
        assert not UUID.search(dealer_page)
    finally:
        await ct._forget(sessions, mobile)


async def test_the_dates_print_in_ist() -> None:
    """EC-12: 20:00 UTC on 31 March is 1 April in India; a plain date stays put."""
    assert complaint_pdf.when("2027-03-31T20:00:00+00:00") == "01 Apr 2027, 01:30"
    assert complaint_pdf.when("2027-03-31") == "31 Mar 2027"
    assert complaint_pdf.clean_name("invoice‮fdp.exe") == "invoicefdp.exe"


# ── when it cannot ──────────────────────────────────────────────────────────

async def test_storage_down_is_503(client: httpx.AsyncClient, shop: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-14: 503, as the attachments answer it."""
    fo = await ct._as(client, shop, "field_officer")
    c = await _submitted(client, shop, fo)
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: UnconfiguredStorage())
    monkeypatch.setattr(complaint_pdf, "get_settings", lambda: type("S", (), {"pdf_renderer": "html"})())
    r = await client.get(f"{V1}/complaints/{c['id']}/pdf", headers=fo)
    assert r.status_code == 503 and ct._code(r) == "storage_unavailable", r.text


async def test_busy_is_shared_with_the_data_sheet(client: httpx.AsyncClient, shop: Shop, kept: _Keep,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """EC-4: one limit for both documents."""
    fo = await ct._as(client, shop, "field_officer")
    c = await _submitted(client, shop, fo)
    monkeypatch.setattr(pdf, "_active", pdf.MAX_RENDERS)
    r = await client.get(f"{V1}/complaints/{c['id']}/pdf", headers=fo)
    assert r.status_code == 503 and ct._code(r) == "busy", r.text


@pytest.mark.skipif(renderer_available() is not None, reason="needs WeasyPrint's libraries (CI has them)")
async def test_a_real_pdf_renders(client: httpx.AsyncClient, shop: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Keep()
    monkeypatch.setattr("api.routers.complaints.get_storage", lambda *a, **k: store)
    fo = await ct._as(client, shop, "field_officer")
    c = await _submitted(client, shop, fo)
    r = await client.get(f"{V1}/complaints/{c['id']}/pdf", headers=fo)
    assert r.status_code == 200, r.text
    body, ctype = next(iter(store.files.values()))
    assert ctype == "application/pdf" and body.startswith(b"%PDF")
    assert r.json()["data"]["filename"].endswith(".pdf")
