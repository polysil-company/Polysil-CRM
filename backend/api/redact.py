"""Keeping the WhatsApp webhook secret out of every log (FS-038 rule 2).

11za signs nothing, so the secret in the webhook path is the credential. Three
places write a request path: the structlog `path` binding in `api/main.py`, the
500 handler in `api/errors.py`, and uvicorn's access log. All three go through
`redact_path()`. It matches by pattern, not by the configured value, so a probe
with a wrong secret is redacted too and the secret is never needed to redact.
"""

from __future__ import annotations

import logging
import re

# both mounts of the public router: /api/v1/public/... and the legacy /public/...
_WEBHOOK = re.compile(r"(/public/webhooks/whatsapp/)[^/?]*")
REDACTED = "<redacted>"


def redact_path(path: str) -> str:
    return _WEBHOOK.sub(r"\g<1>" + REDACTED, path)


class AccessLogRedact(logging.Filter):
    """uvicorn's access record carries (client, method, path, http version, status);
    the path is the third argument, query string included."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], redact_path(args[2]), *args[3:])
        return True


def install_access_log_filter() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogRedact) for f in logger.filters):
        logger.addFilter(AccessLogRedact())
