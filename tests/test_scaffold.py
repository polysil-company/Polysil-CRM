"""The scaffold's own checks. These run without a database."""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_domain_never_imports_sqlalchemy() -> None:
    """CLAUDE.md 4.1 rule 1. Pure logic stays fast and testable."""
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "api" / "domain").rglob("*.py")
        if re.search(r"^\s*(from|import)\s+sqlalchemy", p.read_text(encoding="utf-8"), re.M)
    ]
    assert not offenders, f"domain/ imports SQLAlchemy: {offenders}"


def test_sessions_are_created_only_in_deps_and_worker() -> None:
    """CLAUDE.md 4.1 rule 2. SET LOCAL claim propagation depends on one owner."""
    allowed = {"api/deps.py", "api/db/session.py", "tests/conftest.py"}
    offenders = []
    for p in list((ROOT / "api").rglob("*.py")) + list((ROOT / "worker").rglob("*.py")):
        rel = p.relative_to(ROOT).as_posix()
        if rel in allowed or rel.startswith("worker/"):
            continue
        if "async_session_factory(" in p.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, f"session created outside deps.py and worker/: {offenders}"


@pytest.mark.parametrize(
    "path",
    ["CLAUDE.md", "AGENTS.md", "pyproject.toml", "alembic.ini", "api/config.py"],
)
def test_scaffold_files_exist(path: str) -> None:
    assert (ROOT / path).exists(), f"missing {path}"
