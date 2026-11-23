"""The read-only HTTP checks (FS-065 rules 1, 3, 10 to 15).

Every parameterless GET in `live/inventory.json` is called once with the run's
token and once without. The client refuses anything but GET, so nothing in this
file can write beyond the sign-in and the sign-out the client names.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from live import inventory
from live.client import API, EXPORT_TOO_LARGE, PASS, LiveClient, judge
from live.conftest import resolve_query
from live.redact import describe

TARGET = os.environ.get("LIVE_TARGET", "")
ENTRIES = sorted(inventory.load().values(), key=lambda e: e.path)
PORTAL = f"{API}/portal"


def _query(entry: inventory.Entry, placeholders: dict[str, str]) -> dict[str, str]:
    try:
        return resolve_query(entry.query, placeholders)
    except KeyError as exc:
        # the inventory test in the normal suite rejects an unknown placeholder, so
        # one missing here is a value this box does not have yet, such as no lead
        pytest.skip(f"{exc.args[0]} on this box")


def _called_or_skipped(entry: inventory.Entry, target: str) -> None:
    reason = entry.skip_reason(target)
    if reason:
        pytest.skip(reason)
    if target == "production" and entry.path.startswith(PORTAL):
        # No OTP and no message on production (rule 3); a portal path reaching
        # here means the inventory lost its skip.
        pytest.fail(f"{entry.path} has no production skip; portal paths are never called there")


def test_health_names_the_target(health: dict[str, Any], target: str) -> None:
    assert health["environment"] == target, f"/health reports {health['environment']!r}"
    assert health["pre_auth_containment"] is True, "/health reports containment off"
    assert health["runtime_role"] == "app_role", "/health reports another runtime role"


def test_check_account_is_usable(me: dict[str, Any]) -> None:
    assert me.get("must_change_password") is False, "the check account must change its password"
    assert me.get("permissions"), "the check account holds no permission at all"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.path)
def test_get(entry: inventory.Entry, signed_in: LiveClient, me: dict[str, Any],
             target: str, placeholders: dict[str, str]) -> None:
    _called_or_skipped(entry, target)
    response = signed_in.get(entry.path, params=_query(entry, placeholders))
    if response.status_code == 401:
        pytest.exit(f"auth failure mid-run, stopping (rule 12): {describe(response)}",
                    returncode=1)
    outcome, detail = judge(response, target, entry.forbidden)
    if outcome == EXPORT_TOO_LARGE:
        pytest.xfail(f"export_too_large: {detail}")
    assert outcome == PASS, detail


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.path)
def test_get_without_token(entry: inventory.Entry, client: LiveClient, target: str,
                           placeholders: dict[str, str]) -> None:
    _called_or_skipped(entry, target)
    if entry.public:
        pytest.skip("public by design: answers without a token")
    response = client.get(entry.path, params=_query(entry, placeholders), auth=False)
    assert response.status_code == 401, describe(response)
