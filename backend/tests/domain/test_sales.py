"""When an order counts as a sale (FS-026): the mode and its date."""

from __future__ import annotations

import pytest

from api.domain import sales


def test_every_mode_has_a_date_and_the_default_is_approval() -> None:
    assert set(sales.DATE_OF) == set(sales.MODES)
    assert sales.DEFAULT == "approval"
    assert sales.DATE_OF["dispatch"] == "fully_dispatched_at"


@pytest.mark.parametrize("value", sales.MODES)
def test_a_known_mode_is_read(value: str) -> None:
    assert sales.mode_of(value) == value


@pytest.mark.parametrize("value", ["", "invoice", "Approval", None, 1])
def test_an_unknown_mode_is_refused_not_guessed(value: object) -> None:
    with pytest.raises(ValueError, match="unknown"):
        sales.mode_of(value)
