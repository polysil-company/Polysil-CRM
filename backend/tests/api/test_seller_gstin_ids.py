"""Release review A-3: the seller GSTIN routes take a strict uuid, as every other router."""

from __future__ import annotations

from api.main import app
from api.schemas.leads import UUID_RE


def test_the_gstin_and_lut_ids_are_strict_uuids() -> None:
    paths = app.openapi()["paths"]
    params = [p for path, ops in paths.items() if path.startswith("/api/v1/seller-gstins/")
              for op in ops.values() for p in op.get("parameters", []) if p["in"] == "path"]
    assert params, "the routes exist"
    assert {p["schema"]["pattern"] for p in params} == {UUID_RE}
