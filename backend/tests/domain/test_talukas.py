"""FS-087: the taluka load plan."""

# ruff: noqa: E501  (test data)

from __future__ import annotations

from api.domain.talukas import HeldDistrict, HeldTaluka, TalukaRow, plan_talukas

STATES = {"GJ", "MH"}
MORBI = HeldDistrict("d-morbi", "GJ", "Morbi")
KACHCHH = HeldDistrict("d-kachchh", "GJ", "Kachchh")
MAHESANA = HeldDistrict("d-mahesana", "GJ", "Mahesana")
KHARGONE = HeldDistrict("d-khargone", "MP", "Khargone (West Nimar)")
AURANGABAD_MH = HeldDistrict("d-aur-mh", "MH", "Aurangabad")
DISTRICTS = [MORBI, KACHCHH, MAHESANA, KHARGONE, AURANGABAD_MH]


def row(state: str, district: str, taluka: str, n: str = "1") -> TalukaRow:
    return TalukaRow(state, district, taluka, n)


def test_a_new_taluka_is_added_under_its_district() -> None:
    plan = plan_talukas([row("GJ", "Morbi", "Halvad")], STATES, DISTRICTS, [])
    assert [(a.row.taluka, a.district.id) for a in plan.adds] == [("Halvad", "d-morbi")]
    assert not plan.problems and not plan.skipped


def test_the_district_is_found_by_normalised_name_and_alias() -> None:
    plan = plan_talukas([row("GJ", "MORBI district", "Halvad", "1"),
                         row("GJ", "Kutch", "Mundra", "2")], STATES, DISTRICTS, [])
    assert {a.district.id for a in plan.adds} == {"d-morbi", "d-kachchh"}


def test_a_close_spelling_is_not_a_match() -> None:
    """Rule 3: match_districts would take 'Morbii'; a taluka loader must not."""
    plan = plan_talukas([row("GJ", "Morbii", "Halvad")], STATES, DISTRICTS, [])
    assert not plan.adds and plan.skipped[0][1] == "no district 'Morbii' in GJ"


def test_a_taluka_name_is_never_rewritten_by_the_district_aliases() -> None:
    """Rule 4: 'Mehsana' is an alias of the district Mahesana; as a taluka it stays."""
    plan = plan_talukas([row("GJ", "Mahesana", "Mehsana")], STATES, DISTRICTS, [])
    assert plan.adds[0].row.taluka == "Mehsana"


def test_a_missing_state_or_district_skips_only_that_row() -> None:
    plan = plan_talukas([row("HR", "Bhiwani", "Loharu", "1"), row("GJ", "Botad", "Ranpur", "2"),
                         row("GJ", "Morbi", "Halvad", "3")], STATES, DISTRICTS, [])
    assert [a.row.source_row for a in plan.adds] == ["3"]
    assert [why for _, why in plan.skipped] == ["no such state HR", "no district 'Botad' in GJ"]
    assert not plan.problems


def test_a_taluka_already_there_is_left_alone() -> None:
    held = [HeldTaluka("t1", "d-morbi", "halvad ")]
    plan = plan_talukas([row("GJ", "Morbi", "Halvad")], STATES, DISTRICTS, held)
    assert not plan.adds and plan.present[0][1].id == "t1"


def test_a_soft_deleted_taluka_is_reported_not_re_added() -> None:
    held = [HeldTaluka("t1", "d-morbi", "Halvad", deleted=True)]
    plan = plan_talukas([row("GJ", "Morbi", "Halvad")], STATES, DISTRICTS, held)
    assert not plan.adds and plan.deleted[0][1].id == "t1"


def test_a_live_copy_wins_over_a_deleted_one() -> None:
    held = [HeldTaluka("old", "d-morbi", "Halvad", deleted=True), HeldTaluka("new", "d-morbi", "Halvad")]
    plan = plan_talukas([row("GJ", "Morbi", "Halvad")], STATES, DISTRICTS, held)
    assert plan.present[0][1].id == "new" and not plan.deleted


def test_the_same_taluka_name_under_another_district_is_its_own() -> None:
    held = [HeldTaluka("t1", "d-kachchh", "Mandvi")]
    plan = plan_talukas([row("GJ", "Morbi", "Mandvi")], STATES, DISTRICTS, held)
    assert plan.adds and not plan.present


def test_a_repeated_row_stops_the_load() -> None:
    plan = plan_talukas([row("GJ", "Morbi", "Halvad", "1"), row("GJ", "Morbi", "HALVAD", "2")],
                        STATES, DISTRICTS, [])
    assert plan.problems == ["row 2: 'HALVAD' under Morbi is also row 1"]


def test_a_renamed_taluka_keeps_its_old_name_in_brackets_and_matches_either() -> None:
    """Rule 9: normalise drops bracketed text, so a rerun with the bare new name is a repeat."""
    plan = plan_talukas([row("GJ", "Morbi", "Bhairunda (Nasrullaganj)", "1"),
                         row("GJ", "Morbi", "Bhairunda", "2")], STATES, DISTRICTS, [])
    assert plan.problems and "row 2" in plan.problems[0]


def test_two_held_districts_that_are_one_by_name_stop_the_load() -> None:
    """Plan review C-2: a stray 'Kutch' beside 'Kachchh'."""
    districts = [*DISTRICTS, HeldDistrict("d-kutch", "GJ", "Kutch")]
    plan = plan_talukas([row("GJ", "Morbi", "Halvad")], STATES, districts, [])
    assert plan.problems == ["GJ: ['Kachchh', 'Kutch'] are one district by name"]


def test_the_same_district_name_in_two_states_is_two_districts() -> None:
    districts = [*DISTRICTS, HeldDistrict("d-aur-bihar", "BR", "Aurangabad")]
    plan = plan_talukas([row("MH", "Aurangabad", "Paithan")], STATES | {"BR"}, districts, [])
    assert not plan.problems and plan.adds[0].district.id == "d-aur-mh"


def test_a_blank_taluka_is_a_problem() -> None:
    plan = plan_talukas([row("GJ", "Morbi", " ")], STATES, DISTRICTS, [])
    assert plan.problems == ["row 1: no taluka name"]


def test_the_real_list_plans_cleanly() -> None:
    """data/masters/talukas.csv against its own districts: no problem, no repeat."""
    import csv
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "masters" / "talukas.csv"
    if not path.exists():
        import pytest
        pytest.skip("data/masters/talukas.csv is not in this checkout")
    with path.open(encoding="utf-8") as fh:
        rows = [row(r["state_code"], r["district"], r["taluka"], r["source_row"]) for r in csv.DictReader(fh)]
    with (root / "data" / "masters" / "districts.csv").open(encoding="utf-8-sig") as fh:
        listed = [HeldDistrict(f"{r['state_code']}-{i}", r["state_code"], r["district"])
                  for i, r in enumerate(csv.DictReader(fh))]
    plan = plan_talukas(rows, {d.state_code for d in listed}, listed, [])
    assert not plan.problems, plan.problems
    assert not plan.skipped, plan.skipped
    assert len(plan.adds) == len(rows)
