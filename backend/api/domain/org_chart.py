"""The org chart, built from the rows `reporting_lines()` returns (FS-080).

Pure: no database. The database decides who manages whom and who the caller may
see; this module turns those rows into one subject's picture, or the company's.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Person:
    id: str
    full_name: str
    role_code: str | None
    role_name: str | None
    level: int | None
    org_unit_id: str | None
    org_unit_name: str | None
    manager_ids: tuple[str, ...]
    relation: str              # self, above, below, co_manager, other, unplaced


@dataclass
class Node:
    person: Person
    direct_reports: int
    team_size: int


@dataclass
class Chart:
    subject: Person | None
    managers: list[list[Person]]
    people: list[Node]
    co_managers: list[Person]
    by_role: list[tuple[str, str, int]]      # code, name, count
    unplaced: list[Person] = field(default_factory=list)


def _name_key(p: Person) -> tuple[str, str]:
    return (p.full_name, p.id)


def _people_key(p: Person) -> tuple[int, str, str]:
    # highest level first, then name, then id (spec section 4)
    return (-(p.level or 0), p.full_name, p.id)


def _below(start: Iterable[str], children: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    stack = list(start)
    while stack:
        pid = stack.pop()
        for c in children.get(pid, ()):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    return seen


def build(rows: Sequence[Person], subject_id: str | None) -> Chart:
    """One subject's picture, or with `subject_id` None the whole company.

    The caller has already checked that the subject may be shown.
    """
    index = {p.id: p for p in rows}
    placed = [p for p in rows if p.relation != "unplaced"]
    children: dict[str, list[str]] = {}
    for p in placed:
        for m in p.manager_ids:
            children.setdefault(m, []).append(p.id)

    subject = index[subject_id] if subject_id is not None else None
    managers: list[list[Person]] = []
    if subject is not None:
        member_ids = _below([subject.id], children)
        step = subject.manager_ids
        seen: set[str] = set()
        while step:
            people_step = sorted((index[i] for i in step if i in index and i not in seen),
                                 key=_name_key)
            if not people_step:
                break
            managers.append(people_step)
            seen.update(p.id for p in people_step)
            step = tuple(dict.fromkeys(m for p in people_step for m in p.manager_ids))
        unplaced: list[Person] = []
    else:
        member_ids = {p.id for p in placed}
        unplaced = sorted((p for p in rows if p.relation == "unplaced"), key=_name_key)

    members = sorted((index[i] for i in member_ids), key=_people_key)
    direct, team = _counts(members, member_ids)

    shown = set(member_ids) | {p.id for step in managers for p in step}
    if subject is not None:
        shown.add(subject.id)
    named = {m for p in members for m in p.manager_ids}
    co = sorted((index[i] for i in named - shown if i in index), key=_name_key)

    roles: dict[str, tuple[str, int, int]] = {}
    for p in members:
        code = p.role_code or ""
        name, level, n = roles.get(code, (p.role_name or "", p.level or 0, 0))
        roles[code] = (name, level, n + 1)
    by_role = [(code, name, n) for code, (name, _level, n)
               in sorted(roles.items(), key=lambda kv: (-kv[1][1], kv[0]))]

    return Chart(subject=subject, managers=managers,
                 people=[Node(p, direct[p.id], team[p.id]) for p in members],
                 co_managers=co, by_role=by_role, unplaced=unplaced)


def _counts(members: list[Person], member_ids: set[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Direct reports and team size inside the chart, in one bottom-up pass.

    Levels strictly rise up a chain, so lowest level first visits every report
    before its managers. A report shared by two managers counts once for each of
    them, and once for anyone above both (sets, not sums).
    """
    direct = {p.id: 0 for p in members}
    below: dict[str, set[str]] = {p.id: set() for p in members}
    for p in sorted(members, key=lambda q: q.level or 0):
        for m in p.manager_ids:
            if m in member_ids:
                direct[m] += 1
                below[m].add(p.id)
                below[m] |= below[p.id]
    return direct, {i: len(s) for i, s in below.items()}
