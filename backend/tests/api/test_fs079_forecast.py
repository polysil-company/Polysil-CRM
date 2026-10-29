"""FS-079 over the API: the sales forecast and insights on seeded history, scope,
the staff-only refusals, null-not-zero, and the files. History is written straight
into the database (won and lost leads with their stage events), since building it
through the API would take a year of clicks."""

# ruff: noqa: E501  (inline SQL and bodies)

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.clock import today_ist
from tests.api import test_order_endpoints as endpoints
from tests.api.conftest import V1

pytestmark = pytest.mark.db

shop = endpoints.shop
Shop = endpoints.Shop
Sessions = Callable[[], AsyncSession]
NOW = dt.datetime.now(dt.UTC)


async def _seed(sessions: Sessions, shop: Shop, owner: str, *, stage: str, n: int, created_days_ago: int,
                closed_days_ago: int | None = None, lost_from: str | None = None, reached: tuple[str, ...] = (),
                value: str | None = None, reason: str | None = None, source: str = "employee",
                contacted_after_hours: float | None = None, office: str | None = None) -> list[str]:
    """`n` leads owned by `owner`. Won leads get one stage event per stage in `reached`."""
    s = sessions()
    ids: list[str] = []
    try:
        if stage == "lost" and reason is None:
            reason = str((await s.execute(text("SELECT id FROM won_lost_reason WHERE is_active LIMIT 1"))).scalar_one())
        for _ in range(n):
            created = NOW - dt.timedelta(days=created_days_ago)
            closed = NOW - dt.timedelta(days=closed_days_ago) if closed_days_ago is not None else None
            contacted = created + dt.timedelta(hours=contacted_after_hours) if contacted_after_hours is not None else None
            lead_id = str((await s.execute(text(
                "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, mobile, "
                "  territory_id, owner_user_id, owner_org_unit_id, created_by, estimated_value, stage, created_at, "
                "  won_at, lost_at, lost_from_stage, lost_reason_id, first_contacted_at) "
                "VALUES (:no, 'commercial', (SELECT id FROM mis_system WHERE code = 'drip'), "
                "  (SELECT id FROM lead_source WHERE code = :src), 'Forecast Farmer', :mob, CAST(:t AS uuid), "
                "  CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:o AS uuid), CAST(:v AS numeric), CAST(:stage AS lead_stage), :created, "
                "  :won, :lost, CAST(:lf AS lead_stage), CAST(:reason AS uuid), :contacted) RETURNING id"),
                {"no": f"FC-{uuid.uuid4().hex[:10]}", "mob": "+9196" + f"{uuid.uuid4().int % 10**8:08d}",
                 "t": shop.district, "o": owner, "ou": office or shop.office, "v": value, "stage": stage, "created": created,
                 "won": closed if stage == "won" else None, "lost": closed if stage == "lost" else None,
                 "lf": lost_from, "reason": reason if stage == "lost" else None, "src": source,
                 "contacted": contacted})).scalar_one())
            ids.append(lead_id)
            for to in reached:
                await s.execute(text(
                    "INSERT INTO activity_event (entity_type, entity_id, lead_id, kind, actor_id, payload) "
                    "VALUES ('lead', CAST(:l AS uuid), CAST(:l AS uuid), 'lead.stage_changed', CAST(:o AS uuid), "
                    "CAST(:p AS jsonb))"), {"l": lead_id, "o": owner, "p": f'{{"to": "{to}"}}'})
        await s.commit()
    finally:
        await s.close()
    return ids


async def _history(sessions: Sessions, shop: Shop, owner: str) -> None:
    """12 won from quoted (never negotiated), 18 lost at new: new 40%, quoted 100%."""
    await _seed(sessions, shop, owner, stage="won", n=12, created_days_ago=60, closed_days_ago=20,
                reached=("contacted", "qualified", "quoted", "won"))
    await _seed(sessions, shop, owner, stage="lost", n=18, created_days_ago=50, closed_days_ago=10, lost_from="new")


