"""FS-085: district offices and placing field staff, with no database.

Three jobs, all pure so the loader, its tests and `load_districts.py` share them:

1. **Matching** a list of districts (the LGD CSV) against the districts a database
   already holds, without creating a second copy of one spelled differently
   (rule 2).
2. **Naming** the offices the loader creates (section 4).
3. **Suggesting** an office for each person from where their work sits, and the
   area and regional groupings, for the client to check (rules 11 to 17).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# ── the states (rule 1) ──────────────────────────────────────────────────────

STATE_NAMES: dict[str, str] = {
    "GJ": "Gujarat", "MH": "Maharashtra", "CG": "Chhattisgarh", "UP": "Uttar Pradesh",
    "RJ": "Rajasthan", "AP": "Andhra Pradesh", "MP": "Madhya Pradesh",
}
DEFAULT_STATES: tuple[str, ...] = tuple(STATE_NAMES)

HQ_NAME = "Polysil HQ"

# ── matching (rule 2) ────────────────────────────────────────────────────────

# GAP-584: a close spelling at or above this ratio is the same district. East and
# West Godavari score 0.92, which is why a close match is tried only among the
# districts nothing else has claimed (EC-10).
CLOSE = 0.85

# Known renamings and common spellings, keyed by state, because the same old name
# can mean different districts in different states (EC-10). Both sides are written
# as `normalise` returns them. GAP-584: add a pair when a dry run shows one.
ALIASES: dict[str, dict[str, str]] = {
    "GJ": {"kutch": "kachchh", "kachch": "kachchh", "mehsana": "mahesana",
           "panchmahal": "panchmahals", "dang": "dangs", "thedangs": "dangs",
           "aravalli": "arvalli", "ahmadabad": "ahmedabad", "dohad": "dahod",
           "chhotaudaipur": "chhotaudepur", "devbhoomidwarka": "devbhumidwarka",
           "baroda": "vadodara"},
    "MH": {"aurangabad": "chhatrapatisambhajinagar", "osmanabad": "dharashiv",
           "ahmednagar": "ahilyanagar", "ahmadnagar": "ahilyanagar", "bid": "beed",
           "gondiya": "gondia", "buldana": "buldhana"},
    "UP": {"allahabad": "prayagraj", "faizabad": "ayodhya", "lakhimpurkheri": "kheri",
           "santravidasnagar": "bhadohi", "shravasti": "shrawasti",
           "maharajganj": "mahrajganj", "jyotibaphulenagar": "amroha",
           "kanshiramnagar": "kasganj", "panchsheelnagar": "hapur",
           "prabuddhanagar": "shamli", "bhimnagar": "sambhal",
           "chhatrapatishahujimaharajnagar": "amethi", "badaun": "budaun"},
    "RJ": {"chittaurgarh": "chittorgarh", "jalor": "jalore", "dhaulpur": "dholpur",
           "jhunjhunun": "jhunjhunu", "sriganganagar": "ganganagar",
           "shriganganagar": "ganganagar"},
    "AP": {"anantapur": "ananthapuramu", "anantapuramu": "ananthapuramu",
           "kadapa": "ysrkadapa", "ysr": "ysrkadapa", "cuddapah": "ysrkadapa",
           "nellore": "sripottisriramulunellore", "spsrnellore": "sripottisriramulunellore",
           "konaseema": "drbrambedkarkonaseema", "vishakhapatnam": "visakhapatnam"},
    "CG": {"kawardha": "kabeerdham", "kabirdham": "kabeerdham",
           "dantewada": "dakshinbastardantewada", "kanker": "uttarbastarkanker",
           "koriya": "korea", "balodabazar": "balodabazarbhatapara"},
    "MP": {"hoshangabad": "narmadapuram", "narsinghpur": "narsimhapur",
           "eastnimar": "khandwa", "westnimar": "khargone"},
}

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_DISTRICT_WORD = re.compile(r"\bdistrict\b")


def normalise(name: str) -> str:
    """A district name with case, accents, bracketed text, the word "district",
    spaces and punctuation taken out: "Khandwa (East Nimar)" and "khandwa" agree."""
    text = unicodedata.normalize("NFKD", name).casefold()
    text = _BRACKETS.sub(" ", text)
    text = _DISTRICT_WORD.sub(" ", text)
    return "".join(ch for ch in text if ch.isalnum())


def canonical(state: str, name: str) -> str:
    """The normalised name, with a known alias replaced by the name it stands for."""
    key = normalise(name)
    return ALIASES.get(state.upper(), {}).get(key, key)


@dataclass(frozen=True)
class ListedDistrict:
    """A row of the official list (the CSV)."""

    name: str
    lgd_code: str = ""


@dataclass(frozen=True)
class HeldDistrict:
    """A district the database already holds under the state."""

    id: str
    name: str
    lgd_code: str | None = None


@dataclass(frozen=True)
class Match:
    listed: ListedDistrict
    # None: the district is new and will be created
    existing: HeldDistrict | None
    how: str            # lgd, name, alias, close, new
    score: float = 1.0
    # for a new one: the nearest existing name and its ratio, so a human can see a
    # spelling the threshold missed (EC-10)
    nearest: str | None = None
    nearest_score: float = 0.0


@dataclass
class MatchResult:
    matches: list[Match] = field(default_factory=list)
    unlisted: list[HeldDistrict] = field(default_factory=list)   # rule 3
    problems: list[str] = field(default_factory=list)            # stop the run

    @property
    def new(self) -> list[Match]:
        return [m for m in self.matches if m.existing is None]


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_districts(state: str, listed: Sequence[ListedDistrict],
                    held: Sequence[HeldDistrict]) -> MatchResult:
    """Rule 2, in order: LGD code, normalised name, alias, one close spelling among
    districts nothing else claimed. A district claimed twice, or a close spelling
    with two candidates, is a problem: the caller stops before writing."""
    out = MatchResult()
    claimed: dict[str, ListedDistrict] = {}
    done: dict[int, Match] = {}

    def claim(i: int, row: ListedDistrict, d: HeldDistrict, how: str, score: float = 1.0) -> None:
        if d.id in claimed:
            out.problems.append(
                f"{state}: {row.name!r} and {claimed[d.id].name!r} both match {d.name!r}")
            return
        claimed[d.id] = row
        done[i] = Match(row, d, how, score)

    by_lgd: dict[str, list[HeldDistrict]] = defaultdict(list)
    for d in held:
        if d.lgd_code:
            by_lgd[d.lgd_code.strip()].append(d)
    for code, rows in by_lgd.items():
        if len(rows) > 1:
            out.problems.append(f"{state}: LGD code {code} is on {[r.name for r in rows]}")
    for i, row in enumerate(listed):
        hits = by_lgd.get(row.lgd_code.strip()) if row.lgd_code.strip() else None
        if hits and len(hits) == 1:
            claim(i, row, hits[0], "lgd")

    # every held district is indexed, claimed or not: two listed rows that are the
    # same district under two spellings must be reported, not one of them created
    for how, key in (("name", normalise), ("alias", lambda n: canonical(state, n))):
        index: dict[str, list[HeldDistrict]] = defaultdict(list)
        for d in held:
            index[key(d.name)].append(d)
        for i, row in enumerate(listed):
            if i in done:
                continue
            hits = index.get(key(row.name), [])
            if len(hits) > 1:
                out.problems.append(
                    f"{state}: {row.name!r} matches {[h.name for h in hits]} by {how}")
            elif hits:
                claim(i, row, hits[0], how)

    free = [d for d in held if d.id not in claimed]
    # both directions are checked before anything is claimed: one listed row close to
    # two held districts, and one held district close to two listed rows (code review
    # F-4). Claiming greedily in list order put West Godavari on East's territory.
    pending = [(i, row) for i, row in enumerate(listed) if i not in done]
    suitors: dict[str, list[str]] = defaultdict(list)
    for _, row in pending:
        mine = canonical(state, row.name)
        for d in free:
            if _ratio(mine, canonical(state, d.name)) >= CLOSE:
                suitors[d.id].append(row.name)
    contested = {d_id for d_id, rows in suitors.items() if len(rows) > 1}
    for d in free:
        if d.id in contested:
            out.problems.append(
                f"{state}: {suitors[d.id]} are all close to {d.name!r}; add an alias")
    for i, row in pending:
        mine = canonical(state, row.name)
        scored = sorted(((_ratio(mine, canonical(state, d.name)), d.name, d) for d in free),
                        key=lambda t: (-t[0], t[1]))
        close = [t for t in scored if t[0] >= CLOSE]
        if len(close) > 1:
            out.problems.append(
                f"{state}: {row.name!r} is close to {[t[1] for t in close]}; add an alias")
        elif close and close[0][2].id in contested:
            continue                                        # reported above
        elif close:
            claim(i, row, close[0][2], "close", round(close[0][0], 3))
        else:
            nearest = max(((_ratio(mine, canonical(state, d.name)), d.name) for d in held),
                          default=(0.0, None))
            done[i] = Match(row, None, "new", 0.0, nearest[1], round(nearest[0], 3))

    out.matches = [done[i] for i in sorted(done)]
    out.unlisted = sorted((d for d in held if d.id not in claimed), key=lambda d: d.name)
    return out


# ── office names (section 4) ─────────────────────────────────────────────────

def state_office_name(code: str) -> str:
    return f"{STATE_NAMES.get(code.upper(), code.upper())} State"


def district_office_name(code: str, district: str) -> str:
    return f"{district} District, {code.upper()}"


def area_name(code: str, districts: Iterable[str]) -> str:
    """A default the client renames: the first three districts, then a count."""
    names = sorted(districts, key=str.casefold)
    head = " / ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
    return f"{head} Area, {code.upper()}"


def region_name(codes: Iterable[str]) -> str:
    return "Region " + "-".join(sorted(c.upper() for c in codes))


# ── the people sheet (rules 11 to 17) ────────────────────────────────────────

FIELD_OFFICER, DISTRICT_MANAGER = "field_officer", "district_manager"
STATE_MANAGER, REGIONAL_MANAGER = "state_manager", "regional_manager"
LINE_ROLES = (FIELD_OFFICER, DISTRICT_MANAGER, STATE_MANAGER, REGIONAL_MANAGER)
HIGH, MEDIUM, LOW, NONE = "high", "medium", "low", "none"
_RANK = {LOW: 0, NONE: 1, MEDIUM: 2, HIGH: 3, "": 4}


@dataclass(frozen=True)
class Fact:
    """One row of `scripts/sql/staff_area_facts.sql`."""

    user_id: str
    full_name: str
    email: str
    role_code: str
    role_level: int
    is_functional: bool
    office_id: str
    office_name: str
    kind: str                 # none, user_territory, or an activity kind
    state_code: str = ""
    district: str = ""        # blank: the evidence sits at state level
    n: int = 0
    district_dealers: int = 0
    # the current office's own territory, blank when it has none (Polysil HQ)
    office_territory: str = ""


@dataclass(frozen=True)
class Office:
    """Where someone could sit. `name` is what the workbook shows."""

    kind: str                 # hq, state, district, area, region
    name: str
    state: str = ""
    district: str = ""


@dataclass(frozen=True)
class Group:
    """An area or regional office proposed for the client's approval."""

    kind: str                 # area, region
    name: str
    state: str                # area: its state; region: blank
    members: tuple[str, ...]  # area: district names; region: state codes
    who: str                  # plain words: "X looks after A, B and C"


