"""What the calculate request accepts and what it refuses, with no database.

Both cases here were found by the cross-vendor review in September, and both had
the same shape: a request that should have been a 422 was instead answered with a
**different calculation**, presented as the one that was asked for. That is worse
than an error, because nothing on the screen says so.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.subsidy import CalculateRequest, CropRequest, Line, Sump

HEAD = {"description": "Filter", "uom": "Nos.", "rate": "10000", "qty": "1"}


def test_a_crop_may_not_carry_head_lines() -> None:
    """FS-008 puts the head unit once on the request, not per crop. Ignored rather
    than refused, ten thousand rupees of head unit calculated as head cost 0.00."""
    with pytest.raises(ValidationError) as err:
        CropRequest(crop="POTATO", area="1.5", lateral_spacing="1.2", lines=[],
                    head_lines=[HEAD])
    assert err.value.errors()[0]["type"] == "extra_forbidden"
    assert err.value.errors()[0]["loc"] == ("head_lines",)


def test_a_sprinkler_request_names_a_set_size_only_from_the_list() -> None:
    """FS-056 rule 7: CG, RJ and UP take the set size from the request; GGRC sets it
    by the area band and says so (`pipe_size_ignored`). A size off the list is refused."""
    crops = [{"crop": "POTATO", "area": "1.0", "lateral_spacing": "1.2", "lines": []}]
    ok = CalculateRequest(system_type="sprinkler", crops=crops, nozzle="plastic", pipe_size_mm=90)
    assert ok.pipe_size_mm == 90
    with pytest.raises(ValidationError) as err:
        CalculateRequest(system_type="sprinkler", crops=crops, nozzle="plastic", pipe_size_mm=80)
    assert [e["loc"] for e in err.value.errors()] == [("pipe_size_mm",)]


@pytest.mark.parametrize("model, field, kwargs", [
    (Line, "rate", {"description": "X", "uom": "m", "qty": "1"}),
    (Line, "qty", {"description": "X", "uom": "m", "rate": "10"}),
])
def test_an_oversized_decimal_is_a_field_error_not_a_crash(
        model: type, field: str, kwargs: dict[str, str]) -> None:
    """`1E26` is finite and passes `gt=0`, and quantizing it exceeds the decimal
    context. That raised `InvalidOperation` out of the validator, which the API
    answers as a 500 while promising a 422 naming the field."""
    with pytest.raises(ValidationError) as err:
        model(**kwargs, **{field: "1E26"})
    problem = err.value.errors()[0]
    assert problem["loc"] == (field,)
    assert "may not exceed" in problem["msg"]


def test_the_shapes_that_are_still_accepted() -> None:
    """The refusals above must not have narrowed anything legitimate."""
    crop = CropRequest(crop="POTATO", area="1.5", lateral_spacing="1.2",
                       lines=[Line(description="Lateral", uom="Mtr.", rate="18.5", qty="100")])
    assert crop.area == pytest.approx(1.5)
    request = CalculateRequest(system_type="drip", crops=[crop], head_lines=[Line(**HEAD)],
                               sump=Sump(rate_per_ha="0"))
    assert len(request.head_lines) == 1
