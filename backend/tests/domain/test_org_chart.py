"""FS-080: building the org chart from reporting_lines() rows. No database."""
# ruff: noqa: E501  (expected values inline)

from __future__ import annotations

import time

from api.domain.org_chart import Person, build


def _p(pid: str, name: str, level: int, managers: tuple[str, ...] = (), relation: str = "other",
       role: str | None = None) -> Person:
    code = role or {1: "field_officer", 2: "district_manager", 3: "state_manager",
                    4: "regional_manager", 5: "md_ceo"}[level]
    return Person(pid, name, code, code.replace("_", " ").title(), level, "o", "Office", managers, relation)


# md
# └ rm
#   └ sm
#     ├ dm_a ─┬ fo1 (shared by dm_a and dm_b)
#     └ dm_b ─┴ fo2 (dm_b only)
ROWS = [
    _p("md", "Meera", 5),
    _p("rm", "Rakesh", 4, ("md",)),
    _p("sm", "Suresh", 3, ("rm",)),
    _p("dma", "Asha", 2, ("sm",)),
    _p("dmb", "Bharat", 2, ("sm",)),
    _p("fo1", "Ravi", 1, ("dma", "dmb")),
    _p("fo2", "Kiran", 1, ("dmb",)),
]


def test_the_company_view_counts_a_shared_report_once_for_anyone_above_both() -> None:
    chart = build(ROWS, None)
    nodes = {n.person.id: n for n in chart.people}
    assert chart.subject is None and chart.managers == []
    assert [n.person.id for n in chart.people] == ["md", "rm", "sm", "dma", "dmb", "fo2", "fo1"]
    assert (nodes["dma"].direct_reports, nodes["dma"].team_size) == (1, 1)
    assert (nodes["dmb"].direct_reports, nodes["dmb"].team_size) == (2, 2)
    assert (nodes["sm"].direct_reports, nodes["sm"].team_size) == (2, 4)
    assert nodes["md"].team_size == 6
    assert chart.by_role == [("md_ceo", "Md Ceo", 1), ("regional_manager", "Regional Manager", 1),
                             ("state_manager", "State Manager", 1),
                             ("district_manager", "District Manager", 2), ("field_officer", "Field Officer", 2)]
    assert chart.co_managers == []


def test_a_subject_sees_the_chain_above_and_only_their_own_team() -> None:
    chart = build(ROWS, "dma")
    assert chart.subject is not None and chart.subject.id == "dma"
    assert [[p.id for p in step] for step in chart.managers] == [["sm"], ["rm"], ["md"]]
    assert [n.person.id for n in chart.people] == ["fo1"]
    # fo1's second manager is not in the picture otherwise: named as a co-manager
    assert [p.id for p in chart.co_managers] == ["dmb"]
    assert chart.by_role == [("field_officer", "Field Officer", 1)]


def test_a_two_person_step_is_sorted_by_name_then_id_and_climbs_once() -> None:
    rows = [_p("z", "Admin", 5), _p("a", "Admin", 5), _p("b", "Chandra", 5),
            _p("rm", "R", 4, ("a", "b", "z"))]
    chart = build(rows, "rm")
    assert [[p.id for p in step] for step in chart.managers] == [["a", "z", "b"]]


def test_a_field_officer_has_managers_and_no_team() -> None:
    chart = build(ROWS, "fo2")
    assert [[p.id for p in step] for step in chart.managers] == [["dmb"], ["sm"], ["rm"], ["md"]]
    assert chart.people == [] and chart.by_role == [] and chart.co_managers == []


def test_unplaced_people_are_listed_apart_and_not_counted() -> None:
    rows = [*ROWS, _p("x", "Nobody", 1, relation="unplaced")]
    chart = build(rows, None)
    assert [p.id for p in chart.unplaced] == ["x"]
    assert "x" not in {n.person.id for n in chart.people}
    assert sum(n for _c, _n, n in chart.by_role) == len(chart.people) == 7


def test_three_thousand_people_build_quickly() -> None:
    rows = [_p("md", "MD", 5)]
    for r in range(5):
        rows.append(_p(f"r{r}", f"RM {r}", 4, ("md",)))
        for s in range(6):
            sid = f"r{r}s{s}"
            rows.append(_p(sid, f"SM {sid}", 3, (f"r{r}",)))
            for d in range(10):
                did = f"{sid}d{d}"
                rows.append(_p(did, f"DM {did}", 2, (sid,)))
                for f in range(9):
                    rows.append(_p(f"{did}f{f}", f"FO {did}{f}", 1, (did,)))
    assert len(rows) > 3000
    start = time.perf_counter()
    chart = build(rows, None)
    assert time.perf_counter() - start < 1.0
    assert next(n for n in chart.people if n.person.id == "md").team_size == len(rows) - 1
