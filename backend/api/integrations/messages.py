"""The messages this system sends: their keys, their values, and the English bodies
the mock provider renders.

A WhatsApp message's wording lives in Meta's approval of the client's template,
not here (FS-007 rule 2). What this module holds is what the adapter needs to
send one: the setting that names the template on the account, the payload keys in
the template's positional order, which value (if any) rides on the copy-code
button, and how old a row may be before sending it helps nobody (rule 4).

GAP-022 (narrowed): `notification_template` stays migration 015. The bodies below
are the mock's rendering and the preview, English only (ISS-010).

The rendering happens in the worker, not in the database. `auth_issue_otp_challenge`
writes a `template_key` and a payload precisely so that a function granted to
`app_anon` never accepts free-text message content - that would be an open relay to
any number, at our cost (FS-001 9.6 R5-7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from api.config import Settings

TEMPLATE_AUTH_OTP: Final = "auth.otp"
TEMPLATE_LEAD_ACK: Final = "lead_ack"
TEMPLATE_QUOTATION_SHARE: Final = "quotation_share"
# FS-003a: the public form's code. Its own key, so a lead code never retires a
# sign-in code, but the same approved authentication template: Meta fixes the
# body of an authentication template, so a second one would say the same words.
TEMPLATE_LEAD_VERIFY: Final = "lead.verify"
# FS-012: the order's messages. Their provider names live in the message_template
# table, and the definer that writes the row copies the name into the payload as
# `_template`, so the table is the one switch (EC-5, plan review B-2).
TEMPLATE_ORDER_CONFIRMED: Final = "order.confirmed"
TEMPLATE_APPROVAL_WAITING: Final = "approval.waiting"
TEMPLATE_ORDER_DECIDED: Final = "order.decided"
# FS-015: the complainant's two messages, switched on the same way (GAP-153)
TEMPLATE_COMPLAINT_REGISTERED: Final = "complaint.registered"
TEMPLATE_COMPLAINT_UPDATED: Final = "complaint.updated"
PAYLOAD_TEMPLATE_KEY: Final = "_template"

# FS-007 rule 16: the channel the sign-in code goes out on, a deployment constant
# the 202 body and the definer's row both carry. Never derived from the number.
# GAP-074: a person without WhatsApp cannot sign in; SMS stays unbuilt until the
# client says someone needs it (question 3a.8).
OTP_CHANNEL: Final = "whatsapp"

# Rule 10c: WhatsApp refuses a value with newlines, tabs or long runs of spaces,
# and a farmer's name is free text an officer typed.
VALUE_MAX: Final = 100


@dataclass(frozen=True)
class TemplateSpec:
    name_setting: str | None     # the Settings attribute holding the provider's template
                                 # name; None: the payload's `_template` carries it
    params: tuple[str, ...]      # payload keys, in the template's positional order
    button: str | None           # the payload key sent as the copy-code button's value
    max_age: timedelta | None    # None: derived from settings (the OTP's TTL less a minute)
    # GAP-073: after an uncertain send (no answer in time), send again? Yes for a code:
    # a duplicate code is a nuisance, a lost one locks the person out (FS-001). No for
    # the rest: a duplicate order message is a fee and looks broken to the customer.
    resend_uncertain: bool = False


TEMPLATES: Final[dict[str, TemplateSpec]] = {
    TEMPLATE_AUTH_OTP: TemplateSpec("whatsapp_template_otp", ("code",), "code", None,
                                    resend_uncertain=True),
    # the challenge lives ten minutes; a code older than nine is not worth sending
    TEMPLATE_LEAD_VERIFY: TemplateSpec("whatsapp_template_otp", ("code",), "code",
                                       timedelta(minutes=9), resend_uncertain=True),
    # GAP-072: farmer_name is an officer-typed value on Polysil's number, bounded by
    # normalise_value and by rule 10b (once a day per number) until the client decides.
    TEMPLATE_LEAD_ACK: TemplateSpec("whatsapp_template_lead_ack",
                                    ("farmer_name", "inquiry_no"), None, timedelta(hours=24)),
    # FS-005 rule 16: the link is a body parameter carrying the whole URL, built by
    # the worker from public_web_url and the row's token; the origin is bounded at
    # startup so the value never reaches VALUE_MAX (edge case 17). No button: the
    # adapter's only button is the authentication one (GAP-110).
    TEMPLATE_ORDER_CONFIRMED: TemplateSpec(None, ("party_name", "order_no", "total"), None,
                                           timedelta(hours=24)),
    TEMPLATE_APPROVAL_WAITING: TemplateSpec(None, ("approver_name", "order_no", "party_name",
                                                   "total"), None, timedelta(hours=24)),
    TEMPLATE_ORDER_DECIDED: TemplateSpec(None, ("owner_name", "order_no", "party_name",
                                                "outcome"), None, timedelta(hours=24)),
    TEMPLATE_COMPLAINT_REGISTERED: TemplateSpec(None, ("contact_name", "complaint_no"), None,
                                                timedelta(hours=24)),
    TEMPLATE_COMPLAINT_UPDATED: TemplateSpec(None, ("contact_name", "complaint_no", "status"), None,
                                             timedelta(hours=24)),
    TEMPLATE_QUOTATION_SHARE: TemplateSpec("whatsapp_template_quotation_share",
                                           ("party_name", "quote_no", "link"), None,
                                           timedelta(days=7)),
}

_BODIES: Final[dict[str, str]] = {
    TEMPLATE_AUTH_OTP: (
        "{code} is your Polysil verification code. "
        "It is valid for 5 minutes. Do not share it with anyone."
    ),
    TEMPLATE_LEAD_VERIFY: (
        "{code} is your Polysil verification code. "
        "It is valid for 10 minutes. Do not share it with anyone."
    ),
    # FS-003 rule 17. English only, like every body here (ISS-010). The worker
    # dead-letters an unknown key, so a lead created before this body existed would
    # have failed its acknowledgement silently (plan review B-5).
    TEMPLATE_LEAD_ACK: (
        "Thank you {farmer_name}. Polysil has received your enquiry {inquiry_no}. "
        "Our team will contact you shortly."
    ),
    TEMPLATE_QUOTATION_SHARE: (
        "{party_name}, your Polysil quotation {quote_no} is ready: {link}"
    ),
    TEMPLATE_ORDER_CONFIRMED: (
        "Hello {party_name}, your order {order_no} with Polysil Irrigation is confirmed. "
        "Order value: Rs {total}. Our team will contact you about delivery."
    ),
    TEMPLATE_APPROVAL_WAITING: (
        "Hello {approver_name}, order {order_no} for {party_name}, value Rs {total}, "
        "is waiting for your approval in the Polysil CRM."
    ),
    TEMPLATE_ORDER_DECIDED: (
        "Hello {owner_name}, order {order_no} for {party_name} has been {outcome}. "
        "Please check the Polysil CRM for details."
    ),
    TEMPLATE_COMPLAINT_REGISTERED: (
        "Hello {contact_name}, your complaint {complaint_no} is registered with Polysil "
        "Irrigation. We will keep you informed."
    ),
    TEMPLATE_COMPLAINT_UPDATED: (
        "Hello {contact_name}, your complaint {complaint_no} has been {status}. "
        "We will keep you informed."
    ),
}


class UnknownTemplateError(KeyError):
    """Raised rather than sending a half-rendered message.

    The outbox row is written by a database function and drained by a worker that
    may be a release behind it, so an unknown key is a real state and it must fail
    loudly into the dead-letter path instead of delivering "{code} is your..." to a
    farmer.
    """


def normalise_value(value: object) -> str:
    """Rule 10c: one line, single spaces, trimmed, at most VALUE_MAX characters."""
    return " ".join(str(value).split())[:VALUE_MAX]


def template_values(template_key: str, payload: dict[str, object]) -> tuple[list[str], str | None]:
    """The positional values and the button value for one message, normalised.

    Raises UnknownTemplateError for a key this worker does not know or a payload
    missing one of its values, so the worker dead-letters rather than sends.
    """
    try:
        spec = TEMPLATES[template_key]
    except KeyError as exc:
        raise UnknownTemplateError(template_key) from exc
    try:
        values = [normalise_value(payload[k]) for k in spec.params]
    except KeyError as exc:
        raise UnknownTemplateError(f"{template_key} is missing {exc}") from exc
    button = normalise_value(payload[spec.button]) if spec.button else None
    return values, button


def max_age(template_key: str, settings: Settings) -> timedelta | None:
    """Rule 4. None for a key this worker does not know: the caller dead-letters
    it for that reason instead."""
    spec = TEMPLATES.get(template_key)
    if spec is None:
        return None
    if spec.max_age is not None:
        return spec.max_age
    return settings.otp_ttl - timedelta(seconds=60)


def render(template_key: str, payload: dict[str, object]) -> str:
    """The English body: the mock provider's message and the preview."""
    try:
        body = _BODIES[template_key]
    except KeyError as exc:
        raise UnknownTemplateError(template_key) from exc
    try:
        return body.format(**payload)
    except KeyError as exc:
        raise UnknownTemplateError(f"{template_key} is missing {exc}") from exc


def provider_template(key: str, settings: Settings, payload: dict[str, object]) -> str | None:
    """The account's template name for a key: from its setting, or, for the keys
    the database gates, from the payload the definer wrote (FS-012)."""
    spec = TEMPLATES[key]
    if spec.name_setting is None:
        name = payload.get(PAYLOAD_TEMPLATE_KEY)
        return str(name) if name else None
    value = getattr(settings, spec.name_setting)
    return str(value) if value else None
