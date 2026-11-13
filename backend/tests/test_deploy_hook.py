"""The frontend webhook receiver (infra/frontend/hook.py), from the PR 25 review:
a failed build must not wedge the queue, and an unsigned caller must not hold a
thread or get a traceback instead of an answer."""

from __future__ import annotations

import http.client
import importlib.util
import socket
import threading
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_HOOK = Path(__file__).resolve().parents[1] / "infra/frontend/hook.py"


@pytest.fixture
def hook(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("WEBHOOK_SECRET", "test-secret")
    spec = importlib.util.spec_from_file_location("frontend_hook_under_test", _HOOK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def server(hook: ModuleType) -> Iterator[tuple[ModuleType, int]]:
    hook.Hook.timeout = 0.5
    srv = hook.ThreadingHTTPServer(("127.0.0.1", 0), hook.Hook)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield hook, srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_a_build_that_cannot_start_does_not_wedge_the_queue(
        hook: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any, **__: Any) -> None:
        raise OSError("no space left on device")
    monkeypatch.setattr(hook.subprocess, "run", boom)
    monkeypatch.setattr(hook, "LOG", str(Path(__file__)))  # any file that opens
    hook._state.update(running=True, pending=True)
    hook._run_builds()
    assert hook._state["running"] is False
    assert hook._state["last"].startswith("error:")


def _post(port: int, headers: dict[str, str], body: bytes = b"{}") -> int:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/hooks/github")
    for k, v in headers.items():
        conn.putheader(k, v)
    conn.endheaders(body)
    status = conn.getresponse().status
    conn.close()
    return status


def test_a_bad_length_is_a_400(server: tuple[ModuleType, int]) -> None:
    _, port = server
    assert _post(port, {"Content-Length": "abc"}, b"") == 400


def test_a_non_ascii_signature_is_a_401(server: tuple[ModuleType, int]) -> None:
    _, port = server
    raw = socket.create_connection(("127.0.0.1", port), timeout=5)
    raw.sendall(b"POST /hooks/github HTTP/1.1\r\nHost: x\r\nContent-Length: 2\r\n"
                b"X-Hub-Signature-256: sha256=\xe9\r\n\r\n{}")
    reply = raw.recv(64)
    raw.close()
    assert reply.startswith(b"HTTP/1.0 401") or reply.startswith(b"HTTP/1.1 401"), reply


def test_the_handler_has_a_socket_timeout(hook: ModuleType) -> None:
    """Without one, a client that sends a length and stalls holds a thread for good."""
    assert 0 < (hook.Hook.timeout or 0) <= 30


def test_a_stalled_body_gives_up_its_thread(server: tuple[ModuleType, int]) -> None:
    _, port = server
    raw = socket.create_connection(("127.0.0.1", port), timeout=5)
    raw.sendall(b"POST /hooks/github HTTP/1.1\r\nHost: x\r\nContent-Length: 1000\r\n\r\n{}")
    raw.settimeout(3)
    got = raw.recv(64)  # the server times out and answers or closes; either way it is back
    raw.close()
    assert got == b"" or b"401" in got


def test_an_oversized_body_is_refused(server: tuple[ModuleType, int]) -> None:
    hook, port = server
    assert _post(port, {"Content-Length": str(hook.MAX_BODY + 1)}, b"") == 413
