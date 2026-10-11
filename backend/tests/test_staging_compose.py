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
