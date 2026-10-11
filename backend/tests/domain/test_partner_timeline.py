"""ISS-107: the partner's reading of a lead's history, as a pure function (GAP-284)."""

from __future__ import annotations

import pytest

from api.domain.leads import partner_timeline_entry


@pytest.mark.parametrize("kind", ["lead.duplicate_flagged", "lead.duplicate_dismissed",
                                  "lead.merged", "lead.note_added"])
def test_staff_entries_are_hidden(kind: str) -> None:
    assert partner_timeline_entry(kind, {"note": "x"}, own=False) is None


def test_own_words_always_stay() -> None:
    payload = {"note": "visited", "lost_note": "mine"}
    assert partner_timeline_entry("lead.note_added", payload, own=True) == payload
    assert partner_timeline_entry("lead.stage_changed", payload, own=True) == payload


@pytest.mark.parametrize("kind", ["lead.stage_changed", "lead.reopened"])
def test_a_stage_change_keeps_the_stages_and_drops_the_words(kind: str) -> None:
    payload = {"from": "new", "to": "lost", "lost_reason_id": "r", "lost_reason": "Price",
               "lost_note": "n", "note": "m", "actor_name": "A"}
    assert partner_timeline_entry(kind, payload, own=False) == {"from": "new", "to": "lost",
                                                                 "actor_name": "A"}


def test_everything_else_passes_unchanged() -> None:
    payload = {"to": "x"}
    assert partner_timeline_entry("lead.assigned", payload, own=False) is payload
