"""Message bodies, as constants.

GAP-022: `notification_template` is migration 015, and the WhatsApp
template-approval cycle is 11za's rather than ours. An OTP body is one line with
one substitution, and the template machinery - channel, language, provider
template id - is not needed to deliver it.

**The consequence is written down rather than discovered:** the text cannot be
changed without a release, and it is English only. `Requirements.md` asks for Hindi
and Gujarati, and ISS-010 already records that the content itself is a client
deliverable.

The rendering happens in the worker, not in the database. `auth_issue_otp_challenge`
writes a `template_key` and a payload precisely so that a function granted to
`app_anon` never accepts free-text message content - that would be an open SMS
relay to any number, at our cost (FS-001 9.6 R5-7).
"""

from __future__ import annotations

from typing import Final

TEMPLATE_AUTH_OTP: Final = "auth.otp"
TEMPLATE_LEAD_ACK: Final = "lead_ack"

_BODIES: Final[dict[str, str]] = {
    TEMPLATE_AUTH_OTP: (
        "{code} is your Polysil verification code. "
        "It is valid for 5 minutes. Do not share it with anyone."
    ),
    # FS-003 rule 17. English only, like every body here (ISS-010). The worker
    # dead-letters an unknown key, so a lead created before this body existed would
    # have failed its acknowledgement silently (plan review B-5).
    TEMPLATE_LEAD_ACK: (
        "Thank you {farmer_name}. Polysil has received your enquiry {inquiry_no}. "
        "Our team will contact you shortly."
    ),
}


class UnknownTemplateError(KeyError):
    """Raised rather than sending a half-rendered message.

    The outbox row is written by a database function and drained by a worker that
    may be a release behind it, so an unknown key is a real state and it must fail
    loudly into the dead-letter path instead of delivering "{code} is your..." to a
    farmer.
    """


def render(template_key: str, payload: dict[str, object]) -> str:
    try:
        body = _BODIES[template_key]
    except KeyError as exc:
        raise UnknownTemplateError(template_key) from exc
    try:
        return body.format(**payload)
    except KeyError as exc:
        raise UnknownTemplateError(f"{template_key} is missing {exc}") from exc
