# ruff: noqa: E501  (embedded SQL and sheet data)

"""Import matching fixes, the endpoints (FS-067): a titled sheet finds its header,
an unknown code with a known name is matched and warned about once, a product name
in the code column says so, a discarded batch keeps a check with no cell values,
a committed partner batch keeps no preview, and a discarded mapping is not
remembered.

Built on FS-062's `imported` fixture, which removes batches and lists afterwards."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain.imports.rows import NAME_IN_CODE
from tests.api import test_imports as base
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1, _key

pytestmark = pytest.mark.db

shop = base.shop
imported = base.imported
__all__ = ["imported", "shop"]


@dataclass
class Products:
    plain: str        # no item code, a double space in the catalogue's name is not stored
    coded: str        # has an item code
    code: str


@pytest_asyncio.fixture
async def products(imported: base.Fx,
                   sessions: Callable[[], AsyncSession]) -> AsyncIterator[Products]:
    tag = uuid.uuid4().hex[:8].upper()
    made = Products(plain=f"MATCH PIPE PE 100 {tag}", coded=f"MATCH VALVE {tag}",
                    code=f"MV-{tag}")
    s = sessions()
    ids = []
    for description, code in ((made.plain, None), (made.coded, made.code)):
        ids.append(str((await s.execute(text(
            "INSERT INTO product (description, item_code, product_category_id, "
            "  quotation_category, uom_id) "
            "SELECT CAST(:d AS citext), CAST(:c AS citext), product_category_id, "
            "  quotation_category, uom_id FROM product WHERE id = CAST(:p AS uuid) RETURNING id"),
            {"d": description, "c": code, "p": imported.shop.product})).scalar_one()))
    await s.commit()
    await s.close()
    try:
        yield made
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM price_list_item WHERE product_id = ANY(CAST(:p AS uuid[]))"),
                        {"p": ids})
        await s.execute(text("DELETE FROM product WHERE id = ANY(CAST(:p AS uuid[]))"), {"p": ids})
        await s.commit()
        await s.close()


async def test_a_titled_sheet_finds_its_header_and_matches_names_loosely(
        client: httpx.AsyncClient, imported: base.Fx, products: Products) -> None:
    """Rules 1, 5 and 6 b: a title row above the header; an unknown code beside a
    known name, with an extra space, is a good row and one column warning."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    list_id = await base._draft_list(client, h)
    spaced = products.plain.replace("PE 100", "PE  100")
    batch = (await base._upload(client, h, "price_list_items", base._xlsx([
        ["Polysil price list"],
        ["Item Code", "Product Description", "Rate"],
        ["NOT-A-CODE", spaced, 12.5],
    ]), target_id=list_id)).json()["data"]
    assert batch["header_row"] == 2 and batch["row_count"] == 1
    assert batch["suggested_mapping"] == {"item_code": 0, "description": 1, "rate": 2}

    result = (await base._check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert (result["ok"], result["errors"]) == (1, 0), result
    assert result["column_warnings"]["item_code"] == (
        "1 item code is not in the catalogue. That row was matched by its description.")
    assert (await base._commit(client, h, batch["id"])).status_code == 200
    assert await base._rates(client, h, list_id, products.plain) == {products.plain: "12.50"}


async def test_a_wrong_code_for_a_coded_product_and_a_name_in_the_code_column(
        client: httpx.AsyncClient, imported: base.Fx, products: Products) -> None:
    """Rule 6 c and d."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    list_id = await base._draft_list(client, h)
    batch = (await base._upload(client, h, "price_list_items", base._csv([
        ["Item Code", "Description", "Rate"],
        ["MV-TYPO", products.coded, "5"],
        [products.plain, "", "6"],
    ]), name="r.csv", target_id=list_id)).json()["data"]
    result = (await base._check(client, h, batch["id"], {"item_code": 0, "description": 1,
                                                          "rate": 2})).json()["data"]
    errors = {e["row"]: e["errors"] for e in result["error_rows"]}
    assert errors[2] == {"item_code": f"'MV-TYPO' is not this product's item code ({products.code})"}
    assert errors[3] == {"item_code": NAME_IN_CODE}


async def test_a_discarded_price_batch_keeps_its_reasons_without_the_cells(
        client: httpx.AsyncClient, imported: base.Fx, products: Products,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 9, EC-1, EC-2: a staff sheet filed as prices; GET still works."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    list_id = await base._draft_list(client, h)
    batch = (await base._upload(client, h, "price_list_items", base._csv([
        ["Mobile", "Employee Name", "Rate"],
        ["9876543210", "Ramesh Patel", "abc"],
        ["", products.plain, "7"],
    ]), name="staff.csv", target_id=list_id)).json()["data"]
    await base._check(client, h, batch["id"], {"item_code": 0, "description": 1, "rate": 2})
    assert (await client.delete(f"{V1}/imports/{batch['id']}", headers={**h, **_key()})).status_code == 204

    got = (await client.get(f"{V1}/imports/{batch['id']}", headers=h))
    assert got.status_code == 200, got.text
    check = got.json()["data"]["check"]
    assert (check["total"], check["ok"], check["errors"]) == (2, 1, 1)
    assert check["preview"] == [] and check["lines"] is None
    assert check["error_rows"][0]["row"] == 2
    assert check["error_rows"][0]["errors"]["item_code"] == "no product with item code '…'"
    s = sessions()
    stored = (await s.execute(text("SELECT check_result::text FROM import_batch WHERE id = CAST(:i AS uuid)"),
                              {"i": batch["id"]})).scalar_one()
    await s.close()
    assert "9876543210" not in stored and "Ramesh" not in stored and products.plain not in stored


async def test_a_discarded_partner_batch_keeps_counts_only(
        client: httpx.AsyncClient, imported: base.Fx) -> None:
    h = await endpoints._as(client, imported.shop, "admin_sales")
    batch = (await base._upload(client, h, "partners", base._partner_sheet(
        imported, uuid.uuid4().hex[:6].upper(), bad_mobile=True))).json()["data"]
    await base._check(client, h, batch["id"], batch["suggested_mapping"])
    await client.delete(f"{V1}/imports/{batch['id']}", headers={**h, **_key()})
    got = await client.get(f"{V1}/imports/{batch['id']}", headers=h)
    assert got.status_code == 200, got.text
    check = got.json()["data"]["check"]
    assert check["total"] == 3 and check["errors"] >= 1
    assert check["error_rows"] == [] and check["preview"] == [] and check["column_warnings"] == {}


async def test_a_committed_partner_batch_keeps_no_preview(
        client: httpx.AsyncClient, imported: base.Fx,
        sessions: Callable[[], AsyncSession]) -> None:
    """Rule 9b: the preview holds mobiles."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    batch = (await base._upload(client, h, "partners", base._partner_sheet(
        imported, uuid.uuid4().hex[:6].upper()))).json()["data"]
    checked = (await base._check(client, h, batch["id"], batch["suggested_mapping"])).json()["data"]
    assert checked["preview"], "the person still sees the preview before saving"
    assert (await base._commit(client, h, batch["id"])).status_code == 200
    s = sessions()
    stored = (await s.execute(text("SELECT check_result FROM import_batch WHERE id = CAST(:i AS uuid)"),
                              {"i": batch["id"]})).scalar_one()
    await s.close()
    assert stored["preview"] == [] and stored["ok"] == 3
    assert "919876543210" not in str(stored)


