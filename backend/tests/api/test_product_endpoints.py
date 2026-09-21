"""The ten product, tax and pricing endpoints, end to end (FS-010 section 10).

The domain tests prove the arithmetic with no database. These prove the other
half: that a price resolves from the masters actually in PostgreSQL, that the two
dated facts close their predecessors, that every refusal names its field, and
that the permission gate holds.

**The fixtures build their own masters rather than using the loaded catalogue.**
`scripts/load_product_master.py` publishes an open-ended base list from
2026-04-01, so a test list would either collide with it through the very
constraint being proved, or quietly read its rates instead of its own. Everything
here lives in a closed window in 2020 and quotes against a date inside it, which
also exercises the explicit `seller_gstin_id` path.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.conftest import V1, Admin, _auth, _key

pytestmark = pytest.mark.db

D = Decimal
AS_OF = "2020-06-01"


@dataclass
class Catalogue:
    """One product, classified and taxed, priced in a list of this test's own."""

    product_id: str
    description: str
    category: str
    uom: str
    gstin_id: str
    gujarat_district_id: str
    price_list_id: str
    rate: str


@pytest_asyncio.fixture
async def trader(sessions: Callable[[], AsyncSession], admin: Admin) -> AsyncIterator[Admin]:
    """The API admin's role carries no `products` or `pricing` row; every endpoint
    here is gated on one, so the test grants all four explicitly."""
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) VALUES "
        "(:r, 'products', 'view', 'global'), (:r, 'products', 'edit', 'global'), "
        "(:r, 'pricing', 'view', 'global'), (:r, 'pricing', 'edit', 'global')"),
        {"r": admin.user.role_id})
    await s.commit()
    yield admin


def _gstin() -> str:
    """A registration number of this test's own.

    `ck_seller_gstin_format` is two digits, five letters, four digits, a letter,
    then three alphanumerics, and `gstin` is uniquely indexed. Varying one
    character of a hex tag gives sixteen possible numbers, so a file with thirty
    tests collides with itself - and one of the sixteen is the seeded
    registration, which collides on the first run.
    """
    alnum = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    n = uuid.uuid4().int
    tail = "".join(alnum[(n >> (6 * i)) % 36] for i in range(3))
    return f"24AAAAA{n % 9000 + 1000:04d}A{tail}"


