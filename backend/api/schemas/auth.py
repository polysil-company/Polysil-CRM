"""Request and response shapes for /auth.

**These are the contract with the frontend track** (CLAUDE.md 2.3, ADR-028).
FastAPI emits them as OpenAPI, `scripts/generate_api_docs.py` turns that into
markdown, and the frontend generates a typed client from it. So:

  * every field carries a `description`, because a field without one generates an
    empty cell in the shared document;
  * an additive change (a new endpoint, a new optional field) needs no ceremony;
  * **a breaking change needs agreement from both engineers** - it invalidates
    whatever the other track has already built against the previous shape.

The refresh token never appears in any model here. It travels as an httpOnly
cookie and nothing else (rule 4).
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.integrations.messages import OTP_CHANNEL

# E.164 without the plus, which is what the client sends and what app_user.mobile
# stores. Indian numbers are 12 digits (91 + 10); the range is wider so a future
# country code is not a schema change.
MOBILE_RE = re.compile(r"^[1-9]\d{9,14}$")


class Envelope[T](BaseModel):
    """Every success response is `{"data": ...}`.

    A bare array or scalar at the top level cannot grow a sibling field later
    without breaking every client that parsed it.
    """

    data: T


class ErrorBody(BaseModel):
    code: str = Field(
        description="Stable machine-readable code. Switch on this, never on the message.",
        examples=["invalid_credentials"],
    )
    message: str = Field(
        description="Human-readable and safe to show a user. May be reworded at any "
        "time, and is not part of the contract.",
        examples=["Email or password is incorrect."],
    )
    fields: dict[str, str] | None = Field(
        default=None,
        description="Present only on a 422. Maps a field path to why it was "
        "rejected, so a form can mark the offending input rather than showing a "
        "banner.",
        examples=[{"mobile": "mobile must be E.164 digits without a leading plus"}],
    )


class ErrorResponse(BaseModel):
    """Every failure response is `{"error": {"code", "message"}}`."""

    error: ErrorBody


# ── login ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    # No model-wide str_strip_whitespace here, deliberately. It would strip the
    # password too, and a password with a leading or trailing space would then
    # never match the hash it was created from - the user types the right thing
    # and is told it is wrong, forever.
    email: Annotated[str, Field(
        max_length=254,
        description="Staff email address. Case-insensitive: stored as citext. "
        "Surrounding whitespace is trimmed.",
        examples=["asha@polysil.in"],
    )]
    password: Annotated[str, Field(
        min_length=1,
        max_length=1024,
        # Passed to Argon2 exactly as typed. Whitespace is part of a password.
        description="Sent exactly as typed, including any leading or trailing "
        "spaces. Minimum length is enforced when the password is set, not here - "
        "an existing password shorter than the current policy must still be able to "
        "sign in. The upper bound only stops an Argon2 denial-of-service.",
    )]

    @field_validator("email")
    @classmethod
    def _trim(cls, v: str) -> str:
        return v.strip()


class TokenResponse(BaseModel):
    """The refresh token is deliberately absent - it is set as an httpOnly cookie."""

    access_token: str = Field(description="JWT. Send as `Authorization: Bearer <token>`.")
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = Field(
        description="Seconds until the access token expires. Refresh before this, "
        "not after: a 401 mid-action loses the user's work.",
        examples=[900],
    )


# ── OTP ──────────────────────────────────────────────────────────────────────

class OtpRequestBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mobile: Annotated[str, Field(
        description="E.164 without the leading plus, e.g. 919876543210.",
        examples=["919876543210"],
    )]

    @field_validator("mobile")
    @classmethod
    def _e164(cls, v: str) -> str:
        v = v.lstrip("+").replace(" ", "")
        if not MOBILE_RE.match(v):
            raise ValueError("mobile must be E.164 digits without a leading plus")
        return v


class OtpRequestResponse(BaseModel):
    """**Always 202, and always this body.**

    It is identical whether the number is known, unknown, inactive, or has hit a
    limit. A different response would turn this endpoint into a "is this dealer
    registered" oracle, and a 429 would turn the rate limiter into the same oracle.
    `sent` is therefore always `true` and is not evidence that anything was sent.
    """

    sent: Literal[True] = True
    channel: Literal["whatsapp", "sms"] = Field(
        default=OTP_CHANNEL,
        description="Where the code arrives. A deployment-wide constant, never a "
        "per-number value: render it in the wording, do not branch on it.",
    )
    expires_in: int = Field(
        description="Seconds the code remains valid, for the countdown on the "
        "verify screen.",
        examples=[300],
    )
    resend_after: int = Field(
        description="Seconds before offering a resend. Deliberately longer than "
        "`expires_in` would suggest: three resends a minute apart exhaust the "
        "per-phone burst limit, after which the UI would claim 'code sent' for "
        "another eleven minutes with nothing being sent.",
        examples=[300],
    )


class OtpVerifyBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    mobile: Annotated[str, Field(description="Same number the code was requested for.")]
    code: Annotated[str, Field(
        description="The six digits from the message.",
        examples=["482913"],
    )]

    @field_validator("mobile")
    @classmethod
    def _e164(cls, v: str) -> str:
        return OtpRequestBody._e164(v)

    @field_validator("code")
    @classmethod
    def _digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("code must be digits")
        return v


# ── /auth/me ─────────────────────────────────────────────────────────────────

class RoleRef(BaseModel):
    code: str = Field(description="Stable identifier, e.g. district_manager.")
    name: str = Field(description="Display name.")


class OrgUnitRef(BaseModel):
    id: str
    name: str


class PartnerRef(BaseModel):
    id: str
    name: str | None = Field(
        default=None,
        description="Null until the channel module lands; the id is stable now.",
    )


class ModulePermission(BaseModel):
    module: str = Field(description="e.g. leads, orders, subsidy.")
    actions: list[str] = Field(
        description="Any of view, create, edit, approve, delete.",
        examples=[["view", "create", "edit"]],
    )
    scope: str | None = Field(
        default=None,
        description="One of own, org_subtree, territory, partner_subtree, global. "
        "Taken from the module's `view` row, which the others inherit.",
        examples=["org_subtree"],
    )


class MeResponse(BaseModel):
    """What the frontend needs to render navigation and hide controls.

    > **`permissions` is for rendering, never for security.** Hiding a button is
    > courtesy; the database is the boundary. An endpoint the UI forgets to hide
    > still returns 403, and a row outside scope is still invisible.
    """

    id: str
    full_name: str
    user_type: Literal["staff", "partner_user", "consumer"]
    role: RoleRef | None = Field(
        default=None, description="Null for a consumer, which holds no role."
    )
    org_unit: OrgUnitRef | None = Field(
        default=None, description="Staff only. Never set together with `partner`."
    )
    partner: PartnerRef | None = Field(
        default=None, description="Portal users only. Never set together with `org_unit`."
    )
    must_change_password: bool = Field(
        default=False,
        description="True while a temporary password set by an administrator is in "
        "force. Until the person changes it, every route except this one and "
        "POST /auth/password answers 403 `password_change_required`; show the "
        "change-password screen.")
    permissions: list[ModulePermission] = Field(default_factory=list)


class OwnPasswordChange(BaseModel):
    """POST /auth/password: a signed-in staff member changes their own password."""

    current_password: Annotated[str, Field(
        min_length=1, max_length=128, description="The password in force now.")]
    new_password: Annotated[str, Field(
        min_length=1, max_length=128,
        description="At least 12 characters. Every session, this one included, is "
        "signed out when it is accepted; sign in again with it.")]
