"""FS-085's script: the workbook the client marks, the two deploy steps, and the
read-only facts query against the dev database."""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import io
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.domain import district_offices as do
from scripts import load_district_offices as script

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import deploy_staging

ROOT = Path(__file__).resolve().parents[1]


def _facts() -> list[do.Fact]:
    def f(uid: str, role: str, kind: str, st: str = "", d: str = "", n: int = 1) -> do.Fact:
        return do.Fact(uid, uid.title(), f"{uid}@x.in", role, 1, False, "hq-id", "Polysil HQ",
                       kind, st, d, n, 3)
    return [f("ravi", "field_officer", "user_territory", "GJ", "Rajkot"),
            f("asha", "district_manager", "user_territory", "GJ", "Morbi"),
            f("asha", "district_manager", "user_territory", "GJ", "Rajkot"),
            f("none", "field_officer", "none")]


def test_the_workbook_round_trip(tmp_path: Path) -> None:
    people, groups = do.suggest(_facts(), ("GJ",))
    listed = {"GJ": [do.ListedDistrict("Rajkot"), do.ListedDistrict("Morbi")]}
    out = tmp_path / "placement.xlsx"
    script.write_sheet(out, people, groups, listed, ("GJ",))

    wb = load_workbook(out)
    ws = wb["People"]
    assert [c.value for c in ws[1]] == script.PEOPLE
    assert ws.column_dimensions["I"].hidden and wb["Offices"].sheet_state == "hidden"
    first = [c.value for c in ws[2]]
    assert first[0] == "None" and first[4] == do.NONE, "the rows needing a decision come first"
    offices = [r[0].value for r in wb["Offices"].iter_rows()]
    assert offices[:3] == ["OK", "Polysil HQ", "Gujarat State"]
    assert "Rajkot District, GJ" in offices and groups[0].name in offices
    rule = ws.data_validations.dataValidation[0]
    assert rule.errorStyle == "warning" and "H2" in str(rule.sqref)

    # the client marks it: OK for Ravi and the area, another office for Asha
    rows = {ws.cell(r, 1).value: r for r in range(2, ws.max_row + 1)}
    ws.cell(rows["Ravi"], 8).value = "OK"
    ws.cell(rows["Asha"], 8).value = "Gujarat State"
    wb["Groups"].cell(2, 6).value = "Yes"
    wb["Groups"].cell(2, 2).value = "Morbi Rajkot Area, GJ"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    approved, decisions = script.read_sheet(buf)
    assert [(g.kind, g.name, g.state, g.members) for g in approved] == [
        ("area", "Morbi Rajkot Area, GJ", "GJ", ("Morbi", "Rajkot"))]
    assert {d.full_name: d.office_name for d in decisions} == {
        "Ravi": "Rajkot District, GJ", "Asha": "Gujarat State"}, "blank rows ask for nothing"
    assert all(d.current_office_id == "hq-id" and d.user_id for d in decisions)


def test_ok_with_nothing_suggested_is_refused(tmp_path: Path) -> None:
    people, groups = do.suggest(_facts(), ("GJ",))
    out = tmp_path / "p.xlsx"
    script.write_sheet(out, people, groups, {"GJ": [do.ListedDistrict("Rajkot")]}, ("GJ",))
    wb = load_workbook(out)
    wb["People"].cell(2, 8).value = "OK"     # the "none" row: no suggestion
    wb.save(out)
    with pytest.raises(SystemExit, match="nothing was suggested"):
        script.read_sheet(out)


def test_the_list_must_cover_every_loaded_state(tmp_path: Path) -> None:
    f = tmp_path / "d.csv"
    f.write_text("state_code,district,lgd_code\nGJ,Rajkot,457\n", encoding="utf-8")
    assert [d.name for d in script.read_districts(f, ("GJ",))["GJ"]] == ["Rajkot"]
    with pytest.raises(SystemExit, match="MH"):
        script.read_districts(f, ("GJ", "MH"))


# ── the deploy steps ─────────────────────────────────────────────────────────

ENV = {"PG_CONTAINER": "pg", "PG_SUPERUSER": "su", "DB_NAME": "db", "REMOTE_DIR": "/srv/p",
       "SSH_KEY_PATH": "k", "SSH_USER": "u", "SSH_HOST": "h", "DB_PASSWORD": "x"}


def test_staff_facts_runs_the_query_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(env: dict[str, str], command: str, **kw: Any) -> Any:
        seen.update(command=command, stdin=kw["stdin"].decode())
        return type("R", (), {"returncode": 0, "stdout": b"user_id,kind\nu,none\n", "stderr": b""})()
    monkeypatch.setattr(deploy_staging, "run_remote", fake)
    out = tmp_path / "facts.csv"
    deploy_staging.staff_facts(ENV, out)
    assert "default_transaction_read_only=on" in seen["command"]
    sql = seen["stdin"]
    assert sql.index("BEGIN TRANSACTION READ ONLY") < sql.index("COPY (") < sql.index("ROLLBACK")
    assert "TO STDOUT WITH CSV HEADER" in sql and "-- " not in sql, "comments are stripped"
    assert out.read_text() == "user_id,kind\nu,none\n"


