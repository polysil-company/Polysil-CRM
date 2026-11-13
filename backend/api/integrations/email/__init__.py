"""Email providers behind one port (ADR-020, FS-078).

`none` returns no provider: nothing is collected, and the drain ends any pending
email row "email off" (EC-15).
"""

from __future__ import annotations

from api.config import Settings
from api.integrations.email.mock import MockEmailProvider
from api.integrations.email.provider import EmailProvider
from api.integrations.email.smtp import SmtpProvider


def get_email_provider(settings: Settings) -> EmailProvider | None:
    if settings.email_provider == "smtp":
        return SmtpProvider(settings)
    if settings.email_provider == "mock":
        return MockEmailProvider()
    return None
