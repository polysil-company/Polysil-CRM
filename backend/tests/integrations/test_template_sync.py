"""FS-012 rule 3: a `message_template` row is switched on only for a template the
account has approved, in the language this system sends."""

from __future__ import annotations

from api.integrations.whatsapp.check import approved_names


def _row(name: str, status: str, language: str = "en") -> dict[str, object]:
    return {"name": name, "status": status, "language": language}


def test_only_approved_templates_in_our_language_count() -> None:
    rows = [
        _row("polysil_order_confirmed", "APPROVED"),
        _row("polysil_approval_waiting", "PENDING"),
        _row("polysil_order_decided", "REJECTED"),
        _row("polysil_hindi_only", "APPROVED", "hi"),
        _row("Polysil_Mixed_Case", "Approved"),
    ]
    assert approved_names(rows, "en") == {"polysil_order_confirmed", "polysil_mixed_case"}


def test_our_localization_decides_when_a_name_has_several() -> None:
    rows = [_row("polysil_order_decided", "APPROVED", "hi"),
            _row("polysil_order_decided", "PENDING", "en")]
    assert approved_names(rows, "en") == set()
    rows.reverse()
    assert approved_names(rows, "en") == set(), "order in the listing does not matter"


def test_a_status_that_only_contains_the_word_is_not_approval() -> None:
    assert approved_names([_row("t", "NOT_APPROVED"), _row("u", "unapproved")], "en") == set()


def test_the_script_runs_as_the_deploy_calls_it() -> None:
    """The deploy runs `python scripts/sync_message_templates.py` from the repository
    root; without the root on the path it died on `import api` and the order
    messages were never switched."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["WHATSAPP_PROVIDER"] = "mock"
    done = subprocess.run([sys.executable, "scripts/sync_message_templates.py"], cwd=root,
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "mock provider" in done.stdout
