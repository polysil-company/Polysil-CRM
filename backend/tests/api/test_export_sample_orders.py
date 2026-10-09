"""Export and sample orders (FS-042), end to end over ASGI.

Built on the order endpoints' `shop`: a coded state, its office, its users, one
product at 100 on a 2020 list, taxed at 5 %. Each test here sets the three FS-042
settings it relies on and the fixture puts back what it found, so no test leans on
another's leftovers. The admin_sales role is lent `products.view` and
`products.edit` for the LUT endpoints: no seeded role holds them.
"""

# ruff: noqa: E501  (embedded SQL)

from __future__ import annotations

import datetime as dt
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import enter_role
from api.errors import ForbiddenError
from api.schemas import orders as order_sch
from api.services import orders as order_service
from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_order_endpoints import AS_OF, Shop
from tests.api.test_order_partners import _as_dealer

pytestmark = pytest.mark.db

shop = endpoints.shop

SETTINGS = ("export_tax_treatment", "sample_pricing", "sample_max_value", "order_amend_reapproval")


def _fy_bounds(day: dt.date) -> tuple[str, str]:
    start = dt.date(day.year if day.month >= 4 else day.year - 1, 4, 1)
    return start.isoformat(), dt.date(start.year + 1, 3, 31).isoformat()


@dataclass
class Fx:
    shop: Shop
    sessions: Callable[[], AsyncSession]

    async def setting(self, key: str, value: object) -> None:
        s = self.sessions()
        try:
            await s.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"),
                            {"k": key, "v": json.dumps(value)})
            await s.commit()
        finally:
            await s.close()

    async def lut(self, client: httpx.AsyncClient, h: dict[str, str], *,
                  start: str | None = None, end: str | None = None,
                  arn: str | None = None) -> httpx.Response:
        f, t = _fy_bounds(today_ist())
        return await client.post(
            f"{V1}/seller-gstins/{self.shop.seller}/luts", headers={**h, **_key()},
            json={"arn": arn or f"AD{uuid.uuid4().hex[:12]}", "valid_from": start or f,
                  "valid_to": end or t})


@pytest_asyncio.fixture
async def fx(shop: Shop, sessions: Callable[[], AsyncSession]) -> AsyncIterator[Fx]:
    s = sessions()
    saved = dict((await s.execute(text(
        "SELECT key::text, value::text FROM app_setting WHERE key = ANY(:k)"),
        {"k": list(SETTINGS)})).all())
    lent = (await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "SELECT r.id, 'products', a, 'global' FROM role r, unnest(ARRAY['view', 'edit']::permission_action[]) a "
        "WHERE r.code = 'admin_sales' AND NOT EXISTS (SELECT 1 FROM role_permission x "
        "WHERE x.role_id = r.id AND x.module = 'products' AND x.action = a) "
        "RETURNING id"))).scalars().all()
    await s.commit()
    await s.close()
    try:
        yield Fx(shop, sessions)
    finally:
        c = sessions()
        # the LUTs before the shop's teardown deletes the registration; documents hold
        # the ARN as text, so its orders and quotations go with the shop
        await c.execute(text("DELETE FROM seller_gstin_lut WHERE seller_gstin_id = CAST(:g AS uuid)"),
                        {"g": shop.seller})
        for key, value in saved.items():
            await c.execute(text("UPDATE app_setting SET value = CAST(:v AS jsonb) WHERE key = :k"),
                            {"k": key, "v": value})
        await c.execute(text("DELETE FROM role_permission WHERE id = ANY(CAST(:i AS uuid[]))"),
                        {"i": [str(i) for i in lent]})
        await c.commit()
        await c.close()


def _code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


def _export(shop: Shop, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "order_type": "export", "export_country": "Kenya",
        "party": {"name": "Nairobi Agro Ltd", "mobile": "9876543210", "address": "Nairobi"}}
    body.update(over)
    return endpoints._direct(shop, **body)


# ── samples ──────────────────────────────────────────────────────────────────

