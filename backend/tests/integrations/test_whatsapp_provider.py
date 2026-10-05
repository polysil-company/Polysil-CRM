"""The 11za adapter against a fake transport (FS-007 section 10, the adapter row).

Nothing here touches the network or the database. The request shape, the
classification of every response the collection and the reviews named, and the
one rule that matters most: the token and the code never leave the adapter, even
when the provider echoes the whole request back.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Any

import httpx
import pytest

from api.config import Settings
from api.integrations.messages import (
    TEMPLATE_AUTH_OTP,
    TEMPLATE_LEAD_ACK,
    TEMPLATE_QUOTATION_SHARE,
    TEMPLATES,
    render,
    template_values,
)
from api.integrations.whatsapp import get_provider
from api.integrations.whatsapp.check import check_templates, run
from api.integrations.whatsapp.elevenza import ElevenZaProvider, classify
from api.integrations.whatsapp.mock import MockProvider
from api.integrations.whatsapp.provider import (
    OutboundMessage,
    Outcome,
    ProviderResult,
    scrub,
    scrub_body,
    to_sendto,
)

TOKEN = "U2FsdGVkX1-the-account-token-never-seen"
CODE = "482913"

OTP = OutboundMessage(channel="whatsapp", recipient="919876543210", template_key=TEMPLATE_AUTH_OTP,
                      payload={"code": CODE}, reference="row-1")
ACK = OutboundMessage(channel="whatsapp", recipient="+919876543210", template_key=TEMPLATE_LEAD_ACK,
                      payload={"farmer_name": "Ram\nSham   Patel",
                               "inquiry_no": "POL/GJ/2026-27/00007"},
                      reference="row-2")


def _settings(**over: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://u:p@127.0.0.1:6432/appdb",
        "jwt_secret": "x" * 32,
        "whatsapp_provider": "11za",
        "whatsapp_auth_token": TOKEN,
        "whatsapp_send_timeout": 2.0,
    }
    base.update(over)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def _json(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, json=body)


async def _send(handler: Any, msg: OutboundMessage = OTP,
                **over: Any) -> tuple[ProviderResult, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def _handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        out = handler(request)
        if isinstance(out, Exception):
            raise out
        return out  # type: ignore[no-any-return]

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handle)) as client:
        provider = ElevenZaProvider(_settings(**over), client)
        result = await provider.send(msg)
    return result, seen


ACCEPTED_NO_ID = {"Message": "Message Sent", "Data": 1, "Status": 200, "IsSuccess": True}
TOKEN_ERROR = {"Message": "Invalid authToken! Please try again with valid Token", "Data": 0,
               "Status": 400, "IsSuccess": False}


# ── the request ──────────────────────────────────────────────────────────────

async def test_the_otp_request_carries_the_code_twice_and_our_reference() -> None:
    result, seen = await _send(lambda r: _json(200, ACCEPTED_NO_ID),
                               whatsapp_origin_website="crm.polysil.in")
    assert result.outcome is Outcome.ACCEPTED and result.provider_msg_id is None
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/apis/template/sendTemplate"
    assert body["sendto"] == "919876543210"
    assert body["templateName"] == "polysil_auth_otp" and body["language"] == "en"
    assert body["data"] == [CODE] and body["buttonValue"] == CODE
    assert body["tags"] == "row-1" and body["originWebsite"] == "crm.polysil.in"
    assert body["authToken"] == TOKEN


async def test_the_acknowledgement_is_normalised_and_has_no_button() -> None:
    _, seen = await _send(lambda r: _json(200, ACCEPTED_NO_ID), msg=ACK)
    body = json.loads(seen[0].content)
    assert body["sendto"] == "919876543210", "the plus was not stripped"
    assert body["templateName"] == "polysil_lead_ack"
    assert body["data"] == ["Ram Sham Patel", "POL/GJ/2026-27/00007"]
    assert "buttonValue" not in body and "originWebsite" not in body


def test_values_are_one_line_and_bounded() -> None:
    long_name = "મહેશ " * 60   # a Gujarati name repeated past the cap
    values, button = template_values(TEMPLATE_LEAD_ACK,
                                     {"farmer_name": "  a\t\tb\n\nc  ", "inquiry_no": long_name})
    assert values[0] == "a b c" and len(values[1]) == 100 and button is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("+91 98765 43210", "919876543210"),
    ("919876543210", "919876543210"),
    ("0919876543210", None),
    ("98765", None),
    ("not a number", None),
])
def test_recipients_become_digits_or_nothing(raw: str, expected: str | None) -> None:
    assert to_sendto(raw) == expected


async def test_a_recipient_that_is_not_a_number_is_permanent_before_any_send() -> None:
    result, seen = await _send(lambda r: _json(200, ACCEPTED_NO_ID),
                               msg=OutboundMessage("whatsapp", "nope", TEMPLATE_AUTH_OTP,
                                                   {"code": CODE}, "row-3"))
    assert result.outcome is Outcome.PERMANENT and seen == []


# ── classification, rule 6 ───────────────────────────────────────────────────

async def test_accepted_with_an_id_keeps_it() -> None:
    result, _ = await _send(lambda r: _json(200, {"status": 200, "message": "Message Sent",
                                                  "data": {"messageId": "wamid.abc"},
                                                  "IsSuccess": True}))
    assert result.outcome is Outcome.ACCEPTED and result.provider_msg_id == "wamid.abc"


@pytest.mark.parametrize(("response", "outcome"), [
    (_json(200, TOKEN_ERROR), Outcome.TRANSIENT),
    (_json(401, {"IsSuccess": False, "Message": "Unauthorized", "Status": 401}), Outcome.TRANSIENT),
    (_json(429, {"IsSuccess": False, "Message": "Too many requests", "Status": 429}),
     Outcome.TRANSIENT),
    (httpx.Response(503, text="upstream unavailable"), Outcome.TRANSIENT),
    (_json(200, {"IsSuccess": False, "Message": "Invalid phone number", "Status": 400}),
     Outcome.PERMANENT),
    (_json(200, {"IsSuccess": False, "Message": "Template not found", "Status": 400}),
     Outcome.PERMANENT),
    (_json(200, {"IsSuccess": False, "Message": "Something odd happened", "Status": 400}),
     Outcome.REFUSED),
    (httpx.Response(200, text="<html>not json</html>"), Outcome.REFUSED),
    (httpx.Response(404, text="no such route"), Outcome.REFUSED),
])
async def test_responses_are_classified_on_the_body(response: httpx.Response,
                                                    outcome: Outcome) -> None:
    result, _ = await _send(lambda r: response)
    assert result.outcome is outcome, result


@pytest.mark.parametrize("exc", [
    httpx.ReadTimeout("read timed out"),
    httpx.ConnectError("connection refused; body was authToken=" + TOKEN),
])
async def test_transport_failures_are_transient_and_carry_only_the_class_name(
        exc: Exception) -> None:
    result, _ = await _send(lambda r: exc)
    assert result.outcome is Outcome.TRANSIENT
    assert result.error == type(exc).__name__


async def test_a_send_that_outlives_its_deadline_is_transient() -> None:
    import asyncio

    async def _slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return _json(200, ACCEPTED_NO_ID)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_slow)) as client:
        provider = ElevenZaProvider(_settings(whatsapp_send_timeout=0.05), client)
        result = await provider.send(OTP)
    assert result.outcome is Outcome.TRANSIENT and result.error == "TimeoutError"


# ── rule 5: the token and the code never leave ───────────────────────────────

async def test_an_echoing_provider_leaks_nothing_into_the_error() -> None:
    def _echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"IsSuccess": False, "Status": 400,
                                         "Message": "bad request: " + request.content.decode()})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo)) as client:
        provider = ElevenZaProvider(_settings(), client)
        result = await provider.send(OTP)
    assert result.outcome is Outcome.REFUSED
    assert result.error is not None
    assert TOKEN not in result.error and CODE not in result.error
    assert provider.last_response is not None
    assert TOKEN not in provider.last_response[1] and CODE not in provider.last_response[1]


def test_scrub_replaces_every_secret_and_bounds_the_text() -> None:
    out = scrub("token=" + TOKEN + " code=" + CODE + " " + "x" * 1000, [TOKEN, CODE, ""])
    assert TOKEN not in out and CODE not in out and out.startswith("token=*** code=***")
    assert len(out) == 500


def test_classify_reads_the_documented_shape() -> None:
    assert classify(200, json.dumps(ACCEPTED_NO_ID), []).outcome is Outcome.ACCEPTED
    assert classify(200, json.dumps(TOKEN_ERROR), []).outcome is Outcome.TRANSIENT
    assert classify(200, "", []).outcome is Outcome.REFUSED


# ── the listing and the check, rule 13 ───────────────────────────────────────

async def test_the_listing_pages_until_a_short_page() -> None:
    pages: list[int] = []

    def _list(request: httpx.Request) -> httpx.Response:
        page = json.loads(request.content)["page"]
        pages.append(page)
        count = 100 if page == 1 else 3
        rows = [{"name": f"t{page}_{i}", "status": "APPROVED"} for i in range(count)]
        return _json(200, {"IsSuccess": True, "data": rows})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_list)) as client:
        rows = await ElevenZaProvider(_settings(), client).list_templates()
    assert len(rows) == 103 and pages == [1, 2]


async def test_the_mock_account_passes_the_check() -> None:
    settings = _settings(whatsapp_provider="mock", whatsapp_auth_token=None)
    assert await check_templates(MockProvider(), settings) == []


class _Listing:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def send(self, msg: OutboundMessage) -> ProviderResult:
        raise AssertionError("the check never sends")

    async def list_templates(self) -> list[dict[str, object]]:
        return self.rows


async def test_the_check_names_what_is_wrong() -> None:
    settings = _settings()
    problems = await check_templates(_Listing([
        {"name": "polysil_auth_otp", "status": "PENDING", "language": "en",
         "body": "{{1}} is your verification code.", "category": "AUTHENTICATION"},
        {"name": "polysil_lead_ack", "status": "APPROVED", "language": "gu",
         "body": "Thank you {{1}}. Enquiry {{2}} received, {{3}}.", "category": "UTILITY"},
    ]), settings)
    assert any("not approved" in p for p in problems)
    assert any("'gu'" in p for p in problems)
    assert any("takes 3 values" in p for p in problems)
    assert len(problems) == 3

    missing = await check_templates(_Listing([]), settings)
    assert missing == ["auth.otp: template 'polysil_auth_otp' is not on the account",
                       "lead_ack: template 'polysil_lead_ack' is not on the account"]


def _echo_listing(request: httpx.Request) -> httpx.Response:
    """A listing whose language field echoes the whole request: the token in mixed
    case, in a field the check does not case-fold. The first version of this test
    echoed into the status field, which the check lowercases, so the mixed-case
    token could never appear and the assertion held with the scrub removed (code
    review F-2, executed)."""
    return httpx.Response(200, json={"IsSuccess": True, "data": [
        {"name": "polysil_auth_otp", "status": "APPROVED",
         "language": "echo " + request.content.decode()}]})


def _clean(text: str, *secrets: str) -> bool:
    lower = text.lower()
    return all(s.lower() not in lower for s in secrets)


async def test_check_templates_returns_nothing_raw() -> None:
    """Code review F-1: the worker logs the returned list at startup, so the scrub
    lives inside check_templates, for every caller."""
    settings = _settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo_listing)) as client:
        problems = await check_templates(ElevenZaProvider(settings, client), settings)
    assert any("is in" in p for p in problems), problems
    assert all(_clean(p, TOKEN) for p in problems), problems


async def test_without_the_scrub_the_token_would_show(monkeypatch: pytest.MonkeyPatch) -> None:
    """The assertion above is worth something only if the unscrubbed line trips it."""
    import api.integrations.whatsapp.check as chk

    monkeypatch.setattr(chk, "scrub", lambda t, s: t)
    settings = _settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo_listing)) as client:
        problems = await check_templates(ElevenZaProvider(settings, client), settings)
    assert not all(_clean(p, TOKEN) for p in problems)


async def test_the_check_command_prints_nothing_raw(capsys: pytest.CaptureFixture[str]) -> None:
    """Rule 19: an echoing provider, and the printed lines carry no token."""
    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo_listing)) as client:
        code = await run(_settings(), client)
    out = capsys.readouterr()
    assert code == 1
    assert _clean(out.out + out.err, TOKEN), out.out
    assert "is in" in out.out and "not on the account" in out.out


def _smoke_module() -> Any:
    root = pathlib.Path(__file__).resolve().parents[2]
    path = root / "scripts" / "livetest" / "whatsapp_smoke.py"
    spec = importlib.util.spec_from_file_location("whatsapp_smoke", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_the_smoke_script_prints_nothing_raw(capsys: pytest.CaptureFixture[str]) -> None:
    """Rule 19 for the one script that sends for real (code review F-5): an echoing
    provider, and neither the token nor the sample values reach stdout."""
    smoke = _smoke_module()

    def _echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"IsSuccess": False, "Status": 400,
                                         "Message": "bad request: " + request.content.decode()})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo)) as client:
        code = await smoke.run(_settings(), client, to="919876543210", template=TEMPLATE_LEAD_ACK)
    out = capsys.readouterr()
    assert code == 1
    assert _clean(out.out + out.err, TOKEN, "Smoke Test", "POL/GJ/2026-27/00000"), out.out
    assert "outcome refused" in out.out


def test_every_template_has_a_mock_body() -> None:
    """Code review F-3: a key in TEMPLATES with no body made the mock raise, and a
    raising provider stopped the drain. The mock no longer raises; this keeps the
    registry and the bodies together as the ten later templates arrive."""
    for key, spec in TEMPLATES.items():
        assert render(key, dict.fromkeys(spec.params, "x"))


def test_get_provider_needs_a_client_for_the_real_thing() -> None:
    assert isinstance(get_provider(_settings(whatsapp_provider="mock", whatsapp_auth_token=None)),
                      MockProvider)
    with pytest.raises(ValueError, match="HTTP client"):
        get_provider(_settings())


# ── the cross-vendor review of the code ──────────────────────────────

SLASHED = "U2FsdGVkX1/abc+def/ghi="   # a base64 token carries slashes


async def test_a_json_escaped_token_is_scrubbed_from_the_diagnostics() -> None:
    """P1: a provider that writes `/` as `\\/` hid the token from a literal
    scrub of the raw text; `last_response`, and so the smoke script, kept it."""
    def _echo(request: httpx.Request) -> httpx.Response:
        escaped = SLASHED.replace("/", "\\/")
        return httpx.Response(400, content=('{"IsSuccess": false, "Status": 400, '
                                            '"Message": "bad: authToken=' + escaped + '"}'),
                              headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo)) as client:
        provider = ElevenZaProvider(_settings(whatsapp_auth_token=SLASHED), client)
        result = await provider.send(OTP)
    assert result.error is not None and SLASHED not in result.error
    assert provider.last_response is not None
    text = provider.last_response[1]
    assert SLASHED not in text and SLASHED.replace("/", "\\/") not in text, text


def test_scrub_covers_every_form_of_a_secret() -> None:
    body = json.dumps({"m": "x " + SLASHED + " y"})           # plain
    escaped = body.replace("/", "\\/")                       # a PHP-style encoder
    assert SLASHED not in scrub(body, [SLASHED])
    assert SLASHED.replace("/", "\\/") not in scrub(escaped, [SLASHED])
    assert "%2F" not in scrub(SLASHED.replace("/", "%2F"), [SLASHED])
    assert SLASHED not in scrub_body(escaped, [SLASHED])


async def test_the_smoke_script_prints_no_escaped_token(capsys: pytest.CaptureFixture[str]) -> None:
    smoke = _smoke_module()

    def _echo(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, content=('{"IsSuccess": false, "Status": 400, "Message": "'
                                            + request.content.decode().replace("/", "\\/") + '"}'),
                              headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(_echo)) as client:
        code = await smoke.run(_settings(whatsapp_auth_token=SLASHED), client,
                               to="919876543210", template=TEMPLATE_AUTH_OTP)
    out = capsys.readouterr()
    assert code == 1
    assert _clean(out.out + out.err, SLASHED, SLASHED.replace("/", "\\/"), "123456"), out.out


@pytest.mark.parametrize("status", [429, 503])
async def test_a_transient_http_status_wins_over_the_body(status: int) -> None:
    """P2: a 429 or a 5xx whose body says `Status: 400` is still the outage it is."""
    result, _ = await _send(lambda r: _json(status, {"IsSuccess": False, "Status": 400,
                                                     "Message": "temporarily unavailable"}))
    assert result.outcome is Outcome.TRANSIENT


@pytest.mark.parametrize("field", ["status", "category"])
async def test_a_case_changed_token_in_the_listing_is_scrubbed(field: str) -> None:
    """P2: the check lower-cases status and upper-cases category before it reads
    them; a scrub only at the end missed the case-changed token."""
    def _listing(request: httpx.Request) -> httpx.Response:
        row = {"name": "polysil_auth_otp", "status": "APPROVED", "language": "en",
               "category": "AUTHENTICATION", "placeholders": 1}
        row[field] = "MiXed " + TOKEN
        return _json(200, {"IsSuccess": True, "data": [row]})

    settings = _settings()
    async with httpx.AsyncClient(transport=httpx.MockTransport(_listing)) as client:
        problems = await check_templates(ElevenZaProvider(settings, client), settings)
    assert problems and all(_clean(p, TOKEN) for p in problems), problems


async def test_a_listing_without_a_placeholder_count_fails_the_gate() -> None:
    """P2: an unreadable count was a silent pass; the gate exists for that count."""
    settings = _settings()
    problems = await check_templates(_Listing([
        {"name": "polysil_auth_otp", "status": "APPROVED"},
        {"name": "polysil_lead_ack", "status": "APPROVED"},
    ]), settings)
    assert len(problems) == 2 and all("placeholder count" in p for p in problems), problems


def test_a_refused_configuration_does_not_print_the_token() -> None:
    """P2: pydantic's validation error carried the raw settings, token included."""
    with pytest.raises(ValueError) as exc:
        _settings(environment="production", whatsapp_provider="mock")
    assert TOKEN not in str(exc.value) and "mock" in str(exc.value)


