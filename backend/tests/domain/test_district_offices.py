"""FS-085 with no database: matching districts (rule 2), office names (section 4),
the people suggestions (rules 11 to 17) and reading a Decision."""

from __future__ import annotations

import csv
import itertools
from pathlib import Path

import pytest

from api.domain import district_offices as do
from api.domain.district_offices import Fact, HeldDistrict, ListedDistrict

ROOT = Path(__file__).resolve().parents[2]


def held(*names: str, lgd: dict[str, str] | None = None) -> list[HeldDistrict]:
    return [HeldDistrict(f"id-{i}", n, (lgd or {}).get(n)) for i, n in enumerate(names)]


# ── matching (rule 2) ────────────────────────────────────────────────────────


def test_lgd_code_wins_over_any_spelling() -> None:
    r = do.match_districts(
        "GJ", [ListedDistrict("Kachchh", "449")], held("Bhuj area", lgd={"Bhuj area": "449"})
    )
    assert [(m.how, m.existing and m.existing.name) for m in r.matches] == [("lgd", "Bhuj area")]
    assert not r.problems and not r.unlisted


@pytest.mark.parametrize(
    "listed,existing",
    [
        ("Banas Kantha", "Banaskantha"),
        ("Sabar Kantha", "SABARKANTHA"),
        ("Chhotaudepur", "Chhota Udepur"),
        ("Khandwa (East Nimar)", "Khandwa"),
        ("Rajkot", "Rajkot District"),
        ("Y.S.R. Kadapa", "YSR Kadapa"),
    ],
)
def test_spacing_case_brackets_and_the_word_district_do_not_matter(
    listed: str, existing: str
) -> None:
    state = "AP" if "Kadapa" in listed else "MP" if "Khandwa" in listed else "GJ"
    r = do.match_districts(state, [ListedDistrict(listed)], held(existing))
    assert r.matches[0].how == "name" and r.matches[0].existing is not None


@pytest.mark.parametrize(
    "state,listed,existing",
    [
        ("GJ", "Kachchh", "Kutch"),
        ("GJ", "Mahesana", "Mehsana"),
        ("GJ", "Panch Mahals", "Panchmahal"),
        ("GJ", "Dangs", "Dang"),
        ("MH", "Chhatrapati Sambhajinagar", "Aurangabad"),
        ("MH", "Dharashiv", "Osmanabad"),
        ("UP", "Prayagraj", "Allahabad"),
        ("AP", "Sri Potti Sriramulu Nellore", "Nellore"),
        ("CG", "Kabeerdham", "Kawardha"),
    ],
)
def test_known_renamings_match_by_alias(state: str, listed: str, existing: str) -> None:
    r = do.match_districts(state, [ListedDistrict(listed)], held(existing))
    assert r.matches[0].how in ("alias", "close"), r
    assert r.matches[0].existing is not None and not r.problems


def test_an_alias_belongs_to_its_state() -> None:
    """EC-10: Aurangabad is a Maharashtra rename; in another state it is itself."""
    r = do.match_districts("UP", [ListedDistrict("Chhatrapati Sambhajinagar")], held("Aurangabad"))
    assert r.matches[0].how == "new" and r.unlisted[0].name == "Aurangabad"


def test_a_close_spelling_matches_once() -> None:
    r = do.match_districts("GJ", [ListedDistrict("Arvalli")], held("Aravali"))
    assert r.matches[0].how == "close" and r.matches[0].score >= do.CLOSE


def test_west_godavari_does_not_take_east_godavari() -> None:
    """EC-10: the two score 0.92. East matches by name first, so West is new."""
    r = do.match_districts(
        "AP",
        [ListedDistrict("East Godavari"), ListedDistrict("West Godavari")],
        held("East Godavari"),
    )
    assert [m.how for m in r.matches] == ["name", "new"]
    assert r.matches[1].nearest == "East Godavari" and not r.problems


def test_kanpur_nagar_and_dehat_are_not_kanpur() -> None:
    r = do.match_districts(
        "UP", [ListedDistrict("Kanpur Nagar"), ListedDistrict("Kanpur Dehat")], held("Kanpur")
    )
    assert [m.how for m in r.matches] == ["new", "new"]
    assert r.unlisted[0].name == "Kanpur", "left alone and reported (rule 3)"


def test_two_close_candidates_stop_the_run() -> None:
    r = do.match_districts(
        "GJ", [ListedDistrict("Surendranagr")], held("Surendranagar", "Surendranagara")
    )
    assert r.problems and "add an alias" in r.problems[0]


