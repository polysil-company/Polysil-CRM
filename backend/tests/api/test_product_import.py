# ruff: noqa: E501  (embedded SQL and sheet data)

"""FS-083: the product import, through the endpoints.

Built on the order endpoints' `shop`: its staff, and one product with an HSN that
has a GST rate. Products the import creates carry the shop admin's `created_by`
and are removed by `catalogue` before the shop's teardown.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.errors import ForbiddenError
from api.services import imports as service
from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1
from tests.api.test_imports import _check, _commit, _upload, _xlsx
from tests.api.test_order_endpoints import Shop
from tests.api.test_order_partners import _as_dealer

pytestmark = pytest.mark.db

shop = endpoints.shop
__all__ = ["shop"]

HEADERS = ["Item Code", "Product Description", "Product Category", "Quotation Category", "Unit",
           "HSN", "MRP", "Active"]


@dataclass
class Cat:
    shop: Shop
    tag: str
    product: str          # the shop's product description
    hsn: str              # its HSN, which has a rate today
    category: str
    unit: str


@pytest_asyncio.fixture
async def catalogue(shop: Shop, sessions: Callable[[], AsyncSession]) -> AsyncIterator[Cat]:
    s = sessions()
    row = (await s.execute(text(
        "SELECT p.description::text, h.hsn_code, c.code::text, u.code::text FROM product p "
        "JOIN product_hsn h ON h.product_id = p.id JOIN product_category c ON c.id = p.product_category_id "
        "JOIN uom u ON u.id = p.uom_id WHERE p.id = CAST(:p AS uuid)"), {"p": shop.product})).one()
    await s.close()
    try:
        yield Cat(shop, uuid.uuid4().hex[:6].upper(), row[0], row[1], row[2], row[3])
    finally:
        c = sessions()
        people = list(shop.ids.values())
        for stmt in (
            "DELETE FROM import_batch WHERE created_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM product_hsn h USING product p WHERE p.id = h.product_id "
            "AND p.created_by = ANY(CAST(:p AS uuid[]))",
            "DELETE FROM product WHERE created_by = ANY(CAST(:p AS uuid[]))",
            # rows the import added to the shop's own product
            "DELETE FROM product_hsn WHERE product_id = CAST(:own AS uuid) "
            "AND created_by = ANY(CAST(:p AS uuid[]))",
            "UPDATE product_hsn SET effective_to = NULL, updated_by = NULL WHERE product_id = CAST(:own AS uuid)",
            "UPDATE product SET is_active = true, mrp = NULL, updated_by = NULL "
            "WHERE id = CAST(:own AS uuid)",
        ):
            await c.execute(text(stmt), {"p": people, "own": shop.product})
        await c.commit()
        await c.close()


def _sheet(*rows: list[object]) -> bytes:
    return _xlsx([["Product Master List"], [], HEADERS, *[list(r) for r in rows]])


async def _checked(client: httpx.AsyncClient, h: dict[str, str], data: bytes) -> tuple[str, dict]:
    r = await _upload(client, h, "products", data)
    assert r.status_code == 201, r.text
    batch = r.json()["data"]
    assert batch["header_row"] == 3, "the client's title rows are skipped"
    r = await _check(client, h, batch["id"], batch["suggested_mapping"])
    assert r.status_code == 200, r.text
    return batch["id"], r.json()["data"]


async def test_new_and_changed_products_check_then_commit(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    cat = catalogue
    h = await endpoints._as(client, cat.shop, "admin_sales")
    new_name = f"IMPORT PIPE {cat.tag}"
    batch, result = await _checked(client, h, _sheet(
        [f"IMP-{cat.tag}", new_name + "  ", cat.category, "Field", cat.unit, cat.hsn, "120.5", ""],
        ["", cat.product.lower(), "", "", "", "", "99", "no"],
        ["", f"IMPORT BARE {cat.tag}", cat.category, "head", cat.unit, "", "", ""],
    ))
    assert result["errors"] == 0, result["error_rows"]
    assert len(result["products"].pop("fingerprint")) == 64
    assert result["products"] == {"new": 2, "update": 1, "unchanged": 0, "renamed": 0,
                                  "switched_off": 1, "switched_on": 0, "hsn_changed": 0,
                                  "still_off": 0}
    first = result["preview"][0]["values"]
    assert first["action"] == "update", "a switch-off comes first"
    assert first["changes"]["is_active"] == {"from": True, "to": False}
    assert first["changes"]["mrp"] == {"from": None, "to": "99.00"}
    assert "no HSN code" in result["column_warnings"]["hsn_code"]
    assert "no rate yet" in result["column_warnings"]["description"]

    s = sessions()
    assert (await s.execute(text("SELECT count(*) FROM product WHERE description = CAST(:d AS citext)"),
                            {"d": new_name})).scalar_one() == 0, "a check saves nothing"
    await s.close()

    r = await _commit(client, h, batch)
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"status": "committed", "created": 2, "skipped": 0,
                                "price_list_id": None, "updated": 1, "unchanged": 0}

    s = sessions()
    made = (await s.execute(text(
        "SELECT p.item_code::text, p.mrp, p.is_subsidy_eligible, p.is_active, p.created_by::text, "
        "  (SELECT hsn_code FROM product_hsn WHERE product_id = p.id), "
        "  (SELECT effective_from FROM product_hsn WHERE product_id = p.id) "
        "FROM product p WHERE p.description = CAST(:d AS citext)"), {"d": new_name})).one()
    assert made[0] == f"IMP-{cat.tag}" and str(made[1]) == "120.50" and made[2] and made[3]
    assert made[4] == cat.shop.ids["admin_sales"]
    assert made[5] == cat.hsn and made[6] == today_ist()
    own = (await s.execute(text(
        "SELECT mrp, is_active, updated_by::text, description::text FROM product WHERE id = CAST(:p AS uuid)"),
        {"p": cat.shop.product})).one()
    assert str(own[0]) == "99.00" and own[1] is False and own[2] == cat.shop.ids["admin_sales"]
    assert own[3] == cat.product, "a description match keeps the catalogue's spelling"
    await s.close()

    again = await _commit(client, h, batch)
    assert again.status_code == 409 and again.json()["error"]["code"] == "import_wrong_state"


async def test_a_new_hsn_closes_the_one_in_force_today(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    cat = catalogue
    s = sessions()
    other = f"39{uuid.uuid4().int % 10**6:06d}"
    await s.execute(text("INSERT INTO gst_rate (hsn_code, rate, effective_from) VALUES (:h, 18, DATE '2019-01-01')"),
                    {"h": other})
    await s.commit()
    await s.close()
    try:
        h = await endpoints._as(client, cat.shop, "admin_sales")
        batch, result = await _checked(client, h, _sheet(["", cat.product, "", "", "", other, "", ""]))
        assert result["products"]["hsn_changed"] == 1, result
        assert (await _commit(client, h, batch)).status_code == 200
        s = sessions()
        rows = (await s.execute(text(
            "SELECT hsn_code, effective_from, effective_to FROM product_hsn "
            "WHERE product_id = CAST(:p AS uuid) ORDER BY effective_from"), {"p": cat.shop.product})).all()
        assert [(r[0], r[2]) for r in rows] == [(cat.hsn, today_ist()), (other, None)]
        assert rows[1][1] == today_ist()
        await s.close()

        # set today already: the next import refuses, rather than an empty range
        _, result = await _checked(client, h, _sheet(["", cat.product, "", "", "", cat.hsn, "", ""]))
        assert "set today already" in result["error_rows"][0]["errors"]["hsn_code"]
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM product_hsn WHERE hsn_code = :h"), {"h": other})
        await s.execute(text("DELETE FROM gst_rate WHERE hsn_code = :h"), {"h": other})
        await s.commit()
        await s.close()


async def test_a_deleted_products_name_is_an_error_row_never_a_500(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """EC-2: the unique index still holds a deleted product's description."""
    cat = catalogue
    s = sessions()
    gone = f"IMPORT GONE {cat.tag}"
    await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id, created_by, deleted_at) "
        "SELECT CAST(:d AS citext), product_category_id, 'field', uom_id, CAST(:u AS uuid), now() "
        "FROM product WHERE id = CAST(:p AS uuid)"),
        {"d": gone, "u": cat.shop.ids["admin_sales"], "p": cat.shop.product})
    await s.commit()
    await s.close()
    h = await endpoints._as(client, cat.shop, "admin_sales")
    batch, result = await _checked(client, h, _sheet(["", gone, cat.category, "field", cat.unit, "", "", ""]))
    assert result["error_rows"][0]["errors"] == {"description": "a deleted product has this description"}
    r = await _commit(client, h, batch)
    assert r.status_code == 422 and r.json()["error"]["code"] == "import_has_errors"


