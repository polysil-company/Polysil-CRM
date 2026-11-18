"""FS-045: the action catalogue and the matcher, without a database."""

from __future__ import annotations

from typing import get_args

from api.domain import assistant as a

ALL = {p for x in a.CATALOGUE for alt in x.requires for p in alt}


def test_every_screen_key_is_declared_and_used_once_per_action() -> None:
    screens = set(get_args(a.Screen))
    assert all(x.screen in screens for x in a.CATALOGUE)
    keys = [x.key for x in a.CATALOGUE]
    assert len(keys) == len(set(keys))


def test_words_in_any_order_by_prefix_and_case() -> None:
    assert [x.key for x in a.match("new quote", ALL)] == ["quotation.create"]
    assert [x.key for x in a.match("QUOTE NEW", ALL)] == ["quotation.create"]
    assert "masters.holidays" in [x.key for x in a.match("holi", ALL)]
    assert a.match("zebra", ALL) == []


def test_a_title_hit_ranks_above_a_keyword_hit() -> None:
    keys = [x.key for x in a.match("dispatch", ALL)]
    assert keys[0] == "dispatch.record"


def test_an_action_needs_one_of_its_permission_sets() -> None:
    assert [x.key for x in a.match("approve", {("quotations", "approve")})] == ["approvals"]
    assert [x.key for x in a.match("approve", {("sales_orders", "approve")})] == ["approvals"]
    assert a.match("approve", {("sales_orders", "view")}) == []


def test_staff_only_actions_are_hidden_from_a_dealer() -> None:
    held = {("leads", "edit"), ("leads", "create"), ("leads", "view")}
    assert "lead.duplicates" in [x.key for x in a.match("merge", held)]
    assert a.match("merge", held, staff=False) == []


def test_the_empty_query_is_the_ranked_starter_set() -> None:
    keys = [x.key for x in a.match("", ALL)]
    assert keys[:2] == ["lead.create", "lead.list"]
    assert [x.key for x in a.match(None, {("leads", "view")})] == ["lead.list"]


def test_what_the_text_looks_like() -> None:
    for q in ("+91 98765 43210", "098765 43210", "9876543210", "919876543210"):
        assert a.mobile_digits(q) == "9876543210", q
    assert a.mobile_digits("987") is None and a.mobile_digits("ram") is None
    assert a.looks_like_document("pol/gj/2026-27/00123") and a.looks_like_document("SO/GJ")
    assert not a.looks_like_document("polysil")
    assert a.serial("123") == "00123" and a.serial("1234567") is None
    assert a.name_text("રામ") == "રામ" and a.name_text("ab") is None and a.name_text("  ") is None
    assert a.has_control("ab\x00") and not a.has_control("ab")