# ── the live listing's shape (W10, settled 23 Sep by the first live run) ─────

def _doc(name: str, category: str, *locs: tuple[str, str, str]) -> dict[str, object]:
    """One template as 11za lists it: localizations carry the language, the status
    and the components."""
    return {"_id": "x", "name": name, "category": category, "subCategory": "CUSTOM",
            "localizations": [{"language": lang, "status": status,
                               "components": [{"type": "HEADER", "format": "TEXT", "text": "Hi"},
                                              {"type": "BODY", "text": body}]}
                              for lang, status, body in locs]}


def _live_listing(docs: list[dict[str, object]], pages: list[int] | None = None) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        page = json.loads(request.content)["page"]
        if pages is not None:
            pages.append(page)
        return _json(200, {"Message": "template list",
                           "Data": {"docs": docs if page == 1 else [], "totalDocs": len(docs),
                                    "hasNextPage": False}})
    return handler


async def test_the_live_listing_becomes_one_row_per_localization() -> None:
    docs = [_doc("polysil_lead_ack", "UTILITY",
                 ("hi", "PENDING", "नमस्ते {{1}}, {{2}}"),
                 ("en", "APPROVED", "Hello {{1}}, your inquiry {{2}} is received.")),
            _doc("dealer_gift", "MARKETING", ("en", "APPROVED", "A small gesture"))]
    pages: list[int] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(_live_listing(docs, pages))) as c:
        rows = await ElevenZaProvider(_settings(), c).list_templates()
    assert pages == [1], "three rows from two templates is one short page, not a full one"
    assert [(r["name"], r["language"], r["status"]) for r in rows] == [
        ("polysil_lead_ack", "hi", "PENDING"), ("polysil_lead_ack", "en", "APPROVED"),
        ("dealer_gift", "en", "APPROVED")]
    assert rows[1]["body"] == "Hello {{1}}, your inquiry {{2}} is received."
    assert rows[1]["category"] == "UTILITY"