@pytest.mark.parametrize("listed,existing", [
    (["West Godavari", "East Godavari"], "Est Godavari"),
    (["East Godavari", "West Godavari"], "Est Godavari"),
])
def test_two_listed_rows_close_to_one_district_stop_the_run(
        listed: list[str], existing: str) -> None:
    """Code review F-4: in either list order, neither row claims the district."""
    r = do.match_districts("AP", [ListedDistrict(n) for n in listed], held(existing))
    assert any("are all close to" in p and existing in p for p in r.problems), r.problems
    assert not any(m.how == "close" for m in r.matches)


def test_the_catalogue_resolves_the_lists_spelling_to_the_database_district() -> None:
    cat = do.catalogue(["GJ"], {"GJ": ["Kutch"]}, [], {"GJ": [("Kachchh", "Kutch")]})
    assert cat["kachchh district, gj"] == do.Office("district", "Kutch District, GJ", "GJ", "Kutch")
    assert cat["kutch district, gj"] == cat["kachchh district, gj"]


def test_one_existing_district_claimed_twice_stops_the_run() -> None:
    r = do.match_districts(
        "GJ", [ListedDistrict("Kutch"), ListedDistrict("Kachchh")], held("Kachchh")
    )
    assert r.problems and "both match" in r.problems[0]


def test_an_lgd_code_on_two_districts_stops_the_run() -> None:
    r = do.match_districts(
        "GJ", [ListedDistrict("A", "1")], held("A", "B", lgd={"A": "1", "B": "1"})
    )
    assert r.problems


DISTRICTS = ROOT / "data" / "masters" / "districts.csv"


# data/ stays out of the shared repository, so CI has no list to read
@pytest.mark.skipif(not DISTRICTS.exists(), reason="data/masters/districts.csv is local only")
def test_the_real_list_matches_itself_completely() -> None:
    """Every state of the CSV against a copy of itself with the LGD codes taken off:
    each district finds its own row by name, nothing is new, nothing is a problem."""
    rows = list(csv.DictReader(DISTRICTS.open(encoding="utf-8-sig")))
    for state, group in itertools.groupby(
        sorted(rows, key=lambda r: r["state_code"]), key=lambda r: r["state_code"]
    ):
        g = list(group)
        r = do.match_districts(
            state,
            [ListedDistrict(x["district"], x["lgd_code"]) for x in g],
            held(*[x["district"] for x in g]),
        )
        assert not r.problems, (state, r.problems)
        assert all(m.how == "name" for m in r.matches), state


# ── names ────────────────────────────────────────────────────────────────────


def test_office_names_carry_the_state() -> None:
    assert do.district_office_name("up", "Pratapgarh") == "Pratapgarh District, UP"
    assert do.district_office_name("RJ", "Pratapgarh") != do.district_office_name(
        "UP", "Pratapgarh"
    )
    assert do.state_office_name("GJ") == "Gujarat State"
    assert do.area_name("GJ", ["Patan", "Banas Kantha"]) == "Banas Kantha / Patan Area, GJ"
    assert do.area_name("MH", ["D", "C", "B", "A"]) == "A / B / C +1 Area, MH"
    assert do.region_name(["UP", "CG", "RJ"]) == "Region CG-RJ-UP"


# ── suggestions (rules 11 to 17) ─────────────────────────────────────────────


def person(
    uid: str,
    role: str,
    *rows: tuple[str, str, str, int],
    dealers: dict[str, int] | None = None,
    level: int = 1,
) -> list[Fact]:
    """rows: (kind, state, district, n)."""
    base = {
        "user_id": uid,
        "full_name": uid.upper(),
        "email": f"{uid}@x.in",
        "role_code": role,
        "role_level": level,
        "is_functional": False,
        "office_id": "hq",
        "office_name": "Polysil HQ",
    }
    if not rows:
        return [Fact(**base, kind="none")]  # type: ignore[arg-type]
    return [
        Fact(
            **base,
            kind=k,
            state_code=s,
            district=d,
            n=n,  # type: ignore[arg-type]
            district_dealers=(dealers or {}).get(d, 0),
        )
        for k, s, d, n in rows
    ]


def held_in(state: str, *districts: str) -> list[tuple[str, str, str, int]]:
    return [("user_territory", state, d, 1) for d in districts]


def by_id(facts: list[Fact]) -> tuple[dict[str, do.Suggestion], list[do.Group]]:
    people, groups = do.suggest(facts)
    return {s.user_id: s for s in people}, groups


def test_one_district_fo_goes_there_with_high_confidence() -> None:
    s, _ = by_id(person("fo", "field_officer", *held_in("AP", "Ananthapuramu")))
    assert s["fo"].office == do.Office(
        "district", "Ananthapuramu District, AP", "AP", "Ananthapuramu"
    )
    assert s["fo"].confidence == do.HIGH and "holds Ananthapuramu (AP)" in s["fo"].why