def test_district_offices_sends_the_sheet_on_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake(env: dict[str, str], command: str, **kw: Any) -> Any:
        seen.update(command=command, stdin=kw["stdin"])
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr(deploy_staging, "run_remote", fake)
    monkeypatch.setattr(deploy_staging, "guard", lambda env: None)
    sheet = tmp_path / "s.xlsx"
    sheet.write_bytes(b"workbook")
    deploy_staging.district_offices(ENV, sheet=sheet, dry_run=True, actor=None, all_districts=False)
    cmd = seen["command"]
    assert " -T tools " in cmd and "--sheet -" in cmd and cmd.endswith("--dry-run")
    assert seen["stdin"] == b"workbook", "the client's sheet never lands on the box's disk"
    assert "--as" not in cmd, "ADMIN_EMAIL on the box is the default actor"


# ── the facts query on Postgres ──────────────────────────────────────────────

@pytest.mark.db
async def test_the_facts_query_reports_each_kind_of_evidence(sessions: Callable[[], AsyncSession]) -> None:
    s = sessions()
    tx = await s.begin()
    try:
        tag = uuid.uuid4().hex[:6]
        st = str((await s.execute(text(
            "INSERT INTO territory (level, name, code) VALUES ('state', :n, :c) RETURNING id"),
            {"n": f"fs85f_{tag}", "c": "F" + tag[:4].upper()})).scalar())
        dist = str((await s.execute(text(
            "INSERT INTO territory (level, name, parent_id) VALUES ('district', :n, CAST(:p AS uuid)) RETURNING id"),
            {"n": f"fs85f_d_{tag}", "p": st})).scalar())
        village = str((await s.execute(text(
            "INSERT INTO territory (level, name, parent_id) VALUES ('taluka', :n, CAST(:p AS uuid)) RETURNING id"),
            {"n": f"fs85f_t_{tag}", "p": dist})).scalar())
        uid = str((await s.execute(text(
            "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
            "SELECT 'staff', :e, 'Facts Person', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer' RETURNING id"),
            {"e": f"fs85f_{tag}@polysil.in", "o": "73f0fdc5-8adb-50e6-b1b9-04005fe9e2ea"})).scalar())
        idle = str((await s.execute(text(
            "INSERT INTO app_user (user_type, email, full_name, role_id, org_unit_id) "
            "SELECT 'staff', :e, 'Idle Person', r.id, CAST(:o AS uuid) FROM role r WHERE r.code = 'field_officer' RETURNING id"),
            {"e": f"fs85f_idle_{tag}@polysil.in", "o": "73f0fdc5-8adb-50e6-b1b9-04005fe9e2ea"})).scalar())
        await s.execute(text("INSERT INTO user_territory (user_id, territory_id) VALUES (CAST(:u AS uuid), CAST(:t AS uuid))"),
                        {"u": uid, "t": dist})
        await s.execute(text(
            "INSERT INTO channel_partner (partner_type, code, name, territory_id, price_tier, created_by) "
            "VALUES ('dealer', :c, 'Facts Dealer', CAST(:t AS uuid), 'dealer', CAST(:u AS uuid))"),
            {"c": f"F85F-{tag}", "t": village, "u": uid})
        await s.execute(text(
            "INSERT INTO lead (inquiry_no, inquiry_type, mis_system_id, lead_source_id, farmer_name, mobile, "
            "territory_id, owner_org_unit_id, owner_user_id) VALUES (:no, 'commercial', (SELECT id FROM mis_system LIMIT 1), "
            "(SELECT id FROM lead_source LIMIT 1), 'F', '+919000000002', CAST(:t AS uuid), CAST(:o AS uuid), CAST(:u AS uuid))"),
            {"no": f"F85F-{tag}", "t": village, "o": "73f0fdc5-8adb-50e6-b1b9-04005fe9e2ea", "u": uid})
        sql = (ROOT / "scripts" / "sql" / "staff_area_facts.sql").read_text(encoding="utf-8")
        rows = [dict(r._mapping) for r in (await s.execute(text(sql))).all()
                if str(r.user_id) in (uid, idle)]
        mine = {r["kind"]: r for r in rows if str(r["user_id"]) == uid}
        assert set(mine) == {"user_territory", "dealer_created", "lead_owned"}, mine
        for r in mine.values():
            assert str(r["district_id"]) == dist, "a taluka rolls up to its district"
            assert r["district_dealers"] == 1
        assert [r["kind"] for r in rows if str(r["user_id"]) == idle] == ["none"], "an idle person is listed"
    finally:
        await tx.rollback()
        await s.close()
