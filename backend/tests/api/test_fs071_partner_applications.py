# ruff: noqa: E501  (request bodies inline)

"""FS-071 over the API: distributor applications, the data sheet, the deposit step
and the printed sheet. Builds on FS-051's helpers (tests/api/test_dealer_applications.py)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text

from api import pdf
from api.pdf import renderer_available
from api.services import dealer_sheet
from tests.api import test_dealer_applications as fs051
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = endpoints.shop
apps = fs051.apps
Shop = endpoints.Shop
Sessions = fs051.Sessions
PDF, JPEG = fs051.PDF, fs051.JPEG
KEYS = ("dealer_deposit_amount", "distributor_deposit_amount", "deposit_relaxation_roles",
        "dealer_application_deciders", "distributor_application_deciders",
        "dealer_application_required", "distributor_application_required")
SetSetting = Callable[[str, str], Awaitable[None]]


@pytest_asyncio.fixture
async def setting(sessions: Sessions, apps: list[str]) -> AsyncIterator[SetSetting]:
    """Change a setting for one test; every one of the seven is put back. Also clears
    the deposit entries before FS-051's fixture removes the applications."""
    s = sessions()
    saved = dict((await s.execute(text("SELECT key::text, value::text FROM app_setting WHERE key = ANY(:k)"),
                                  {"k": list(KEYS)})).all())
    await s.close()

    async def put(key: str, value: str) -> None:
        c = sessions()
        await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"), {"k": key, "v": value})
        await c.commit()
        await c.close()

    yield put
    c = sessions()
    for key, value in saved.items():
        await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"), {"k": key, "v": value})
    await c.execute(text(
        "DELETE FROM dealer_application_deposit_entry WHERE application_id IN "
        "(SELECT id FROM dealer_application WHERE mobile = ANY(:n))"), {"n": ["91" + m for m in apps]})
    await c.commit()
    await c.close()


async def _new(client: httpx.AsyncClient, shop: Shop, h: dict[str, str], apps: list[str], *,
               partner_type: str = "dealer") -> tuple[dict, str, str]:
    m10 = fs051._mobile10()
    apps.append(m10)
    r = await client.post(f"{V1}/dealer-applications", headers={**h, **_key()}, json={
        "firm_name": "Shree Ganesh Traders", "contact_name": "Ganesh Patil", "mobile": m10,
        "territory_id": shop.district, "partner_type": partner_type})
    assert r.status_code == 201, r.text
    app = r.json()["data"]
    return app, app["apply_url"].rsplit("/", 1)[1], m10


async def _slip(client: httpx.AsyncClient, h: dict[str, str], app_id: str, data: bytes = PDF) -> str:
    r = await client.post(f"{V1}/documents", headers={**h, **_key()},
                          data={"record_type": "dealer_application", "record_id": app_id, "doc_type": "deposit_slip"},
                          files={"file": ("slip.pdf", data, "application/pdf")})
    assert r.status_code in (200, 201), r.text
    return str(r.json()["data"]["id"])


async def _pay(client: httpx.AsyncClient, h: dict[str, str], app_id: str, amount: str, slip: str) -> httpx.Response:
    return await client.post(f"{V1}/dealer-applications/{app_id}/deposit", headers={**h, **_key()},
                             json={"amount": amount, "paid_on": "2026-10-01", "reference": "UTR123", "slip_id": slip})


async def _relax(client: httpx.AsyncClient, h: dict[str, str], app_id: str, due: str, reason: str = "Old partner") -> httpx.Response:
    return await client.post(f"{V1}/dealer-applications/{app_id}/deposit/relaxation", headers={**h, **_key()},
                             json={"amount_due": due, "reason": reason})


async def _decide(client: httpx.AsyncClient, h: dict[str, str], app_id: str, **body: object) -> httpx.Response:
    return await client.post(f"{V1}/dealer-applications/{app_id}/decision", headers={**h, **_key()},
                             json={"decision": "approve", **body})


async def _staff_complete(client: httpx.AsyncClient, h: dict[str, str], app_id: str) -> None:
    r = await client.patch(f"{V1}/dealer-applications/{app_id}", headers={**h, **_key()}, json={
        "firm_type": "partnership", "gst_registered": False, "pan": fs051.PAN, "address": "Station Road",
        "pincode": "360002", "bank_account_name": "Shree Ganesh", "bank_account_no": "998877665544",
        "bank_ifsc": "HDFC0001234"})
    assert r.status_code == 200, r.text
    for doc_type, data in (("pan_card", JPEG), ("cancelled_cheque", PDF + b"c")):
        r = await client.post(f"{V1}/documents", headers={**h, **_key()},
                              data={"record_type": "dealer_application", "record_id": app_id, "doc_type": doc_type},
                              files={"file": ("f", data, "application/pdf")})
        assert r.status_code in (200, 201), r.text
    r = await client.post(f"{V1}/dealer-applications/{app_id}/submit", headers={**h, **_key()})
    assert r.status_code == 200, r.text