@pytest_asyncio.fixture
async def catalogue(sessions: Callable[[], AsyncSession]) -> AsyncIterator[Catalogue]:
    tag = uuid.uuid4().hex[:8]
    description = f"TEST PIPE {tag}"
    s = sessions()
    category = (await s.execute(text(
        "SELECT code::text FROM product_category ORDER BY sort_order LIMIT 1"))).scalar_one()
    uom = (await s.execute(text(
        "SELECT code::text FROM uom WHERE decimals = 0 LIMIT 1"))).scalar_one()
    product = str((await s.execute(text(
        "INSERT INTO product (description, product_category_id, quotation_category, uom_id, "
        "  provisional_fields) "
        "SELECT CAST(:d AS citext), c.id, 'field', u.id, ARRAY['gst_slab','mrp']::text[] "
        "FROM product_category c, uom u "
        "WHERE c.code = CAST(:c AS citext) AND u.code = CAST(:u AS citext) RETURNING id"),
        {"d": description, "c": category, "u": uom})).scalar_one())
    await s.execute(text(
        "INSERT INTO product_hsn (product_id, hsn_code, effective_from) "
        "VALUES (CAST(:p AS uuid), '3917', DATE '2019-01-01')"), {"p": product})
    # 3917 already carries a rate from 2026-04-01; this one covers the test window
    # and closes before it, so the two never overlap.
    await s.execute(text(
        "INSERT INTO gst_rate (hsn_code, rate, effective_from, effective_to) "
        "VALUES ('3917', 5, DATE '2019-01-01', DATE '2021-01-01')"))
    # A second registration, not the default: the unique index allows only one
    # default, and the seeded one does not start until 2026.
    gstin = str((await s.execute(text(
        "INSERT INTO seller_gstin (gstin, legal_name, state_territory_id, effective_from, "
        "  effective_to) "
        "SELECT CAST(:g AS citext), 'Polysil Test', t.id, DATE '2019-01-01', DATE '2021-01-01' "
        "FROM territory t WHERE t.level = 'state' AND t.code = 'GJ' RETURNING id"),
        {"g": _gstin()})).scalar_one())
    district = str((await s.execute(text(
        "SELECT d.id FROM territory d JOIN territory s ON s.id = d.parent_id "
        "WHERE s.level = 'state' AND s.code = 'GJ' AND d.level = 'district' LIMIT 1"
    ))).scalar_one())
    price_list = str((await s.execute(text(
        "INSERT INTO price_list (name, channel_tier, status, published_at, effective_from, "
        "  effective_to, is_provisional) "
        "VALUES (:n, 'farmer', 'published', now(), DATE '2020-01-01', DATE '2021-01-01', true) "
        "RETURNING id"), {"n": f"test list {tag}"})).scalar_one())
    await s.execute(text(
        "INSERT INTO price_list_item (price_list_id, product_id, rate) "
        "VALUES (CAST(:l AS uuid), CAST(:p AS uuid), 103.19)"),
        {"l": price_list, "p": product})
    await s.commit()

    try:
        yield Catalogue(product, description, category, uom, gstin, district, price_list,
                        "103.19")
    finally:
        c = sessions()
        for stmt in (
            "DELETE FROM price_list_item WHERE product_id = CAST(:p AS uuid)",
            "DELETE FROM price_list WHERE id = CAST(:l AS uuid)",
            "DELETE FROM product_hsn WHERE product_id = CAST(:p AS uuid)",
            "DELETE FROM gst_rate WHERE hsn_code = '3917' AND effective_to = DATE '2021-01-01'",
            "DELETE FROM seller_gstin WHERE id = CAST(:g AS uuid)",
            "DELETE FROM product WHERE id = CAST(:p AS uuid)",
        ):
            await c.execute(text(stmt), {"p": product, "l": price_list, "g": gstin})
        await c.commit()


_SLOT = itertools.count()


def _window() -> dict[str, str]:
    """A published list's scope and dates have to be this run's own.

    A published row survives the request that made it, so a hardcoded window
    collides with itself on the next run: the second publish finds the first as an
    overlapping predecessor starting on the same day and refuses. The admin
    fixture's teardown does clear these, but a test that only passes because
    cleanup worked is a test with a second way to fail.
    """
    year = 1900 + next(_SLOT) + (uuid.uuid4().int % 90)
    return {"effective_from": f"{year}-01-01", "effective_to": f"{year}-07-01"}


def _quote(cat: Catalogue, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "as_of": AS_OF,
        "place_of_supply_territory_id": cat.gujarat_district_id,
        "seller_gstin_id": cat.gstin_id,
        "lines": [{"product_id": cat.product_id, "qty": "18"}],
    }
    body.update(over)
    return body


# ── the catalogue ────────────────────────────────────────────────────────────

