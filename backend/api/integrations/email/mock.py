"""The email mock: chosen only by name, refused in production (EC-24).

It keeps what it was given in memory so tests can read it, and logs nothing of
the content.
"""

from __future__ import annotations

import asyncio

import structlog

from api.integrations.email.provider import Email
from api.integrations.whatsapp.provider import Outcome, ProviderResult

log = structlog.get_logger()


class MockEmailProvider:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, msg: Email) -> ProviderResult:
        await asyncio.sleep(0)
        self.sent.append(msg)
        log.info("email.mock_send", reference=msg.reference, chars=len(msg.text))
        return ProviderResult(Outcome.ACCEPTED, f"mock-email-{len(self.sent)}")
