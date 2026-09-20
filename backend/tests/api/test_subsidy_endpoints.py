"""The subsidy endpoints, end to end (FS-008 section 10, the service and API rows).

The golden tests prove the arithmetic against the workbooks with no database.
These prove the other half: that the masters loaded into PostgreSQL reach the
domain unchanged, that the date in force selects them, that every refusal names
its field, and that the permission gate holds. The Drip sample is run through
the live endpoint and compared against the same workbook cells, so a matrix cell
mistyped by the loader fails here even though the domain tests stay green.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.subsidy import clear_cache
from tests.api.conftest import V1, Admin, _auth

pytestmark = pytest.mark.db

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "subsidy"
D = Decimal


def _fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return data


def _body(name: str) -> dict[str, Any]:
    """The workbook's own quotation, in the request shape."""
    inp = _fixture(name)["inputs"]
    crops = [{"crop": c["crop"], "inter_crop": c["inter_crop"], "area": c["area"],
              "crop_spacing": c["crop_spacing"], "lateral_spacing": c["lateral_spacing"],
              "lines": [{k: ln[k] for k in ("description", "uom", "rate", "qty")}
                        for ln in c.get("lines", [])]}
             for c in inp["crops"]]
    if name == "sprinkler":
        for crop in crops:
            crop["lines"] = []
        return {"system_type": "sprinkler", "crops": crops, "nozzle": inp["nozzle"]}
    return {
        "system_type": inp["system_type"], "crops": crops,
        "head_lines": [{k: ln[k] for k in ("description", "uom", "rate", "qty")}
                       for ln in inp["head_lines"]],
        "sump": {"rate_per_ha": inp["sump"]["rate_per_ha"]},
        "group_total_area": inp["group_total_area"],
        "installation_rate_per_ha": inp["installation_rate_per_ha"],
    }


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    """The service caches the resolved masters for a minute. A test that changes a
    master and then calls the endpoint would otherwise read the previous answer."""
    clear_cache()


@pytest_asyncio.fixture
async def viewer(sessions: Callable[[], AsyncSession], admin: Admin) -> AsyncIterator[Admin]:
    """The API admin fixture's role holds no `subsidy` row; the endpoints are gated
    on `subsidy.view`, so the test grants it explicitly."""
    s = sessions()
    await s.execute(text(
        "INSERT INTO role_permission (role_id, module, action, scope) "
        "VALUES (CAST(:r AS uuid), 'subsidy', 'view', 'global')"), {"r": admin.user.role_id})
    await s.commit()
    yield admin


# ── the Drip sample, through the live endpoint ───────────────────────────────

