# ruff: noqa: E501  (embedded SQL and sheet data)

"""Excel import, the endpoints (FS-062): upload, check, commit and discard for
partners, rates and lines; the owner-only batch; staff-only kinds; the purge.

Built on the order endpoints' `shop`: a coded state and district, an office at the
district, its staff and one product. Imported partners and batches are removed by
`imported` before the shop's teardown.
"""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import openpyxl
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.db.session import enter_role
from api.errors import ForbiddenError
from api.schemas.imports import ImportCheckRequest
from api.services import imports as service
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key
from tests.api.test_order_endpoints import Shop
from tests.api.test_order_partners import _as_dealer

pytestmark = pytest.mark.db

shop = endpoints.shop
__all__ = ["shop"]


@dataclass
class Fx:
    shop: Shop
    district_name: str
    product_description: str


@pytest_asyncio.fixture
async def imported(shop: Shop, sessions: Callable[[], AsyncSession]) -> AsyncIterator[Fx]:
    s = sessions()
    district = (await s.execute(text("SELECT name FROM territory WHERE id = CAST(:d AS uuid)"),
                                {"d": shop.district})).scalar_one()
    product = (await s.execute(text("SELECT description::text FROM product "
                                    "WHERE id = CAST(:p AS uuid)"), {"p": shop.product})).scalar_one()
    await s.close()
    try:
        yield Fx(shop, district, product)
    finally:
        c = sessions()
        people = list(shop.ids.values())
        ids = [str(i) for i in (await c.execute(text(
            "SELECT id FROM channel_partner WHERE territory_id IN (CAST(:s AS uuid), CAST(:d AS uuid)) "
            "AND id <> CAST(:own AS uuid)"),
            {"s": shop.state, "d": shop.district, "own": shop.partner})).scalars().all()]
        for stmt in (
            "DELETE FROM import_batch WHERE created_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM price_list_item WHERE price_list_id IN "
            "(SELECT id FROM price_list WHERE created_by = ANY(CAST(:p AS uuid[])))",
            "DELETE FROM price_list WHERE created_by = ANY(CAST(:p AS uuid[]))",
        ):
            await c.execute(text(stmt), {"p": people})
        await c.execute(text("DELETE FROM activity_event WHERE partner_id = ANY(CAST(:i AS uuid[]))"),
                        {"i": ids})
        for ptype in ("sub_dealer", "dealer", "distributor"):
            await c.execute(text(
                "DELETE FROM channel_partner WHERE id = ANY(CAST(:i AS uuid[])) "
                "AND partner_type = CAST(:t AS partner_type)"), {"i": ids, "t": ptype})
        await c.commit()
        await c.close()