async def test_a_discarded_mapping_is_not_remembered(
        client: httpx.AsyncClient, imported: base.Fx) -> None:
    """Rule 4a: the 16 Oct mistake must not be suggested back."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    list_id = await base._draft_list(client, h)
    sheet = base._csv([["Naam", "Kimat"], [imported.product_description, "5"]])
    first = (await base._upload(client, h, "price_list_items", sheet, name="r.csv",
                                target_id=list_id)).json()["data"]
    assert first["suggested_mapping"] == {}
    await base._check(client, h, first["id"], {"item_code": 0, "rate": 1})
    await client.delete(f"{V1}/imports/{first['id']}", headers={**h, **_key()})
    second = (await base._upload(client, h, "price_list_items", sheet, name="r.csv",
                                 target_id=list_id)).json()["data"]
    assert second["suggested_mapping"] == {}

    await base._check(client, h, second["id"], {"description": 0, "rate": 1})
    assert (await base._commit(client, h, second["id"])).status_code == 200
    third = (await base._upload(client, h, "price_list_items", sheet, name="r.csv",
                                target_id=list_id)).json()["data"]
    assert third["suggested_mapping"] == {"description": 0}, "a committed one is; never the rate"


async def test_an_empty_rate_is_not_guessed_and_is_warned_about(
        client: httpx.AsyncClient, imported: base.Fx) -> None:
    """Rule 4 and FS-062 EC-16 through the service: the empty columns reach
    `suggest` on upload and GET, and a mapped empty column gets its warning."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    list_id = await base._draft_list(client, h)
    batch = (await base._upload(client, h, "price_list_items", base._csv([
        ["Description", "Rate", "MRP"], [imported.product_description, "", "50"],
    ]), name="r.csv", target_id=list_id)).json()["data"]
    assert batch["suggested_mapping"] == {"description": 0}
    got = (await client.get(f"{V1}/imports/{batch['id']}", headers=h)).json()["data"]
    assert got["suggested_mapping"] == {"description": 0}
    result = (await base._check(client, h, batch["id"], {"description": 0, "rate": 1})).json()["data"]
    assert result["column_warnings"]["rate"].startswith("This column is empty on every row")


async def test_a_line_import_remembers_its_last_check(
        client: httpx.AsyncClient, imported: base.Fx) -> None:
    """Code review F1: a line batch is never committed, so its check is what worked."""
    h = await endpoints._as(client, imported.shop, "admin_sales")
    sheet = base._csv([["Naam", "Ginti"], [imported.product_description, "5"]])
    first = (await base._upload(client, h, "lines", sheet, name="l.csv")).json()["data"]
    assert first["suggested_mapping"] == {}
    assert (await base._check(client, h, first["id"], {"description": 0, "qty": 1})).status_code == 200
    second = (await base._upload(client, h, "lines", sheet, name="l.csv")).json()["data"]
    assert second["suggested_mapping"] == {"description": 0, "qty": 1}