async def test_the_paging_counts_templates_not_localizations() -> None:
    """A full page of 100 templates, half of them with no localization yet, is 50
    rows: counting rows would stop there and lose page 2."""
    asked: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = json.loads(request.content)["page"]
        asked.append(page)
        count = 100 if page == 1 else 1
        docs = [_doc(f"t{page}_{i}", "UTILITY", *([("en", "APPROVED", "x")] if i % 2 == 0 else []))
                for i in range(count)]
        return _json(200, {"Data": {"docs": docs}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        rows = await ElevenZaProvider(_settings(), c).list_templates()
    assert asked == [1, 2] and len(rows) == 51


async def test_the_check_reads_the_live_shape_in_our_language() -> None:
    """The approved English localization passes even when a pending Hindi one is
    listed first; the missing templates are named."""
    docs = [_doc("polysil_lead_ack", "UTILITY",
                 ("hi", "PENDING", "नमस्ते {{1}}, {{2}}"),
                 ("en", "APPROVED", "Hello {{1}}, your inquiry {{2}} is received."))]
    settings = _settings(whatsapp_template_lead_ack="polysil_lead_ack")
    async with httpx.AsyncClient(transport=httpx.MockTransport(_live_listing(docs))) as c:
        problems = await check_templates(ElevenZaProvider(settings, c), settings)
    assert problems == ["auth.otp: template 'polysil_auth_otp' is not on the account"], problems


async def test_an_unset_template_name_is_a_dead_letter_and_sends_nothing() -> None:
    """PR 11 review: with the quotation share template unset (GAP-110), the send went
    out with a null name and its outcome depended on the provider's wording."""
    share = OutboundMessage(channel="whatsapp", recipient="919876543210",
                            template_key=TEMPLATE_QUOTATION_SHARE,
                            payload={"party_name": "Ram", "quote_no": "QT/GJ/2026-27/00001",
                                     "link": "https://example.test/q/abc"},
                            reference="row-3")
    result, seen = await _send(lambda r: _json(200, {"IsSuccess": True}), share,
                               whatsapp_template_quotation_share=None)
    assert result.outcome is Outcome.PERMANENT and result.error == "template not configured"
    assert seen == [], "no request reaches the provider"
