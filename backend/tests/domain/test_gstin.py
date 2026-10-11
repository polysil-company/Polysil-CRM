"""FS-051: the GSTIN read from itself."""

from __future__ import annotations

import pytest

from api.domain import gstin


@pytest.mark.parametrize("good", ["27AAPFU0939F1ZV", "29AAGCB7383J1Z4"])
def test_known_gstins_are_valid(good: str) -> None:
    facts = gstin.read(good)
    assert facts.valid, facts
    assert facts.state_code == good[:2] and facts.pan == good[2:12]


def test_one_changed_character_fails_the_check() -> None:
    bad = gstin.read("27AAPFU0939F1ZW")
    assert not bad.valid and bad.reason == "the check character does not match"


@pytest.mark.parametrize(("raw", "reason"), [
    ("27AAPFU0939F1Z", "not the shape of a GSTIN"),
    ("27aapfu0939f1zv ", None),            # spaces and case are forgiven
    ("00AAPFU0939F1ZV", "not a GST state code"),
    ("27AAPFU0939F1YV", "not the shape of a GSTIN"),
])
def test_shape_case_and_state(raw: str, reason: str | None) -> None:
    facts = gstin.read(raw)
    assert facts.reason == reason, facts


def test_every_check_character_round_trips() -> None:
    """For any 14-character prefix, appending its check character reads valid, and
    any other final character does not."""
    prefix = "24ABCDE1234F1Z"
    good = prefix + gstin.check_character(prefix)
    assert gstin.read(good).valid
    for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if ch != good[-1]:
            assert not gstin.read(prefix + ch).valid
