"""WhatsApp providers behind one port (ADR-020, FS-007).

Nothing outside this package knows which provider is configured. The worker asks
for one at startup, with the HTTP client it owns for its lifetime (rule 20).
"""

from __future__ import annotations

import httpx

from api.config import Settings
from api.integrations.whatsapp.elevenza import ElevenZaProvider
from api.integrations.whatsapp.mock import MockProvider
from api.integrations.whatsapp.provider import MessageProvider


def get_provider(settings: Settings, client: httpx.AsyncClient | None = None) -> MessageProvider:
    if settings.whatsapp_provider == "11za":
        if client is None:
            raise ValueError("the 11za provider needs the process's HTTP client")
        return ElevenZaProvider(settings, client)
    return MockProvider()
