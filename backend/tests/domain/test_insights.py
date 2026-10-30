"""FS-079: the insights' rules and wording. No database. Each threshold is tested
at, just below and just above."""

# ruff: noqa: E501  (inline cases)

from __future__ import annotations

from api.domain import insights as i


def test_lost_reason_rising_needs_ten_losses_each_side_and_five_points() -> None:
    labels = {"r1": "Price too high", "r2": "Went elsewhere"}
    row = i.lost_reason_rising({"r1": 38, "r2": 62}, {"r1": 22, "r2": 78}, labels)
    assert row is not None and row["title"] == "“Price too high” is now 38.0% of lost leads, up from 22.0%."
    assert row["link"] == {"report": "lost-leads", "group_by": "reason"}
    assert i.lost_reason_rising({"r1": 5, "r2": 4}, {"r1": 22, "r2": 78}, labels) is None, "9 losses"
    assert i.lost_reason_rising({"r1": 24, "r2": 76}, {"r1": 20, "r2": 80}, labels) is None, "a 4-point rise"
    assert i.lost_reason_rising({"r1": 25, "r2": 75}, {"r1": 20, "r2": 80}, labels) is not None, "exactly 5 points"


def test_the_threshold_compares_the_rounded_figures_shown() -> None:
    """EC-29: 4.96 points shows as 5.0 and counts as 5.0."""
    row = i.lost_reason_rising({"a": 3496, "b": 6504}, {"a": 30, "b": 70}, {"a": "A", "b": "B"})
    assert row is not None and row["figure"] == "35.0" and row["previous"] == "30.0"


def test_ties_break_by_share_then_name() -> None:
    """EC-28: deterministic."""
    labels = {"a": "Beta", "b": "Alpha"}
    row = i.lost_reason_rising({"a": 30, "b": 30, "c": 40}, {"a": 20, "b": 20, "c": 60}, {**labels, "c": "C"})
    assert row is not None and "Alpha" in row["title"]


def test_a_missing_label_and_a_quote_in_a_name() -> None:
    """EC-30."""
    row = i.lost_reason_rising({"x": 50, "y": 50}, {"x": 10, "y": 90}, {"x": None})
    assert row is not None and "“Unnamed reason”" in row["title"]
    row = i.lost_reason_rising({"x": 50, "y": 50}, {"x": 10, "y": 90}, {"x": 'Too "costly"'})
    assert row is not None and "“Too \"costly\"”" in row["title"]


def test_drop_off_never_names_unknown() -> None:
    """EC-27: unknown stays in the total."""
    row = i.drop_off_stage({"unknown": 50, "quoted": 30, "new": 20}, {})
    assert row is not None and row["title"] == "Most lost leads were lost at Quoted: 30.0% of them."
    assert row["previous"] is None
    assert i.drop_off_stage({"quoted": 9}, {}) is None
    assert i.drop_off_stage({"unknown": 12}, {}) is None


def test_source_best_and_worst() -> None:
    labels = {"a": "Website", "b": "Exhibition", "c": "Walk-in"}
    row = i.source_best_worst({"a": (40, 12), "b": (20, 2), "c": (9, 9)}, labels)
    assert row is not None
    assert row["title"] == "“Website” leads convert best (30.0%); “Exhibition” leads convert least (10.0%)."
    assert i.source_best_worst({"a": (10, 1), "b": (20, 2)}, labels) is None, "equal rates: no row"
    assert i.source_best_worst({"a": (40, 12)}, labels) is None, "one source"


def test_quotation_answers() -> None:
    row = i.quotation_answers((12, 8, 3), (10, 10, 0), 31)
    assert row is not None
    assert row["title"] == "60.0% of answered quotations were accepted, against 50.0% in the 31 days before. 3 more expired unanswered."
    assert i.quotation_answers((5, 4, 30), (10, 10, 0), 31) is None, "9 answered"


def test_quotation_discount() -> None:
    row = i.quotation_discount((2, 5), (8, 10))
    assert row is not None and row["figure"] == "40.0" and row["previous"] == "80.0"
    assert i.quotation_discount((2, 4), (8, 10)) is None


def test_first_contact_speed() -> None:
    row = i.first_contact_speed([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 50.0, -2.0], 3)
    assert row is not None
    assert row["title"] == "New leads were first contacted after a median of 5.0 hours. 3 waited over 48 hours."
    assert i.first_contact_speed([1.0] * 9, 0) is None
    row = i.first_contact_speed([1.0] * 10, 0)
    assert row is not None and row["title"] == "New leads were first contacted after a median of 1.0 hour."


def test_no_sentence_uses_an_em_dash() -> None:
    rows = [i.lost_reason_rising({"x": 50, "y": 50}, {"x": 10, "y": 90}, {"x": "A"}),
            i.drop_off_stage({"quoted": 30}, {}), i.quotation_discount((2, 5), (8, 10)),
            i.first_contact_speed([1.0] * 10, 2), i.quotation_answers((12, 8, 0), (10, 10, 0), 30)]
    assert all(r is not None and "—" not in r["title"] for r in rows)
