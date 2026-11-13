"""The staging compose file: the one-shot tools container runs the template sync
after every migration (FS-012), so it must reach the same WhatsApp account the
worker sends through."""

from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[1] / "infra" / "docker-compose.staging.yml"


def test_the_tools_container_reaches_the_workers_whatsapp_account() -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    worker = {k for k in services["worker"]["environment"] if k.startswith("WHATSAPP_")}
    tools = set(services["tools"]["environment"])
    needed = {"WHATSAPP_PROVIDER", "WHATSAPP_AUTH_TOKEN", "WHATSAPP_ORIGIN_WEBSITE"}
    assert needed <= worker, "the worker lost a setting this test assumes"
    assert needed <= tools, sorted(needed - tools)


def test_the_profile_switch_reaches_the_worker_and_is_never_empty() -> None:
    """FS-064 rule 25: both compose files pass an explicit environment list, so a
    key missing here never reaches the container and the switch does nothing. An
    empty default would stop the worker: Settings reads it as a bool."""
    want = "${QUOTATION_PROFILE_ENABLED:-true}"
    staging = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    assert staging["worker"]["environment"]["QUOTATION_PROFILE_ENABLED"] == want
    prod = yaml.safe_load(COMPOSE.with_name("docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert prod["services"]["worker"]["environment"]["QUOTATION_PROFILE_ENABLED"] == want
