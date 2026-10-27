"""Schemathesis over the API (test build-out 2).

Generated requests against every GET route, signed in as an MD (global scope on
every module, so the most code runs). Two claims, both of which the frontend's
Zod schemas rely on:

* **no 5xx**, whatever the parameters: a bad query is a 4xx with the envelope;
* **every response matches the OpenAPI schema** the API docs are generated from,
  so `docs/api/` is the truth and not a description of it.

Mutations are not generated here: random bodies would create rows in a shared
development database. Their validation is covered route by route in tests/api.
"""

# ruff: noqa: E501  (inline SQL)

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
import schemathesis
from argon2 import PasswordHasher
from hypothesis import HealthCheck, settings
from schemathesis.config import SchemathesisConfig
from schemathesis.specs.openapi.checks import response_schema_conformance
from starlette.testclient import TestClient

from api.config import get_settings
from api.integrations.cache import get_redis
from api.main import app

pytestmark = pytest.mark.db

PASSWORD = "schemathesis horse battery staple"
ANSWERS_503 = frozenset({"pdf_unavailable", "busy", "storage_unavailable", "service_unavailable"})
# Schemathesis 4 adds its own coverage and examples phases on top of Hypothesis's
# examples: about a minute a route against the remote dev database. The fuzzing
# phase alone, at SCHEMATHESIS_EXAMPLES per route, keeps the whole sweep in CI time.
CONFIG = SchemathesisConfig.from_dict({"phases": {"coverage": {"enabled": False},
                                                  "examples": {"enabled": False},
                                                  "stateful": {"enabled": False}}})
schema = schemathesis.openapi.from_asgi("/openapi.json", app, config=CONFIG).include(method="GET")


def _dsn() -> str:
    url = str(get_settings().database_url)
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(autouse=True)
def _redis_per_event_loop() -> Iterator[None]:
    """Replaces the conftest fixture of this name. Each Schemathesis call runs the
    app on a loop of its own, so the cached client is dropped, not closed: closing
    it from the test's loop raised "attached to a different loop" (CI, 27 Oct)."""
    get_redis.cache_clear()
    yield
    get_redis.cache_clear()


@pytest.fixture(scope="module")
def headers() -> Iterator[dict[str, str]]:
    email = f"schema_{uuid.uuid4().hex[:8]}@polysil.in"
    with psycopg.connect(_dsn(), autocommit=True, prepare_threshold=None) as c:
        office = c.execute("SELECT id FROM org_unit WHERE deleted_at IS NULL ORDER BY role_level DESC, id LIMIT 1").fetchone()
        assert office is not None
        row = c.execute(
            "INSERT INTO app_user (user_type, email, password_hash, full_name, role_id, org_unit_id) "
            "SELECT 'staff', %s, %s, 'Schema Walker', r.id, %s FROM role r WHERE r.code = 'md_ceo' RETURNING id",
            (email, PasswordHasher().hash(PASSWORD), office[0])).fetchone()
        assert row is not None
        uid = row[0]
    try:
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert r.status_code == 200, r.text
            get_redis.cache_clear()
            yield {"Authorization": f"Bearer {r.json()['data']['access_token']}"}
    finally:
        with psycopg.connect(_dsn(), autocommit=True, prepare_threshold=None) as c:
            for stmt in ("DELETE FROM tracking_view_log WHERE viewer_id = %s",
                         "DELETE FROM idempotency_record WHERE user_id = %s",
                         "DELETE FROM activity_event WHERE actor_id = %s OR entity_id = %s",
                         "DELETE FROM session WHERE user_id = %s",
                         "DELETE FROM app_user WHERE id = %s"):
                c.execute(stmt, (uid,) * stmt.count("%s"))
            c.execute("DELETE FROM login_attempt WHERE identifier = %s", (email,))


@schema.parametrize()
@settings(max_examples=int(os.environ.get("SCHEMATHESIS_EXAMPLES", "8")), deadline=None,
          suppress_health_check=list(HealthCheck))
def test_no_get_route_errors_or_breaks_its_schema(case: Any, headers: dict[str, str]) -> None:
    get_redis.cache_clear()  # a client from the previous call's loop is no use here
    response = case.call(headers=headers)
    status = response.status_code
    if status >= 500:
        # A 503 with one of these codes is the API answering, not failing: the
        # renderer or storage is down or busy (on this box WeasyPrint is missing).
        # Anything else in 5xx, a 500 above all, is a crash.
        try:
            code = (response.json().get("error") or {}).get("code")
        except ValueError:
            code = None
        assert status == 503 and code in ANSWERS_503, f"{case.method} {case.formatted_path}: {status} {response.text[:200]}"
        return
    case.validate_response(response, checks=[response_schema_conformance])
