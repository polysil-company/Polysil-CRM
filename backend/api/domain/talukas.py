"""The taluka load plan (FS-087): which rows of a taluka list to add, which are
already there, and which cannot load. Pure: the script reads the database and
writes what this returns.

Districts are matched by `canonical()` equality only (rule 3). `match_districts`
also accepts one close spelling, which is right for the official district list and
wrong here, where a typo would file a taluka under a neighbouring district.
Talukas are compared by `normalise()` only (rule 4): the alias table is keyed by
district names and would rewrite a taluka that shares one ("Mehsana")."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from api.domain.district_offices import canonical, normalise


@dataclass(frozen=True)
class TalukaRow:
    """One row of talukas.csv."""

    state_code: str
    district: str
    taluka: str
    source_row: str = ""


@dataclass(frozen=True)
class HeldDistrict:
    id: str
    state_code: str
    name: str


@dataclass(frozen=True)
class HeldTaluka:
    id: str
    district_id: str
    name: str
    deleted: bool = False


@dataclass(frozen=True)
class Add:
    row: TalukaRow
    district: HeldDistrict


@dataclass
class Plan:
    adds: list[Add] = field(default_factory=list)
    present: list[tuple[TalukaRow, HeldTaluka]] = field(default_factory=list)
    deleted: list[tuple[TalukaRow, HeldTaluka]] = field(default_factory=list)
    skipped: list[tuple[TalukaRow, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def plan_talukas(rows: Sequence[TalukaRow], states: set[str],
                 districts: Sequence[HeldDistrict], talukas: Sequence[HeldTaluka]) -> Plan:
    """`states`: the state codes on the database. `districts`: every live district
    with its state's code. `talukas`: every taluka under those districts, soft-deleted
    ones included. Any problem means the caller writes nothing (rules 3 and 5)."""
    out = Plan()

    by_key: dict[tuple[str, str], list[HeldDistrict]] = defaultdict(list)
    for d in districts:
        by_key[(d.state_code.upper(), canonical(d.state_code, d.name))].append(d)
    for (state, _), found in sorted(by_key.items()):
        if len(found) > 1:
            out.problems.append(
                f"{state}: {sorted(d.name for d in found)} are one district by name")

    held: dict[tuple[str, str], list[HeldTaluka]] = defaultdict(list)
    for t in talukas:
        held[(t.district_id, normalise(t.name))].append(t)

    seen: dict[tuple[str, str], TalukaRow] = {}
    for row in rows:
        state = row.state_code.upper()
        label = f"row {row.source_row}" if row.source_row else repr(row.taluka)
        if not row.taluka.strip() or not normalise(row.taluka):
            out.problems.append(f"{label}: no taluka name")
            continue
        if state not in states:
            out.skipped.append((row, f"no such state {state}"))
            continue
        hits = by_key.get((state, canonical(state, row.district)))
        if not hits:
            out.skipped.append((row, f"no district {row.district!r} in {state}"))
            continue
        district = hits[0]
        key = (district.id, normalise(row.taluka))
        if key in seen:
            out.problems.append(f"{label}: {row.taluka!r} under {district.name} is also "
                                f"row {seen[key].source_row or repr(seen[key].taluka)}")
            continue
        seen[key] = row
        existing = held.get(key, [])
        live = [t for t in existing if not t.deleted]
        if live:
            out.present.append((row, live[0]))
        elif existing:
            out.deleted.append((row, existing[0]))
        else:
            out.adds.append(Add(row, district))
    return out
