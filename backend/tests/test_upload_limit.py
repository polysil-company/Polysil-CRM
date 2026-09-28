"""The attachment size cap (FS-015 rule 10, plan review B-2), at the ASGI level:
refused before the application reads anything, with or without a length."""

from __future__ import annotations

import json
from typing import Any

import pytest

from api.upload_limit import BODY_LIMIT, BodyTooLarge, UploadLimit

PATH = "/api/v1/complaints/7b1c7c3e-8a51-4f53-9d93-2a8f5f5c0e11/attachments"


class _App:
    """Reads the whole body, as FastAPI's form parsing does."""

    def __init__(self) -> None:
        self.called = False
        self.read = 0

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.called = True
        while True:
            message = await receive()
            self.read += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _scope(path: str = PATH, method: str = "POST", length: int | None = None) -> dict[str, Any]:
    headers = [(b"content-type", b"multipart/form-data; boundary=x")]
    if length is not None:
        headers.append((b"content-length", str(length).encode()))
    return {"type": "http", "method": method, "path": path, "headers": headers}


def _receiver(chunks: list[bytes]) -> Any:
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
             for i, c in enumerate(chunks)]

    async def receive() -> dict[str, Any]:
        return queue.pop(0)
    return receive


class _Sent:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


async def test_a_declared_length_over_the_cap_is_refused_before_the_app() -> None:
    app, sent = _App(), _Sent()
    await UploadLimit(app)(_scope(length=BODY_LIMIT + 1), _receiver([b"x"]), sent)
    assert not app.called, "nothing reached the application"
    assert sent.messages[0]["status"] == 413
    assert json.loads(sent.messages[1]["body"])["error"]["code"] == "attachment_too_large"


async def test_without_a_length_the_count_stops_it_mid_body() -> None:
    app, sent = _App(), _Sent()
    chunk = b"x" * (1024 * 1024)
    with pytest.raises(BodyTooLarge):
        await UploadLimit(app)(_scope(), _receiver([chunk] * 12), sent)
    assert app.read <= BODY_LIMIT, "the application never read past the cap"


async def test_a_ten_megabyte_file_with_its_framing_passes() -> None:
    """Delta B-2: the cap leaves room for the multipart framing around a 10 MB file."""
    app, sent = _App(), _Sent()
    body = [b"x" * (10 * 1024 * 1024), b"y" * 2048]
    await UploadLimit(app)(_scope(length=sum(map(len, body))), _receiver(body), sent)
    assert app.called and sent.messages[0]["status"] == 201


@pytest.mark.parametrize(("path", "method"), [("/api/v1/complaints", "POST"), (PATH, "GET"),
                                              ("/api/v1/leads", "POST")])
async def test_other_routes_are_untouched(path: str, method: str) -> None:
    app, sent = _App(), _Sent()
    await UploadLimit(app)(_scope(path, method, length=BODY_LIMIT * 3), _receiver([b"x"]), sent)
    assert app.called


async def test_through_the_real_app_a_streamed_body_gets_the_envelope() -> None:
    """Executed, not reasoned (plan review): FastAPI reads the form before any
    dependency, so the 413 comes back in the envelope without a session opening."""
    import httpx

    from api.main import create_app

    async def body() -> Any:
        yield (b"--x\r\nContent-Disposition: form-data; name=\"file\"; "
               b"filename=\"a.jpg\"\r\n\r\n")
        for _ in range(12):
            yield b"x" * (1024 * 1024)
        yield b"\r\n--x--\r\n"

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(PATH, content=body(),
                              headers={"content-type": "multipart/form-data; boundary=x",
                                       "authorization": "Bearer x", "idempotency-key": "k"})
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "attachment_too_large"