def test_a_multi_district_fo_sits_in_the_district_with_most_dealers() -> None:
    """Rule 13: never an area office; the others named in the notes (GAP-585)."""
    s, groups = by_id(
        person(
            "fo",
            "field_officer",
            *held_in("MH", "Akola", "Buldhana", "Washim"),
            dealers={"Akola": 4, "Buldhana": 26, "Washim": 4},
        )
    )
    assert s["fo"].office is not None and s["fo"].office.district == "Buldhana"
    assert s["fo"].confidence == do.LOW
    assert "Akola (MH) and Washim (MH) are not visible" in s["fo"].notes
    assert groups == []


def test_dealer_ties_go_by_name() -> None:
    s, _ = by_id(person("fo", "field_officer", *held_in("GJ", "Patan", "Banas Kantha")))
    assert s["fo"].office is not None and s["fo"].office.district == "Banas Kantha"


def test_a_multi_district_dm_gets_an_area_proposed() -> None:
    s, groups = by_id(
        person("dm", "district_manager", *held_in("GJ", "Patan", "Banas Kantha"), level=2)
    )
    assert [g.kind for g in groups] == ["area"]
    g = groups[0]
    assert g.state == "GJ" and set(g.members) == {"Patan", "Banas Kantha"}
    assert g.who == "DM looks after Banas Kantha and Patan"
    assert s["dm"].office == do.Office("area", g.name, "GJ") and s["dm"].confidence == do.HIGH


def test_a_one_district_dm_sits_in_the_district_office() -> None:
    s, groups = by_id(person("dm", "district_manager", *held_in("MH", "Jalgaon"), level=2))
    assert s["dm"].office is not None and s["dm"].office.kind == "district" and not groups


def test_a_dm_across_two_states_gets_no_area() -> None:
    s, groups = by_id(
        person("dm", "district_manager", *held_in("GJ", "Dahod"), *held_in("MP", "Jhabua"), level=2)
    )
    assert not groups and s["dm"].office is None and s["dm"].confidence == do.LOW
    assert "two states" in s["dm"].notes


def test_two_dms_on_one_district_both_go_low() -> None:
    facts = person("a", "district_manager", *held_in("GJ", "Patan", "Mahesana"), level=2) + person(
        "b", "district_manager", *held_in("GJ", "Patan", "Banas Kantha"), level=2
    )
    s, groups = by_id(facts)
    assert not groups
    assert s["a"].confidence == s["b"].confidence == do.LOW
    assert "B" in s["a"].notes and "A" in s["b"].notes


def test_all_activity_outside_the_held_district_is_low_and_counts_the_leads() -> None:
    """EC-4: the prod shape, held Jalna but every lead and order in Gujarat."""
    s, _ = by_id(
        person(
            "fo",
            "field_officer",
            *held_in("MH", "Jalna"),
            ("lead_owned", "GJ", "Vadodara", 1),
            ("lead_owned", "GJ", "Ahmedabad", 1),
            ("order_owned", "GJ", "Vadodara", 1),
        )
    )
    assert s["fo"].confidence == do.LOW
    assert "all their work is elsewhere" in s["fo"].notes and "2 lead(s)" in s["fo"].notes


def test_some_activity_outside_lowers_high_to_medium() -> None:
    s, _ = by_id(
        person(
            "fo",
            "field_officer",
            *held_in("GJ", "Rajkot"),
            ("lead_owned", "GJ", "Rajkot", 5),
            ("lead_owned", "GJ", "Morbi", 1),
        )
    )
    assert s["fo"].confidence == do.MEDIUM and "Morbi (GJ)" in s["fo"].notes


def test_activity_inside_the_area_keeps_a_dm_high() -> None:
    s, _ = by_id(
        person(
            "dm",
            "district_manager",
            *held_in("GJ", "Patan", "Mahesana"),
            ("lead_owned", "GJ", "Patan", 3),
            level=2,
        )
    )
    assert s["dm"].confidence == do.HIGH


def test_state_managers() -> None:
    facts = (
        person("whole", "state_manager", ("user_territory", "AP", "", 1), level=3)
        + person("dist", "state_manager", *held_in("MH", "Nashik"), level=3)
        + person(
            "two",
            "state_manager",
            ("user_territory", "AP", "", 1),
            ("user_territory", "MP", "", 1),
            level=3,
        )
    )
    s, _ = by_id(facts)
    assert s["whole"].office == do.Office("state", "Andhra Pradesh State", "AP")
    assert s["whole"].confidence == do.HIGH
    assert s["dist"].office is not None and s["dist"].office.state == "MH"
    assert s["dist"].confidence == do.MEDIUM and "not the state" in s["dist"].notes
    assert s["two"].office is None and s["two"].confidence == do.LOW