async def _quote(sessions: Sessions, shop: Shop, lead_id: str, owner: str, total: str, *,
                 status: str = "sent", sent_days_ago: int = 1) -> str:
    """A sent quotation straight in the table, `total` GST included."""
    s = sessions()
    try:
        qid = str((await s.execute(text(
            "INSERT INTO quotation (lead_id, sales_type, owner_user_id, owner_org_unit_id, territory_id, "
            "  party_name, party_mobile, seller_gstin_id, place_of_supply_territory_id, place_of_supply_state_id, "
            "  intra_state, price_effective_date, status, quote_no, version, sent_at, valid_until, share_token, "
            "  seller_legal_name, seller_gstin_no, seller_state_code, pdf_state, total) "
            "VALUES (CAST(:l AS uuid), 'commercial', CAST(:o AS uuid), CAST(:ou AS uuid), CAST(:t AS uuid), "
            "  'Forecast Farmer', '+919800000000', (SELECT id FROM seller_gstin ORDER BY is_default DESC LIMIT 1), "
            "  CAST(:t AS uuid), (SELECT c.ancestor_id FROM territory_closure c JOIN territory x ON x.id = c.ancestor_id "
            "    WHERE c.descendant_id = CAST(:t AS uuid) AND x.level = 'state'), true, CURRENT_DATE, "
            "  CAST(:st AS quotation_status), :no, 1, :sent, CURRENT_DATE + 45, :tok, 'Polysil', '24AAAAA0000A1Z5', "
            "  'GJ', 'pending', CAST(:total AS numeric)) RETURNING id"),
            {"l": lead_id, "o": owner, "ou": shop.office, "t": shop.district, "st": status,
             "no": "QT/FC/" + uuid.uuid4().hex[:8], "sent": NOW - dt.timedelta(days=sent_days_ago),
             "tok": uuid.uuid4().hex, "total": total})).scalar_one())
        await s.commit()
    finally:
        await s.close()
    return qid


async def test_the_forecast_weights_open_leads_by_their_stage(client: httpx.AsyncClient, shop: Shop,
                                                              sessions: Sessions) -> None:
    fo = shop.ids["field_officer"]
    await _history(sessions, shop, fo)
    await _seed(sessions, shop, fo, stage="new", n=1, created_days_ago=2, value="100000")
    await _seed(sessions, shop, fo, stage="quoted", n=1, created_days_ago=2, value="50000")
    await _seed(sessions, shop, fo, stage="contacted", n=1, created_days_ago=2)          # no value
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/reports/sales-forecast", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    rates = {x["stage"]: x for x in data["rates"]}
    assert rates["new"]["win_rate_pct"] == "40.0" and rates["new"]["closed"] == 30
    assert rates["quoted"]["win_rate_pct"] == "100.0"
    assert rates["negotiation"]["low_confidence"] and rates["negotiation"]["closed"] == 0, \
        "no lead negotiated: EC-1, a won lead is not counted as having reached it"
    t = data["totals"]
    assert t["open"] == 3 and t["with_value"] == 2
    assert t["pipeline_value"] == "150000.00" and t["weighted_value"] == "90000.00"
    assert t["valued_by"] == {"quotation": 0, "estimate": 2}
    assert sum(float(v) for v in t["by_month"].values()) == 90000.0, "the months add up to the weighted total"
    assert data["median_days_to_win"] == 40 and data["reason"] is None
    assert data["months"][0] == today_ist().strftime("%Y-%m")
    assert data["filters"]["rates_from"] == "your_whole_scope"


