"""The prod seed resets only the roles it declares (ISS-214)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "seed_prod", Path(__file__).resolve().parents[1] / "scripts" / "seed_prod.py")
assert _spec is not None and _spec.loader is not None
seed_prod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_prod)


def test_the_built_in_roles_keep_their_migration_grants() -> None:
    roles = {"intake": 1, "system": 2, "field_officer": 3, "dealer": 4}
    assert seed_prod.managed(roles) == {"field_officer": 3, "dealer": 4}


def test_every_declared_role_is_managed() -> None:
    declared = {code: i for i, (code, *_) in enumerate(seed_prod.ROLES)}
    assert seed_prod.managed({**declared, "intake": -1}) == declared
