"""FS-038: scripts/whatsapp_webhook.py against a mock 11za. No database."""

# ruff: noqa: E501

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import httpx
import pytest
from pydantic import SecretStr

from api.config import Settings, get_settings

TOKEN = "Salted-fs038-token-0123456789"
SECRET = "fs038-webhook-secret-0123456789abcdefgh"
OLD = "fs038-older-secret-from-before-0123456789"
NOTHING = {"Message": "Cannot convert undefined or null to object", "Data": 0, "Status": 500,
           "IsSuccess": False}


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "whatsapp_webhook.py"
    spec = importlib.util.spec_from_file_location("whatsapp_webhook_script", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _settings() -> Settings:
    return get_settings().model_copy(update={
        "whatsapp_auth_token": SecretStr(TOKEN), "whatsapp_webhook_secret": SecretStr(SECRET)})


class Fake:
    """11za: answers `get` with a queue of replies, records every call."""

    def __init__(self, gets: list[httpx.Response | Exception]) -> None:
        self.gets = gets
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append((request.url.path, body))
        if request.url.path.endswith("/get"):
            reply = self.gets.pop(0) if len(self.gets) > 1 else self.gets[0]
            if isinstance(reply, Exception):
                raise reply
            return reply
        return httpx.Response(200, json={"IsSuccess": True})

    def paths(self) -> list[str]:
        return [p.rsplit("/", 1)[1] for p, _ in self.calls]


def _run(fake: Fake, argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    with httpx.Client(transport=httpx.MockTransport(fake.handler)) as http:
        code = _script().run(argv, _settings(), http)
    out = capsys.readouterr()
    return code, out.out + out.err


def test_register_builds_the_api_v1_urls_with_one_slash(capsys: pytest.CaptureFixture[str]) -> None:
    fake = Fake([httpx.Response(500, json=NOTHING)])
    code, out = _run(fake, ["register", "--base-url", "https://polysil-api.example.in/"], capsys)
    assert code == 0 and fake.paths() == ["get", "add", "get"]
    add = fake.calls[1][1]
    assert add["webhookUrl"] == f"https://polysil-api.example.in/api/v1/public/webhooks/whatsapp/{SECRET}/inbound"
    assert add["statusMessageWebhookUrl"].endswith(f"/whatsapp/{SECRET}/status")
    assert SECRET not in out and TOKEN not in out


def test_an_http_base_is_refused_before_any_call(capsys: pytest.CaptureFixture[str]) -> None:
    fake = Fake([httpx.Response(500, json=NOTHING)])
    code, out = _run(fake, ["register", "--base-url", "http://polysil-api.example.in"], capsys)
    assert code == 2 and fake.calls == [] and "https" in out


def test_register_refuses_over_an_existing_registration_without_replace(
        capsys: pytest.CaptureFixture[str]) -> None:
    existing = httpx.Response(200, json={"webhookUrl": f"https://old.example/x/whatsapp/{OLD}/inbound"})
    fake = Fake([existing])
    code, out = _run(fake, ["register", "--base-url", "https://polysil-api.example.in"], capsys)
    assert code == 2 and fake.paths() == ["get"]
    assert OLD not in out, "an older secret is masked by pattern"
    fake = Fake([existing])
    code, _ = _run(fake, ["register", "--base-url", "https://polysil-api.example.in", "--replace"], capsys)
    assert code == 0 and fake.paths() == ["get", "add", "get"]


def test_register_refuses_when_the_state_cannot_be_read(capsys: pytest.CaptureFixture[str]) -> None:
    """Code review F-3: a timeout used to read as nothing registered."""
    for reply in (httpx.ConnectTimeout("slow"), httpx.Response(502, text="bad gateway")):
        for extra in ([], ["--replace"]):
            fake = Fake([reply])
            code, out = _run(fake, ["register", "--base-url", "https://polysil-api.example.in", *extra], capsys)
            assert code == 2 and "add" not in fake.paths(), (reply, extra, out)


def test_escaped_slashes_and_the_token_are_masked(capsys: pytest.CaptureFixture[str]) -> None:
    body = ('{"webhookUrl":"https:\\/\\/h\\/whatsapp\\/' + OLD + '\\/inbound","authToken":"' + TOKEN + '"}')
    fake = Fake([httpx.Response(200, text=body)])
    code, out = _run(fake, ["get"], capsys)
    assert code == 0 and OLD not in out and TOKEN not in out


def test_delete_sends_its_type_and_prints_the_state_after(capsys: pytest.CaptureFixture[str]) -> None:
    fake = Fake([httpx.Response(500, json=NOTHING)])
    code, _ = _run(fake, ["delete", "--type", "statusMessage"], capsys)
    assert code == 0 and fake.paths() == ["delete", "get"]
    assert fake.calls[0][1] == {"authToken": TOKEN, "type": "statusMessage"}
