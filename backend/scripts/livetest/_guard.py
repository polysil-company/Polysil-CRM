"""The drivers' one guard: they run against a developer's own stack and nothing else
(FS-065 rule 25).

They create leads on random real-format mobiles, delete a lead and add a lost
reason on every run. Port 8100 is also the port the deploy tool's tunnel hint
uses, so a driver started with a tunnel open would write to a deployed box, which
sends real WhatsApp. `/health` names the environment; anything but `local` stops
the driver before its first request.
"""

from __future__ import annotations

import sys
from urllib.parse import urlsplit

import httpx


def require_local(base_url: str, *, transport: httpx.BaseTransport | None = None) -> None:
    """Exit unless `/health` at the base URL's root reports `environment: local`."""
    parts = urlsplit(base_url)
    health = f"{parts.scheme}://{parts.netloc}/health"
    try:
        with httpx.Client(timeout=5, transport=transport, trust_env=False) as client:
            response = client.get(health)
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        sys.exit(f"refused: could not read {health} ({type(exc).__name__}). "
                 "These drivers run against a local stack only.")
    found = body.get("environment") if isinstance(body, dict) else None
    if found != "local":
        sys.exit(f"refused: {health} reports environment {found!r}. "
                 "These drivers write test data and run against a local stack only.")
