"""What the live checks may print about a response (FS-065 rule 27).

A failure line goes to a terminal and into a deploy log. It names the path, the
status and `error.code`, and nothing else from the body. Any other text that has
to be printed passes through `redact` first: a 200-character excerpt is enough to
leak a token or a farmer's number.
"""

from __future__ import annotations

import re

import httpx

# Three base64url segments, the first a JSON header. Signature may be empty (alg none).
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Ten digits, optionally after +91 or 91. The lookarounds keep a longer digit run,
# such as part of an amount or an id, from losing ten of its digits.
_PHONE = re.compile(r"(?<![\d+])(?:\+91[\s-]?|91[\s-]?)?\d{10}(?!\d)")

_SIGN_IN = ("/auth/login", "/auth/otp/verify", "/auth/refresh")


def redact(text: str) -> str:
    """The text with JWT-shaped strings, phone numbers and emails replaced."""
    text = _JWT.sub("[token]", text)
    text = _EMAIL.sub("[email]", text)
    return _PHONE.sub("[phone]", text)


def error_code(response: httpx.Response) -> str | None:
    """`error.code` from the envelope, or None for any other body."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("code")
        return code if isinstance(code, str) else None
    return None


def describe(response: httpx.Response) -> str:
    """`METHOD /path -> status code`. Never the body, and for a sign-in not even
    the code unless it is an error: a 200 from `/auth/login` carries the token."""
    request = response.request
    path = request.url.path
    line = f"{request.method} {path} -> {response.status_code}"
    if path.endswith(_SIGN_IN) and response.status_code < 400:
        return line
    code = error_code(response)
    return redact(f"{line} {code}" if code else line)