async def test_too_little_history_is_null_never_zero(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """EC-6, rule 6."""
    await _seed(sessions, shop, shop.ids["field_officer"], stage="new", n=2, created_days_ago=1, value="1000")
    h = await endpoints._as(client, shop, "field_officer")
    data = (await client.get(f"{V1}/reports/sales-forecast", headers=h)).json()["data"]
    assert data["reason"] == "not_enough_history" and data["rates"] == []
    assert data["totals"]["weighted_value"] is None and data["totals"]["pipeline_value"] == "2000.00"
    assert all(v is None for v in data["totals"]["by_month"].values())


async def test_a_field_officer_never_counts_the_managers_leads(client: httpx.AsyncClient, shop: Shop,
                                                                sessions: Sessions) -> None:
    """The negative scope case: the manager's open lead stays out of the officer's
    pipeline and out of the officer's rates."""
    fo, dm = shop.ids["field_officer"], shop.ids["district_manager"]
    await _history(sessions, shop, dm)
    await _seed(sessions, shop, dm, stage="new", n=1, created_days_ago=1, value="777777")
    h = await endpoints._as(client, shop, "field_officer")
    data = (await client.get(f"{V1}/reports/sales-forecast", headers=h)).json()["data"]
    assert data["totals"]["open"] == 0 and data["rates"] == []
    m = await endpoints._as(client, shop, "district_manager")
    mine = (await client.get(f"{V1}/reports/sales-forecast", headers=m)).json()["data"]
    assert mine["totals"]["pipeline_value"] == "777777.00" and fo != dm


async def test_the_owner_filter_chooses_rows_not_rates(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Plan review S-6: rates come from the whole scope."""
    dm = shop.ids["district_manager"]
    await _history(sessions, shop, shop.ids["field_officer"])
    h = await endpoints._as(client, shop, "district_manager")
    whole = (await client.get(f"{V1}/reports/sales-forecast", headers=h)).json()["data"]["rates"]
    one = (await client.get(f"{V1}/reports/sales-forecast", headers=h, params={"owner_id": dm})).json()["data"]["rates"]
    assert whole == one and whole


async def test_both_reports_are_for_staff(client: httpx.AsyncClient, shop: Shop, sessions: Sessions) -> None:
    """Plan review S-9: a dealer gets 403 on both."""
    from tests.api import test_complaints as complaints_t
    dealer, _ = await complaints_t._dealer(client, shop, sessions)
    for name in ("sales-forecast", "insights"):
        r = await client.get(f"{V1}/reports/{name}", headers=dealer)
        assert r.status_code == 403, (name, r.text)


async def test_history_days_is_bounded(client: httpx.AsyncClient, shop: Shop) -> None:
    h = await endpoints._as(client, shop, "district_manager")
    for bad in (89, 366):
        r = await client.get(f"{V1}/reports/sales-forecast", headers=h, params={"history_days": bad})
        assert r.status_code == 422, (bad, r.text)


async def test_insights_name_the_rising_reason_and_the_drop_off_stage(client: httpx.AsyncClient, shop: Shop,
                                                                      sessions: Sessions) -> None:
    fo = shop.ids["field_officer"]
    s = sessions()
    reasons = [str(x) for x in (await s.execute(text(
        "SELECT id FROM won_lost_reason WHERE is_active ORDER BY name LIMIT 2"))).scalars().all()]
    await s.close()
    assert len(reasons) == 2
    # this period: 12 for reason A at quoted; the 30 days before: 2 for A, 10 for B
    await _seed(sessions, shop, fo, stage="lost", n=12, created_days_ago=20, closed_days_ago=5,
                lost_from="quoted", reason=reasons[0])
    await _seed(sessions, shop, fo, stage="lost", n=2, created_days_ago=50, closed_days_ago=40,
                lost_from="new", reason=reasons[0])
    await _seed(sessions, shop, fo, stage="lost", n=10, created_days_ago=50, closed_days_ago=40,
                lost_from="new", reason=reasons[1])
    await _seed(sessions, shop, fo, stage="new", n=10, created_days_ago=3, contacted_after_hours=5)
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/reports/insights", headers=h)
    assert r.status_code == 200, r.text
    rows = {x["code"]: x for x in r.json()["data"]["rows"]}
    assert rows["lost_reason_rising"]["figure"] == "100.0" and rows["lost_reason_rising"]["previous"] == "16.7"
    assert rows["drop_off_stage"]["title"] == "Most lost leads were lost at Quoted: 100.0% of them."
    assert "first_contact_speed" in rows and "5.0 hours" in rows["first_contact_speed"]["title"]
    assert "—" not in str(rows), "no em dashes"
    f = r.json()["data"]["filters"]
    start, end = dt.date.fromisoformat(f["from"]), dt.date.fromisoformat(f["to"])
    p_start, p_end = dt.date.fromisoformat(f["previous_from"]), dt.date.fromisoformat(f["previous_to"])
    assert p_end == start - dt.timedelta(days=1), "the periods touch (code review F-4)"
    assert (p_end - p_start) == (end - start), "and are the same length"
    # every link opens its report (code review F-1)
    for row in rows.values():
        if row["link"]:
            params = {k: v for k, v in row["link"].items() if k != "report"}
            linked = await client.get(f"{V1}/reports/{row['link']['report']}", headers=h, params=params)
            assert linked.status_code == 200, (row["code"], linked.text)


async def test_both_reports_export(client: httpx.AsyncClient, shop: Shop, sessions: Sessions,
                                   monkeypatch: pytest.MonkeyPatch) -> None:
    import csv
    import io

    from api.services import report_pdf
    monkeypatch.setattr(report_pdf, "get_settings", lambda: type("S", (), {"pdf_renderer": "html"})())
    await _history(sessions, shop, shop.ids["field_officer"])
    await _seed(sessions, shop, shop.ids["field_officer"], stage="new", n=1, created_days_ago=2, value="100000")
    h = await endpoints._as(client, shop, "field_officer")
    r = await client.get(f"{V1}/reports/sales-forecast", headers=h, params={"format": "csv"})
    assert r.status_code == 200, r.text
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8").lstrip("﻿"))))
    assert rows[0][:5] == ["Owner", "Open leads", "With a value", "Pipeline value", "Weighted value"]
    total = next(x for x in rows if x[0] == "Total")
    assert total[3] == "100000.00" and total[4] == "40000.00"
    r = await client.get(f"{V1}/reports/sales-forecast", headers=h, params={"format": "pdf"})
    assert r.status_code == 200 and "Sales forecast" in r.text and "Win rates from leads closed in the last 180 days" in r.text
    r = await client.get(f"{V1}/reports/insights", headers=h, params={"format": "csv"})
    assert r.status_code == 200, r.text
    lines = list(csv.reader(io.StringIO(r.content.decode("utf-8").lstrip("﻿"))))
    assert lines[0] == ["Insight", "Figure", "Previous", "Unit"]
    assert not any(x and x[0] == "Total" for x in lines), "sentences have no Total (code review F-5)"


async def test_the_cohort_and_value_queries_use_their_indexes(sessions: Sessions) -> None:
    """Rule 13a: uncast enums keep the partial indexes usable (plan review S-3)."""
    s = sessions()
    try:
        # a small table lets the planner pick any index; these settings leave only
        # the question that matters: can the partial index be used at all
        await s.execute(text("SET LOCAL enable_seqscan = off"))
        await s.execute(text("SET LOCAL enable_sort = off"))
        plan = "\n".join(r[0] for r in (await s.execute(text(
            "EXPLAIN SELECT id FROM lead WHERE stage = 'lost' AND lost_at >= now() - interval '180 days'"))).all())
        assert "ix_lead_lost_at" in plan, plan
        plan = "\n".join(r[0] for r in (await s.execute(text(
            "EXPLAIN SELECT total FROM quotation WHERE lead_id = '00000000-0000-4000-8000-000000000000' AND superseded_by_id IS NULL "
            "AND deleted_at IS NULL AND status IN ('sent', 'viewed', 'negotiation') "
            "ORDER BY sent_at DESC NULLS LAST, id DESC LIMIT 1"))).all())
        assert "ix_quotation_live_value" in plan, plan
    finally:
        await s.rollback()
        await s.close()


async def test_a_live_quotation_values_the_lead_and_a_merged_leads_counts(client: httpx.AsyncClient, shop: Shop,
                                                                          sessions: Sessions) -> None:
    """Rule 8: the newest live quotation wins over the estimate, a merged lead's
    quotation counts for its winner, and a rejected one does not."""
    fo = shop.ids["field_officer"]
    await _history(sessions, shop, fo)
    (a,) = await _seed(sessions, shop, fo, stage="quoted", n=1, created_days_ago=3, value="10000")
    await _quote(sessions, shop, a, fo, "20000.00", sent_days_ago=3)
    await _quote(sessions, shop, a, fo, "30000.00", sent_days_ago=1)                 # newest: this one
    (b,) = await _seed(sessions, shop, fo, stage="quoted", n=1, created_days_ago=3)   # no estimate
    (loser,) = await _seed(sessions, shop, fo, stage="quoted", n=1, created_days_ago=4)
    await _quote(sessions, shop, loser, fo, "45000.00")
    (c,) = await _seed(sessions, shop, fo, stage="quoted", n=1, created_days_ago=3, value="5000")
    await _quote(sessions, shop, c, fo, "99000.00", status="rejected")             # not live: the estimate
    s = sessions()
    try:
        await s.execute(text("UPDATE lead SET stage = 'merged', merged_into_id = CAST(:b AS uuid) "
                             "WHERE id = CAST(:l AS uuid)"), {"b": b, "l": loser})
        await s.commit()
    finally:
        await s.close()
    h = await endpoints._as(client, shop, "field_officer")
    t = (await client.get(f"{V1}/reports/sales-forecast", headers=h)).json()["data"]["totals"]
    assert t["open"] == 3, "the merged lead is not open"
    assert t["pipeline_value"] == "80000.00", "30000 newest + 45000 from the merged lead + 5000 estimate"
    assert t["valued_by"] == {"quotation": 2, "estimate": 1}


async def test_a_quotation_the_caller_cannot_see_never_values_their_lead(client: httpx.AsyncClient, shop: Shop,
                                                                         sessions: Sessions) -> None:
    """EC-18, code review F-2: the officer sees their lead, not the manager's
    quotation on it, so the lead is valued by its estimate."""
    fo, dm = shop.ids["field_officer"], shop.ids["district_manager"]
    await _history(sessions, shop, fo)
    (lead,) = await _seed(sessions, shop, fo, stage="quoted", n=1, created_days_ago=2, value="1000")
    await _quote(sessions, shop, lead, dm, "500000.00")
    h = await endpoints._as(client, shop, "field_officer")
    t = (await client.get(f"{V1}/reports/sales-forecast", headers=h)).json()["data"]["totals"]
    assert t["pipeline_value"] == "1000.00" and t["valued_by"] == {"quotation": 0, "estimate": 1}
    m = await endpoints._as(client, shop, "district_manager")
    t = (await client.get(f"{V1}/reports/sales-forecast", headers=m)).json()["data"]["totals"]
    assert t["pipeline_value"] == "500000.00", "the manager sees both, so the quotation counts"


async def test_a_manager_never_counts_another_offices_leads(client: httpx.AsyncClient, shop: Shop,
                                                             sessions: Sessions) -> None:
    """Code review F-2: org_subtree scope. A lead of a sibling office stays out of
    the pipeline and out of the rates."""
    s = sessions()
    other = str((await s.execute(text(
        "INSERT INTO org_unit (name, role_level, territory_id) VALUES (:n, 2, CAST(:t AS uuid)) RETURNING id"),
        {"n": f"fc_other_{uuid.uuid4().hex[:8]}", "t": shop.district})).scalar_one())
    await s.commit()
    await s.close()
    fo = shop.ids["field_officer"]
    ids: list[str] = []
    try:
        ids += await _seed(sessions, shop, fo, stage="new", n=1, created_days_ago=1, value="424242", office=other)
        ids += await _seed(sessions, shop, fo, stage="won", n=12, created_days_ago=60, closed_days_ago=20,
                           reached=("contacted",), office=other)
        ids += await _seed(sessions, shop, fo, stage="lost", n=18, created_days_ago=50, closed_days_ago=10,
                           lost_from="new", office=other)
        m = await endpoints._as(client, shop, "district_manager")
        data = (await client.get(f"{V1}/reports/sales-forecast", headers=m)).json()["data"]
        assert data["totals"]["open"] == 0 and data["rates"] == []
    finally:
        s = sessions()
        await s.execute(text("DELETE FROM activity_event WHERE lead_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
        await s.execute(text("DELETE FROM lead WHERE id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
        await s.execute(text("DELETE FROM org_unit WHERE id = CAST(:o AS uuid)"), {"o": other})
        await s.commit()
        await s.close()
