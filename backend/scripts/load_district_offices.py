"""FS-085: district offices, and placing field staff in them.

Two commands:

    # the client's workbook, from the read-only facts (deploy_staging.py staff-facts)
    python scripts/load_district_offices.py sheet --facts facts.csv \\
        --csv data/masters/districts.csv --out placement.xlsx

    # districts only (safe on its own), then the whole placement
    python scripts/load_district_offices.py apply --csv data/masters/districts.csv --dry-run
    python scripts/load_district_offices.py apply --csv data/masters/districts.csv \\
        --sheet placement.xlsx --as admin@polysil.in --dry-run

`apply` runs in one transaction as the named administrator, with RLS on, through
the services the admin screens use (`api/services/district_offices.py`). With
`--dry-run` it does everything, prints the report and rolls back, so every guard
runs. Reruns with the same input write nothing. `--sheet -` reads the workbook from
stdin, which is how `deploy_staging.py district-offices` passes it to the box.

The workbook: People (one row per person, Decision: OK, an office name, or blank)
and Groups (area and regional offices, Decision: Yes or No). See FS-085 section 4.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Font, PatternFill  # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

from api.domain import district_offices as do  # noqa: E402

PEOPLE = ["Name", "Role", "Current office", "Suggested office", "How sure", "Why", "Notes",
          "Decision", "user_id", "role_code", "current_office_id"]
GROUPS = ["Kind", "Office name", "Who and where", "State", "Members", "Decision"]
UNSURE = PatternFill("solid", fgColor="FFF2CC")


# ── inputs ───────────────────────────────────────────────────────────────────

def read_districts(path: Path, states: tuple[str, ...]) -> dict[str, list[do.ListedDistrict]]:
    """The LGD list, only the loaded states (rule 1)."""
    out: dict[str, list[do.ListedDistrict]] = defaultdict(list)
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            st = (row.get("state_code") or "").strip().upper()
            name = (row.get("district") or "").strip()
            if st in states and name:
                out[st].append(do.ListedDistrict(name, (row.get("lgd_code") or "").strip()))
    missing = [st for st in states if not out.get(st)]
    if missing:
        raise SystemExit(f"the district list has no rows for {', '.join(missing)}")
    return dict(out)


def read_facts(path: Path) -> list[do.Fact]:
    def flag(v: str) -> bool:
        return v.strip().lower() in ("t", "true", "1", "yes")

    with path.open(encoding="utf-8-sig") as fh:
        return [do.Fact(r["user_id"], r["full_name"] or "", r["email"] or "", r["role_code"],
                        int(r["role_level"] or 0), flag(r["is_functional"] or ""),
                        r["office_id"] or "", r["office_name"] or "", r["kind"],
                        (r["state_code"] or "").upper(), r["district_name"] or "",
                        int(r["n"] or 0), int(r.get("district_dealers") or 0),
                        r.get("office_territory") or "")
                for r in csv.DictReader(fh)]


# ── the workbook ─────────────────────────────────────────────────────────────

def write_sheet(path: Path | io.BytesIO, people: list[do.Suggestion], groups: list[do.Group],
                listed: dict[str, list[do.ListedDistrict]], states: tuple[str, ...]) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "People"
    ws.append(PEOPLE)
    for s in people:
        ws.append([s.full_name, s.role_code.replace("_", " ").title(), s.current_office,
                   s.office.name if s.office else "", s.confidence, s.why, s.notes, "",
                   s.user_id, s.role_code, s.current_office_id])
        if s.needs_decision:
            for cell in ws[ws.max_row][:8]:
                cell.fill = UNSURE

    gs = wb.create_sheet("Groups")
    gs.append(GROUPS)
    for g in groups:
        gs.append(["Area" if g.kind == "area" else "Region", g.name, g.who, g.state,
                   "; ".join(g.members), ""])

    names = ["OK", do.HQ_NAME]
    for st in states:
        names.append(do.state_office_name(st))
        names += [do.district_office_name(st, d.name)
                  for d in sorted(listed.get(st, []), key=lambda x: x.name.casefold())]
    names += [g.name for g in groups]
    os_ = wb.create_sheet("Offices")
    for n in names:
        os_.append([n])
    os_.sheet_state = "hidden"

    # a warning, not an error: a renamed group or another existing office still works
    pick = DataValidation(type="list", formula1=f"=Offices!$A$1:$A${len(names)}",
                          allow_blank=True, errorStyle="warning",
                          error="Not in the list of offices. Keep it only if the office exists.")
    ws.add_data_validation(pick)
    pick.add(f"H2:H{max(ws.max_row, 2)}")
    yes = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    gs.add_data_validation(yes)
    yes.add(f"F2:F{max(gs.max_row, 2)}")

    for sheet, widths in ((ws, [28, 18, 16, 34, 9, 40, 60, 34]), (gs, [8, 40, 70, 6, 50, 9])):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for i, w in enumerate(widths):
            sheet.column_dimensions[chr(65 + i)].width = w
        sheet.freeze_panes = "A2"
    for col in ("I", "J", "K"):
        ws.column_dimensions[col].hidden = True
    wb.save(path)


def _rows(ws: Any, header: list[str]) -> list[dict[str, str]]:
    it = ws.iter_rows(values_only=True)
    top = [str(c or "").strip() for c in next(it)]
    missing = [h for h in header if h not in top]
    if missing:
        raise SystemExit(f"sheet {ws.title!r} lacks the columns {missing}")
    return [{h: str(v).strip() if v is not None else "" for h, v in zip(top, row, strict=False)}
            for row in it if any(v not in (None, "") for v in row)]


def read_sheet(source: Path | io.BytesIO) -> tuple[list[do.Group], list[Any]]:
    """Approved groups, and the People rows that ask for a move."""
    from api.services.district_offices import Decision

    wb = load_workbook(source, read_only=True, data_only=True)
    groups = []
    for r in _rows(wb["Groups"], GROUPS):
        if r["Decision"].casefold() != "yes":
            continue
        kind = {"area": "area", "region": "region"}.get(r["Kind"].casefold())
        if kind is None:
            raise SystemExit(f"Groups: kind {r['Kind']!r} is neither Area nor Region")
        members = tuple(m.strip() for m in r["Members"].split(";") if m.strip())
        groups.append(do.Group(kind, r["Office name"], r["State"].upper() if kind == "area" else "",
                               members, r["Who and where"]))
    decisions = []
    errors = []
    for r in _rows(wb["People"], PEOPLE):
        try:
            name = do.decided(r["Decision"], r["Suggested office"])
        except do.DecisionError as exc:
            errors.append(f"{r['Name']}: {exc}")
            continue
        if name is None:
            continue
        decisions.append(Decision(r["user_id"], r["Name"], r["role_code"],
                                  r["current_office_id"], name))
    if errors:
        raise SystemExit("the People sheet has decisions that name no office:\n  "
                         + "\n  ".join(errors))
    return groups, decisions


# ── apply ────────────────────────────────────────────────────────────────────

async def run_apply(plan: Any, actor_email: str, dry_run: bool) -> int:
    from sqlalchemy import text

    from api.config import get_settings
    from api.db.session import act_as, async_session_factory
    from api.deps import caller_for
    from api.services import district_offices as service

    async with async_session_factory() as session:
        tx = await session.begin()
        try:
            # read as the connecting role, before the switch: the actor must exist
            actor = (await session.execute(text(
                "SELECT id FROM app_user WHERE lower(email::text) = lower(:e) "
                "AND deleted_at IS NULL"), {"e": actor_email})).scalar_one_or_none()
            if actor is None:
                print(f"  refused: nobody has the email {actor_email!r}")
                await tx.rollback()
                return 2
            await act_as(session, str(actor), get_settings().db_app_role)
            caller = await caller_for(session, str(actor))
            await service.check_actor(session, caller)
            report = await service.apply(session, caller, plan)
        except service.PlanError as exc:
            await tx.rollback()
            _print(exc.report)
            print(f"\n  refused, nothing written ({len(exc.problems)}):")
            for p in exc.problems:
                print(f"    - {p}")
            return 1
        except BaseException:
            await tx.rollback()
            raise
        _print(report)
        if dry_run:
            await tx.rollback()
            print("\n  dry run: everything above was done and rolled back")
        else:
            await tx.commit()
            print("\n  committed")
    return 0


def _print(report: Any) -> None:
    for line in report.lines:
        if line:
            print(f"  {line}")
    for k, n in sorted(report.counts.items()):
        print(f"  {k}: {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sheet", help="write the client's workbook from the facts")
    s.add_argument("--facts", type=Path, required=True)
    s.add_argument("--csv", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--states", default=",".join(do.DEFAULT_STATES))
    a = sub.add_parser("apply", help="districts, offices and the approved moves")
    a.add_argument("--csv", type=Path, required=True)
    a.add_argument("--sheet", help="the marked workbook, or - for stdin")
    a.add_argument("--states", default=",".join(do.DEFAULT_STATES))
    a.add_argument("--as", dest="actor", default=os.environ.get("ADMIN_EMAIL", ""),
                   help="the administrator to act as (default: ADMIN_EMAIL)")
    a.add_argument("--all-districts", action="store_true",
                   help="an office for every district, not only where someone is placed")
    a.add_argument("--dry-run", action="store_true", help="do it all, report, roll back")
    args = parser.parse_args(argv)
    states = tuple(x.strip().upper() for x in args.states.split(",") if x.strip())
    unknown = [x for x in states if x not in do.STATE_NAMES]
    if unknown:
        raise SystemExit(f"unknown state codes {unknown}; known: {', '.join(do.STATE_NAMES)}")
    listed = read_districts(args.csv, states)

    if args.command == "sheet":
        people, groups = do.suggest(read_facts(args.facts), states)
        write_sheet(args.out, people, groups, listed, states)
        unsure = sum(p.needs_decision for p in people)
        print(f"  {len(people)} people ({unsure} need a decision), {len(groups)} groups "
              f"-> {args.out}")
        return 0

    from api.services.district_offices import Plan

    plan = Plan(states=states, listed=listed, all_districts=args.all_districts)
    if args.sheet:
        source: Path | io.BytesIO = (io.BytesIO(sys.stdin.buffer.read()) if args.sheet == "-"
                                     else Path(args.sheet))
        plan.groups, plan.decisions = read_sheet(source)
        print(f"  sheet: {len(plan.groups)} approved group(s), "
              f"{len(plan.decisions)} move(s) asked for")
    if not args.actor:
        raise SystemExit("name the administrator with --as, or set ADMIN_EMAIL")
    return asyncio.run(run_apply(plan, args.actor, args.dry_run))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.exit(main())