async def test_a_free_sample_costs_nothing_and_is_approved_on_its_list_value(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rules 11, 12 and 14: every line 100 % off whatever was typed, a total of 0
    that still submits, and a chain worked out on the gross. A district manager
    capped at 500 sends a 1,000 sample on to the state manager; on its total of 0
    the district manager alone would have taken it."""
    shop = fx.shop
    await fx.setting("sample_pricing", "free")
    await fx.setting("sample_max_value", 50000)
    s = fx.sessions()
    try:
        await s.execute(text(
            "INSERT INTO approval_threshold (doc_type, role_id, territory_id, max_amount) "
            "SELECT 'sales_order', id, CAST(:t AS uuid), 500 FROM role WHERE code = 'district_manager'"),
            {"t": shop.state})
        await s.commit()
    finally:
        await s.close()
    ho = await endpoints._as(client, shop, "field_officer")
    draft = await endpoints._create(client, ho, endpoints._direct(shop, order_type="sample"))
    assert draft["sample_pricing"] == "free" and draft["tax_treatment"] == "domestic"
    assert draft["lines"][0]["discount_pct"] == "100.000"
    assert draft["totals"]["gross"] == "1000.00" and draft["totals"]["total"] == "0.00"

    order = await endpoints._submit(client, ho, draft["id"])
    roles = [st["role"] for st in order["approval"]["steps"]]
    assert "state_manager" in roles, roles
    s = fx.sessions()
    try:
        amount = (await s.execute(text(
            "SELECT amount FROM approval_request WHERE entity_id = CAST(:o AS uuid)"),
            {"o": order["id"]})).scalar_one()
    finally:
        await s.close()
    assert str(amount) == "1000.00"


async def test_a_charged_sample_is_priced_and_a_typed_full_discount_is_still_zero_total(
        client: httpx.AsyncClient, fx: Fx) -> None:
    await fx.setting("sample_pricing", "charged")
    await fx.setting("sample_max_value", 50000)
    ho = await endpoints._as(client, fx.shop, "field_officer")
    draft = await endpoints._create(client, ho, endpoints._direct(fx.shop, order_type="sample"))
    assert draft["sample_pricing"] == "charged" and draft["totals"]["total"] == "945.00"
    body = endpoints._direct(fx.shop, order_type="sample")
    body["lines"] = [{"product_id": fx.shop.product, "qty": "1", "discount_pct": "100"}]
    zero = await endpoints._create(client, ho, body)
    r = await client.post(f"{V1}/orders/{zero['id']}/submit", json={}, headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "zero_total", r.text


async def test_the_sample_limit_holds_at_create_and_again_at_submit(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rule 13: against the gross, at the setting in force at that moment. 1,000 at
    a 1,000 limit passes; a limit lowered before submit refuses it there."""
    await fx.setting("sample_pricing", "free")
    await fx.setting("sample_max_value", 999)
    ho = await endpoints._as(client, fx.shop, "field_officer")
    r = await client.post(f"{V1}/orders", json=endpoints._direct(fx.shop, order_type="sample"),
                          headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "sample_over_limit", r.text
    await fx.setting("sample_max_value", 1000)
    draft = await endpoints._create(client, ho, endpoints._direct(fx.shop, order_type="sample"))
    await fx.setting("sample_max_value", 500)
    r = await client.post(f"{V1}/orders/{draft['id']}/submit", json={}, headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "sample_over_limit", r.text


async def test_a_sample_is_typed_in_and_a_draft_changing_type_drops_the_free_lines(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rules 10 and 18: no sample from quotations. A plain draft may change type,
    and leaving a free sample takes the 100 % off its lines."""
    await fx.setting("sample_pricing", "free")
    await fx.setting("sample_max_value", 50000)
    ho = await endpoints._as(client, fx.shop, "field_officer")
    r = await client.post(f"{V1}/orders", headers={**ho, **_key()},
                          json={"order_type": "sample", "quotation_ids": [str(uuid.uuid4())]})
    assert r.status_code == 422 and _code(r) == "sample_from_quotation", r.text

    draft = await endpoints._create(client, ho, endpoints._direct(fx.shop, order_type="sample"))
    r = await client.patch(f"{V1}/orders/{draft['id']}", json={"order_type": "commercial"},
                           headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    moved = r.json()["data"]
    assert moved["sample_pricing"] is None and moved["lines"][0]["discount_pct"] == "0.000"
    assert moved["totals"]["total"] == "1050.00"
    r = await client.patch(f"{V1}/orders/{draft['id']}", json={"order_type": "sample"},
                           headers={**ho, **_key()})
    assert r.status_code == 200 and r.json()["data"]["totals"]["total"] == "0.00", r.text


async def test_export_and_sample_are_refused_to_a_dealer(
        fx: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """Rule 19: staff only, refused in the service (and by order_submit, 045)."""
    s, dealer = await _as_dealer(sessions, fx.shop)
    try:
        for kind in ("sample", "export"):
            body = order_sch.OrderCreate.model_validate(
                endpoints._direct(fx.shop, order_type=kind, export_country="Kenya" if kind == "export" else None))
            with pytest.raises(ForbiddenError) as err:
                await order_service.create_order(s, dealer, body, None)  # type: ignore[arg-type]
            assert err.value.code == "type_staff_only"
    finally:
        await s.rollback()
        await s.close()


# ── exports ──────────────────────────────────────────────────────────────────

async def test_an_export_under_a_lut_is_zero_rated_and_carries_the_arn(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rules 2 to 7: no LUT, no export; with one, IGST at 0 % on every line, never
    intra-state although the stored place of supply is the seller's own state, the
    country on the order and the ARN taken at submit."""
    shop = fx.shop
    await fx.setting("export_tax_treatment", "lut")
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/orders", json=_export(shop), headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "lut_missing", r.text

    admin = await endpoints._as(client, shop, "admin_sales")
    r = await fx.lut(client, admin, arn="AD2404260012345")
    assert r.status_code == 201, r.text
    draft = await endpoints._create(client, ho, _export(shop))
    assert draft["tax_treatment"] == "export_lut" and draft["export_country"] == "Kenya"
    assert draft["intra_state"] is False and draft["lut_arn"] is None
    line = draft["lines"][0]
    assert (line["igst_rate"], line["igst"], line["cgst"]) == ("0.000", "0.00", "0.00")
    assert line["gst_slab"] == "5.000", "the slab stays on the line (rule 2a)"
    assert draft["totals"]["total"] == draft["totals"]["taxable"] == "900.00"
    assert draft["place_of_supply"]["id"] == shop.state

    # the preview takes the treatment and agrees to the paisa
    r = await client.post(f"{V1}/pricing/quote-lines", headers=ho, json={
        "place_of_supply_territory_id": shop.state, "seller_gstin_id": shop.seller,
        "as_of": AS_OF, "tax_treatment": "export_lut",
        "lines": [{"product_id": shop.product, "qty": "10", "discount_pct": "10"}]})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["totals"]["total"] == "900.00"
    assert r.json()["data"]["lines"][0]["igst_rate"] == "0.000"

    # a setting flipped after create changes nothing on this order (rule 5)
    await fx.setting("export_tax_treatment", "igst")
    order = await endpoints._submit(client, ho, draft["id"])
    assert order["tax_treatment"] == "export_lut" and order["lut_arn"] == "AD2404260012345"
    assert order["totals"]["total"] == "900.00"


async def test_an_export_under_igst_is_charged_at_the_slab_inter_state(
        client: httpx.AsyncClient, fx: Fx) -> None:
    await fx.setting("export_tax_treatment", "igst")
    ho = await endpoints._as(client, fx.shop, "field_officer")
    draft = await endpoints._create(client, ho, _export(fx.shop))
    assert draft["tax_treatment"] == "export_igst" and draft["lut_arn"] is None
    assert draft["lines"][0]["igst"] == "45.00" and draft["totals"]["total"] == "945.00"
    order = await endpoints._submit(client, ho, draft["id"])
    assert order["status"] == "submitted"


async def test_an_export_names_its_country_and_no_party_gstin(
        client: httpx.AsyncClient, fx: Fx) -> None:
    await fx.setting("export_tax_treatment", "igst")
    ho = await endpoints._as(client, fx.shop, "field_officer")
    for body, code in (
            (_export(fx.shop, export_country=None), "export_country_required"),
            (_export(fx.shop, party={"name": "X", "gstin": "24AAACP1234A1Z5"}), "export_party_gstin"),
            (endpoints._direct(fx.shop, export_country="Kenya"), "export_country_not_export")):
        r = await client.post(f"{V1}/orders", json=body, headers={**ho, **_key()})
        assert r.status_code == 422 and _code(r) == code, r.text


async def _export_quote(client: httpx.AsyncClient, shop: Shop, h: dict[str, str],
                        **over: object) -> httpx.Response:
    lead = (await client.post(f"{V1}/leads", headers={**h, **_key()}, json={
        "farmer_name": "Nairobi Agro", "mobile": "97" + f"{uuid.uuid4().int % 10**8:08d}",
        "territory_id": shop.district, "inquiry_type": "commercial", "mis_system": "drip",
        "village": "Vadod"})).json()["data"]
    for stage in ("contacted", "qualified"):
        r = await client.post(f"{V1}/leads/{lead['id']}/transition", json={"to_stage": stage},
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    body: dict[str, object] = {
        "lead_id": lead["id"], "sales_type": "export", "export_country": "Kenya",
        "partner_id": None, "seller_gstin_id": shop.seller, "price_effective_date": AS_OF,
        "lines": [{"product_id": shop.product, "qty": "20", "discount_pct": "5"}]}
    body.update(over)
    return await client.post(f"{V1}/quotations", headers={**h, **_key()}, json=body)


async def _accepted_export(client: httpx.AsyncClient, shop: Shop, h: dict[str, str],
                           treatment: str = "export_igst") -> dict:
    r = await _export_quote(client, shop, h)
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert q["tax_treatment"] == treatment
    assert q["totals"]["igst"] == ("95.00" if treatment == "export_igst" else "0.00")
    for path, body in (("send", {"channel": "none"}), ("transition", {"to": "accepted"})):
        r = await client.post(f"{V1}/quotations/{q['id']}/{path}", json=body,
                              headers={**h, **_key()})
        assert r.status_code == 200, r.text
    return r.json()["data"]


async def test_an_export_order_is_made_from_export_quotations_only(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rule 17: the order takes the quotation's treatment and country; a commercial
    order from an export quotation is refused, and commercial quotations still make
    an industrial order as before."""
    await fx.setting("export_tax_treatment", "igst")
    ho = await endpoints._as(client, fx.shop, "field_officer")
    q = await _accepted_export(client, fx.shop, ho)
    r = await client.post(f"{V1}/orders", json={"quotation_ids": [q["id"]]},
                          headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "type_mismatch", r.text
    # a flipped setting does not reach an order made from the quotation
    await fx.setting("export_tax_treatment", "lut")
    order = await endpoints._create(client, ho, {"order_type": "export", "quotation_ids": [q["id"]]})
    assert order["tax_treatment"] == "export_igst" and order["export_country"] == "Kenya"
    assert order["totals"]["total"] == q["totals"]["total"]
    r = await client.patch(f"{V1}/orders/{order['id']}", json={"order_type": "commercial"},
                           headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "order_type_fixed", r.text
    r = await client.patch(f"{V1}/orders/{order['id']}", json={"export_country": "Uganda"},
                           headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "quotations_disagree", r.text

    plain = await endpoints._accepted_quotation(client, fx.shop, ho)
    ind = await endpoints._create(client, ho, {"order_type": "industrial", "quotation_ids": [plain["id"]]})
    assert ind["order_type"] == "industrial"


# ── seller GSTINs and LUTs ───────────────────────────────────────────────────

async def test_luts_are_one_per_financial_year_and_stay_once_a_document_carries_them(
        client: httpx.AsyncClient, fx: Fx) -> None:
    shop = fx.shop
    await fx.setting("export_tax_treatment", "lut")
    admin = await endpoints._as(client, shop, "admin_sales")
    ho = await endpoints._as(client, shop, "field_officer")
    r = await client.post(f"{V1}/seller-gstins/{shop.seller}/luts", headers={**ho, **_key()},
                          json={"arn": "AD1111111111", "valid_from": "2026-04-01", "valid_to": "2027-03-31"})
    assert r.status_code == 403, r.text

    r = await fx.lut(client, admin, start="2026-04-01", end="2027-04-01")
    assert r.status_code == 422 and _code(r) == "lut_dates", r.text
    this = await fx.lut(client, admin)
    assert this.status_code == 201, this.text
    r = await fx.lut(client, admin)
    assert r.status_code == 409 and _code(r) == "lut_overlap", r.text
    f, _ = _fy_bounds(today_ist())
    nxt = dt.date.fromisoformat(f).replace(year=dt.date.fromisoformat(f).year + 1)
    r = await fx.lut(client, admin, start=nxt.isoformat(),
                     end=nxt.replace(month=3, day=31, year=nxt.year + 1).isoformat(),
                     arn=this.json()["data"]["arn"])
    assert r.status_code == 409 and _code(r) == "lut_duplicate", r.text
    later = await fx.lut(client, admin, start=nxt.isoformat(),
                         end=nxt.replace(month=3, day=31, year=nxt.year + 1).isoformat())
    assert later.status_code == 201, later.text

    order = await endpoints._submit(client, ho, (await endpoints._create(client, ho, _export(shop)))["id"])
    assert order["lut_arn"] == this.json()["data"]["arn"]
    r = await client.get(f"{V1}/seller-gstins", headers=admin)
    mine = next(g for g in r.json()["data"] if g["id"] == shop.seller)
    assert [x["in_use"] for x in mine["luts"]] == [False, True], "newest year first"
    r = await client.request("DELETE", f"{V1}/seller-gstins/{shop.seller}/luts/{this.json()['data']['id']}",
                             headers={**admin, **_key()})
    assert r.status_code == 409 and _code(r) == "lut_in_use", r.text
    r = await client.request("DELETE", f"{V1}/seller-gstins/{shop.seller}/luts/{later.json()['data']['id']}",
                             headers={**admin, **_key()})
    assert r.status_code == 204, r.text


# ── the database as the second enforcer (045's order_submit) ─────────────────

async def _submit_in_db(sessions: Callable[[], AsyncSession], user_id: str, order_id: str) -> str:
    """order_submit called straight, as app_role: what a caller past the service meets.
    Returns the SQLSTATE it raised, or 'ok'."""
    s = sessions()
    try:
        await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"), {"u": user_id})
        await enter_role(s, "app_role")
        try:
            await s.execute(text("SELECT order_submit(CAST(:o AS uuid))"), {"o": order_id})
        except DBAPIError as exc:
            return str(getattr(exc.orig, "sqlstate", "") or getattr(exc.orig, "pgcode", ""))
        return "ok"
    finally:
        await s.rollback()
        await s.close()


async def _owner(sessions: Callable[[], AsyncSession], sql: str, **params: object) -> None:
    s = sessions()
    try:
        await s.execute(text(sql), params)
        await s.commit()
    finally:
        await s.close()


async def test_order_submit_refuses_what_the_service_would(
        client: httpx.AsyncClient, fx: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """A priced line on a free sample, a sample over the limit, an export under a LUT
    no LUT covers, a taxed line on a LUT export, and a dealer: each refused by the
    definer with the service out of the way."""
    shop = fx.shop
    officer = shop.ids["field_officer"]
    await fx.setting("sample_pricing", "free")
    await fx.setting("sample_max_value", 50000)
    ho = await endpoints._as(client, shop, "field_officer")

    sample = await endpoints._create(client, ho, endpoints._direct(shop, order_type="sample"))
    await _owner(sessions, "UPDATE order_line SET discount_pct = 50 WHERE sales_order_id = CAST(:o AS uuid)",
                 o=sample["id"])
    assert await _submit_in_db(sessions, officer, sample["id"]) == "ORDSF"
    await _owner(sessions, "UPDATE order_line SET discount_pct = 100 WHERE sales_order_id = CAST(:o AS uuid)",
                 o=sample["id"])
    await fx.setting("sample_max_value", 10)
    assert await _submit_in_db(sessions, officer, sample["id"]) == "ORDSL"
    await fx.setting("sample_max_value", 50000)
    assert await _submit_in_db(sessions, officer, sample["id"]) == "ok"

    await fx.setting("export_tax_treatment", "lut")
    admin = await endpoints._as(client, shop, "admin_sales")
    lut = await fx.lut(client, admin)
    assert lut.status_code == 201, lut.text
    export = await endpoints._create(client, ho, _export(shop))
    await _owner(sessions, "DELETE FROM seller_gstin_lut WHERE seller_gstin_id = CAST(:g AS uuid)",
                 g=shop.seller)
    assert await _submit_in_db(sessions, officer, export["id"]) == "ORDLT"
    await _owner(sessions, "UPDATE order_line SET igst_rate = 5 WHERE sales_order_id = CAST(:o AS uuid)",
                 o=export["id"])
    assert await _submit_in_db(sessions, officer, export["id"]) == "ORDLX"

    dealer_sample = await endpoints._create(
        client, ho, endpoints._direct(shop, order_type="sample", partner_id=shop.partner))
    got = await _submit_in_db(sessions, shop.ids["dealer"], dealer_sample["id"])
    assert got == "ORDXS", got


async def test_an_amended_free_sample_is_compared_on_its_gross_and_confirms_nothing_to_the_party(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Plan review B-1: under value_rises, an amended free sample whose gross did not
    rise skips the managers, and one whose gross rose goes back through them. Rule 20:
    its approval queues no confirmation to the party, even with the template on."""
    shop = fx.shop
    await fx.setting("sample_pricing", "free")
    await fx.setting("sample_max_value", 50000)
    await fx.setting("order_amend_reapproval", "value_rises")
    s = fx.sessions()
    try:
        tpl = (await s.execute(text(
            "SELECT enabled, provider_name FROM message_template WHERE key = 'order.confirmed'"))).one()
        await s.execute(text("UPDATE message_template SET enabled = true, "
                             "provider_name = COALESCE(provider_name, 'fs042_test') "
                             "WHERE key = 'order.confirmed'"))
        await s.commit()
    finally:
        await s.close()
    try:
        ho = await endpoints._as(client, shop, "field_officer")
        order = await endpoints._submit(client, ho, (await endpoints._create(
            client, ho, endpoints._direct(shop, order_type="sample")))["id"])
        order = await endpoints._approve_all(client, shop, order)
        assert order["status"] == "approved"
        c = fx.sessions()
        try:
            queued = (await c.execute(text(
                "SELECT count(*) FROM notification_outbox WHERE template_key = 'order.confirmed' "
                "AND payload->>'order_no' = :n"), {"n": order["order_no"]})).scalar_one()
        finally:
            await c.close()
        assert queued == 0

        for qty, managers_skipped in (("10", True), ("20", False)):
            r = await client.post(f"{V1}/orders/{order['id']}/amend", headers={**ho, **_key()},
                                  json={"remark": "Change the sample"})
            assert r.status_code == 200, r.text
            c = fx.sessions()
            try:
                gross = (await c.execute(text(
                    "SELECT amended_from_gross FROM sales_order WHERE id = CAST(:o AS uuid)"),
                    {"o": order["id"]})).scalar_one()
            finally:
                await c.close()
            assert str(gross) == "1000.00"
            r = await client.put(f"{V1}/orders/{order['id']}/lines", headers={**ho, **_key()},
                                 json={"lines": [{"product_id": shop.product, "qty": qty}]})
            assert r.status_code == 200 and r.json()["data"]["totals"]["total"] == "0.00", r.text
            again = await endpoints._submit(client, ho, order["id"])
            roles = [st["role"] for st in again["approval"]["steps"]]
            if managers_skipped:
                assert roles == ["account_manager", "dispatch_manager"], roles
                order = await endpoints._approve_all(client, shop, again)
            else:
                assert roles[:1] != ["account_manager"], roles
    finally:
        r2 = fx.sessions()
        try:
            await r2.execute(text("UPDATE message_template SET enabled = :e, provider_name = :p "
                                  "WHERE key = 'order.confirmed'"),
                             {"e": tpl.enabled, "p": tpl.provider_name})
            await r2.commit()
        finally:
            await r2.close()


async def test_an_export_quotation_under_a_lut_takes_the_arn_of_its_price_date(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rules 4 and 5 on a quotation: the ARN is the one covering its price date, at
    create, on a PATCH that moves the date, and again on a revision, which keeps the
    treatment though the setting has moved on (code review F-4)."""
    shop = fx.shop
    await fx.setting("export_tax_treatment", "lut")
    ho = await endpoints._as(client, shop, "field_officer")
    admin = await endpoints._as(client, shop, "admin_sales")
    r = await _export_quote(client, shop, ho)
    assert r.status_code == 422 and _code(r) == "lut_missing", r.text

    assert (await fx.lut(client, admin, start="2020-04-01", end="2021-03-31",
                         arn="AD2020210000001")).status_code == 201
    r = await _export_quote(client, shop, ho)
    assert r.status_code == 201, r.text
    q = r.json()["data"]
    assert (q["tax_treatment"], q["lut_arn"], q["totals"]["igst"]) == ("export_lut", "AD2020210000001", "0.00")

    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"price_effective_date": "2020-03-20"},
                           headers={**ho, **_key()})
    assert r.status_code == 422 and _code(r) == "lut_missing", r.text
    assert (await fx.lut(client, admin, start="2019-04-01", end="2020-03-31",
                         arn="AD2019200000001")).status_code == 201
    r = await client.patch(f"{V1}/quotations/{q['id']}", json={"price_effective_date": "2020-03-20"},
                           headers={**ho, **_key()})
    assert r.status_code == 200 and r.json()["data"]["lut_arn"] == "AD2019200000001", r.text

    r = await client.post(f"{V1}/quotations/{q['id']}/send", json={"channel": "none"},
                          headers={**ho, **_key()})
    assert r.status_code == 200, r.text
    await fx.setting("export_tax_treatment", "igst")
    r = await client.post(f"{V1}/quotations/{q['id']}/revise", json={"price_effective_date": AS_OF},
                          headers={**ho, **_key()})
    assert r.status_code == 201 or r.status_code == 200, r.text
    v2 = r.json()["data"]
    assert (v2["tax_treatment"], v2["lut_arn"]) == ("export_lut", "AD2020210000001")


async def test_export_quotations_taxed_differently_make_no_order_together(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rule 17: one treatment per export order (code review F-4)."""
    shop = fx.shop
    ho = await endpoints._as(client, shop, "field_officer")
    admin = await endpoints._as(client, shop, "admin_sales")
    await fx.setting("export_tax_treatment", "igst")
    first = await _accepted_export(client, shop, ho)
    await fx.setting("export_tax_treatment", "lut")
    assert (await fx.lut(client, admin, start="2020-04-01", end="2021-03-31")).status_code == 201
    second = await _accepted_export(client, shop, ho, treatment="export_lut")
    r = await client.post(f"{V1}/orders", headers={**ho, **_key()},
                          json={"order_type": "export", "quotation_ids": [first["id"], second["id"]]})
    assert r.status_code == 422 and _code(r) == "type_mismatch", r.text


async def test_a_draft_becomes_an_export_and_back_and_its_place_of_supply_follows(
        client: httpx.AsyncClient, fx: Fx) -> None:
    """Rule 7 and code review F-1: becoming an export prices from the seller's state;
    leaving export puts the place of supply back on the order's own territory."""
    shop = fx.shop
    await fx.setting("export_tax_treatment", "igst")
    ho = await endpoints._as(client, shop, "field_officer")
    draft = await endpoints._create(client, ho, endpoints._direct(shop))
    assert draft["place_of_supply"]["id"] == shop.district
    r = await client.patch(f"{V1}/orders/{draft['id']}", headers={**ho, **_key()},
                           json={"order_type": "export", "export_country": "Kenya"})
    assert r.status_code == 200, r.text
    got = r.json()["data"]
    assert (got["tax_treatment"], got["intra_state"]) == ("export_igst", False)
    assert got["place_of_supply"]["id"] == shop.state
    r = await client.patch(f"{V1}/orders/{draft['id']}", headers={**ho, **_key()},
                           json={"order_type": "commercial"})
    assert r.status_code == 200, r.text
    back = r.json()["data"]
    assert (back["tax_treatment"], back["export_country"]) == ("domestic", None)
    assert back["place_of_supply"]["id"] == shop.district
