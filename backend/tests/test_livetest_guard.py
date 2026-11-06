"""FS-065 rule 25: the three live drivers in `scripts/livetest/` refuse any box but a
local stack, before their first request. Code review F2.

The drivers are top-level scripts that write on import, so they are parsed, never
imported or run."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import httpx
import pytest

LIVETEST = Path(__file__).resolve().parent.parent / "scripts" / "livetest"
sys.path.insert(0, str(LIVETEST))

from _guard import require_local  # noqa: E402

DRIVERS = ("lifecycle.py", "auth_and_create.py", "assign_edit_duplicates_admin.py")
BASE = "http://127.0.0.1:8100/api/v1"


def _transport(handler):  # type: ignore[no-untyped-def]
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    return httpx.MockTransport(answer), seen


def test_a_local_stack_passes_and_health_is_read_at_the_root() -> None:
    transport, seen = _transport(lambda r: httpx.Response(200, json={"environment": "local"}))
    require_local(BASE, transport=transport)
    assert seen == ["http://127.0.0.1:8100/health"]


@pytest.mark.parametrize("body", [{"environment": "staging"}, {"environment": "production"},
                                  {"status": "ok"}, ["local"]])
def test_any_other_answer_refuses(body: object) -> None:
    transport, _ = _transport(lambda r: httpx.Response(200, json=body))
    with pytest.raises(SystemExit) as stopped:
        require_local(BASE, transport=transport)
    assert "refused" in str(stopped.value)


def test_an_html_page_refuses() -> None:
    transport, _ = _transport(lambda r: httpx.Response(200, text="<html>Polysil</html>"))
    with pytest.raises(SystemExit, match="refused"):
        require_local(BASE, transport=transport)


def test_no_answer_refuses() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport, _ = _transport(down)
    with pytest.raises(SystemExit, match="ConnectError"):
        require_local(BASE, transport=transport)


def _first_action(tree: ast.Module) -> ast.stmt:
    """The first statement that is not a docstring, an import or a plain constant."""
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Constant):
            continue
        return node
    raise AssertionError("no executable statement")


@pytest.mark.parametrize("driver", DRIVERS)
def test_each_driver_calls_the_guard_before_anything_else(driver: str) -> None:
    tree = ast.parse((LIVETEST / driver).read_text(encoding="utf-8"))
    first = _first_action(tree)
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call), \
        f"{driver}: the first action is not the guard (line {first.lineno})"
    call = first.value
    assert isinstance(call.func, ast.Name) and call.func.id == "require_local", \
        f"{driver}: the first action is not require_local (line {first.lineno})"
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "BASE"
