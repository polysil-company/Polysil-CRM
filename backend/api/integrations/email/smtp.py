"""SMTP, from the standard library, in a thread (FS-078 section 5.1).

The outcome follows the phase the failure happened in:

| Failure | Outcome |
|---|---|
| connect, TLS, certificate, AUTH (535 included), MAIL FROM | transient: the breaker, logged at error |
| 5xx on RCPT TO or on this message's DATA | permanent |
| 4xx on RCPT TO or DATA | transient |
| the deadline, before DATA started | transient |
| the deadline or a dropped socket after DATA started | uncertain: may have arrived |

Every error is scrubbed of the username, the password, the address and the
base64 AUTH string before it leaves this module (EC-30).
"""

# ruff: noqa: E501  (the phase table and the outcome lines)

from __future__ import annotations

import asyncio
import base64
import contextlib
import smtplib
import ssl
import threading
from email.headerregistry import Address
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import make_msgid

import structlog

from api.config import Settings
from api.integrations.email.provider import Email, one_line, parse_address
from api.integrations.whatsapp.provider import Outcome, ProviderResult, scrub

log = structlog.get_logger()


class _Phase:
    """Where the thread got to, and whether the caller gave up.

    `asyncio.wait_for` stops waiting but cannot stop the thread. Without this, a
    deadline at RCPT answered "transient" while the thread went on to DATA and
    delivered, and the retry sent a second email (code review F-1, executed). The
    step into DATA and the cancel take the same lock, so exactly one wins: the
    thread never starts DATA after a cancel, and a cancel after DATA started
    reads "data" and answers uncertain.
    """

    def __init__(self) -> None:
        self.name = "connect"
        self._lock = threading.Lock()
        self._cancelled = False

    def cancel(self) -> str:
        with self._lock:
            self._cancelled = True
            return self.name

    def start_data(self) -> bool:
        with self._lock:
            if self._cancelled:
                return False
            self.name = "data"
            return True


def build_message(msg: Email, sender: str, to: str) -> EmailMessage:
    m = EmailMessage(policy=SMTP)
    m["From"] = sender
    local, _, domain = to.partition("@")
    # the display name is encoded by the policy, never pasted into the header (EC-18)
    m["To"] = Address(display_name=one_line(msg.to_name, 80), username=local, domain=domain)
    m["Subject"] = one_line(msg.subject)
    m["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    m.set_content(msg.text)
    m.add_alternative(msg.html, subtype="html")
    return m


class SmtpProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        assert settings.smtp_host and settings.smtp_username and settings.smtp_password \
            and settings.email_from
        self.host = settings.smtp_host
        self.user = settings.smtp_username
        self.password = settings.smtp_password.get_secret_value()
        self.sender = settings.email_from
        auth = base64.b64encode(f"\0{self.user}\0{self.password}".encode()).decode()
        self._secrets = [self.user, self.password, auth]

    def _redirect(self, to: str) -> str:
        # outside production, every email goes to one address (EC-23)
        if self.settings.environment != "production" and self.settings.email_redirect_to:
            return self.settings.email_redirect_to
        return to

    async def send(self, msg: Email) -> ProviderResult:
        to = parse_address(self._redirect(msg.to))
        if to is None:
            return ProviderResult(Outcome.PERMANENT, None, "not one email address")
        phase = _Phase()
        secrets = [*self._secrets, to, msg.to]
        try:
            msg_id = await asyncio.wait_for(asyncio.to_thread(self._send, msg, to, phase),
                                            timeout=self.settings.smtp_send_deadline)
        except TimeoutError:
            # the thread may still finish; what matters is whether DATA started (EC-16)
            if phase.cancel() in ("data", "sent"):
                return ProviderResult(Outcome.UNCERTAIN, None, "no answer after the message was sent")
            return ProviderResult(Outcome.TRANSIENT, None, f"timed out at {phase.name}")
        except _RefusedError as exc:
            return ProviderResult(exc.outcome, None, scrub(str(exc), secrets))
        except smtplib.SMTPNotSupportedError as exc:
            if phase.name in ("connect", "tls"):
                log.error("email.tls_unavailable", phase=phase.name)
                return ProviderResult(Outcome.TRANSIENT, None, scrub(f"{phase.name}: {exc}", secrets))
            return ProviderResult(Outcome.PERMANENT, None, scrub(f"{phase.name}: {exc}", secrets))
        except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
            if phase.name in ("data", "sent"):
                return ProviderResult(Outcome.UNCERTAIN, None,
                                      scrub(f"{phase.name}: {type(exc).__name__}", secrets))
            log.error("email.transport_failed", phase=phase.name, kind=type(exc).__name__)
            return ProviderResult(Outcome.TRANSIENT, None,
                                  scrub(f"{phase.name}: {type(exc).__name__}: {exc}", secrets))
        return ProviderResult(Outcome.ACCEPTED, msg_id)

    def _send(self, msg: Email, to: str, phase: _Phase) -> str:
        s = self.settings
        context = ssl.create_default_context()
        timeout = s.smtp_socket_timeout
        phase.name = "connect"
        smtp: smtplib.SMTP = (smtplib.SMTP_SSL(self.host, s.smtp_port, timeout=timeout, context=context)
                              if s.smtp_security == "ssl"
                              else smtplib.SMTP(self.host, s.smtp_port, timeout=timeout))
        try:
            smtp.set_debuglevel(0)
            smtp.ehlo()
            if s.smtp_security == "starttls":
                phase.name = "tls"
                # raises when the server offers no STARTTLS: never a plain-text fallback
                smtp.starttls(context=context)
                smtp.ehlo()
            phase.name = "auth"
            smtp.login(self.user, self.password)
            # parse_address admits ASCII addresses only, so no SMTPUTF8 (code review F-4)
            message = build_message(msg, self.sender, to)
            phase.name = "mail"
            code, _ = smtp.mail(self.sender)
            if code != 250:
                raise _RefusedError(Outcome.TRANSIENT, f"MAIL FROM refused: {code}")
            phase.name = "rcpt"
            code, _ = smtp.rcpt(to)
            if code not in (250, 251):
                raise _RefusedError(Outcome.PERMANENT if code >= 500 else Outcome.TRANSIENT,
                               f"RCPT TO refused: {code}")
            if not phase.start_data():
                # the caller gave up and answered transient: never send now
                raise _RefusedError(Outcome.TRANSIENT, "cancelled before DATA")
            try:
                code, _ = smtp.data(message.as_bytes())
            except smtplib.SMTPDataError as exc:
                raise _RefusedError(Outcome.PERMANENT if exc.smtp_code >= 500 else Outcome.TRANSIENT,
                               f"DATA refused: {exc.smtp_code}") from None
            if code != 250:
                raise _RefusedError(Outcome.PERMANENT if code >= 500 else Outcome.TRANSIENT,
                               f"DATA refused: {code}")
            phase.name = "sent"
            return str(message["Message-ID"])
        finally:
            # the message's fate is already decided
            with contextlib.suppress(Exception):
                smtp.quit()


class _RefusedError(Exception):
    def __init__(self, outcome: Outcome, message: str) -> None:
        super().__init__(message)
        self.outcome = outcome
