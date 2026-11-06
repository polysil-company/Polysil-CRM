"""The parameterless GET paths the live checks call, and the ones they skip (FS-065 rule 8).

`inventory.json` beside this file is the one list. The live suite reads it to decide
what to call on a box; `tests/api/test_live_inventory.py` guards it in the normal
suite: every such path in the schema is listed, and every path checked on production
runs inside a read-only transaction without failing.

Stdlib only, and nothing happens at import: the live suite runs on a machine that
talks to a box, and this module must load without the app's settings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PATH = Path(__file__).with_name("inventory.json")
ENVIRONMENTS = ("local", "staging", "production")


@dataclass(frozen=True)
class Entry:
    """One path. `query` values starting with `@` are resolved by the live suite at
    run time; `skip` maps an environment, or `all`, to the reason it is not called;
    `forbidden` lists the environments where 403 `insufficient_permission` is the
    expected answer. `unproven` is why the read-only guard could not exercise it."""

    path: str
    query: dict[str, str]
    public: bool
    skip: dict[str, str]
    forbidden: tuple[str, ...]
    unproven: str | None = None

    def skip_reason(self, environment: str) -> str | None:
        return self.skip.get("all") or self.skip.get(environment)


def load(path: Path = PATH) -> dict[str, Entry]:
    """The inventory, keyed by full path (`/api/v1/...`)."""
    raw: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return {
        p: Entry(path=p, query=dict(e.get("query", {})), public=bool(e.get("public", False)),
                 skip=dict(e.get("skip", {})), forbidden=tuple(e.get("forbidden", [])),
                 unproven=e.get("unproven"))
        for p, e in raw.items()
    }


def schema_paths(openapi: dict[str, Any]) -> set[str]:
    """Every GET in an OpenAPI document with no path parameter."""
    return {p for p, ops in openapi.get("paths", {}).items() if "get" in ops and "{" not in p}
