"""Which funnel stages a lead has reached, from its row alone (FS-024 rule 6, ISS-201)."""

from __future__ import annotations

import pytest

from api.services.reports import _reached


@pytest.mark.parametrize(("stage", "from_stage", "reached", "not_reached"), [
    ("qualified", None, ("contacted", "qualified"), ("quoted",)),
    ("won", None, ("contacted", "qualified", "quoted"), ()),
    ("lost", "quoted", ("contacted", "qualified", "quoted"), ()),
    ("lost", "new", (), ("contacted",)),
    # ISS-201: a dormant lead counts up to the stage it went dormant from, as a lost one does
    ("dormant", "qualified", ("contacted", "qualified"), ("quoted",)),
    ("dormant", None, (), ("contacted",)),
    ("merged", None, (), ("contacted",)),
])
def test_reached(stage: str, from_stage: str | None, reached: tuple[str, ...],
                 not_reached: tuple[str, ...]) -> None:
    for k in reached:
        assert _reached(stage, from_stage, k), (stage, from_stage, k)
    for k in not_reached:
        assert not _reached(stage, from_stage, k), (stage, from_stage, k)