@dataclass(frozen=True)
class Suggestion:
    user_id: str
    full_name: str
    email: str
    role_code: str
    current_office: str
    current_office_id: str
    office: Office | None
    confidence: str           # high, medium, low, none, or "" for roles not placed
    why: str
    notes: str

    @property
    def needs_decision(self) -> bool:
        return self.confidence in (LOW, NONE)


@dataclass
class _Person:
    first: Fact
    held_districts: set[tuple[str, str]] = field(default_factory=set)
    held_states: set[str] = field(default_factory=set)      # held at state level
    outside: set[str] = field(default_factory=set)          # held, not loaded
    activity: Counter[tuple[str, str]] = field(default_factory=Counter)
    activity_kinds: Counter[tuple[str, str, str]] = field(default_factory=Counter)
    dealers: dict[tuple[str, str], int] = field(default_factory=dict)


def _join(words: Sequence[str]) -> str:
    words = list(words)
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _people(facts: Iterable[Fact], states: Sequence[str]) -> dict[str, _Person]:
    loaded = {s.upper() for s in states}
    people: dict[str, _Person] = {}
    for f in facts:
        p = people.setdefault(f.user_id, _Person(f))
        st = f.state_code.upper()
        if f.kind == "none" or not st:
            continue
        if f.district:
            p.dealers[(st, f.district)] = f.district_dealers
        if f.kind == "user_territory":
            if st not in loaded:
                p.outside.add(f"{f.district or STATE_NAMES.get(st, st)} ({st})")
            elif f.district:
                p.held_districts.add((st, f.district))
            else:
                p.held_states.add(st)
        else:
            p.activity[(st, f.district)] += f.n
            p.activity_kinds[(f.kind, st, f.district)] += f.n
    return people


