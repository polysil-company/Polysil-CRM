"""FS-078's email adapter without a network: the address check, what an email
says, the SMTP outcome by phase against a fake server, and the settings refusals."""

# ruff: noqa: E501  (parametrised cases)

from __future__ import annotations

import asyncio
import datetime as dt
import smtplib
import threading
import time
from typing import Any, ClassVar

import pytest

from api.config import Settings
from api.integrations.email import get_email_provider, render
from api.integrations.email import smtp as smtp_mod
from api.integrations.email.mock import MockEmailProvider
from api.integrations.email.provider import Email, one_line, parse_address
from api.integrations.whatsapp.provider import Outcome

PASSWORD = "s3cret-Pass-word"


def _settings(**over: Any) -> Settings:
    base: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://u:p@127.0.0.1:6432/appdb",
        "jwt_secret": "x" * 32,
        "email_provider": "smtp", "smtp_host": "mail.example.in", "smtp_username": "crm@example.in",
        "smtp_password": PASSWORD, "email_from": "crm@example.in",
        "email_redirect_to": None, "environment": "production",
        "public_web_url": "https://crm.example.in", "pdf_renderer": "weasyprint",
        "whatsapp_provider": "11za", "whatsapp_auth_token": "t" * 20,
        "smtp_send_deadline": 2.0,
    }
    base.update(over)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


# ── the address ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["a@x.com,b@y.com", "a@x.com;b@y.com", "Ravi <r@x.com>", '"r"@x.com',
                                 "r@x", "r @x.com", "", None, "r@x.com\nBcc: e@evil.com", "@x.com", "r@@x.com"])
def test_anything_but_one_address_is_refused(raw: str | None) -> None:
    """EC-5, ISS-221."""
    assert parse_address(raw) is None


def test_one_address_passes() -> None:
    assert parse_address(" ravi.k@polysil.in ") == "ravi.k@polysil.in"


def test_a_subject_is_one_line_and_capped() -> None:
    assert one_line("a\r\nBcc: x@y.com\tb") == "a Bcc: x@y.com b"
    assert len(one_line("x" * 400)) == 150


# ── what it says ─────────────────────────────────────────────────────────────

AT = dt.datetime(2026, 10, 27, 4, 30, tzinfo=dt.UTC)


def test_one_notice_is_its_own_subject_and_links_its_record() -> None:
    out = render.notices("https://crm.example.in/", "Ravi", "staff",
                         [render.Notice("Waits for\nyour approval", AT, "quotation", "q-1")], 1)
    assert out.subject == "Waits for your approval"
    assert "https://crm.example.in/quotations/q-1" in out.text and "27 Oct 2026, 10:00 IST" in out.text
    assert render.FOOTER in out.text and render.FOOTER in out.html


def test_a_type_with_no_page_opens_the_crm_and_a_partner_opens_the_portal() -> None:
    assert render.link("https://c.in", "staff", "dispatch", "d-1") == "https://c.in/dashboard"
    assert render.link("https://c.in", "staff", None, None) == "https://c.in/dashboard"
    assert render.link("https://c.in", "partner_user", "lead", "l-1") == "https://c.in/portal"


def test_titles_are_escaped_and_bodies_never_appear() -> None:
    out = render.notices("https://c.in", "<Ravi>", "staff",
                         [render.Notice("<script>x</script>", AT, "lead", "l")], 1)
    assert "<script>" not in out.html and "&lt;script&gt;" in out.html and "&lt;Ravi&gt;" in out.html


def test_more_than_twenty_lists_twenty_and_says_how_many_more() -> None:
    items = [render.Notice(f"N{i}", AT, "lead", str(i)) for i in range(25)]
    out = render.notices("https://c.in", "Ravi", "staff", items, 1980)
    assert out.subject == "1980 updates in Polysil CRM"
    assert out.text.count("/leads/") == 20 and "And 1960 more" in out.text


def test_the_morning_summary_is_counts_and_a_link() -> None:
    out = render.morning("https://c.in", "Ravi", "staff", 2, 1)
    assert out.subject == "Your tasks: 2 due today, 1 overdue"
    assert "https://c.in/my-tasks" in out.text and "Tasks overdue: 1" in out.text


# ── SMTP by phase ────────────────────────────────────────────────────────────

