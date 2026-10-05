"""11za, the client's WhatsApp Business Solution Provider.

The contract, as far as the published collection says it
(docs/specs/WhatsApp-11za-Integration.md sections 2 and 6): POST for everything,
the auth token in the request body, `sendto` as digits with the country code and
no plus, positional `data[]`, `buttonValue` for a button's dynamic value, `tags`
for our own reference. The response is `{Message, Data, Status, IsSuccess}`; one
variant of the same API returns `data.messageId`. Classification is on the body,
never on the HTTP status alone (rule 6).

Three rules the token forces (11za doc section 1.1, rule 5): the request body is
built inside `send` and exists nowhere else; nothing here logs a request or a
response body; every error text leaves scrubbed of the token and of every value
sent, and a transport exception leaves as its class name, because an httpx error
can carry the request.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import structlog

from api.config import Settings
from api.integrations.messages import (
    UnknownTemplateError,
    provider_template,
    template_values,
)
from api.integrations.whatsapp.provider import (
    OutboundMessage,
    Outcome,
    ProviderResult,
    mask,
    scrub,
    scrub_body,
    to_sendto,
)

log = structlog.get_logger()

SEND_PATH = "/apis/template/sendTemplate"
LIST_PATH = "/apis/template/getTemplatesAll"
LIST_PAGE = 100

# Rule 6. The vocabulary of `Message` is W6, filled from executed responses; these
# are the words the collection and the Pabbly variant use.
_TOKEN_WORDS = ("invalid authtoken", "invalid auth token", "invalid token", "unauthori",
                "authentication failed")
# Phrases, not words: an echoed request carries "templateName" and "data", and a
# refusal that merely echoes is not known to be permanent.
_PERMANENT_WORDS = ("invalid phone", "invalid number", "invalid contact", "invalid recipient",
                    "not on whatsapp", "template not found", "invalid template",
                    "template is not", "template does not", "template has", "parameter",
                    "placeholder", "variable")


class ElevenZaProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        if settings.whatsapp_auth_token is None:
            raise ValueError("whatsapp_auth_token is required for the 11za provider")
        self._settings = settings
        self._client = client
        self._base = settings.whatsapp_base_url.rstrip("/")
        # The last status and scrubbed body: the smoke script's diagnostic (rule 19).
        self.last_response: tuple[int, str] | None = None

    def _token(self) -> str:
        assert self._settings.whatsapp_auth_token is not None
        return self._settings.whatsapp_auth_token.get_secret_value()

    async def send(self, msg: OutboundMessage) -> ProviderResult:
        sendto = to_sendto(msg.recipient)
        if sendto is None:
            return ProviderResult(Outcome.PERMANENT, None, "recipient is not a phone number")
        try:
            values, button = template_values(msg.template_key, msg.payload)
        except UnknownTemplateError as exc:
            return ProviderResult(Outcome.PERMANENT, None, f"unknown template: {exc}")
        name = provider_template(msg.template_key, self._settings, msg.payload)
        if name is None:
            # an unset template name is a dead letter here, never a send with a null
            # name whose outcome depends on how the provider words its refusal (GAP-110)
            return ProviderResult(Outcome.PERMANENT, None, "template not configured")
        token = self._token()
        body: dict[str, Any] = {
            "authToken": token,
            "sendto": sendto,
            "templateName": name,
            "language": self._settings.whatsapp_template_language,
            "data": values,
            "tags": msg.reference,
        }
        if button is not None:
            body["buttonValue"] = button
        if self._settings.whatsapp_origin_website:
            body["originWebsite"] = self._settings.whatsapp_origin_website
        secrets = [token, *values]

        try:
            # A total deadline: httpx's timeout bounds each socket operation, not
            # the request (cross-vendor recommendation).
            response = await asyncio.wait_for(
                self._client.post(self._base + SEND_PATH, json=body),
                timeout=self._settings.whatsapp_send_timeout)
        except Exception as exc:
            # A provider never raises: a transport error, a timeout, and a bad
            # base URL (httpx.InvalidURL is not an HTTPError) all leave as their
            # class name, transient, for the breaker to see (code review F-3).
            log.warning("outbox.transport_failure", recipient=mask(msg.recipient),
                        kind=type(exc).__name__)
            return ProviderResult(Outcome.TRANSIENT, None, type(exc).__name__)

        self.last_response = (response.status_code, scrub_body(response.text, secrets))
        result = classify(response.status_code, response.text, secrets)
        log.info("outbox.provider_response", recipient=mask(msg.recipient),
                 status=response.status_code, outcome=str(result.outcome))
        return result

    async def list_templates(self) -> list[dict[str, object]]:
        """Every template on the account, through the paginated listing. The rows
        come back as the provider shapes them (W10); the check reads what it can."""
        token = self._token()
        out: list[dict[str, object]] = []
        page = 1
        while True:
            response = await asyncio.wait_for(
                self._client.post(self._base + LIST_PATH,
                                  json={"authToken": token, "limit": LIST_PAGE, "page": page,
                                        "search": ""}),
                timeout=self._settings.whatsapp_send_timeout)
            self.last_response = (response.status_code, scrub_body(response.text, [token]))
            rows, fetched = _template_page(response.text)
            out.extend(rows)
            if fetched < LIST_PAGE:
                return out
            page += 1


def classify(status: int, text: str, secrets: list[str]) -> ProviderResult:
    """Rule 6, on the body. A dict with `IsSuccess` true is accepted, with or
    without an id. A token problem, a 429 or a 5xx is transient. A refusal naming
    the recipient, the template or a parameter is permanent. Anything else the
    provider refused is charged and retried on the backoff."""
    body: Any = None
    try:
        body = json.loads(text) if text else None
    except ValueError:
        body = None

    if isinstance(body, dict):
        flag = body.get("IsSuccess", body.get("isSuccess", body.get("success")))
        if flag is True or str(flag).lower() == "true":
            return ProviderResult(Outcome.ACCEPTED, _message_id(body), None)
        message = str(body.get("Message") or body.get("message") or body.get("msg") or "")
        code = _int(body.get("Status", body.get("status"))) or status
        error = scrub(message or f"HTTP {status}", secrets)
        # A 429 or a 5xx on the wire is an outage whatever the body says about
        # itself (cross-vendor review of the code, P2): charging it would march
        # rows to dead through the breaker's blind spot.
        if status == 429 or status >= 500:
            return ProviderResult(Outcome.TRANSIENT, None, error)
        lower = message.lower()
        if code in (401, 403) or any(w in lower for w in _TOKEN_WORDS):
            return ProviderResult(Outcome.TRANSIENT, None, error)
        if code == 429 or code >= 500:
            return ProviderResult(Outcome.TRANSIENT, None, error)
        if any(w in lower for w in _PERMANENT_WORDS):
            return ProviderResult(Outcome.PERMANENT, None, error)
        return ProviderResult(Outcome.REFUSED, None, error)

    # Scrub the whole text, then bound it: a secret cut by the bound would survive
    # as a prefix (code review F-7).
    error = scrub(f"HTTP {status}: {text}" if text else f"HTTP {status}", secrets)[:140]
    if status in (401, 403, 429) or status >= 500:
        return ProviderResult(Outcome.TRANSIENT, None, error)
    # A 2xx whose body is not the documented shape is not a success we can trust,
    # and a 4xx we cannot read is not known to be permanent: both are charged.
    return ProviderResult(Outcome.REFUSED, None, "unreadable response: " + error)


def _message_id(body: dict[str, Any]) -> str | None:
    data = body.get("data", body.get("Data"))
    if isinstance(data, dict):
        for key in ("messageId", "message_id", "id"):
            if data.get(key):
                return str(data[key])
    for key in ("messageId", "message_id"):
        if body.get(key):
            return str(body[key])
    return None


def _int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _template_page(text: str) -> tuple[list[dict[str, object]], int]:
    """One page of the listing: the rows, and how many templates the page held.

    W10, settled by the first live listing: `{"Data": {"docs": [...]}}`, each doc
    with `name` and `category` and a `localizations` list carrying `language`,
    `status` and `components`. Each localization becomes its own row, with the
    BODY component's text as `body`. The count is of templates, not rows, because
    it decides whether another page exists."""
    try:
        body = json.loads(text) if text else None
    except ValueError:
        return [], 0
    rows: Any = body
    if isinstance(body, dict):
        rows = body.get("data", body.get("Data", body.get("templates", [])))
        if isinstance(rows, dict):
            rows = rows.get("docs", rows.get("data", rows.get("templates", rows.get("items", []))))
    if not isinstance(rows, list):
        return [], 0
    docs = [r for r in rows if isinstance(r, dict)]
    out: list[dict[str, object]] = []
    for doc in docs:
        locs = doc.get("localizations")
        if not isinstance(locs, list):
            out.append(doc)
            continue
        for loc in locs:
            if not isinstance(loc, dict):
                continue
            components = loc.get("components")
            text_ = next((c.get("text") for c in components
                          if isinstance(c, dict) and str(c.get("type", "")).upper() == "BODY"),
                         None) if isinstance(components, list) else None
            out.append({"name": doc.get("name"), "category": doc.get("category"),
                        "status": loc.get("status"), "language": loc.get("language"),
                        "body": text_})
    return out, len(docs)
