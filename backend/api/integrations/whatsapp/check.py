"""The template check (FS-007 rule 13): every template this system sends exists on
the account, is approved, takes the values we send, and is in the language we
send. Run at deploy as a gate (`python scripts/dev.py whatsapp-check`) and at
worker startup as an error log.

The listing's field names are W10 (unknown until the first live run), so each
check reads the names it can and reports what it cannot read rather than passing
in silence. Nothing here prints a body: the token and the values sent are scrubbed
from every line (rule 19).
"""

from __future__ import annotations

import asyncio
import re
import sys

import httpx

from api.config import Settings, get_settings
from api.integrations.messages import TEMPLATES
from api.integrations.whatsapp.provider import MessageProvider, scrub

_PLACEHOLDER = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def _first(row: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def _placeholders(row: dict[str, object]) -> int | None:
    count = _first(row, "placeholders", "variableCount", "bodyVariables", "variables")
    if isinstance(count, int):
        return count
    if isinstance(count, list):
        return len(count)
    body = _first(row, "body", "bodyText", "content", "text", "templateBody")
    if isinstance(body, str):
        return len(set(_PLACEHOLDER.findall(body)))
    return None


def unconfigured_templates(settings: Settings) -> list[str]:
    """The template keys whose account name is unset: sends with that key will
    dead-letter until it is configured. Logged at worker startup, one line."""
    return [key for key, spec in TEMPLATES.items()
            if getattr(settings, spec.name_setting) is None]


async def check_templates(provider: MessageProvider, settings: Settings) -> list[str]:
    """The problems found, each one line, scrubbed. Empty means the account is
    ready for what this system sends."""
    token = settings.whatsapp_auth_token
    secrets = [token.get_secret_value()] if token else []
    # Scrubbed before anything is lower- or upper-cased: a case-changed token would
    # survive a case-sensitive scrub at the end (cross-vendor review of the code, P2).
    rows = [{str(k): (scrub(v, secrets) if isinstance(v, str) else v) for k, v in r.items()}
            for r in await provider.list_templates()]
    by_name = {str(_first(r, "name", "templateName", "Name") or "").lower(): r for r in rows}
    problems: list[str] = []
    for key, spec in TEMPLATES.items():
        configured = getattr(settings, spec.name_setting)
        if configured is None:
            # An expected state, not a problem: the client's BSP has not approved
            # the template yet (GAP-110). unconfigured_templates() names it on its
            # own line at worker startup; the gate stays green for the rest.
            continue
        name = str(configured)
        row = by_name.get(name.lower())
        if row is None:
            problems.append(f"{key}: template {name!r} is not on the account")
            continue
        status = str(_first(row, "status", "Status", "templateStatus") or "").lower()
        if not status:
            problems.append(f"{key}: {name!r}: the listing carries no status field (W10); "
                            f"fields: {sorted(row)}")
        elif "approved" not in status:
            problems.append(f"{key}: {name!r} is {status}, not approved")
        language = str(_first(row, "language", "languageCode", "Language") or "")
        if language and language.lower() != settings.whatsapp_template_language.lower():
            problems.append(f"{key}: {name!r} is in {language!r}, this system sends "
                            f"{settings.whatsapp_template_language!r}")
        count = _placeholders(row)
        if count is None:
            # Fail closed: a count the listing does not carry is not a match
            # (cross-vendor review of the code, P2). W10 says which field carries it.
            problems.append(f"{key}: {name!r}: the listing carries no placeholder count "
                            f"(W10); fields: {sorted(row)}")
        elif count != len(spec.params):
            problems.append(f"{key}: {name!r} takes {count} values, this system sends "
                            f"{len(spec.params)}")
        category = str(_first(row, "category", "Category") or "").upper()
        if category and spec.button and category != "AUTHENTICATION":
            problems.append(f"{key}: {name!r} is a {category} template, not AUTHENTICATION")
    # The listing's values are the provider's text and may echo anything, and the
    # worker logs this list at startup: scrubbed once more here, for every caller
    # (code review F-1, executed with a token in the language field).
    return [scrub(p, secrets) for p in problems]


async def run(settings: Settings, client: httpx.AsyncClient) -> int:
    """The command's body, separated so a test can drive it with a fake transport
    and read what it printed."""
    from api.integrations.whatsapp import get_provider

    token = settings.whatsapp_auth_token
    secrets = [token.get_secret_value()] if token else []
    provider = get_provider(settings, client)
    try:
        problems = await check_templates(provider, settings)
    except Exception as exc:
        print(scrub(f"whatsapp-check: the listing failed: {type(exc).__name__}", secrets))
        return 2
    for problem in problems:
        print(scrub("whatsapp-check: " + problem, secrets))
    if not problems:
        print(f"whatsapp-check: {len(TEMPLATES)} templates present, approved and matching "
              f"({settings.whatsapp_provider})")
    return 1 if problems else 0


def main() -> int:
    settings = get_settings()

    async def _go() -> int:
        timeout = httpx.Timeout(settings.whatsapp_send_timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await run(settings, client)

    return asyncio.run(_go())


if __name__ == "__main__":
    sys.exit(main())