def _xlsx(rows: list[list[object]]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode()


async def _upload(client: httpx.AsyncClient, h: dict[str, str], kind: str, data: bytes,
                  name: str = "sheet.xlsx", key: str | None = None,
                  **form: str) -> httpx.Response:
    return await client.post(f"{V1}/imports", headers={**h, "Idempotency-Key": key or str(uuid.uuid4())},
                             data={"kind": kind, **form}, files={"file": (name, data)})


async def _check(client: httpx.AsyncClient, h: dict[str, str], batch: str,
                 mapping: dict[str, int], **options: str) -> httpx.Response:
    body: dict[str, object] = {"mapping": mapping}
    if options:
        body["options"] = options
    return await client.post(f"{V1}/imports/{batch}/check", headers={**h, **_key()}, json=body)


async def _commit(client: httpx.AsyncClient, h: dict[str, str], batch: str,
                  skip_invalid: bool = False) -> httpx.Response:
    return await client.post(f"{V1}/imports/{batch}/commit", headers={**h, **_key()},
                             json={"skip_invalid": skip_invalid})


def _partner_sheet(fx: Fx, tag: str, *, bad_mobile: bool = False) -> bytes:
    shop = fx.shop
    return _xlsx([
        ["Firm", "Mob", "Type", "Code", "State", "Dist", "Parent"],
        ["Shree Agro", "98765 43210", "Distributor", f"X{tag}", shop.code, fx.district_name, ""],
        ["Patel Irrigation", "12345" if bad_mobile else 9876543211, "Dealer", f"D{tag}",
         shop.code, fx.district_name, f"x{tag}"],
        ["Ram Krishi", "", "sub dealer", f"S{tag}", shop.code, "", f"D{tag}"],
    ])


# ── partners ─────────────────────────────────────────────────────────────────

async def test_partners_upload_check_and_commit_without_any_login(
        client: httpx.AsyncClient, imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """Rules 1 to 3 and 5: nothing saved before commit; parents first; no app_user."""
    shop = imported.shop
    h = await endpoints._as(client, shop, "admin_sales")
    tag = uuid.uuid4().hex[:6].upper()
    r = await _upload(client, h, "partners", _partner_sheet(imported, tag))
    assert r.status_code == 201, r.text
    batch = r.json()["data"]
    assert batch["status"] == "uploaded" and batch["row_count"] == 3
    assert batch["headers"][:2] == ["Firm", "Mob"] and len(batch["sample"]) == 3
    mapping = batch["suggested_mapping"]
    assert mapping == {"name": 0, "mobile": 1, "partner_type": 2, "code": 3, "state": 4,
                       "district": 5, "parent_code": 6}

    r = await _check(client, h, batch["id"], mapping)
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert (result["total"], result["ok"], result["errors"]) == (3, 3, 0), result
    first = result["preview"][0]["values"]
    assert first["mobile"] == "919876543210"
    assert first["territory"] == f"{imported.district_name}, {shop.code}" or \
        first["territory"].startswith(imported.district_name)

    s = sessions()
    none_yet = (await s.execute(text("SELECT count(*) FROM channel_partner WHERE code = ANY(:c)"),
                                {"c": [f"X{tag}", f"D{tag}", f"S{tag}"]})).scalar_one()
    assert none_yet == 0, "a check saves nothing"
    await s.close()

    r = await _commit(client, h, batch["id"])
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"status": "committed", "created": 3, "skipped": 0,
                                "price_list_id": None}

    s = sessions()
    made = {row[0]: row for row in (await s.execute(text(
        "SELECT c.code::text, c.partner_type::text, p.code::text, c.territory_id::text, c.mobile "
        "FROM channel_partner c LEFT JOIN channel_partner p ON p.id = c.parent_id "
        "WHERE c.code = ANY(:c)"), {"c": [f"X{tag}", f"D{tag}", f"S{tag}"]})).all()}
    assert made[f"X{tag}"][1:4] == ("distributor", None, shop.district)
    assert made[f"D{tag}"][1:3] == ("dealer", f"X{tag}")
    assert made[f"S{tag}"][1:4] == ("sub_dealer", f"D{tag}", shop.state)
    logins = (await s.execute(text(
        "SELECT count(*) FROM app_user u JOIN channel_partner c ON c.id = u.partner_id "
        "WHERE c.code = ANY(:c)"), {"c": [f"X{tag}", f"D{tag}", f"S{tag}"]})).scalar_one()
    assert logins == 0, "rule 3: portal access stays a separate step"
    events = (await s.execute(text(
        "SELECT count(*) FROM activity_event e JOIN channel_partner c ON c.id = e.entity_id "
        "WHERE e.kind = 'partner.created' AND e.payload->>'via' = 'import' "
        "AND c.code = ANY(:c)"), {"c": [f"X{tag}", f"D{tag}", f"S{tag}"]})).scalar_one()
    assert events == 3
    await s.close()

    again = await _commit(client, h, batch["id"])
    assert again.status_code == 409 and again.json()["error"]["code"] == "import_wrong_state"


async def test_a_bad_row_refuses_the_commit_unless_skipped_and_strands_its_children(
        client: httpx.AsyncClient, imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """EC-12: the dealer with a bad mobile is skipped, and so is its sub-dealer."""
    shop = imported.shop
    h = await endpoints._as(client, shop, "admin_sales")
    tag = uuid.uuid4().hex[:6].upper()
    batch = (await _upload(client, h, "partners",
                           _partner_sheet(imported, tag, bad_mobile=True))).json()["data"]
    result = (await _check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert (result["ok"], result["errors"]) == (1, 2)
    by_row = {e["row"]: e["errors"] for e in result["error_rows"]}
    assert by_row[3] == {"mobile": "not an Indian mobile number"}
    assert by_row[4] == {"parent_code": "the parent on row 3 has errors"}

    refused = await _commit(client, h, batch["id"])
    assert refused.status_code == 422, refused.text
    body = refused.json()["error"]
    assert body["code"] == "import_has_errors" and "rows[3].mobile" in body["fields"]

    done = await _commit(client, h, batch["id"], skip_invalid=True)
    assert done.status_code == 200, done.text
    assert (done.json()["data"]["created"], done.json()["data"]["skipped"]) == (1, 2)


async def test_a_district_manager_cannot_import_outside_the_area(
        client: httpx.AsyncClient, imported: Fx) -> None:
    """EC-10: the real insert policy decides, row by row."""
    shop = imported.shop
    h = await endpoints._as(client, shop, "district_manager")
    tag = uuid.uuid4().hex[:6].upper()
    data = _xlsx([["Type", "Code", "Name", "State", "District"],
                  ["Dealer", f"IN{tag}", "Inside", shop.code, imported.district_name],
                  ["Dealer", f"OUT{tag}", "Outside", "GJ", ""]])
    batch = (await _upload(client, h, "partners", data)).json()["data"]
    result = (await _check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert result["ok"] == 1, result
    [error] = result["error_rows"]
    assert error["row"] == 3 and error["errors"]["state"].endswith("is outside your area")


async def test_a_code_in_use_anywhere_is_an_error_even_when_hidden(
        client: httpx.AsyncClient, imported: Fx) -> None:
    """EC-11: the shop's dealer code, in another case, from a district manager."""
    shop = imported.shop
    h = await endpoints._as(client, shop, "admin_sales")
    s_code = (await client.get(f"{V1}/partners/{shop.partner}", headers=h)).json()["data"]["code"]
    data = _xlsx([["Type", "Code", "Name", "State"], ["Dealer", s_code.lower(), "Dup", shop.code]])
    batch = (await _upload(client, h, "partners", data)).json()["data"]
    result = (await _check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert result["error_rows"][0]["errors"]["code"].endswith("is already in use")


async def test_a_code_taken_after_the_check_names_its_row(
        client: httpx.AsyncClient, imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-1: the late clash at commit names the sheet row."""
    shop = imported.shop
    h = await endpoints._as(client, shop, "admin_sales")
    tag = uuid.uuid4().hex[:6].upper()
    data = _xlsx([["Type", "Code", "Name", "State"], ["Dealer", f"LATE{tag}", "Late", shop.code]])
    batch = (await _upload(client, h, "partners", data)).json()["data"]
    assert (await _check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]["ok"] == 1
    s = sessions()
    await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier) "
        "VALUES ('dealer', :c, 'Got there first', CAST(:t AS uuid), 'dealer')"),
        {"c": f"LATE{tag}", "t": shop.state})
    await s.commit()
    await s.close()
    # commit re-checks inside its transaction, so the clash comes back by row
    r = await _commit(client, h, batch["id"])
    assert r.status_code == 422, r.text
    assert r.json()["error"]["fields"] == {"rows[2].code": f"LATE{tag} is already in use"}


async def test_a_late_unique_clash_is_named_by_row(imported: Fx) -> None:
    """F-1 at the mapping itself: asyncpg's detail carries the key."""
    from types import SimpleNamespace

    from sqlalchemy.exc import DBAPIError

    from api.domain.imports.rows import RowResult

    orig = SimpleNamespace(sqlstate="23505", args=("duplicate key value violates unique "
                                                   "constraint \"uq_channel_partner_code\"",),
                           detail="Key (code)=(D-7) already exists.")
    exc = DBAPIError("INSERT", {}, orig)  # type: ignore[arg-type]
    tier = [RowResult(5, {"code": "d-7"}), RowResult(9, {"code": "D-8"})]
    out = service._late_refusal(exc, tier)
    assert getattr(out, "fields", None) == {"rows[5].code": "already in use"}


async def test_a_closed_partners_code_can_be_imported_again(
        client: httpx.AsyncClient, imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-2: the partial unique index frees a closed partner's code."""
    shop = imported.shop
    tag = uuid.uuid4().hex[:6].upper()
    s = sessions()
    await s.execute(text(
        "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, deleted_at) "
        "VALUES ('dealer', :c, 'Closed', CAST(:t AS uuid), 'dealer', now())"),
        {"c": f"REUSE{tag}", "t": shop.state})
    await s.commit()
    await s.close()
    h = await endpoints._as(client, shop, "admin_sales")
    data = _xlsx([["Type", "Code", "Name", "State"], ["Dealer", f"REUSE{tag}", "New", shop.code]])
    batch = (await _upload(client, h, "partners", data)).json()["data"]
    result = (await _check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert result["ok"] == 1, result


async def test_the_batch_is_its_uploaders_alone(client: httpx.AsyncClient, imported: Fx) -> None:
    """Negative RLS: another user of the same office gets 404 on every verb."""
    shop = imported.shop
    owner = await endpoints._as(client, shop, "admin_sales")
    other = await endpoints._as(client, shop, "md_ceo")
    batch = (await _upload(client, owner, "partners",
                           _partner_sheet(imported, uuid.uuid4().hex[:6].upper()))).json()["data"]
    bid = batch["id"]
    assert (await client.get(f"{V1}/imports/{bid}", headers=other)).status_code == 404
    assert (await _check(client, other, bid, batch["suggested_mapping"])).status_code == 404
    assert (await _commit(client, other, bid)).status_code == 404
    gone = await client.delete(f"{V1}/imports/{bid}", headers={**other, **_key()})
    assert gone.status_code == 404
    assert (await client.get(f"{V1}/imports/{bid}", headers=owner)).status_code == 200


async def test_a_partner_user_may_not_import_partners_or_prices(
        imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """EC-18: dealers hold partners.create, but the import is staff only."""
    s, caller = await _as_dealer(sessions, imported.shop)
    try:
        with pytest.raises(ForbiddenError):
            await service.upload(s, caller, kind="partners", target_id=None, file_name="x.csv",
                                 data=b"code\nA\n", sha256="0" * 64, sheet=None, header_row=None)
        batch = await service.upload(s, caller, kind="lines", target_id=None, file_name="x.csv",
                                     data=f"description,qty\n{imported.product_description},5\n"
                                     .encode(), sha256="0" * 64, sheet=None, header_row=None)
        result = await service.check(s, caller, batch.id, ImportCheckRequest(
            mapping=batch.suggested_mapping))
        assert result.ok == 1, result
    finally:
        await s.rollback()
        await s.close()


# ── prices ───────────────────────────────────────────────────────────────────

async def _draft_list(client: httpx.AsyncClient, h: dict[str, str]) -> str:
    r = await client.post(f"{V1}/price-lists", headers={**h, **_key()}, json={
        "name": f"import {uuid.uuid4().hex[:6]}", "effective_from": "2290-01-01",
        "channel_tier": "sub_dealer"})
    assert r.status_code == 201, r.text
    return str(r.json()["data"]["id"])


async def _rates(client: httpx.AsyncClient, h: dict[str, str], list_id: str,
                 *descriptions: str) -> dict[str, str]:
    out = {}
    for d in descriptions:
        r = await client.get(f"{V1}/price-lists/{list_id}/items", headers=h, params={"q": d})
        out.update({i["description"]: i["rate"] for i in r.json()["data"]
                    if i["rate"] and i["description"] == d})
    return out


async def test_rates_fill_a_draft_list_and_merge_keeps_the_others(
        client: httpx.AsyncClient, imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    shop = imported.shop
    h = await endpoints._as(client, shop, "admin_sales")
    list_id = await _draft_list(client, h)
    # CI has no product master (client data stays out of the shared repo), so the
    # second product is made here rather than picked from the catalogue
    other = f"IMPORT OTHER {uuid.uuid4().hex[:8].upper()}"
    s = sessions()
    other_id = str((await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id) "
        "SELECT CAST(:d AS citext), product_category_id, quotation_category, uom_id "
        "FROM product WHERE id = CAST(:p AS uuid) RETURNING id"),
        {"d": other, "p": shop.product})).scalar_one())
    await s.commit()
    await s.close()
    try:
        await _rates_round_trip(client, h, imported, list_id, other)
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM price_list_item WHERE product_id = CAST(:p AS uuid)"),
                        {"p": other_id})
        await s.execute(text("DELETE FROM product WHERE id = CAST(:p AS uuid)"), {"p": other_id})
        await s.commit()
        await s.close()


async def _rates_round_trip(client: httpx.AsyncClient, h: dict[str, str], imported: Fx,
                            list_id: str, other: str) -> None:
    first = (await _upload(client, h, "price_list_items",
                           _csv([["Product", "Price"], [imported.product_description, "1,234.50"],
                                 [other, "10"]]), name="r.csv", target_id=list_id)).json()["data"]
    assert first["suggested_mapping"] == {"description": 0, "rate": 1}
    assert (await _check(client, h, first["id"], first["suggested_mapping"])).json()["data"]["ok"] == 2
    done = await _commit(client, h, first["id"])
    assert done.json()["data"]["created"] == 2 and done.json()["data"]["price_list_id"] == list_id
    assert await _rates(client, h, list_id, imported.product_description, other) == {imported.product_description: "1234.50",
                                                other: "10.00"}

    second = (await _upload(client, h, "price_list_items",
                            _csv([["Product", "Price"], [imported.product_description, "99"]]),
                            name="r.csv", target_id=list_id)).json()["data"]
    await _check(client, h, second["id"], second["suggested_mapping"], mode="merge")
    assert (await _commit(client, h, second["id"])).status_code == 200
    assert await _rates(client, h, list_id, imported.product_description, other) == {imported.product_description: "99.00",
                                                other: "10.00"}

    third = (await _upload(client, h, "price_list_items",
                           _csv([["Product", "Price"], [imported.product_description, "98.765"]]),
                           name="r.csv", target_id=list_id)).json()["data"]
    result = (await _check(client, h, third["id"], third["suggested_mapping"])).json()["data"]
    assert result["error_rows"][0]["errors"] == {"rate": "at most 2 decimal places"}


async def test_a_published_list_takes_no_import(client: httpx.AsyncClient, imported: Fx) -> None:
    """EC-19: published between check and commit is a 409, nothing written."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    list_id = await _draft_list(client, h)
    batch = (await _upload(client, h, "price_list_items",
                           _csv([["description", "rate"], [imported.product_description, "5"]]),
                           name="r.csv", target_id=list_id)).json()["data"]
    await _check(client, h, batch["id"], batch["suggested_mapping"])
    r = await client.post(f"{V1}/price-lists/{list_id}/publish", headers={**h, **_key()},
                          json={"allow_unpriced": True})
    assert r.status_code == 200, r.text
    r = await _commit(client, h, batch["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "price_list_published"
    r = await _upload(client, h, "price_list_items", _csv([["description", "rate"]]),
                      name="r.csv", target_id=list_id)
    assert r.status_code == 409


# ── lines ────────────────────────────────────────────────────────────────────

async def test_lines_come_back_for_the_form_and_have_no_commit(
        client: httpx.AsyncClient, imported: Fx) -> None:
    h = await endpoints._as(client, imported.shop, "field_officer")
    batch = (await _upload(client, h, "lines", _xlsx([
        ["Item", "Qty", "Disc"], [imported.product_description, 12, 0.05], ["NO SUCH THING", 1, 0]
    ]))).json()["data"]
    assert batch["suggested_mapping"] == {"description": 0, "qty": 1, "discount_pct": 2}
    result = (await _check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert result["ok"] == 1 and result["errors"] == 1
    [line] = result["lines"]
    assert line["product_id"] == imported.shop.product and line["qty"] == "12"
    assert line["discount_pct"] == "0.050", "a plain number cell is read as typed"
    r = await _commit(client, h, batch["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "import_wrong_state"


# ── the edges of the endpoints ───────────────────────────────────────────────

async def test_bad_files_mappings_and_a_replayed_upload(
        client: httpx.AsyncClient, imported: Fx) -> None:
    h = await endpoints._as(client, imported.shop, "admin_sales")
    r = await _upload(client, h, "partners", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1xx", name="old.xls")
    assert r.status_code == 422 and r.json()["error"]["code"] == "import_unreadable"

    key = str(uuid.uuid4())
    data = _partner_sheet(imported, uuid.uuid4().hex[:6].upper())
    a = await _upload(client, h, "partners", data, key=key)
    b = await _upload(client, h, "partners", data, key=key)
    assert a.status_code == b.status_code == 201
    assert a.json()["data"]["id"] == b.json()["data"]["id"], "the same key replays"

    bid = a.json()["data"]["id"]
    r = await _check(client, h, bid, {"name": 0, "code": 0})
    assert r.status_code == 422
    fields = r.json()["error"]["fields"]
    assert fields["mapping.code"].startswith("that column is already")
    assert fields["mapping.partner_type"] == "required"

    r = await client.delete(f"{V1}/imports/{bid}", headers={**h, **_key()})
    assert r.status_code == 204
    got = (await client.get(f"{V1}/imports/{bid}", headers=h)).json()["data"]
    assert got["status"] == "discarded" and got["sample"] == []
    assert (await _check(client, h, bid, {"name": 0})).status_code == 409


async def test_an_upload_over_ten_megabytes_is_413(client: httpx.AsyncClient, imported: Fx) -> None:
    h = await endpoints._as(client, imported.shop, "admin_sales")
    r = await _upload(client, h, "partners", b"a" * (10 * 1024 * 1024 + 1), name="big.csv")
    assert r.status_code == 413 and r.json()["error"]["code"] == "attachment_too_large"


async def test_the_worker_purges_batches_after_seven_days(
        client: httpx.AsyncClient, imported: Fx, sessions: Callable[[], AsyncSession]) -> None:
    """EC-13: the system principal, through the definer; anyone else is refused."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    bid = (await _upload(client, h, "partners",
                         _partner_sheet(imported, uuid.uuid4().hex[:6].upper()))).json()["data"]["id"]
    fresh = (await _upload(client, h, "partners",
                           _partner_sheet(imported, uuid.uuid4().hex[:6].upper()))).json()["data"]["id"]
    s = sessions()
    await s.execute(text("UPDATE import_batch SET created_at = now() - interval '6 days' "
                         "WHERE id = CAST(:i AS uuid)"), {"i": fresh})
    await s.execute(text("UPDATE import_batch SET created_at = now() - interval '8 days' "
                         "WHERE id = CAST(:i AS uuid)"), {"i": bid})
    await s.commit()
    await s.close()

    s = sessions()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                    {"u": imported.shop.ids["admin_sales"]})
    await enter_role(s, "app_role")
    with pytest.raises(Exception, match="only the system principal"):
        await s.execute(text("SELECT import_batch_purge(now() - interval '7 days')"))
    await s.rollback()
    await s.execute(text("SELECT set_config('app.current_user_id', :u, true)"),
                    {"u": get_settings().system_user_id})
    await enter_role(s, "app_role")
    gone = (await s.execute(text("SELECT import_batch_purge(now() - interval '7 days')"))).scalar_one()
    assert gone >= 1
    await s.commit()
    await s.close()
    assert (await client.get(f"{V1}/imports/{bid}", headers=h)).status_code == 404
    assert (await client.get(f"{V1}/imports/{fresh}", headers=h)).status_code == 200, \
        "a batch inside the seven days stays (code review F-5)"
