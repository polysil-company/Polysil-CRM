"""The default provider: everything is built and tested against this.

It renders the English body for a character count, logs a masked recipient, and
accepts. **The body is never logged.** It contains the OTP, and rule 8 puts the
code out of responses, logs and errors alike - a mock that printed it would put
every code into the container logs, which is the cheapest possible way to break
that rule.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from api.integrations.messages import TEMPLATES, UnknownTemplateError, render
from api.integrations.whatsapp.provider import OutboundMessage, Outcome, ProviderResult, mask

log = structlog.get_logger()


class MockProvider:
    async def send(self, msg: OutboundMessage) -> ProviderResult:
        try:
            body = render(msg.template_key, msg.payload)
        except UnknownTemplateError as exc:
            # A key in TEMPLATES with no body here is a programming error. A
            # provider never raises (code review F-3: one raising send stopped
            # the drain, tick after tick), so it is a permanent refusal the row
            # records instead.
            return ProviderResult(Outcome.PERMANENT, None, f"no mock body: {exc}")
        # An await, so the worker's claim and role are proven to survive one
        # (FS-007 section 8's executed claim).
        await asyncio.sleep(0)
        log.info("outbox.mock_send", channel=msg.channel, recipient=mask(msg.recipient),
                 template=msg.template_key, chars=len(body))
        return ProviderResult(Outcome.ACCEPTED, f"mock-{datetime.now(UTC).timestamp():.0f}")

    async def list_templates(self) -> list[dict[str, object]]:
        """What a well-configured account would list: both templates approved, with
        the placeholder counts this system sends."""
        from api.config import get_settings

        settings = get_settings()
        return [
            {"name": getattr(settings, spec.name_setting) if spec.name_setting else key,
             "status": "APPROVED",
             "language": settings.whatsapp_template_language,
             "category": "AUTHENTICATION" if spec.button else "UTILITY",
             "placeholders": len(spec.params)}
            for key, spec in TEMPLATES.items()
        ]