async def test_the_picker_lists_products_with_the_tax_in_force_on_the_date(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.get(f"{V1}/products", params={"q": catalogue.description,
                                                   "as_of": AS_OF}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["total"] == 1
    row = body["data"][0]
    assert row["description"] == catalogue.description
    assert row["hsn_code"] == "3917"
    assert row["gst_slab"] == "5.000"
    assert row["uom"] == catalogue.uom
    assert row["provisional_fields"] == ["gst_slab", "mrp"]


async def test_a_date_with_no_classification_returns_the_row_without_one(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """Not an error and not a missing row: the product exists, its tariff heading
    started later. A picker must still show it."""
    h = await _auth(client, trader.user)
    r = await client.get(f"{V1}/products", params={"q": catalogue.description,
                                                   "as_of": "2018-01-01"}, headers=h)
    row = r.json()["data"][0]
    assert row["hsn_code"] is None and row["gst_slab"] is None


async def test_the_search_treats_an_underscore_as_an_underscore(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """`_` is a single-character wildcard in LIKE. Unescaped, a search for `A_B`
    matches `AxB`, which is a picker showing the wrong product."""
    h = await _auth(client, trader.user)
    pattern = catalogue.description.replace(" ", "_")
    r = await client.get(f"{V1}/products", params={"q": pattern}, headers=h)
    assert r.json()["meta"]["total"] == 0


async def test_creating_a_product_and_replaying_the_key(
        client: httpx.AsyncClient, trader: Admin) -> None:
    h = await _auth(client, trader.user)
    category = (await client.get(f"{V1}/products", params={"limit": 1},
                                 headers=h)).json()["data"][0]["product_category"]
    uom = (await client.get(f"{V1}/products", params={"limit": 1},
                            headers=h)).json()["data"][0]["uom"]
    body = {"description": f"NEW PRODUCT {uuid.uuid4().hex[:8]}",
            "product_category": category, "quotation_category": "field", "uom": uom}
    key = _key()

    first = await client.post(f"{V1}/products", json=body, headers={**h, **key})
    assert first.status_code == 201, first.text
    created = first.json()["data"]
    assert created["provisional_fields"] == [], "a figure an administrator typed is not a stand-in"

    again = await client.post(f"{V1}/products", json=body, headers={**h, **key})
    assert again.status_code == 201
    assert again.json()["data"]["id"] == created["id"], "replayed, not created twice"

    duplicate = await client.post(f"{V1}/products", json=body, headers={**h, **_key()})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "duplicate_description"


async def test_an_unknown_category_is_a_422_and_creates_nothing(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """Never created implicitly: a typo would become a category of one in every
    picker."""
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/products", headers={**h, **_key()},
                          json={"description": "GHOST PRODUCT", "product_category": "NO SUCH",
                                "quotation_category": "field", "uom": "NOS."})
    assert r.status_code == 422
    assert "product_category" in r.json()["error"]["fields"]


async def test_a_patch_clears_only_the_field_it_sets(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """Rev 1 had one boolean over four, so setting a pack multiple would have
    marked a guessed tax slab as confirmed."""
    h = await _auth(client, trader.user)
    r = await client.patch(f"{V1}/products/{catalogue.product_id}", json={"mrp": "250.00"},
                           headers={**h, **_key()})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["provisional_fields"] == ["gst_slab"], "mrp confirmed, slab untouched"
    assert r.json()["data"]["mrp"] == "250.00"


# ── the two dated facts ──────────────────────────────────────────────────────

async def test_classifying_a_product_closes_the_previous_row_and_confirms_the_slab(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.put(f"{V1}/products/{catalogue.product_id}/hsn",
                         json={"hsn_code": "3926", "effective_from": "2020-07-01"},
                         headers={**h, **_key()})
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert [row["hsn_code"] for row in rows] == ["3926", "3917"], "newest first"
    assert rows[1]["effective_to"] == "2020-07-01", "the predecessor is closed, exclusive"
    assert rows[0]["effective_to"] is None

    product = (await client.get(f"{V1}/products/{catalogue.product_id}",
                                headers=h)).json()["data"]
    assert "hsn_code" not in product["provisional_fields"]


async def test_classifying_on_the_same_day_is_a_409_naming_the_remedy(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """Closing a row at its own start leaves a range in force for no day at all,
    and every past document that cited it can no longer explain itself."""
    h = await _auth(client, trader.user)
    r = await client.put(f"{V1}/products/{catalogue.product_id}/hsn",
                         json={"hsn_code": "3926", "effective_from": "2019-01-01"},
                         headers={**h, **_key()})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "hsn_same_start_date"
    assert "later date" in r.json()["error"]["message"]


async def test_a_rate_outside_the_slabs_in_force_is_refused(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """A new slab is a Council decision and arrives as a migration, deliberately:
    it is a legal event and should not be one data entry away."""
    h = await _auth(client, trader.user)
    r = await client.put(f"{V1}/tax-rates/3917", json={"rate": "7.000",
                                                       "effective_from": "2030-01-01"},
                         headers={**h, **_key()})
    assert r.status_code == 422
    assert "rate" in r.json()["error"]["fields"]


async def test_the_tax_rate_list_reads_for_any_signed_in_principal(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.get(f"{V1}/tax-rates", params={"hsn_code": "3917"}, headers=h)
    assert r.status_code == 200
    assert {row["hsn_code"] for row in r.json()["data"]} == {"3917"}
    assert all(D(row["rate"]) in (D("5"), D("12"), D("18")) for row in r.json()["data"])


# ── price lists ──────────────────────────────────────────────────────────────

async def test_a_draft_is_filled_then_published_and_refuses_what_it_should(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """The whole sequence, and the refusal that matters most: publishing a list
    that does not price every active product would, on the day it starts, leave
    every other product falling through or refusing to price."""
    h = await _auth(client, trader.user)
    created = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                                json={"name": f"draft {uuid.uuid4().hex[:6]}",
                                      "channel_tier": "sub_dealer", **_window()})
    assert created.status_code == 201, created.text
    list_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "draft"
    assert created.json()["data"]["is_provisional"] is False, "only the loader marks a list"

    filled = await client.put(f"{V1}/price-lists/{list_id}/items", headers={**h, **_key()},
                              json={"items": [{"product_id": catalogue.product_id,
                                               "rate": "99.50"}]})
    assert filled.status_code == 200, filled.text
    assert filled.json()["unpriced"] > 0, "one rate in a catalogue of many"

    refused = await client.post(f"{V1}/price-lists/{list_id}/publish", headers={**h, **_key()},
                                json={"allow_unpriced": False})
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "price_list_unpriced"

    published = await client.post(f"{V1}/price-lists/{list_id}/publish", headers={**h, **_key()},
                                  json={"allow_unpriced": True})
    assert published.status_code == 200, published.text
    assert published.json()["data"]["price_list"]["status"] == "published"
    assert published.json()["data"]["closed_predecessor_id"] is None

    frozen = await client.put(f"{V1}/price-lists/{list_id}/items", headers={**h, **_key()},
                              json={"items": [{"product_id": catalogue.product_id,
                                               "rate": "1.00"}]})
    assert frozen.status_code == 409
    assert frozen.json()["error"]["code"] == "price_list_published"
    # No cleanup call here. There is no DELETE route for a price list (GAP-100),
    # and the line that used to sit here asked for one and never checked the
    # answer - a cleanup that read as if it worked and did nothing. The admin
    # fixture's teardown removes what this test created.


async def test_a_rate_with_three_decimals_is_refused_not_rounded(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """It is the client's number and we may not quietly change it."""
    h = await _auth(client, trader.user)
    created = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                                json={"name": f"draft {uuid.uuid4().hex[:6]}",
                                      "channel_tier": "sub_dealer",
                                      "effective_from": "2020-01-01"})
    list_id = created.json()["data"]["id"]
    r = await client.put(f"{V1}/price-lists/{list_id}/items", headers={**h, **_key()},
                         json={"items": [{"product_id": catalogue.product_id,
                                          "rate": "99.505"}]})
    assert r.status_code == 422
    assert "rate" in str(r.json()["error"]["fields"])


async def test_a_price_list_is_scoped_to_a_state_not_a_district(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                          json={"name": "district list", "effective_from": "2020-01-01",
                                "state_territory_id": catalogue.gujarat_district_id})
    assert r.status_code == 422
    assert "district" in r.json()["error"]["fields"]["state_territory_id"]


async def test_closing_a_list_is_forward_only(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """Closing a list retrospectively changes what past documents were priced
    from, which is the one thing effective dating exists to prevent."""
    h = await _auth(client, trader.user)
    created = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                                json={"name": f"draft {uuid.uuid4().hex[:6]}",
                                      "channel_tier": "sub_dealer",
                                      "effective_from": "2020-01-01"})
    list_id = created.json()["data"]["id"]
    for date in ("2019-01-01", "2020-06-01"):
        r = await client.patch(f"{V1}/price-lists/{list_id}", json={"effective_to": date},
                               headers={**h, **_key()})
        assert r.status_code == 422, date
        assert r.json()["error"]["code"] == "effective_to_not_forward"


# ── the preview ──────────────────────────────────────────────────────────────

async def test_an_intra_state_quotation_splits_the_tax_and_reports_every_figure(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """Gujarat to Gujarat. 103.19 x 18 = 1857.42 at 5 %, which is 46.44 of CGST
    and the same again of SGST, exactly as the client's workbook computes it."""
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", json=_quote(catalogue), headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["intra_state"] is True
    assert data["seller_state"] == "GJ" and data["place_of_supply_state"] == "GJ"
    assert data["price_list_ids"] == [catalogue.price_list_id]

    line = data["lines"][0]
    assert line["rate"] == "103.19" and line["qty"] == "18"
    assert line["gross"] == "1857.42"
    assert line["discount"] == "0.00" and line["taxable"] == "1857.42"
    assert line["hsn_code"] == "3917" and line["gst_slab"] == "5.000"
    assert line["cgst_rate"] == "2.500" and line["sgst_rate"] == "2.500"
    assert line["cgst"] == line["sgst"] == "46.44"
    assert line["igst"] == "0.00" and line["igst_rate"] == "0.000"
    assert line["total"] == "1950.30"
    assert line["price_list_item_id"] and line["gst_rate_id"], "FS-005 re-resolves against these"
    assert set(line["provisional_fields"]) == {"rate", "gst_slab"}

    assert data["totals"]["total"] == "1950.30"
    assert any(w.startswith("provisional_pricing:") for w in data["warnings"])


async def test_an_inter_state_quotation_charges_igst_at_the_full_slab(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """The place of supply is the ship-to, resolved up to its state. Sending the
    admin's own district, which is under another state, makes this inter-state -
    and the IGST is a paisa less than the two halves, which is correct under
    per-component rounding."""
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=h, json=_quote(
        catalogue, place_of_supply_territory_id=trader.territory_id))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["intra_state"] is False
    assert data["place_of_supply_state"] == trader.state_code

    line = data["lines"][0]
    assert line["igst_rate"] == "5.000" and line["igst"] == "92.87"
    assert line["cgst"] == line["sgst"] == "0.00"
    assert D(line["igst"]) == D("92.87") < D("46.44") * 2


async def test_a_quantity_the_unit_does_not_admit_is_a_422_naming_the_line(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=h, json=_quote(
        catalogue, lines=[{"product_id": catalogue.product_id, "qty": "1.5"}]))
    assert r.status_code == 422, r.text
    assert "lines[0].qty" in r.json()["error"]["fields"]


async def test_a_date_with_no_price_in_force_names_the_product_and_the_date(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=h,
                          json=_quote(catalogue, as_of="2019-06-01"))
    assert r.status_code in (404, 422), r.text
    if r.status_code == 422:
        assert r.json()["error"]["code"] in ("product_not_priced", "product_missing_tax_rate")


async def test_a_price_date_more_than_a_year_ahead_is_refused(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", headers=h,
                          json=_quote(catalogue, as_of="2099-01-01"))
    assert r.status_code == 422
    assert "as_of" in r.json()["error"]["fields"]


async def test_a_place_of_supply_with_no_state_above_it_is_refused(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """For goods the place of supply decides which tax applies, so a territory
    that resolves to no state cannot be priced against."""
    s = sessions()
    orphan = str((await s.execute(text(
        "INSERT INTO territory (level, name) VALUES ('district', :n) RETURNING id"),
        {"n": f"orphan_{uuid.uuid4().hex[:8]}"})).scalar_one())
    await s.commit()
    try:
        h = await _auth(client, trader.user)
        r = await client.post(f"{V1}/pricing/quote-lines", headers=h, json=_quote(
            catalogue, place_of_supply_territory_id=orphan))
        assert r.status_code == 422
        assert "place_of_supply_territory_id" in r.json()["error"]["fields"]
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM territory WHERE id = CAST(:t AS uuid)"), {"t": orphan})
        await c.commit()


# ── the gate ─────────────────────────────────────────────────────────────────

async def test_reading_needs_products_view_and_writing_needs_products_edit(
        client: httpx.AsyncClient, admin: Admin, catalogue: Catalogue) -> None:
    """`admin` without the `trader` fixture holds neither row, so both refuse.
    ADR-039: the endpoint gate is the primary enforcer and RLS is the second."""
    h = await _auth(client, admin.user)
    assert (await client.get(f"{V1}/products", headers=h)).status_code == 403
    assert (await client.post(f"{V1}/pricing/quote-lines", json=_quote(catalogue),
                              headers=h)).status_code == 403


async def test_a_mutation_without_an_idempotency_key_is_a_400(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    h = await _auth(client, trader.user)
    r = await client.patch(f"{V1}/products/{catalogue.product_id}", json={"mrp": "1.00"},
                           headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "idempotency_key_required"


async def test_the_preview_takes_no_idempotency_key(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """Nothing is stored, for the same reason `POST /subsidy/calculate` takes
    none."""
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", json=_quote(catalogue), headers=h)
    assert r.status_code == 200


async def test_a_dated_write_fills_the_gap_between_two_existing_rows(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """A revision dated between two rows already on file used to insert
    open-ended, overlap the later one, and hand the caller a raw exclusion
    violation as a 500. The gap between them is a perfectly good window.

    The loader had this exact shape and a cross-vendor review found it there. The
    same shape was in the two endpoints that write a dated fact, and nothing
    caught it, because every other test writes the newest row.
    """
    s = sessions()
    hsn = "8" + uuid.uuid4().int.__str__()[:3]
    await s.execute(text(
        "INSERT INTO gst_rate (hsn_code, rate, effective_from, effective_to) VALUES "
        "(:h, 5, DATE '2019-01-01', DATE '2020-01-01'), (:h, 18, DATE '2021-01-01', NULL)"),
        {"h": hsn})
    await s.commit()
    try:
        h = await _auth(client, trader.user)
        r = await client.put(f"{V1}/tax-rates/{hsn}", headers={**h, **_key()},
                             json={"rate": "12.000", "effective_from": "2020-06-01"})
        assert r.status_code == 200, r.text
        rows = {row["effective_from"]: row for row in r.json()["data"]}
        assert rows["2020-06-01"]["effective_to"] == "2021-01-01", "bounded by the next revision"
        assert rows["2020-06-01"]["rate"] == "12.000"
        assert rows["2021-01-01"]["effective_to"] is None, "the later row is untouched"
        assert rows["2019-01-01"]["effective_to"] == "2020-01-01", "and so is the earlier one"
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM gst_rate WHERE hsn_code = :h"), {"h": hsn})
        await c.commit()


async def test_a_classification_dated_before_a_later_one_is_bounded_too(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue,
        sessions: Callable[[], AsyncSession]) -> None:
    """The same fix on the other dated fact."""
    s = sessions()
    # The fixture's classification runs from 2019 with no end, so close it first:
    # this test is about a write landing between two rows, not about overlapping one.
    await s.execute(text(
        "UPDATE product_hsn SET effective_to = DATE '2022-01-01' "
        "WHERE product_id = CAST(:p AS uuid) AND effective_to IS NULL"),
        {"p": catalogue.product_id})
    await s.execute(text(
        "INSERT INTO product_hsn (product_id, hsn_code, effective_from) "
        "VALUES (CAST(:p AS uuid), '8424', DATE '2022-01-01')"), {"p": catalogue.product_id})
    await s.commit()

    h = await _auth(client, trader.user)
    r = await client.put(f"{V1}/products/{catalogue.product_id}/hsn", headers={**h, **_key()},
                         json={"hsn_code": "3926", "effective_from": "2020-06-01"})
    assert r.status_code == 200, r.text
    rows = {row["effective_from"]: row for row in r.json()["data"]}
    assert rows["2020-06-01"]["effective_to"] == "2022-01-01"
    assert rows["2022-01-01"]["effective_to"] is None


async def test_a_product_no_longer_sold_is_refused_on_a_new_line(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """The mechanism a review named as deletable with the suite staying green.

    Every other test here quotes an active product, so the `is_active` refusal in
    `quote_lines` was never executed: deleting it, or inverting it, left all
    twenty-three tests passing. A discontinued product could be quoted to a farmer
    and nothing would have noticed.
    """
    h = await _auth(client, trader.user)
    priced = await client.post(f"{V1}/pricing/quote-lines", json=_quote(catalogue), headers=h)
    assert priced.status_code == 200, "active first, so the refusal below is the only change"

    off = await client.patch(f"{V1}/products/{catalogue.product_id}", json={"is_active": False},
                             headers={**h, **_key()})
    assert off.status_code == 200, off.text

    r = await client.post(f"{V1}/pricing/quote-lines", json=_quote(catalogue), headers=h)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "product_inactive"
    assert "no longer sold" in r.json()["error"]["fields"]["lines[0].product_id"]


async def test_a_bounded_list_that_would_strand_the_scope_is_refused(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """Publishing closes the predecessor at this list's start, which discards
    everything the predecessor covered after this list ends.

    Executed before the fix: a list covering June and July, published over one
    running from January with no end, left September with no list in force at all,
    and every quotation dated after it refused to price a scope that had worked
    the day before. Two sequential, individually valid admin actions.
    """
    h = await _auth(client, trader.user)
    year = _window()["effective_from"][:4]

    async def make(**body: object) -> str:
        r = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                              json={"name": f"L {uuid.uuid4().hex[:6]}",
                                    "channel_tier": "distributor", **body})
        assert r.status_code == 201, r.text
        return str(r.json()["data"]["id"])

    open_ended = await make(effective_from=f"{year}-01-01")
    published = await client.post(f"{V1}/price-lists/{open_ended}/publish",
                                  headers={**h, **_key()}, json={"allow_unpriced": True})
    assert published.status_code == 200, published.text

    bounded = await make(effective_from=f"{year}-06-01", effective_to=f"{year}-08-01")
    r = await client.post(f"{V1}/price-lists/{bounded}/publish", headers={**h, **_key()},
                          json={"allow_unpriced": True})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "price_list_gap"
    assert f"{year}-08-01" in r.json()["error"]["message"]


async def test_a_second_item_code_is_a_409_naming_it(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """The one duplicate the contract promises that no test exercised."""
    h = await _auth(client, trader.user)
    sample = (await client.get(f"{V1}/products", params={"limit": 1}, headers=h)).json()["data"][0]
    code = f"IC-{uuid.uuid4().hex[:8]}"
    body = {"product_category": sample["product_category"], "quotation_category": "field",
            "uom": sample["uom"], "item_code": code}

    first = await client.post(f"{V1}/products", headers={**h, **_key()},
                              json={**body, "description": f"ITEM ONE {uuid.uuid4().hex[:8]}"})
    assert first.status_code == 201, first.text
    second = await client.post(f"{V1}/products", headers={**h, **_key()},
                               json={**body, "description": f"ITEM TWO {uuid.uuid4().hex[:8]}"})
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "duplicate_item_code"


async def test_a_list_may_not_be_created_as_provisional(
        client: httpx.AsyncClient, trader: Admin) -> None:
    """Only the loader marks a list as carrying stand-in rates. The field was
    accepted from any caller holding `pricing.edit`, so a genuine list could be
    marked a stand-in and every quotation drawn from it would carry a warning
    telling the user not to send it."""
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/price-lists", headers={**h, **_key()},
                          json={"name": "marked", "channel_tier": "sub_dealer",
                                "is_provisional": True, **_window()})
    assert r.status_code == 422, r.text
    assert "is_provisional" in str(r.json()["error"]["fields"])


async def test_a_tax_rate_is_reported_at_the_precision_its_column_carries(
        client: httpx.AsyncClient, trader: Admin, catalogue: Catalogue) -> None:
    """Half of the 0.25 per cent slab is 0.125, and two decimals renders that as
    0.13: a line would print two halves summing to 0.26 against a slab of 0.25.
    The engine keeps the halved rate exact and the display layer was rounding it
    away again."""
    h = await _auth(client, trader.user)
    r = await client.post(f"{V1}/pricing/quote-lines", json=_quote(catalogue), headers=h)
    line = r.json()["data"]["lines"][0]
    assert line["gst_slab"] == "5.000"
    assert line["cgst_rate"] == line["sgst_rate"] == "2.500"
    assert D(line["cgst_rate"]) + D(line["sgst_rate"]) == D(line["gst_slab"])