async def test_a_similar_new_name_is_flagged(client: httpx.AsyncClient, catalogue: Cat) -> None:
    """EC-5: the client's sheet has no item codes, so a spelling fix arrives as new."""
    cat = catalogue
    h = await endpoints._as(client, cat.shop, "admin_sales")
    near = cat.product[:-1] + ("X" if cat.product[-1] != "X" else "Y")
    _, result = await _checked(client, h, _sheet(["", near, cat.category, "field", cat.unit, "", "", ""]))
    row = result["preview"][0]["values"]
    assert row["action"] == "new" and row["near"] == cat.product, row
    assert "close to an existing name" in result["column_warnings"]["description"]


async def test_an_edit_between_check_and_commit_means_check_again(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """EC-11: the product page changed the MRP the file states, so saving would undo it."""
    cat = catalogue
    h = await endpoints._as(client, cat.shop, "admin_sales")
    s = sessions()
    await s.execute(text("UPDATE product SET mrp = 50 WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    batch, result = await _checked(client, h, _sheet(["", cat.product, "", "", "", "", "50", ""]))
    assert result["products"]["unchanged"] == 1
    await s.execute(text("UPDATE product SET mrp = 70 WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    r = await _commit(client, h, batch)
    assert r.status_code == 409 and r.json()["error"]["code"] == "import_wrong_state", r.text
    mrp = (await s.execute(text("SELECT mrp FROM product WHERE id = CAST(:p AS uuid)"),
                           {"p": cat.shop.product})).scalar_one()
    assert str(mrp) == "70.00", "the edit survives"
    await s.execute(text("UPDATE product SET mrp = NULL WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    await s.close()


async def test_who_may_import_products(client: httpx.AsyncClient, catalogue: Cat,
                                       sessions: Callable[[], AsyncSession]) -> None:
    cat = catalogue
    dm = await endpoints._as(client, cat.shop, "district_manager")
    r = await _upload(client, dm, "products", _sheet(["", cat.product, "", "", "", "", "1", ""]))
    assert r.status_code == 403, r.text
    r = await client.get(f"{V1}/imports/template", headers=dm, params={"kind": "products"})
    assert r.status_code == 403
    admin = await endpoints._as(client, cat.shop, "admin_sales")
    r = await client.get(f"{V1}/imports/template", headers=admin, params={"kind": "products"})
    assert r.status_code == 200 and r.headers["content-disposition"].endswith('product-import-template.xlsx"')
    r = await _upload(client, admin, "products", _sheet(["", cat.product, "", "", "", "", "1", ""]),
                      target_id=str(uuid.uuid4()))
    assert r.status_code == 422, r.text

    s, caller = await _as_dealer(sessions, cat.shop)
    try:
        with pytest.raises(ForbiddenError):
            await service.upload(s, caller, kind="products", target_id=None, file_name="x.csv",
                                 data=b"description\nA\n", sha256="0" * 64, sheet=None,
                                 header_row=None)
    finally:
        await s.rollback()
        await s.close()


async def test_stand_ins_are_confirmed_per_field_without_a_new_hsn_row(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """Rule 10, EC-10, plan review N-3: the HSN restated clears its marks and
    writes no row; MRP set clears its own mark; nothing else is touched."""
    cat = catalogue
    s = sessions()
    await s.execute(text("UPDATE product SET provisional_fields = '{hsn_code,gst_slab,mrp,pack_multiple}' "
                         "WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    try:
        h = await endpoints._as(client, cat.shop, "admin_sales")
        batch, result = await _checked(client, h, _sheet(["", cat.product, "", "", "", cat.hsn, "15", ""]))
        changes = result["preview"][0]["values"]["changes"]
        assert changes["hsn_code"]["confirmed"] is True and "confirmed" not in changes["mrp"]
        assert result["products"]["hsn_changed"] == 0
        assert (await _commit(client, h, batch)).status_code == 200
        row = (await s.execute(text(
            "SELECT provisional_fields, mrp, (SELECT count(*) FROM product_hsn WHERE product_id = p.id) "
            "FROM product p WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})).one()
        assert list(row[0]) == ["pack_multiple"] and str(row[1]) == "15.00" and row[2] == 1
    finally:
        await s.execute(text("UPDATE product SET provisional_fields = '{}' WHERE id = CAST(:p AS uuid)"),
                        {"p": cat.shop.product})
        await s.commit()
        await s.close()


async def test_a_product_moved_into_marketing_is_not_subsidy_eligible(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """EC-15, FS-010 rule 2."""
    cat = catalogue
    h = await endpoints._as(client, cat.shop, "admin_sales")
    batch, _ = await _checked(client, h, _sheet([f"MKT-{cat.tag}", f"IMPORT UMBRELLA {cat.tag}", cat.category,
                                                  "both", cat.unit, "", "", ""]))
    assert (await _commit(client, h, batch)).status_code == 200
    batch, result = await _checked(client, h, _sheet([f"MKT-{cat.tag}", "", "Marketing", "", "", "", "", ""]))
    assert result["preview"][0]["values"]["changes"]["is_subsidy_eligible"] == {"from": True, "to": False}
    assert (await _commit(client, h, batch)).status_code == 200
    s = sessions()
    eligible = (await s.execute(text("SELECT is_subsidy_eligible FROM product WHERE item_code = CAST(:c AS citext)"),
                                {"c": f"MKT-{cat.tag}"})).scalar_one()
    await s.close()
    assert eligible is False


async def test_an_edit_to_a_field_the_file_changes_means_check_again(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """Plan review N-2: the counts stay the same, but the preview said "from 100"."""
    cat = catalogue
    h = await endpoints._as(client, cat.shop, "admin_sales")
    s = sessions()
    await s.execute(text("UPDATE product SET mrp = 100 WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    batch, result = await _checked(client, h, _sheet(["", cat.product, "", "", "", "", "120", ""]))
    assert result["preview"][0]["values"]["changes"]["mrp"]["from"] == "100.00"
    await s.execute(text("UPDATE product SET mrp = 110 WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    r = await _commit(client, h, batch)
    assert r.status_code == 409, r.text
    assert str((await s.execute(text("SELECT mrp FROM product WHERE id = CAST(:p AS uuid)"),
                                {"p": cat.shop.product})).scalar_one()) == "110.00"
    await s.close()


async def test_a_role_with_products_view_only_may_not_import(client: httpx.AsyncClient, catalogue: Cat) -> None:
    """Plan review N-7: the negative case for a staff role."""
    cat = catalogue
    sm = await endpoints._as(client, cat.shop, "state_manager")
    r = await _upload(client, sm, "products", _sheet(["", cat.product, "", "", "", "", "1", ""]))
    assert r.status_code == 403, r.text
    r = await client.get(f"{V1}/imports/template", headers=sm, params={"kind": "products"})
    assert r.status_code == 403


async def test_a_clear_that_misses_leaves_the_stand_in_marks_as_they_were(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-3: MRP set on a product whose MRP is not a stand-in leaves its
    other marks alone, in their order, so the audit row shows no change to them."""
    cat = catalogue
    s = sessions()
    await s.execute(text("UPDATE product SET provisional_fields = '{hsn_code,gst_slab,pack_multiple}' "
                         "WHERE id = CAST(:p AS uuid)"), {"p": cat.shop.product})
    await s.commit()
    try:
        h = await endpoints._as(client, cat.shop, "admin_sales")
        batch, _ = await _checked(client, h, _sheet(["", cat.product, "", "", "", "", "17", ""]))
        assert (await _commit(client, h, batch)).status_code == 200
        marks = (await s.execute(text("SELECT provisional_fields FROM product WHERE id = CAST(:p AS uuid)"),
                                 {"p": cat.shop.product})).scalar_one()
        assert list(marks) == ["hsn_code", "gst_slab", "pack_multiple"]
    finally:
        await s.execute(text("UPDATE product SET provisional_fields = '{}' WHERE id = CAST(:p AS uuid)"),
                        {"p": cat.shop.product})
        await s.commit()
        await s.close()


async def test_the_commit_and_the_product_page_wait_for_the_catalogue_lock(
        client: httpx.AsyncClient, catalogue: Cat, sessions: Callable[[], AsyncSession]) -> None:
    """Code review F-1 and F-2: the commit, PATCH /products/{id} and the loader take
    one lock (api/db/locks.py), so a commit never writes over an edit it did not read."""
    import asyncio
    import inspect

    from api.db import locks
    from scripts.load_product_master import Loader

    assert "locks.PRODUCT_CATALOGUE" in inspect.getsource(Loader.lock), "the loader takes the same key"
    cat = catalogue
    h = await endpoints._as(client, cat.shop, "admin_sales")
    batch, _ = await _checked(client, h, _sheet(["", cat.product, "", "", "", "", "19", ""]))
    holder = sessions()
    await holder.execute(text(locks.PRODUCT_CATALOGUE))
    try:
        commit = asyncio.ensure_future(_commit(client, h, batch))
        patch = asyncio.ensure_future(client.patch(
            f"{V1}/products/{cat.shop.product}", json={"mrp": "21.00"},
            headers={**h, "Idempotency-Key": str(uuid.uuid4())}))
        done, _ = await asyncio.wait({commit, patch}, timeout=1.5)
        assert not done, "a commit or an edit ran while the catalogue lock was held"
    finally:
        await holder.rollback()
        await holder.close()
    assert (await patch).status_code == 200
    # Either order is safe. The edit first: the commit sees a changed catalogue and
    # asks for a fresh check. The commit first: the edit lands after it. The edit
    # is never written over.
    saved = await commit
    assert saved.status_code == 200 or saved.json()["error"]["code"] == "import_wrong_state", saved.text
    s = sessions()
    mrp = (await s.execute(text("SELECT mrp FROM product WHERE id = CAST(:p AS uuid)"),
                           {"p": cat.shop.product})).scalar_one()
    await s.close()
    assert str(mrp) == "21.00", "the product page's edit was lost"