async def test_a_distributor_pays_its_deposit_and_is_approved_under_polysil(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str], setting: SetSetting) -> None:
    await setting("distributor_deposit_amount", "50000")
    fo = await endpoints._as(client, shop, "field_officer")
    app, token, m10 = await _new(client, shop, fo, apps, partner_type="distributor")
    assert app["partner_type"] == "distributor"
    assert app["deposit"] == {"status": "pending", "amount_set": "50000.00", "amount_due": "50000.00",
                              "paid_amount": None, "paid_on": None, "reference": None, "slip_id": None, "history": []}
    assert app["can"]["record_deposit"] and not app["can"]["relax_deposit"], "the creator never relaxes"

    # the applicant fills the sheet and uploads the slip; staff record the payment against it
    hs = await fs051._verified(client, sessions, token, m10)
    pub = f"{V1}/public/dealer-apply/{token}"
    r = await client.patch(pub, headers=hs, json={"partner_type": "dealer"})
    assert r.status_code == 422, "the applicant does not choose the type"
    r = await client.patch(pub, headers=hs, json={
        "telephone": "0281-2451234", "bank_name": "HDFC Bank", "bank_branch": "Rajkot",
        "working_capital": [{"facility": "Cash credit", "amount_lakhs": "12.50"}], "other_sources_lakhs": "2",
        "manpower": [{"category": "Fitter", "people": 3, "experience_years": 4}],
        "previous_installations": [{"year": 2025, "customers": 40, "description": "Drip, cotton", "scope": "both", "cost_lakhs": "18"}],
        "two_wheelers": 2, "sales_executives": 1, "technicians": 3, "appointment_place": "Gondal"})
    assert r.status_code == 200, r.text
    view = r.json()["data"]
    assert view["deposit"]["status"] == "pending" and "history" not in view["deposit"]
    assert view["district"] and view["state"], "the printed place comes from the view"
    r = await client.post(f"{pub}/documents", headers=hs, files={"file": ("slip", PDF + b"slip", "application/pdf")},
                          data={"doc_type": "deposit_slip"})
    assert r.status_code == 201, r.text
    slip = r.json()["data"]["id"]

    assert (await _pay(client, fo, app["id"], "40000", slip)).json()["error"]["code"] == "deposit_short"
    for bad in ("5e4", "NaN", "50000.005", "-50000"):
        assert (await _pay(client, fo, app["id"], bad, slip)).status_code == 422, bad
    r = await _pay(client, fo, app["id"], "50000", slip)
    assert r.status_code == 200, r.text
    dep = r.json()["data"]["deposit"]
    assert dep["status"] == "paid" and dep["paid_amount"] == "50000.00" and dep["slip_id"] == slip

    # B-1: the applicant cannot remove the slip a payment names
    r = await client.delete(f"{pub}/documents/{slip}", headers=hs)
    assert r.status_code == 409 and r.json()["error"]["code"] == "document_in_use", r.text
    await fs051._complete(client, token, hs)

    # a State Manager is not a distributor decider; a Regional Manager is
    sm = await endpoints._as(client, shop, "state_manager")
    got = (await client.get(f"{V1}/dealer-applications/{app['id']}", headers=sm)).json()["data"]
    assert got["can"]["decide"] is False
    assert (await _decide(client, sm, app["id"])).status_code == 403
    rm = await endpoints._as(client, shop, "regional_manager")
    parent = str(shop.partner)
    r = await _decide(client, rm, app["id"], parent_id=parent)
    assert r.status_code == 422 and "parent_id" in r.json()["error"]["fields"], r.text
    r = await _decide(client, rm, app["id"])
    assert r.status_code == 200, r.text
    s = sessions()
    row = (await s.execute(text(
        "SELECT p.partner_type::text AS ptype, p.price_tier::text AS tier, p.code::text AS code, p.parent_id, r.code::text AS role "
        "FROM channel_partner p JOIN app_user u ON u.partner_id = p.id JOIN role r ON r.id = u.role_id "
        "WHERE p.id = CAST(:p AS uuid)"), {"p": r.json()["data"]["partner_id"]})).one()
    await s.close()
    assert (row.ptype, row.tier, row.role, row.parent_id) == ("distributor", "distributor", "distributor", None)
    assert row.code.startswith("DIST-"), row.code

    # E-2: closed, so even its uploader cannot remove a document
    cheque = next(d for d in (await client.get(f"{V1}/documents", headers=fo, params={
        "record_type": "dealer_application", "record_id": app["id"]})).json()["data"] if d["doc_type"] == "pan_card")
    r = await client.delete(f"{V1}/documents/{cheque['id']}", headers={**fo, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_closed", r.text


async def test_relaxing_a_deposit_by_whom_how_far_and_when(
        client: httpx.AsyncClient, shop: Shop, apps: list[str], setting: SetSetting) -> None:
    await setting("dealer_deposit_amount", "100000")
    fo = await endpoints._as(client, shop, "field_officer")
    sm = await endpoints._as(client, shop, "state_manager")
    rm = await endpoints._as(client, shop, "regional_manager")
    app, _, _ = await _new(client, shop, fo, apps)

    assert (await _relax(client, fo, app["id"], "0")).status_code == 403, "the creator"
    r = await _relax(client, sm, app["id"], "0")
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_your_relaxation", "not in the setting"
    r = await _relax(client, rm, app["id"], "150000")
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_lower"
    assert (await _relax(client, rm, app["id"], "60000", reason=" ")).status_code == 422
    r = await _relax(client, rm, app["id"], "60000")
    assert r.status_code == 200 and r.json()["data"]["deposit"]["status"] == "pending"
    r = await _relax(client, rm, app["id"], "0")
    dep = r.json()["data"]["deposit"]
    assert dep["status"] == "waived" and dep["amount_due"] == "0.00" and dep["amount_set"] == "100000.00"
    assert [(h["kind"], h["from_due"], h["to"]) for h in dep["history"]] == [
        ("relaxation", "100000.00", "60000.00"), ("relaxation", "60000.00", "0.00")]
    slip = await _slip(client, fo, app["id"])
    r = await _pay(client, fo, app["id"], "1", slip)
    assert r.status_code == 409 and r.json()["error"]["code"] == "deposit_not_due"
    # waived: approval goes through
    await _staff_complete(client, fo, app["id"])
    assert (await _decide(client, sm, app["id"])).status_code == 200

    # a partial relaxation, then the lower amount paid twice; then no relaxation
    app2, _, _ = await _new(client, shop, fo, apps)
    assert (await _relax(client, rm, app2["id"], "40000")).status_code == 200
    slip2 = await _slip(client, fo, app2["id"], PDF + b"2")
    assert (await _pay(client, fo, app2["id"], "40000", slip2)).status_code == 200
    r = await _pay(client, fo, app2["id"], "45000", slip2)
    hist = r.json()["data"]["deposit"]["history"]
    assert [h["kind"] for h in hist] == ["relaxation", "payment", "payment"], "both payments kept"
    assert r.json()["data"]["deposit"]["paid_amount"] == "45000.00"
    r = await _relax(client, rm, app2["id"], "0")
    assert r.status_code == 409 and r.json()["error"]["code"] == "deposit_paid"
    r = await client.delete(f"{V1}/documents/{slip2}", headers={**fo, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "document_in_use"

    # pending blocks approval
    app3, _, _ = await _new(client, shop, fo, apps)
    await _staff_complete(client, fo, app3["id"])
    r = await _decide(client, sm, app3["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "deposit_pending"


async def test_the_amount_is_kept_and_the_type_changes_only_before_a_deposit(
        client: httpx.AsyncClient, shop: Shop, apps: list[str], setting: SetSetting) -> None:
    await setting("dealer_deposit_amount", "25000")
    await setting("distributor_deposit_amount", "75000")
    fo = await endpoints._as(client, shop, "field_officer")
    rm = await endpoints._as(client, shop, "regional_manager")
    app, _, _ = await _new(client, shop, fo, apps)
    await setting("dealer_deposit_amount", "0")
    got = (await client.get(f"{V1}/dealer-applications/{app['id']}", headers=fo)).json()["data"]
    assert got["deposit"]["amount_set"] == "25000.00", "rule 4: a setting change moves no application in flight"

    r = await client.patch(f"{V1}/dealer-applications/{app['id']}", headers={**fo, **_key()}, json={"partner_type": "distributor"})
    assert r.status_code == 200 and r.json()["data"]["deposit"]["amount_set"] == "75000.00", r.text
    assert (await _relax(client, rm, app["id"], "70000")).status_code == 200
    r = await client.patch(f"{V1}/dealer-applications/{app['id']}", headers={**fo, **_key()}, json={"partner_type": "dealer"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "deposit_recorded"
    rows = (await client.get(f"{V1}/dealer-applications", headers=fo, params={"partner_type": "distributor"})).json()["data"]
    assert any(x["id"] == app["id"] and x["deposit_status"] == "pending" for x in rows)


async def test_the_decider_and_required_settings(
        client: httpx.AsyncClient, shop: Shop, apps: list[str], setting: SetSetting) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    sm = await endpoints._as(client, shop, "state_manager")
    dm = await endpoints._as(client, shop, "district_manager")
    await setting("dealer_deposit_amount", "0")
    await setting("dealer_application_required", '["manpower", "staff_counts"]')
    app, _, _ = await _new(client, shop, fo, apps)
    assert app["deposit"]["status"] == "not_required"
    r = await client.patch(f"{V1}/dealer-applications/{app['id']}", headers={**fo, **_key()}, json={
        "firm_type": "partnership", "gst_registered": False, "pan": fs051.PAN, "address": "Station Road",
        "pincode": "360002", "bank_account_name": "Shree Ganesh", "bank_account_no": "998877665544",
        "bank_ifsc": "HDFC0001234"})
    assert {"manpower", "staff_counts"} <= set(r.json()["data"]["missing"])
    r = await client.post(f"{V1}/dealer-applications/{app['id']}/submit", headers={**fo, **_key()})
    assert r.status_code == 422 and {"manpower", "staff_counts"} <= set(r.json()["error"]["fields"]), r.text
    r = await client.patch(f"{V1}/dealer-applications/{app['id']}", headers={**fo, **_key()}, json={
        "manpower": [{"category": "Fitter", "people": 2}], "sales_executives": 1, "technicians": 2})
    assert r.status_code == 200
    await _staff_complete(client, fo, app["id"])

    await setting("dealer_application_deciders", '["regional_manager", "district_manager"]')
    assert (await _decide(client, sm, app["id"])).status_code == 403, "no longer in the setting"
    got = (await client.get(f"{V1}/dealer-applications/{app['id']}", headers=dm)).json()["data"]
    assert got["can"]["decide"] is True
    assert (await _decide(client, dm, app["id"])).status_code == 200


async def test_clearing_and_bad_values(client: httpx.AsyncClient, shop: Shop, apps: list[str], setting: SetSetting) -> None:
    """E-3, ISS-217: `null` and `[]` clear every typed field; decimals are strict."""
    fo = await endpoints._as(client, shop, "field_officer")
    app, _, _ = await _new(client, shop, fo, apps)
    url = f"{V1}/dealer-applications/{app['id']}"
    full = {"years_in_business": 4, "established_on": "2015-04-01", "office_area": "120.5", "area_unit": "sq_m",
            "manpower": [{"category": "Fitter", "people": 2}], "two_wheelers": 1, "gst_registered": False,
            "working_capital": [{"facility": "CC", "amount_lakhs": "10"}, {"facility": "OD", "amount_lakhs": "2.25"}],
            "other_sources_lakhs": "1"}
    r = await client.patch(url, headers={**fo, **_key()}, json=full)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["working_capital_total_lakhs"] == "13.25" and d["office_area"] == "120.50" and d["area_unit"] == "sq_m"
    cleared = dict.fromkeys(full)
    cleared["manpower"] = []
    r = await client.patch(url, headers={**fo, **_key()}, json=cleared)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert all(d[k] is None for k in ("years_in_business", "established_on", "office_area", "manpower",
                                      "two_wheelers", "working_capital", "working_capital_total_lakhs"))
    assert d["gst_registered"] is True and d["area_unit"] == "sq_ft", "a cleared default falls back"
    for bad in ({"office_area": "5e4"}, {"office_area": "1.005"}, {"established_on": "2999-01-01"},
                {"manpower": [{"category": "x\u0000", "people": 1}]}, {"manpower": [{"category": "x", "people": 0}]},
                {"previous_installations": [{"year": 2999, "customers": 1, "description": "x", "scope": "both", "cost_lakhs": "1"}]}):
        assert (await client.patch(url, headers={**fo, **_key()}, json=bad)).status_code == 422, bad


async def test_the_printed_sheet(client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str],
                                 setting: SetSetting, monkeypatch: pytest.MonkeyPatch) -> None:
    fo = await endpoints._as(client, shop, "field_officer")
    sm = await endpoints._as(client, shop, "state_manager")
    app, token, m10 = await _new(client, shop, fo, apps)
    url = f"{V1}/dealer-applications/{app['id']}"
    await client.patch(url, headers={**fo, **_key()}, json={
        "firm_name": 'શ્રી "Ganesh" <img src="http://169.254.169.254/x">', "bank_account_no": "998877665544",
        "manpower": [{"category": "<b>Fitter</b>", "people": 2}]})

    class _Html:
        pdf_renderer = "html"
    monkeypatch.setattr(dealer_sheet, "get_settings", lambda: _Html())
    r = await client.get(f"{url}/pdf", headers=sm)
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"].startswith('attachment; filename="Data-Sheet-')
    page = r.text
    assert "998877665544" not in page and "xxxxxxxx5544" in page, "masked even for a decider (GAP-518)"
    assert "&lt;img" in page and "<img src=\"http://169" not in page and "&lt;b&gt;Fitter" in page, "escaped"
    assert "DEALER DATA SHEET" in page
    r = await client.get(f"{V1}/dealer-applications/form.pdf", headers=fo, params={"partner_type": "distributor"})
    assert r.status_code == 200 and "DISTRIBUTOR DATA SHEET" in r.text
    dealer_sheet._blank.clear()

    hs = await fs051._verified(client, sessions, token, m10)
    pub = f"{V1}/public/dealer-apply/{token}"
    assert (await client.get(f"{pub}/pdf")).status_code == 403, "the session first"
    r = await client.get(f"{pub}/pdf", headers=hs)
    assert r.status_code == 200 and "xxxxxxxx5544" in r.text

    monkeypatch.setattr(dealer_sheet, "get_settings", lambda: type("S", (), {"pdf_renderer": "weasyprint"})())
    monkeypatch.setattr(dealer_sheet, "renderer_available", lambda: None)
    monkeypatch.setattr(pdf, "_active", pdf.MAX_RENDERS)
    r = await client.get(f"{url}/pdf", headers=sm)
    assert r.status_code == 503 and r.json()["error"]["code"] == "busy"


@pytest.mark.skipif(renderer_available() is not None, reason="WeasyPrint's libraries are not on this box")
async def test_the_sheet_renders_a_pdf_and_fetches_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Code review F-1: the fetcher is the installed WeasyPrint's own kind, the logo
    loads, and a real http image (not escaped text) is refused while the page still
    renders. CI has the libraries; a GTK-less box skips."""
    from api.pdf import render_pdf
    monkeypatch.setattr(dealer_sheet, "get_settings", lambda: type("S", (), {"pdf_renderer": "weasyprint"})())
    body, ctype = await dealer_sheet.render(
        {"firm_name": '<img src="http://169.254.169.254/x">', "partner_type": "dealer",
         "deposit": {"status": "paid", "paid_amount": "50000.00", "paid_on": "2026-10-01"}}, partner_type="dealer")
    assert ctype == "application/pdf" and body.startswith(b"%PDF")

    fetcher = pdf.logo_only_fetcher()
    with pytest.raises(ValueError):
        fetcher.fetch("http://169.254.169.254/x")
    with pytest.raises(ValueError):
        fetcher.fetch("file:///etc/passwd")
    fetcher.fetch(pdf.logo()).close()
    raw = f'<img src="{pdf.logo()}"><img src="http://169.254.169.254/x"><img src="file:///etc/passwd">'
    assert render_pdf(raw, fetcher).startswith(b"%PDF")


async def test_codes_go_past_9999(client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str],
                                  setting: SetSetting) -> None:
    """Code review F-2: lpad cut 10000 to 1000, so one typed 9999 jammed every later
    automatic code in the state."""
    await setting("dealer_deposit_amount", "0")
    fo = await endpoints._as(client, shop, "field_officer")
    sm = await endpoints._as(client, shop, "state_manager")
    first, _, _ = await _new(client, shop, fo, apps)
    second, _, _ = await _new(client, shop, fo, apps)
    for app in (first, second):
        await _staff_complete(client, fo, app["id"])
    assert (await _decide(client, sm, first["id"], code=f"DLR-{shop.code}-9999")).status_code == 200
    r = await _decide(client, sm, second["id"])
    assert r.status_code == 200, r.text
    c = sessions()
    code = (await c.execute(text("SELECT code::text FROM channel_partner WHERE id = CAST(:p AS uuid)"),
                            {"p": r.json()["data"]["partner_id"]})).scalar_one()
    await c.close()
    assert code == f"DLR-{shop.code}-10000"


async def test_the_events_and_a_closed_applications_documents(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str], setting: SetSetting) -> None:
    """Rule 7 for the three new events, amounts as strings (E-17); and the uploader's
    own document frozen once the application is decided (E-2)."""
    await setting("dealer_deposit_amount", "25000")
    await setting("distributor_deposit_amount", "75000")
    fo = await endpoints._as(client, shop, "field_officer")
    rm = await endpoints._as(client, shop, "regional_manager")
    app, _, _ = await _new(client, shop, fo, apps)
    assert (await client.patch(f"{V1}/dealer-applications/{app['id']}", headers={**fo, **_key()},
                               json={"partner_type": "distributor"})).status_code == 200
    assert (await _relax(client, rm, app["id"], "70000")).status_code == 200
    slip = await _slip(client, fo, app["id"])
    assert (await _pay(client, fo, app["id"], "70000", slip)).status_code == 200
    s = sessions()
    events = {r.kind: r.payload for r in (await s.execute(text(
        "SELECT kind, payload FROM activity_event WHERE entity_type = 'dealer_application' "
        "AND entity_id = CAST(:a AS uuid)"), {"a": app["id"]})).all()}
    await s.close()
    assert events["dealer_application.type_changed"] == {"from": "dealer", "to": "distributor", "deposit_set": "75000.00"}
    assert events["dealer_application.deposit_relaxed"] == {"from": "75000.00", "to": "70000.00"}
    paid = events["dealer_application.deposit_recorded"]
    assert paid["amount"] == "70000.00" and paid["previous_amount"] is None and paid["slip_id"] == slip

    await _staff_complete(client, fo, app["id"])
    assert (await _decide(client, rm, app["id"])).status_code == 200
    mine = next(d for d in (await client.get(f"{V1}/documents", headers=fo, params={
        "record_type": "dealer_application", "record_id": app["id"]})).json()["data"] if d["doc_type"] == "pan_card")
    r = await client.delete(f"{V1}/documents/{mine['id']}", headers={**fo, **_key()})
    assert r.status_code == 409 and r.json()["error"]["code"] == "record_closed", "even its uploader"


async def test_removing_a_document_waits_for_the_application(
        client: httpx.AsyncClient, shop: Shop, sessions: Sessions, apps: list[str], setting: SetSetting) -> None:
    """Code review F-4: both remove paths lock the application row before the document
    (plan review B-1, R-1). With the row held, as a payment or an approval holds it,
    each remove waits; without that lock this test fails."""
    from api.db.session import enter_role
    from api.services.dealer_applications import _hash
    fo = await endpoints._as(client, shop, "field_officer")
    app, token, m10 = await _new(client, shop, fo, apps)
    staff_doc = await _slip(client, fo, app["id"])
    hs = await fs051._verified(client, sessions, token, m10)
    r = await client.post(f"{V1}/public/dealer-apply/{token}/documents", headers=hs,
                          files={"file": ("slip", PDF + b"applicant", "application/pdf")}, data={"doc_type": "deposit_slip"})
    applicant_doc = r.json()["data"]["id"]

    holder = sessions()
    await holder.execute(text("SELECT 1 FROM dealer_application WHERE id = CAST(:a AS uuid) FOR UPDATE"), {"a": app["id"]})
    try:
        for call, params, role, user in (
                ("SELECT record_document_remove(CAST(:d AS uuid))", {"d": staff_doc}, "app_role", shop.ids["field_officer"]),
                ("SELECT dealer_apply_document_remove(:t, :s, CAST(:d AS uuid))",
                 {"t": _hash(token), "s": _hash(hs["X-Apply-Session"]), "d": applicant_doc}, "app_anon", None)):
            waiter = sessions()
            try:
                await waiter.execute(text("SET LOCAL lock_timeout = '400ms'"))
                if user:
                    await waiter.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user})
                await enter_role(waiter, role)
                with pytest.raises(Exception) as err:
                    await waiter.execute(text(call), params)
                assert "lock timeout" in str(err.value) or "55P03" in str(err.value), err.value
            finally:
                await waiter.rollback()
                await waiter.close()
    finally:
        await holder.rollback()
        await holder.close()