async def test_the_drip_workbook_reproduces_through_the_endpoint(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """Every rounded cell of `'Quo Summary'!I18:K40`, with the matrices read from
    PostgreSQL rather than from the fixture."""
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate", json=_body("drip"), headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    expected = _fixture("drip")["expected"]

    rows = {"a_plus_b": 20, "cgst_ab": 21, "installation": 23, "total_abc_gst": 26,
            "insurance": 27, "cgst_d": 28, "inspection": 30, "cgst_e": 32, "education": 34,
            "sump": 35, "cost_excl_gst": 36, "total_cgst": 37, "total_gst": 39,
            "total_incl_gst": 40}
    for block, row in rows.items():
        for column, prefix in (("I", "summary.crop1"), ("J", "summary.crop2"),
                               ("K", "summary.total")):
            want = expected[f"{prefix}.{column}{row}"]
            got = (data["total"] if prefix.endswith("total") else
                   data["crops"][0 if prefix.endswith("crop1") else 1])["blocks"][block]
            assert D(got) == D(str(want["value"])).quantize(D("0.01")), f"{prefix} {block}"

    crop = data["crops"][0]
    assert crop["jantri"]["regular"] == "74503.0400"
    assert crop["jantri"]["regular_for_cap"] == "74503.0400"
    assert crop["jantri"]["seven_year"] == "181684.5087"
    assert crop["lateral_spacing_standard"] == "5.00"
    assert crop["lateral_spacing_for_subsidy"] == "5.00"
    assert crop["categories"][0]["subsidy"] == "52152.13"
    assert crop["categories"][0]["farmer_share"] == "157805.43"
    assert data["masters"]["formula_version"] == "ggrc-2026-06-13"
    assert data["sprinkler"] is None


async def test_the_sprinkler_workbook_reproduces_through_the_endpoint(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate", json=_body("sprinkler"), headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["sprinkler"]["pipe_size_mm"] == 75
    assert data["sprinkler"]["dbt_farmer_payable"] == "23106.78"
    assert [ln["amount"] for ln in data["sprinkler"]["lines"]][:3] == \
        ["17493.60", "1957.45", "520.85"]
    assert data["total"]["blocks"]["cost_excl_gst"] == "22206.46"
    assert data["total"]["blocks"]["total_incl_gst"] == "23342.78"
    assert data["crops"][0]["categories"][0]["subsidy"] == "15544.52"


async def test_the_printed_figures_tie_on_every_row(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """SUB-6, on the strings the API actually returns: on a regular row the sump
    comes back, on a 7-year row it does not (the workbook's own formula omits it)."""
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate", json=_body("mini_sprinkler"), headers=h)
    assert r.status_code == 200, r.text
    crop = r.json()["data"]["crops"][0]
    cost, gst = D(crop["blocks"]["cost_excl_gst"]), D(crop["blocks"]["total_gst"])
    sump = D(crop["blocks"]["sump"])
    # The identity alone is true of any four numbers the service derives from each
    # other, so the workbook's own figures are asserted beside it (code review F-1).
    assert (cost, gst) == (D("124236.25"), D("6271.45"))
    first = crop["categories"][0]
    assert (first["subsidy"], first["farmer_share"]) == ("68582.03", "61925.67")
    assert first["gsdma_farmer_share"] == "18695.07"
    for row in crop["categories"]:
        term = sump if row["variant"] == "regular" else D(0)
        assert D(row["subsidy"]) + D(row["farmer_share"]) - gst + term == cost, row["code"]
        if row["variant"] == "regular":
            assert row["gsdma_farmer_share"] is not None, "Mini at 0.8 Ha is inside the window"


# ── the date in force ────────────────────────────────────────────────────────

async def test_a_date_before_the_earliest_matrix_is_not_found(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate", json={**_body("drip"), "as_of": "2020-01-01"},
                          headers=h)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "not_found"


async def test_a_future_date_is_refused(client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    tomorrow = (dt.date.today() + dt.timedelta(days=2)).isoformat()
    r = await client.post(f"{V1}/subsidy/calculate", json={**_body("drip"), "as_of": tomorrow},
                          headers=h)
    assert r.status_code == 422, r.text
    assert "as_of" in r.json()["error"]["fields"]


async def test_the_end_of_a_range_is_exclusive(
        client: httpx.AsyncClient, viewer: Admin, sessions: Callable[[], AsyncSession]) -> None:
    """A calculation dated on a matrix's `effective_to` reads the successor, and one
    dated the day before reads the old figure (SUB-3)."""
    h = await _auth(client, viewer.user)
    # After the load date and before today, since a future `as_of` is refused.
    cut = dt.date(2026, 7, 1)
    s = sessions()
    scheme = (await s.execute(
        text("SELECT id FROM subsidy_scheme WHERE code = 'GGRC'"))).scalar_one()
    old = (await s.execute(text(
        "SELECT id FROM unit_cost_matrix WHERE scheme_id = :s AND system_type = 'drip' "
        "AND variant = 'regular'"), {"s": scheme})).scalar_one()
    await s.execute(text("UPDATE unit_cost_matrix SET effective_to = :c WHERE id = :i"),
                    {"c": cut, "i": old})
    new = (await s.execute(text(
        "INSERT INTO unit_cost_matrix (scheme_id, system_type, variant, dimensionality, "
        "effective_from, source) VALUES (:s, 'drip', 'regular', 2, :c, 'test revision') "
        "RETURNING id"), {"s": scheme, "c": cut})).scalar_one()
    await s.execute(text(
        "INSERT INTO unit_cost_cell (matrix_id, lateral_spacing, area_breakpoint, unit_cost) "
        "SELECT :n, lateral_spacing, area_breakpoint, unit_cost * 2 FROM unit_cost_cell "
        "WHERE matrix_id = :o"), {"n": new, "o": old})
    await s.commit()
    try:
        before = await client.post(f"{V1}/subsidy/calculate",
                                   json={**_body("drip"), "as_of": "2026-06-30"}, headers=h)
        clear_cache()
        on_the_day = await client.post(f"{V1}/subsidy/calculate",
                                       json={**_body("drip"), "as_of": "2026-07-01"}, headers=h)
        assert before.status_code == 200 and on_the_day.status_code == 200
        old_jantri = D(before.json()["data"]["crops"][0]["jantri"]["regular"])
        new_jantri = D(on_the_day.json()["data"]["crops"][0]["jantri"]["regular"])
        assert old_jantri == D("74503.0400")
        assert new_jantri == old_jantri * 2
        assert before.json()["data"]["masters"]["regular_matrix_id"] != \
            on_the_day.json()["data"]["masters"]["regular_matrix_id"]
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM unit_cost_cell WHERE matrix_id = :n"), {"n": new})
        await c.execute(text("DELETE FROM unit_cost_matrix WHERE id = :n"), {"n": new})
        await c.execute(text("UPDATE unit_cost_matrix SET effective_to = NULL WHERE id = :i"),
                        {"i": old})
        await c.commit()
        clear_cache()


# ── the refusals, each naming its field ──────────────────────────────────────

@pytest.mark.parametrize(("patch", "field"), [
    ({"crops": []}, None),
    ({"group_total_area": "1.000"}, "group_total_area"),
    ({"nozzle": "brass"}, "nozzle"),
    ({"crops": [{"crop": "Mangoo", "inter_crop": None, "area": "1.000",
                 "crop_spacing": "", "lateral_spacing": "1.37", "lines": []}]}, "crops[0].crop"),
    ({"crops": [{"crop": "Mango", "inter_crop": None, "area": "1.0005",
                 "crop_spacing": "", "lateral_spacing": "1.37", "lines": []}]}, None),
], ids=["no crops", "group below crops", "nozzle on drip", "unknown crop", "four decimals"])
async def test_every_refusal_is_a_422(client: httpx.AsyncClient, viewer: Admin,
                                      patch: dict[str, Any], field: str | None) -> None:
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate", json={**_body("drip"), **patch}, headers=h)
    assert r.status_code == 422, r.text
    body = r.json()["error"]
    assert body["code"] == "validation_error"
    assert body["message"]
    if field is not None:
        assert field in body["fields"], body["fields"]


async def test_a_crop_name_is_matched_after_trimming(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    body = _body("drip")
    body["crops"][0]["crop"] = "  mango  "
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["crops"][0]["lateral_spacing_standard"] == "5.00"


async def test_an_off_step_sprinkler_area_names_the_steps(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """Rule 18, SUB-4: the workbook returns `#N/A`; the API says which areas exist."""
    h = await _auth(client, viewer.user)
    body = _body("sprinkler")
    body["crops"][0]["area"] = "1.100"
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422, r.text
    message = r.json()["error"]["fields"]["area"]
    assert "0.4" in message and "2.01" in message


async def test_a_sprinkler_request_carrying_lines_is_refused(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    body = _body("sprinkler")
    body["crops"][0]["lines"] = [{"description": "x", "uom": "No.", "rate": "1.00", "qty": "1"}]
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422, r.text
    assert "crops[0].lines" in r.json()["error"]["fields"]


async def test_two_crops_are_refused_for_a_single_crop_system(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    body = _body("mini_sprinkler")
    body["crops"] = body["crops"] * 2
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422, r.text
    assert "crops" in r.json()["error"]["fields"]


# ── the lookups ──────────────────────────────────────────────────────────────

async def test_the_lookups_answer(client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    crops = await client.get(f"{V1}/subsidy/crops", headers=h)
    assert crops.status_code == 200, crops.text
    rows = crops.json()["data"]
    assert len(rows) == 79
    assert {"crop": "Mango", "standard_spacing": "5.00"} in rows

    cats = await client.get(f"{V1}/subsidy/categories?system_type=mini_sprinkler", headers=h)
    assert cats.status_code == 200, cats.text
    assert [c["code"] for c in cats.json()["data"]][:2] == ["small_farmer",
                                                            "darkzone_small_farmer"]
    assert cats.json()["data"][0]["gsdma_pct"] == "10"

    conf = await client.get(f"{V1}/subsidy/config", headers=h)
    assert conf.status_code == 200, conf.text
    data = conf.json()["data"]
    systems = {s["system_type"]: s for s in data["systems"]}
    assert systems["drip"]["crop_count_max"] == 2
    assert systems["sprinkler"]["sprinkler_areas"] is not None
    assert systems["drip"]["sprinkler_areas"] is None
    assert data["parameters"]["education_amount"] == "1000.00"
    assert data["parameters"]["drip.inspection_floor"] == "0.00"
    assert data["parameters"]["mini_sprinkler.inspection_floor"] == "200.00"


async def test_a_warning_carries_its_code_and_a_sentence(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """Every warning is `code: sentence`, at the quotation level and at the crop
    level, so a screen can switch on the code and print the sentence."""
    h = await _auth(client, viewer.user)
    body = _body("drip")
    body["crops"][0]["lateral_spacing"] = "20"
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 200, r.text
    crop = r.json()["data"]["crops"][0]
    seen = {w.split(":", 1)[0]: w for w in crop["warnings"]}
    assert "spacing_outside_table" in seen
    assert "seven_year_spacing_outside_table" in seen, "both tables clamped; both are reported"
    for warning in crop["warnings"]:
        head, _, sentence = warning.partition(":")
        assert sentence.strip(), f"{head} carries no sentence"


async def test_the_prorated_cap_is_returned_not_only_used(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """Below 0.2 Ha the Mini cap is pro-rated, and the pro-rated figure is what the
    scheme's own sheet prints beside the subsidy."""
    h = await _auth(client, viewer.user)
    body = _body("mini_sprinkler")
    body["crops"][0]["area"] = "0.100"
    body["group_total_area"] = "1"
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 200, r.text
    crop = r.json()["data"]["crops"][0]
    assert crop["jantri"]["regular_with_sump"] == "39239.0000"
    assert crop["jantri"]["regular_for_cap"] == "19619.5000"
    assert D(crop["categories"][0]["subsidy"]) == D("19619.5000") * D("0.7")


async def test_an_unknown_scheme_names_the_field(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """Section 4 lists the scheme in the validation list; `not_found` is reserved
    for a master that is not in force on the date (code review F-12)."""
    h = await _auth(client, viewer.user)
    r = await client.post(f"{V1}/subsidy/calculate",
                          json={**_body("drip"), "scheme": "NOPE"}, headers=h)
    assert r.status_code == 422, r.text
    assert "scheme" in r.json()["error"]["fields"]


# ── the gate ─────────────────────────────────────────────────────────────────

async def test_a_caller_without_subsidy_view_is_refused_on_every_endpoint(
        client: httpx.AsyncClient, admin: Admin) -> None:
    """The `admin` fixture, without the `viewer` fixture's grant. Its role holds
    users, leads, partners and masters at global and still gets nothing here."""
    h = await _auth(client, admin.user)
    for method, path in (("post", "/subsidy/calculate"), ("get", "/subsidy/crops"),
                         ("get", "/subsidy/config"),
                         ("get", "/subsidy/categories?system_type=drip")):
        call = getattr(client, method)
        r = await (call(f"{V1}{path}", json=_body("drip"), headers=h) if method == "post"
                   else call(f"{V1}{path}", headers=h))
        assert r.status_code == 403, f"{path}: {r.status_code} {r.text}"
        assert r.json()["error"]["code"] == "insufficient_permission"


async def test_the_endpoints_need_a_token_at_all(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{V1}/subsidy/crops")
    assert r.status_code == 401


async def test_calculate_takes_no_idempotency_key(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    """It is a preview: nothing is stored, so rule 5 does not apply and a client
    that sends one is not punished for it."""
    h = await _auth(client, viewer.user)
    first = await client.post(f"{V1}/subsidy/calculate", json=_body("drip"), headers=h)
    second = await client.post(f"{V1}/subsidy/calculate", json=_body("drip"),
                               headers={**h, "Idempotency-Key": uuid.uuid4().hex})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["data"] == second.json()["data"]


# ── the two checks the product master makes possible (GAP-080) ───────────────

@pytest_asyncio.fixture
async def catalogue_rows(sessions: Callable[[], AsyncSession]) -> AsyncIterator[dict[str, str]]:
    """One product per shape the checks care about: head-unit only, field only,
    and one the scheme does not fund at all."""
    tag = uuid.uuid4().hex[:8]
    s = sessions()
    made: dict[str, str] = {}
    for key, category, eligible in (("head", "head", True), ("field", "field", True),
                                    ("marketing", "both", False)):
        made[key] = str((await s.execute(text(
            "INSERT INTO product (description, product_category_id, quotation_category, uom_id, "
            "  is_subsidy_eligible) "
            "SELECT CAST(:d AS citext), c.id, CAST(:q AS quotation_category), u.id, :e "
            "FROM product_category c, uom u "
            "WHERE c.id = (SELECT id FROM product_category ORDER BY sort_order LIMIT 1) "
            "AND u.id = (SELECT id FROM uom LIMIT 1) RETURNING id"),
            {"d": f"SUBSIDY CHECK {key.upper()} {tag}", "q": category, "e": eligible},
        )).scalar_one())
    await s.commit()
    try:
        yield made
    finally:
        c = sessions()
        await c.execute(text("DELETE FROM product WHERE id = ANY(CAST(:ids AS uuid[]))"),
                        {"ids": list(made.values())})
        await c.commit()


def _with_product(body: dict[str, Any], where: str, product_id: str) -> dict[str, Any]:
    line = dict(body[where][0] if where == "head_lines" else body["crops"][0]["lines"][0])
    line["product_id"] = product_id
    if where == "head_lines":
        return {**body, "head_lines": [line, *body["head_lines"][1:]]}
    crops = [{**body["crops"][0], "lines": [line, *body["crops"][0]["lines"][1:]]},
             *body["crops"][1:]]
    return {**body, "crops": crops}


async def test_a_head_unit_product_is_refused_inside_a_crop_block(
        client: httpx.AsyncClient, viewer: Admin, catalogue_rows: dict[str, str]) -> None:
    """FS-010 rule 2, and the reason the flag exists beside the category: the block
    an item belongs in changes the group cost share, so a head item costed inside
    a crop block asks the scheme to fund the wrong figure."""
    h = await _auth(client, viewer.user)
    body = _with_product(_body("drip"), "crops", catalogue_rows["head"])
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422, r.text
    assert "crops[0].lines[0].product_id" in r.json()["error"]["fields"]


async def test_a_field_product_is_refused_in_the_head_unit(
        client: httpx.AsyncClient, viewer: Admin, catalogue_rows: dict[str, str]) -> None:
    h = await _auth(client, viewer.user)
    body = _with_product(_body("drip"), "head_lines", catalogue_rows["field"])
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422, r.text
    assert "head_lines[0].product_id" in r.json()["error"]["fields"]


async def test_an_item_the_scheme_does_not_fund_is_refused_anywhere(
        client: httpx.AsyncClient, viewer: Admin, catalogue_rows: dict[str, str]) -> None:
    """Executed on the client's file: all fifteen marketing items are marked usable
    in either block, so the category alone would let a company umbrella through the
    head-unit check and the scheme would be asked to fund 70 to 90 % of it."""
    h = await _auth(client, viewer.user)
    for where, path in (("head_lines", "head_lines[0].product_id"),
                        ("crops", "crops[0].lines[0].product_id")):
        body = _with_product(_body("drip"), where, catalogue_rows["marketing"])
        r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
        assert r.status_code == 422, r.text
        assert "not eligible for subsidy" in r.json()["error"]["fields"][path]


async def test_a_product_that_belongs_in_either_block_passes_both(
        client: httpx.AsyncClient, viewer: Admin, catalogue_rows: dict[str, str],
        sessions: Callable[[], AsyncSession]) -> None:
    """`both` is 111 of the client's 1,094 rows, and the check has nothing to say
    about them. A stated limit, not a silent one."""
    s = sessions()
    await s.execute(text(
        "UPDATE product SET is_subsidy_eligible = true, quotation_category = 'both' "
        "WHERE id = CAST(:p AS uuid)"), {"p": catalogue_rows["marketing"]})
    await s.commit()
    h = await _auth(client, viewer.user)
    for where in ("head_lines", "crops"):
        body = _with_product(_body("drip"), where, catalogue_rows["marketing"])
        r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
        assert r.status_code == 200, r.text


async def test_the_rate_still_comes_from_the_request_not_the_catalogue(
        client: httpx.AsyncClient, viewer: Admin, catalogue_rows: dict[str, str]) -> None:
    """A subsidy quotation is costed at the scheme's figures, so naming a product
    must not change a single number. The Drip workbook reproduces either way."""
    h = await _auth(client, viewer.user)
    plain = await client.post(f"{V1}/subsidy/calculate", json=_body("drip"), headers=h)
    named = await client.post(f"{V1}/subsidy/calculate", headers=h,
                              json=_with_product(_body("drip"), "crops",
                                                 catalogue_rows["field"]))
    assert plain.status_code == named.status_code == 200, named.text
    assert plain.json()["data"] == named.json()["data"]


async def test_an_unknown_product_id_names_the_line(
        client: httpx.AsyncClient, viewer: Admin) -> None:
    h = await _auth(client, viewer.user)
    body = _with_product(_body("drip"), "crops", str(uuid.uuid4()))
    r = await client.post(f"{V1}/subsidy/calculate", json=body, headers=h)
    assert r.status_code == 422
    assert "No such product" in r.json()["error"]["fields"]["crops[0].lines[0].product_id"]
