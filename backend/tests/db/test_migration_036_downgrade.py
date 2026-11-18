"""036 adds indexes to tables 033 owns. Downgrading to exactly 033 must remove them,
or the next upgrade fails with "relation already exists". A downgrade past 033 hides
this, because dropping the table drops its indexes."""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[2] / "api" / "db" / "migrations" / "versions"


def _module(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_index_036_adds_to_an_older_table_is_gone_after_its_downgrade() -> None:
    src = (VERSIONS / "036_rewards.py").read_text(encoding="utf-8")
    created_tables = set(re.findall(r"CREATE TABLE (\w+)", src))
    downgrade = inspect.getsource(_module("036_rewards").downgrade)
    loop = downgrade.split("DROP COLUMN {col}")[0].rsplit("for col in", 1)[-1]
    dropped_cols = set(re.findall(r'"(\w+)"', loop))
    dropped_cols |= set(re.findall(r"DROP COLUMN (\w+)", downgrade))
    missing = []
    index = r"CREATE (?:UNIQUE )?INDEX (\w+) ON (\w+) \(([^)]*)\)"
    for name, table, cols in re.findall(index, src):
        if table in created_tables:
            continue
        indexed = {c.strip().split()[0] for c in cols.split(",")}
        if not indexed & dropped_cols and name not in downgrade:
            missing.append(name)
    assert missing == []