def _places(items: Iterable[tuple[str, str]]) -> str:
    return _join([f"{d} ({s})" if d else f"{STATE_NAMES.get(s, s)} (state)"
                  for s, d in sorted(items, key=lambda t: (t[0], t[1].casefold()))])


def _activity_check(p: _Person, states: set[str], districts: set[tuple[str, str]],
                    confidence: str) -> tuple[str, str]:
    """Rule 16: activity outside what the office covers lowers the confidence; all
    of it outside makes it low, with the leads counted (EC-4)."""
    if not p.activity:
        return confidence, ""
    inside = {k for k in p.activity if k[0] in states or k in districts}
    outside = [k for k in p.activity if k not in inside]
    if not outside:
        return confidence, ""
    leads = sum(n for (kind, s, d), n in p.activity_kinds.items()
                if kind == "lead_owned" and (s, d) in outside)
    where = _places(outside)
    if not inside:
        note = f"all their work is elsewhere: {where}"
        if leads:
            note += f"; {leads} lead(s) they own would leave that district on a move"
        return LOW, note
    return (MEDIUM if confidence == HIGH else confidence), f"some work is elsewhere: {where}"


def suggest(facts: Iterable[Fact], states: Sequence[str] = DEFAULT_STATES
            ) -> tuple[list[Suggestion], list[Group]]:
    """Rules 11 to 17. Returns the people, rows needing a decision first, and the
    proposed groups."""
    people = _people(facts, states)
    loaded = {s.upper() for s in states}
    groups: list[Group] = []
    out: list[Suggestion] = []

    # every DM's districts first: an overlap makes both low (EC-9)
    dm_sets = {uid: p.held_districts for uid, p in people.items()
               if p.first.role_code == DISTRICT_MANAGER}
    holders: dict[tuple[str, str], list[str]] = defaultdict(list)
    for uid, ds in dm_sets.items():
        for place in ds:
            holders[place].append(uid)

    for uid, p in people.items():
        f = p.first
        office: Office | None = None
        confidence, why, notes = NONE, "", []
        held = sorted(p.held_districts, key=lambda t: (t[0], t[1].casefold()))
        if p.outside:
            notes.append(f"holds {_join(sorted(p.outside))}, which this load does not cover")

        if f.role_code not in LINE_ROLES:
            # rule 15: head office and functional roles stay where they are
            out.append(Suggestion(uid, f.full_name, f.email, f.role_code, f.office_name,
                                  f.office_id, None, "", "head office or functional role: stays",
                                  "; ".join(notes)))
            continue

        if f.office_territory:
            # already in an office with an area: a sheet made after a placement
            # leaves them be (rule 9). The admin moves them in the app if needed.
            out.append(Suggestion(uid, f.full_name, f.email, f.role_code, f.office_name,
                                  f.office_id, None, "",
                                  f"already placed in {f.office_name} ({f.office_territory})",
                                  "; ".join(notes)))
            continue

        if f.role_code in (FIELD_OFFICER, DISTRICT_MANAGER):
            from_work = False
            if held:
                why = f"holds {_places(held)}"
            elif p.held_states:
                why = f"holds {_places((s, '') for s in p.held_states)}"
                notes.append("holds a whole state; a field role needs a district")
                confidence = LOW
            elif any(d and s in loaded for s, d in p.activity):
                # rule 16: no area held, so the district with most of their work
                work = Counter({k: n for k, n in p.activity.items() if k[1] and k[0] in loaded})
                top, n = sorted(work.items(), key=lambda t: (-t[1], t[0][1].casefold()))[0]
                total = sum(work.values())
                held = [top]
                from_work = True
                why = (f"holds no area; {n} of their {total} leads, orders and visits are in "
                       f"{_places([top])}")
                notes.append("no area held: suggested from their work")
            states_held = {s for s, _ in held}
            members: tuple[str, ...] = ()
            if f.role_code == DISTRICT_MANAGER and len(held) > 1:
                clash = sorted({people[o].first.full_name for h in held for o in holders[h]
                                if o != uid})
                if len(states_held) > 1:
                    confidence = LOW
                    notes.append("districts in two states: no area proposed")
                elif clash:
                    confidence = LOW
                    notes.append(f"another District Manager holds some of these: {_join(clash)}")
                else:
                    st = next(iter(states_held))
                    names = [d for _, d in held]
                    g = Group("area", area_name(st, names), st, tuple(names),
                              f"{f.full_name} looks after {_join(names)}")
                    groups.append(g)
                    office = Office("area", g.name, st)
                    members = g.members
                    confidence = HIGH
            elif len(held) == 1:
                st, d = held[0]
                office = Office("district", district_office_name(st, d), st, d)
                confidence = HIGH
            elif held:
                # rule 13: a Field Officer always sits in one district office
                st, d = sorted(held, key=lambda t: (-p.dealers.get(t, 0), t[1].casefold()))[0]
                office = Office("district", district_office_name(st, d), st, d)
                confidence = LOW
                rest = [x for x in held if x != (st, d)]
                notes.append(f"chosen for its {p.dealers.get((st, d), 0)} dealers; dealers in "
                             f"{_places(rest)} are not visible from here (GAP-585)")
            if office is not None:
                cover_d = ({(office.state, m) for m in members} if office.kind == "area"
                           else {(office.state, office.district)})
                confidence, note = _activity_check(p, set(), cover_d | set(held), confidence)
                if note:
                    notes.append(note)
                if from_work:
                    # GAP-581: work alone is weaker evidence than an area held
                    confidence = MEDIUM if total >= 5 and n >= 0.8 * total else LOW

        elif f.role_code == STATE_MANAGER:
            st_set = p.held_states | {s for s, _ in held}
            if len(st_set) == 1:
                st = next(iter(st_set))
                office = Office("state", state_office_name(st), st)
                confidence = HIGH if p.held_states else MEDIUM
                why = f"holds {_places([(st, '')] if p.held_states else held)}"
                if not p.held_states:
                    notes.append("holds districts, not the state")
                confidence, note = _activity_check(p, {st}, set(), confidence)
                if note:
                    notes.append(note)
            elif st_set:
                confidence = LOW
                why = f"holds {_places((s, '') for s in st_set)}"
                notes.append("several states: a State Manager sits in one state office")

        else:   # regional manager, rule 14
            st_set = p.held_states | {s for s, _ in held}
            if st_set:
                why = f"holds {_places([(s, '') for s in p.held_states] + held)}"
            if len(st_set) >= 2:
                codes = tuple(sorted(st_set))
                g = Group("region", region_name(codes), "", codes,
                          f"{f.full_name} looks after {_join([STATE_NAMES[c] for c in codes])}")
                groups.append(g)
                office = Office("region", g.name)
                confidence = HIGH if not held else MEDIUM
                confidence, note = _activity_check(p, set(codes), set(), confidence)
                if note:
                    notes.append(note)
            else:
                confidence = LOW
                notes.append("no region to sit in; at Polysil HQ they see every dealer and "
                             "manage every State Manager not under a region (GAP-583)")

        away = sorted({k for k in p.activity if k[0] not in loaded})
        if office is None and away:
            notes.append(f"their work is in {_places(away)}, which this load does not cover")
        if not why and away:
            why, confidence = "holds no area, and their work is outside this load", LOW
        elif not why:
            why = "holds no area and has no leads, orders or visits"
            if confidence != LOW:
                confidence = NONE
        if office is None and confidence == HIGH:
            confidence = LOW
        out.append(Suggestion(uid, f.full_name, f.email, f.role_code, f.office_name, f.office_id,
                              office, confidence, why, "; ".join(n for n in notes if n)))

    level = {FIELD_OFFICER: 1, DISTRICT_MANAGER: 2, STATE_MANAGER: 3, REGIONAL_MANAGER: 4}
    out.sort(key=lambda s: (_RANK[s.confidence], -level.get(s.role_code, 0),
                            s.full_name.casefold(), s.user_id))
    groups.sort(key=lambda g: (g.kind, g.state, g.name))
    return out, groups