def test_a_regional_manager_over_three_states_gets_a_region() -> None:
    s, groups = by_id(
        person(
            "rm",
            "regional_manager",
            *[("user_territory", c, "", 1) for c in ("UP", "CG", "RJ")],
            level=4,
        )
    )
    assert [(g.kind, g.members) for g in groups] == [("region", ("CG", "RJ", "UP"))]
    assert (
        s["rm"].office == do.Office("region", "Region CG-RJ-UP") and s["rm"].confidence == do.HIGH
    )


@pytest.mark.parametrize("rows", [(), (("user_territory", "GJ", "Vadodara", 1),)])
def test_a_regional_manager_with_one_area_or_none_is_low_with_the_warning(rows: tuple) -> None:
    s, groups = by_id(person("rm", "regional_manager", *rows, level=4))
    assert not groups and s["rm"].office is None and s["rm"].confidence == do.LOW
    assert "every dealer" in s["rm"].notes


def test_nobody_with_no_evidence_gets_none() -> None:
    s, _ = by_id(person("fo", "field_officer"))
    assert s["fo"].office is None and s["fo"].confidence == do.NONE


def test_a_fo_holding_a_whole_state_gets_no_office() -> None:
    s, _ = by_id(person("fo", "field_officer", ("user_territory", "GJ", "", 1)))
    assert s["fo"].office is None and s["fo"].confidence == do.LOW


def test_held_areas_outside_the_load_are_named() -> None:
    s, _ = by_id(person("fo", "field_officer", ("user_territory", "HR", "Hisar", 1)))
    assert "Hisar (HR)" in s["fo"].notes and s["fo"].office is None


@pytest.mark.parametrize("role", ["admin_sales", "md_ceo", "account_manager", "state_coordinator"])
def test_head_office_and_functional_roles_stay(role: str) -> None:
    s, _ = by_id(person("x", role, *held_in("GJ", "Vadodara")))
    assert s["x"].office is None and s["x"].confidence == "" and not s["x"].needs_decision


def test_rows_needing_a_decision_come_first() -> None:
    facts = (
        person("sure", "field_officer", *held_in("GJ", "Rajkot"))
        + person("admin", "admin_sales")
        + person("unsure", "field_officer", *held_in("GJ", "Patan", "Morbi"))
        + person("nothing", "field_officer")
    )
    people, _ = do.suggest(facts)
    assert [p.user_id for p in people] == ["unsure", "nothing", "sure", "admin"]


# ── decisions ────────────────────────────────────────────────────────────────


def test_decisions() -> None:
    assert do.decided("", "Rajkot District, GJ") is None
    assert do.decided(None, None) is None
    assert do.decided(" ok ", "Rajkot District, GJ") == "Rajkot District, GJ"
    assert do.decided("Morbi District, GJ", "Rajkot District, GJ") == "Morbi District, GJ"
    with pytest.raises(do.DecisionError):
        do.decided("OK", "")


def test_the_catalogue_names_every_office_a_decision_may_use() -> None:
    g = do.Group("area", "North Area, GJ", "GJ", ("Patan",), "x")
    cat = do.catalogue(["GJ", "UP"], {"GJ": ["Patan"], "UP": ["Pratapgarh"]}, [g])
    assert cat["polysil hq"].kind == "hq"
    assert cat["gujarat state"] == do.Office("state", "Gujarat State", "GJ")
    assert cat["pratapgarh district, up"].district == "Pratapgarh"
    assert cat["north area, gj"].kind == "area"


def test_no_area_held_suggests_from_work() -> None:
    """Rule 16: the district with most of their work; medium only when it is clear."""
    clear = person(
        "a", "field_officer", ("lead_owned", "GJ", "Rajkot", 5), ("visit", "GJ", "Morbi", 1)
    )
    thin = person(
        "b", "field_officer", ("lead_owned", "GJ", "Rajkot", 2), ("lead_owned", "GJ", "Morbi", 1)
    )
    s, _ = by_id(clear + thin)
    assert s["a"].office is not None and s["a"].office.district == "Rajkot"
    assert s["a"].confidence == do.MEDIUM and "suggested from their work" in s["a"].notes
    assert s["b"].office is not None and s["b"].office.district == "Rajkot"
    assert s["b"].confidence == do.LOW


def test_work_outside_the_load_earns_no_office() -> None:
    s, _ = by_id(person("x", "field_officer", ("lead_owned", "HR", "Hisar", 9)))
    assert s["x"].office is None and s["x"].confidence == do.LOW
    assert "Hisar (HR)" in s["x"].notes and "outside this load" in s["x"].why


def test_someone_already_in_an_area_office_is_left_alone() -> None:
    f = do.Fact(
        "p",
        "P",
        "p@x.in",
        "field_officer",
        1,
        False,
        "o",
        "Gondal Field",
        "user_territory",
        "GJ",
        "Rajkot",
        1,
        0,
        "Gondal",
    )
    s, _ = by_id([f])
    assert s["p"].office is None and s["p"].confidence == "" and "already placed" in s["p"].why
