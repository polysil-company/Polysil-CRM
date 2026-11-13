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


@pytest.mark.parametrize("path", ["pyproject.toml", "alembic.ini", "api/config.py"])
def test_scaffold_files_exist(path: str) -> None:
    """The files any checkout of this backend has to carry."""
    assert (ROOT / path).exists(), f"missing {path}"


# The internal repository's operating documents. They are deliberately excluded
# from the scrubbed snapshot the shared repository receives, so their absence
# there is the design rather than a deletion - and CI, which runs on that
# snapshot, failed on both until this split existed.
#
# `docs/decisions` is the marker: it is internal-only too, so where it exists the
# checkout is the internal one and these must exist with it. Where it does not,
# there is nothing to guard.
INTERNAL_ONLY = ["CLAUDE.md", "AGENTS.md"]


@pytest.mark.parametrize("path", INTERNAL_ONLY)
def test_the_internal_checkout_keeps_its_operating_documents(path: str) -> None:
    if not (ROOT / "docs" / "decisions").is_dir():
        pytest.skip("a scrubbed checkout: the internal documents are removed on purpose")
    assert (ROOT / path).exists(), f"missing {path}"
