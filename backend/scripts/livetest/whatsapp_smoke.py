"""One real send through 11za, by hand, to a number given on the command line.

    python scripts/livetest/whatsapp_smoke.py --to 91XXXXXXXXXX --template auth.otp
    python scripts/livetest/whatsapp_smoke.py --to 91XXXXXXXXXX --template lead_ack

The only place this project sends a real message outside a deployment (FS-007
rule 19). It refuses to run without a number, it never reads a farmer's number
from the database, and it prints sanitised fields only: the outcome, the provider
message id, the HTTP status, and the response text with the token and every value
sent replaced by ***. The raw responses this reveals fill rule 6's recognised
shapes (W6), settle W5, W8 and W9, and size `whatsapp_send_timeout`; record them
in the spec's section 9, sanitised.

Needs `WHATSAPP_PROVIDER=11za` and `WHATSAPP_AUTH_TOKEN` in the environment (the
settings refuse the provider without its token).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import httpx

from api.config import Settings, get_settings
from api.integrations.messages import TEMPLATE_AUTH_OTP, TEMPLATE_LEAD_ACK, template_values
from api.integrations.whatsapp.elevenza import ElevenZaProvider
from api.integrations.whatsapp.provider import OutboundMessage, scrub

SAMPLES: dict[str, dict[str, object]] = {
    TEMPLATE_AUTH_OTP: {"code": "123456"},
    TEMPLATE_LEAD_ACK: {"farmer_name": "Smoke Test", "inquiry_no": "POL/GJ/2026-27/00000"},
}


async def run(settings: Settings, client: httpx.AsyncClient, *, to: str, template: str) -> int:
    """The command's body, separated so a test can drive it with a fake transport
    and read what it printed."""
    if settings.whatsapp_provider != "11za" or settings.whatsapp_auth_token is None:
        print("whatsapp-smoke: WHATSAPP_PROVIDER must be 11za with WHATSAPP_AUTH_TOKEN set")
        return 2
    payload = SAMPLES[template]
    values, button = template_values(template, payload)
    secrets = [settings.whatsapp_auth_token.get_secret_value(),
               *(str(v) for v in payload.values()), *values, *([button] if button else [])]
    provider = ElevenZaProvider(settings, client)
    result = await provider.send(OutboundMessage(
        channel="whatsapp", recipient=to, template_key=template, payload=payload,
        reference="smoke-" + uuid.uuid4().hex[:8]))
    status, body = provider.last_response or (0, "")
    for line in (
        f"template {template} to {to[:4]}…{to[-2:]}",
        f"outcome {result.outcome} provider_msg_id {result.provider_msg_id}",
        f"error {result.error}",
        f"http {status} body {scrub(body, secrets)[:400]}",
    ):
        print(scrub(line, secrets))
    return 0 if result.outcome == "accepted" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--to", required=True, help="digits with the country code, no plus")
    parser.add_argument("--template", choices=sorted(SAMPLES), default=TEMPLATE_AUTH_OTP)
    args = parser.parse_args(argv)
    if not args.to.isdigit() or not 10 <= len(args.to) <= 15:
        print("whatsapp-smoke: --to must be digits with the country code, e.g. 919876543210")
        return 2
    settings = get_settings()

    async def _go() -> int:
        timeout = httpx.Timeout(settings.whatsapp_send_timeout)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await run(settings, client, to=args.to, template=args.template)

    return asyncio.run(_go())


if __name__ == "__main__":
    sys.exit(main())
