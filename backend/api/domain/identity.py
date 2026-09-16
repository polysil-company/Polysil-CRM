"""Identity rules with no database (FS-006 rules 1, 2, 5 and 12).

How an email and a mobile are normalised, what a password must be, which roles a
person may hold, how a partner user's role follows its partner's type, and which
lead stages count as open. Pure functions and tables, so the service and the tests
share one answer.

`normalise_mobile` lives here now; `api/domain/leads.py` re-exports it. A lead
stores the result with the `+` (E.164), `app_user` stores it without, so the stored
form matches migration 007's `91[6-9]xxxxxxxxx` CHECK (FS-001's shape).
"""

from __future__ import annotations

import unicodedata


class MobileError(ValueError):
    """The number is not an Indian mobile in any accepted form."""


class EmailError(ValueError):
    """The address is not one the system stores."""


def normalise_mobile(raw: str) -> str:
    """Any Indian form a person types or pastes into +91XXXXXXXXXX.

    First NFKC-normalise and keep only digit values and a leading plus, so spaces,
    hyphens, brackets, dots, bidi marks and non-ASCII (Devanagari) digits all fall
    away. Then the Indian rules: a leading +91, 91 or 0 is stripped, and the ten
    digits must start 6 to 9. A foreign +<cc> number is refused (GAP-052).
    """
    if not raw:
        raise MobileError("mobile is required")
    s = unicodedata.normalize("NFKC", raw)
    had_plus = False
    seen_digit = False
    digits: list[str] = []
    for ch in s:
        value = unicodedata.digit(ch, None)
        if value is not None:
            digits.append(str(value))
            seen_digit = True
        elif ch == "+" and not seen_digit:
            had_plus = True
    d = "".join(digits)

    if had_plus:
        if d.startswith("91") and len(d) == 12:
            d = d[2:]
        else:
            # +<something else> is a foreign number, or a malformed +91 (GAP-052).
            raise MobileError("only Indian mobile numbers are accepted")
    elif d.startswith("91") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]

    if len(d) == 10 and d[0] in "6789":
        return "+91" + d
    raise MobileError("not an Indian mobile number")


def mobile_for_user(raw: str) -> str:
    """The `app_user.mobile` form: the same number without the plus, `91XXXXXXXXXX`."""
    return normalise_mobile(raw)[1:]


EMAIL_MAX = 254


def normalise_email(raw: str) -> str:
    """Trimmed and lower-cased. The database compares case-insensitively (citext)
    and enforces the trim and the length; the lower-casing is done here so the
    stored form is the one the person sees on their profile. The shape check is
    deliberately loose: one `@`, something on each side, a dot in the domain.
    Anything stricter refuses real addresses."""
    s = unicodedata.normalize("NFKC", raw or "").strip().lower()
    if not s or len(s) > EMAIL_MAX:
        raise EmailError("not an email")
    local, sep, domain = s.partition("@")
    if not sep or not local or "." not in domain or domain.startswith(".") \
            or domain.endswith(".") or any(ch.isspace() for ch in s):
        raise EmailError("not an email")
    return s


PASSWORD_MIN = 12
PASSWORD_MAX = 128   # Argon2 is deliberately slow; an unbounded input is a lever


def password_problem(password: str) -> str | None:
    """None when the password is acceptable, else the reason in the words the API
    returns under `fields.password` (rule 5; GAP-013 keeps the policy at length only)."""
    if len(password) < PASSWORD_MIN:
        return f"at least {PASSWORD_MIN} characters"
    if len(password) > PASSWORD_MAX:
        return f"at most {PASSWORD_MAX} characters"
    return None


# RBAC section 2: the sixteen roles a person may hold. The `system` role is never
# assignable and never listed (rule 1, rule 19); a test leftover is never listed.
ASSIGNABLE_ROLES: tuple[str, ...] = (
    "field_officer", "district_manager", "state_manager", "regional_manager",
    "admin_sales", "md_ceo",
    "account_manager", "dispatch_manager", "qc_manager", "state_coordinator",
    "marketing", "support",
    "distributor", "dealer", "sub_dealer",
    "board",
)

# A partner user's role is its partner's type (rule 2; GAP-063). The API derives
# the code; the database checks the role's level against the seeded level of the
# type's portal role. LEVEL_BY_TYPE is what the seed must hold for that check to
# mean anything; tests/db/test_functions_007.py asserts the seeded rows match it.
PORTAL_ROLE_BY_TYPE: dict[str, str] = {
    "distributor": "distributor",
    "dealer": "dealer",
    "sub_dealer": "sub_dealer",
}
LEVEL_BY_TYPE: dict[str, int] = {"sub_dealer": 1, "dealer": 2, "distributor": 3}

# Rule 12 (open = not won, lost or merged, not deleted; dormant is open) is
# api/domain/leads.py's TERMINAL, bound into the handover's lead lock; the two
# definers that count open leads carry the same three stages as SQL.
