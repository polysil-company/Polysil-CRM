"""api/domain/identity.py: identity normalisation, the password policy, the role
tables and the open-stage set. Pure, no database (FS-006 10)."""

from __future__ import annotations

import pytest

from api.domain import leads
from api.domain.identity import (
    ASSIGNABLE_ROLES,
    LEVEL_BY_TYPE,
    PASSWORD_MAX,
    PASSWORD_MIN,
    PORTAL_ROLE_BY_TYPE,
    EmailError,
    MobileError,
    mobile_for_user,
    normalise_email,
    normalise_mobile,
    password_problem,
)

# ── email ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("raw", "want"), [
    ("Meera@Polysil.in", "meera@polysil.in"),
    ("  meera@polysil.in \n", "meera@polysil.in"),
    ("ＭＥＥＲＡ@polysil.in", "meera@polysil.in"),   # NFKC folds full-width  # noqa: RUF001
    ("a.b+tag@sub.example.co.in", "a.b+tag@sub.example.co.in"),
])
def test_an_email_is_trimmed_lower_cased_and_folded(raw: str, want: str) -> None:
    assert normalise_email(raw) == want


@pytest.mark.parametrize("raw", [
    "", "   ", "meera", "@polysil.in", "meera@", "meera@polysil", "meera@.in",
    "meera@polysil.in.", "me era@polysil.in", "a" * 250 + "@x.in",
])
def test_a_malformed_email_is_refused(raw: str) -> None:
    with pytest.raises(EmailError, match="not an email"):
        normalise_email(raw)


# ── mobile ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "9876543210", "09876543210", "919876543210", "+919876543210",
    "+91 98765 43210", "98765-43210", "(0) 98765 43210", "९८७६५४३२१०",
])
def test_every_indian_form_becomes_one_stored_form(raw: str) -> None:
    assert normalise_mobile(raw) == "+919876543210"
    assert mobile_for_user(raw) == "919876543210"


@pytest.mark.parametrize("raw", ["", "12345", "5876543210", "+447700900123", "+9198765432100"])
def test_a_foreign_or_malformed_number_is_refused(raw: str) -> None:
    with pytest.raises(MobileError):
        mobile_for_user(raw)


def test_the_lead_domain_re_exports_the_same_normaliser() -> None:
    """The lead service and its tests import from api.domain.leads; the function
    moved and the name must resolve to the one implementation."""
    assert leads.normalise_mobile is normalise_mobile
    assert leads.MobileError is MobileError


# ── password ─────────────────────────────────────────────────────────────────

def test_the_password_policy_is_length_only() -> None:
    assert password_problem("x" * (PASSWORD_MIN - 1)) == f"at least {PASSWORD_MIN} characters"
    assert password_problem("x" * PASSWORD_MIN) is None
    assert password_problem("correct horse battery staple") is None
    assert password_problem("x" * (PASSWORD_MAX + 1)) == f"at most {PASSWORD_MAX} characters"


# ── roles and stages ─────────────────────────────────────────────────────────

def test_sixteen_assignable_roles_and_never_system() -> None:
    assert len(ASSIGNABLE_ROLES) == 16
    assert len(set(ASSIGNABLE_ROLES)) == 16
    assert "system" not in ASSIGNABLE_ROLES
    for portal in PORTAL_ROLE_BY_TYPE.values():
        assert portal in ASSIGNABLE_ROLES


def test_every_partner_type_has_a_portal_role_and_a_level() -> None:
    """The two tables agree with each other; whether the seeded roles carry these
    levels is a database question, asserted in tests/db/test_functions_007.py."""
    assert set(PORTAL_ROLE_BY_TYPE) == set(LEVEL_BY_TYPE) == {"distributor", "dealer", "sub_dealer"}
    assert sorted(LEVEL_BY_TYPE.values()) == [1, 2, 3]


def test_the_handover_treats_dormant_as_open() -> None:
    """Rule 12 is leads.TERMINAL, the one set the handover binds (F-3)."""
    assert {"won", "lost", "merged"} == leads.TERMINAL
    assert "dormant" not in leads.TERMINAL