# ── decisions (section 4) ────────────────────────────────────────────────────

OK = "OK"


class DecisionError(ValueError):
    """A Decision that names no office, or is OK with nothing suggested."""


def decided(decision: str | None, suggested: str | None) -> str | None:
    """The office name a Decision cell asks for. Blank: leave the person alone."""
    value = (decision or "").strip()
    if not value:
        return None
    if value.casefold() == OK.casefold():
        if not (suggested or "").strip():
            raise DecisionError("OK, but nothing was suggested")
        return (suggested or "").strip()
    return value


def catalogue(states: Iterable[str], districts: dict[str, list[str]],
              groups: Iterable[Group],
              spellings: dict[str, list[tuple[str, str]]] | None = None) -> dict[str, Office]:
    """Every office name a Decision may use, casefolded: Polysil HQ, the state
    offices, every district office of the loaded states, and the approved groups.

    `districts` holds the database's spelling. `spellings` maps a state to
    (the list's spelling, the database's spelling) pairs, so a Decision written with
    either name resolves to the same district office."""
    out: dict[str, Office] = {HQ_NAME.casefold(): Office("hq", HQ_NAME)}
    for st in states:
        st = st.upper()
        out[state_office_name(st).casefold()] = Office("state", state_office_name(st), st)
        for d in districts.get(st, []):
            name = district_office_name(st, d)
            out[name.casefold()] = Office("district", name, st, d)
        for listed, d in (spellings or {}).get(st, []):
            out.setdefault(district_office_name(st, listed).casefold(),
                           Office("district", district_office_name(st, d), st, d))
    for g in groups:
        out[g.name.casefold()] = Office(g.kind, g.name, g.state)
    return out