class FakeSMTP:
    """Answers per phase from `script`; records what it was given."""

    script: ClassVar[dict[str, Any]] = {}
    seen: ClassVar[list[tuple[str, Any]]] = []

    def __init__(self, host: str, port: int, timeout: float = 0, **_: Any) -> None:
        self._do("connect", (host, port, timeout))

    def _do(self, phase: str, arg: Any) -> Any:
        FakeSMTP.seen.append((phase, arg))
        answer = FakeSMTP.script.get(phase)
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            return answer()
        return answer

    def set_debuglevel(self, n: int) -> None:
        FakeSMTP.seen.append(("debug", n))

    def ehlo(self) -> None: ...

    def starttls(self, context: Any = None) -> None:
        self._do("tls", None)

    def login(self, user: str, password: str) -> None:
        self._do("auth", user)

    def has_extn(self, name: str) -> bool:
        return bool(FakeSMTP.script.get("smtputf8"))

    def mail(self, sender: str, options: list[str] = []) -> tuple[int, bytes]:  # noqa: B006
        return self._do("mail", sender) or (250, b"ok")

    def rcpt(self, to: str) -> tuple[int, bytes]:
        return self._do("rcpt", to) or (250, b"ok")

    def data(self, body: bytes) -> tuple[int, bytes]:
        return self._do("data", body) or (250, b"queued")

    def quit(self) -> None: ...


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.script, FakeSMTP.seen = {}, []
    monkeypatch.setattr(smtp_mod.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtp_mod.smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def _send(settings: Settings | None = None, to: str = "ravi@polysil.in") -> Any:
    provider = smtp_mod.SmtpProvider(settings or _settings())
    return asyncio.run(provider.send(Email(to=to, to_name="Ravi\r\nBcc: x@y.com", subject="Hi",
                                           text="t", html="<p>h</p>", reference="r1")))


def test_an_accepted_send_goes_to_exactly_one_address_with_the_name_encoded(fake_smtp: type[FakeSMTP]) -> None:
    result = _send()
    assert result.outcome is Outcome.ACCEPTED and result.provider_msg_id
    assert ("rcpt", "ravi@polysil.in") in fake_smtp.seen and ("debug", 0) in fake_smtp.seen
    body = next(a for p, a in fake_smtp.seen if p == "data").decode()
    assert "\nBcc:" not in body and "Subject: Hi" in body


@pytest.mark.parametrize(("phase", "answer", "outcome"), [
    ("connect", OSError("refused"), Outcome.TRANSIENT),
    ("tls", smtplib.SMTPNotSupportedError("no STARTTLS"), Outcome.TRANSIENT),
    ("auth", smtplib.SMTPAuthenticationError(535, b"bad credentials"), Outcome.TRANSIENT),
    ("mail", (451, b"later"), Outcome.TRANSIENT),
    ("rcpt", (550, b"no such user"), Outcome.PERMANENT),
    ("rcpt", (450, b"mailbox busy"), Outcome.TRANSIENT),
    ("data", (554, b"rejected"), Outcome.PERMANENT),
    ("data", smtplib.SMTPServerDisconnected("gone"), Outcome.UNCERTAIN),
])
def test_the_outcome_follows_the_phase(fake_smtp: type[FakeSMTP], phase: str, answer: Any,
                                       outcome: Outcome) -> None:
    fake_smtp.script = {phase: answer}
    assert _send().outcome is outcome


def test_a_deadline_after_data_is_uncertain_and_before_it_transient(fake_smtp: type[FakeSMTP]) -> None:
    """EC-16: the thread may finish later; what decides is whether DATA started."""
    hold = threading.Event()
    fake_smtp.script = {"data": lambda: hold.wait(5) and (250, b"late")}
    assert _send(_settings(smtp_send_deadline=0.3)).outcome is Outcome.UNCERTAIN
    hold.set()
    hold2 = threading.Event()
    fake_smtp.script = {"rcpt": lambda: hold2.wait(5)}
    fake_smtp.seen = []
    assert _send(_settings(smtp_send_deadline=0.3)).outcome is Outcome.TRANSIENT
    hold2.set()
    # the thread finishes RCPT, sees the cancel and never starts DATA (code review F-1)
    time.sleep(0.5)
    assert ("rcpt", "ravi@polysil.in") in fake_smtp.seen
    assert not any(p == "data" for p, _ in fake_smtp.seen), "a transient answer must never deliver"


def test_errors_never_carry_the_password_the_user_or_the_address(fake_smtp: type[FakeSMTP]) -> None:
    fake_smtp.script = {"auth": smtplib.SMTPAuthenticationError(
        535, f"bad crm@example.in {PASSWORD} ravi@polysil.in".encode())}
    error = _send().error or ""
    assert PASSWORD not in error and "crm@example.in" not in error and "ravi@polysil.in" not in error


def test_a_non_ascii_address_is_permanent_and_never_reaches_the_server(fake_smtp: type[FakeSMTP]) -> None:
    """Code review F-4: ASCII only, here and in the database's eligibility check."""
    result = _send(to="रवि@polysil.in")
    assert result.outcome is Outcome.PERMANENT and result.error == "not one email address"
    assert fake_smtp.seen == []


def test_outside_production_every_email_goes_to_the_redirect(fake_smtp: type[FakeSMTP]) -> None:
    """EC-23."""
    s = _settings(environment="staging", email_redirect_to="dev@example.in",
                  public_web_url="https://staging.example.in")
    assert _send(s).outcome is Outcome.ACCEPTED
    assert ("rcpt", "dev@example.in") in fake_smtp.seen
    assert not any(p == "rcpt" and a == "ravi@polysil.in" for p, a in fake_smtp.seen)


# ── settings ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("over", "message"), [
    ({"email_provider": "mock"}, "mock in production"),
    ({"smtp_password": None}, "smtp_password"),
    ({"smtp_host": "  "}, "smtp_host"),
    ({"environment": "staging", "public_web_url": "https://s.example.in"}, "email_redirect_to"),
    ({"smtp_security": "ssl", "smtp_port": 587}, "does not go with port"),
    ({"smtp_security": "starttls", "smtp_port": 465}, "does not go with port"),
    ({"environment": "staging", "public_web_url": "https://s.example.in",
      "email_redirect_to": "dev@x.com,me@y.com"}, "email_redirect_to is not one email address"),
])
def test_a_misconfigured_email_refuses_to_start(over: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(**over)


def test_the_default_is_none_and_none_builds_no_provider() -> None:
    s = _settings(email_provider="none")
    assert get_email_provider(s) is None
    assert Settings.model_fields["email_provider"].default == "none"
    assert isinstance(get_email_provider(_settings(email_provider="mock", environment="local",
                                                   pdf_renderer="html")), MockEmailProvider)
