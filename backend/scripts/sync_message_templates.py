"""Switch each `message_template` row on only when its template is approved on the
WhatsApp account (FS-012 rule 3).

    python scripts/sync_message_templates.py

Migration 016 seeds the three order messages enabled. On an account where a
template is not yet approved, every one of those messages would dead-letter; with
the row off, nothing is written. Run by `deploy_staging.py` after the migration,
and again once 11za approves a template.

With the mock provider nothing changes: the mock sends every key. If the listing
fails, nothing changes either, and the command says so and exits 1.

Runs as the table owner (the tools container's connection): `message_template`
has no grant for `app_role`.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# run as `python scripts/...`: the repository root is not on the path otherwise
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.config import get_settings  # noqa: E402
from api.db.session import async_session_factory  # noqa: E402
from api.integrations.whatsapp import get_provider  # noqa: E402
from api.integrations.whatsapp.check import approved_names  # noqa: E402
from api.integrations.whatsapp.provider import scrub  # noqa: E402


async def sync() -> int:
    settings = get_settings()
    if settings.whatsapp_provider == "mock":
        print("sync-templates: mock provider, switches left as they are")
        return 0
    token = settings.whatsapp_auth_token
    secrets = [token.get_secret_value()] if token else []
    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.whatsapp_send_timeout)) as c:
        try:
            rows = await get_provider(settings, c).list_templates()
        except Exception as exc:
            print(scrub(f"sync-templates: the listing failed ({type(exc).__name__}); "
                        "switches left as they are", secrets))
            return 1
    approved = approved_names(rows, settings.whatsapp_template_language)
    async with async_session_factory() as session, session.begin():
        found = (await session.execute(text(
            "SELECT key, provider_name, enabled FROM message_template ORDER BY key"))).all()
        for key, name, enabled in found:
            want = bool(name) and name.lower() in approved
            if want != enabled:
                await session.execute(text(
                    "UPDATE message_template SET enabled = :on, updated_at = now() "
                    "WHERE key = :k"), {"on": want, "k": key})
            print(f"sync-templates: {key} ({name}) {'on' if want else 'off, not approved'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(sync()))
