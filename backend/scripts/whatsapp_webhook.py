"""Read, register or remove the webhook URLs on the 11za account (FS-038).

    python scripts/whatsapp_webhook.py get
    python scripts/whatsapp_webhook.py register --base-url https://<api host> [--replace]
    python scripts/whatsapp_webhook.py delete --type statusMessage

`register` posts both URLs, built from `--base-url` and WHATSAPP_WEBHOOK_SECRET,
on the `/api/v1` mount, because a deployment's proxy sends only `/api/v1` to the
API. It refuses when something is registered already, unless `--replace`.

`delete` takes 11za's `type`. The collection shows only `statusMessage`; the
value that removes the inbound URL is unknown (GAP-355), so it is not guessed.

Every command ends with a `get`, so the account's state is always printed.
Everything printed is masked: the token, and any `/whatsapp/<segment>/` path
segment, so an older secret from an earlier registration is masked too.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from api.config import Settings, get_settings  # noqa: E402
from api.integrations.whatsapp.provider import scrub  # noqa: E402

GET_PATH = "/apis/inboundwebhook/get"
ADD_PATH = "/apis/inboundwebhook/add"
DELETE_PATH = "/apis/inboundwebhook/delete"
WEBHOOK_PATH = "/api/v1/public/webhooks/whatsapp"
# a JSON body may escape its slashes (\/whatsapp\/...), review F-8
_SEGMENT = re.compile(r"(\\?/whatsapp\\?/)[^/\\\s\"']+")


class RefusedError(Exception):
    """A command that must not call 11za, with the reason to print."""


def check_base(base: str) -> str:
    base = base.strip().rstrip("/")
    parts = urlsplit(base)
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme != "https" and not (parts.scheme == "http" and local):
        raise RefusedError("--base-url must be https (the secret travels in the path)")
    if not parts.hostname:
        raise RefusedError("--base-url has no host")
    return base


def webhook_urls(base: str, secret: str) -> tuple[str, str]:
    root = f"{check_base(base)}{WEBHOOK_PATH}/{secret}"
    return f"{root}/inbound", f"{root}/status"


def masked(text: str, settings: Settings) -> str:
    secrets: list[str] = []
    if settings.whatsapp_auth_token is not None:
        secrets.append(settings.whatsapp_auth_token.get_secret_value())
    if settings.whatsapp_webhook_secret is not None:
        secrets.append(settings.whatsapp_webhook_secret.get_secret_value())
    return _SEGMENT.sub(r"\g<1>****", scrub(text, secrets))


# what 11za answers `get` with when nothing is registered (read 7 Oct 2026)
_NOTHING = "Cannot convert undefined or null to object"


def state(status: int | None, body: str) -> str:
    """`registered`, `empty`, or `unknown` when the reply could not be read. Only
    `empty` lets `register` add without `--replace`, and `unknown` refuses even
    with it (code review F-3: a timeout used to read as nothing registered)."""
    if status is None:
        return "unknown"
    if status == 500 and _NOTHING in body:
        return "empty"
    if status != 200:
        return "unknown"
    return "registered" if "http" in body else "empty"


class Client:
    def __init__(self, settings: Settings, http: httpx.Client) -> None:
        if settings.whatsapp_auth_token is None:
            raise RefusedError("WHATSAPP_AUTH_TOKEN is unset")
        self.settings = settings
        self.http = http
        self.base = settings.whatsapp_base_url.rstrip("/")
        self.token = settings.whatsapp_auth_token.get_secret_value()

    def call(self, path: str, extra: dict[str, str] | None = None) -> tuple[int | None, str]:
        try:
            r = self.http.post(self.base + path, json={"authToken": self.token, **(extra or {})},
                               timeout=20)
        except httpx.HTTPError as exc:
            return None, f"transport error: {type(exc).__name__}"
        return r.status_code, f"{r.status_code} {r.text}"


def run(argv: list[str], settings: Settings, http: httpx.Client) -> int:
    ap = argparse.ArgumentParser(prog="whatsapp_webhook.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("get")
    reg = sub.add_parser("register")
    reg.add_argument("--base-url", required=True)
    reg.add_argument("--replace", action="store_true")
    rm = sub.add_parser("delete")
    rm.add_argument("--type", required=True)
    args = ap.parse_args(argv)

    def out(label: str, text: str) -> None:
        print(f"{label}: {masked(text, settings)}")

    try:
        client = Client(settings, http)
        if args.cmd == "register":
            secret = settings.whatsapp_webhook_secret
            if secret is None:
                raise RefusedError("WHATSAPP_WEBHOOK_SECRET is unset")
            inbound, status = webhook_urls(args.base_url, secret.get_secret_value())
            code, before = client.call(GET_PATH)
            out("registered now", before)
            now = state(code, before)
            if now == "unknown":
                raise RefusedError("could not read the current registration; nothing changed")
            if now == "registered" and not args.replace:
                raise RefusedError("something is registered already; --replace to overwrite it")
            out("inbound url", inbound)
            out("status url", status)
            out("add", client.call(ADD_PATH, {"webhookUrl": inbound,
                                               "statusMessageWebhookUrl": status})[1])
        elif args.cmd == "delete":
            out("delete", client.call(DELETE_PATH, {"type": args.type})[1])
        out("registered now", client.call(GET_PATH)[1])
    except RefusedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    with httpx.Client() as http:
        return run(sys.argv[1:], get_settings(), http)


if __name__ == "__main__":
    raise SystemExit(main())
