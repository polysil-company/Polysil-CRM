"""Box checks on a deployed worker (FS-065 rules 2, 4 to 7).

Run as `python -m worker.live_check` in a one-off container of the worker service
(`compose run --rm --no-deps worker ...`): the worker's settings and image, its
own memory, and the live worker untouched (rule 7). A plain module, because the
image carries no pytest.

Each check returns one result and stdout carries one JSON object per check,
nothing else. The exit code is 1 when any check fails.

**Nothing here writes.** The database is read in one transaction whose first
statement is `SET TRANSACTION READ ONLY`, never a session setting: PgBouncer
drops a connect option, and a session SET would outlive this transaction on a
pooled backend a real user borrows next (rule 2). The render runs on a made-up
document through `render_document` alone; the job's own entry point claims a
real quotation and is never imported here (rule 6). The storage check is the
startup probe, and the Redis check is `PING`.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import json
import pathlib
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from pypdf import PdfReader
from redis.asyncio import Redis
from sqlalchemy import text

from api.config import Settings, get_settings
from api.db.session import async_session_factory
from api.storage import get_storage
from worker.jobs.quotations import (
    company_profile,
    profile_problem,
    render_document,
    renderer_available,
)
from worker.sample_quotation import PAGE_ONE_FIGURES, document

Outcome = Literal["pass", "fail", "skip"]

ROOT = pathlib.Path(__file__).resolve().parents[1]
# a hung database or Redis is a fail with a reason, not a run that never ends
# (rule 16)
TIMEOUT_SECONDS = 60.0
DETAIL_LIMIT = 300

# what a storage provider says when it refuses the credentials, as opposed to
# not answering at all (edge case 27)
_DENIED = re.compile(r"\b(401|403)\b|AccessDenied|Forbidden|Unauthorized|InvalidAccessKeyId"
                     r"|SignatureDoesNotMatch", re.IGNORECASE)
_USERINFO = re.compile(r"://[^@\s/]+@")
_KEY_VALUE = re.compile(r"\b(password|passwd|secret|token)=[^\s&;]+", re.IGNORECASE)


@dataclass(frozen=True)
class Result:
    check: str
    outcome: Outcome
    detail: str

    def line(self) -> str:
        return json.dumps({"check": self.check, "outcome": self.outcome, "detail": self.detail})


def redact(message: str) -> str:
    """No credential in a detail: an exception from a driver can quote its whole
    connection string (rule 27)."""
    message = _USERINFO.sub("://***@", message)
    message = _KEY_VALUE.sub(lambda m: f"{m.group(1)}=***", message)
    return " ".join(message.split())[:DETAIL_LIMIT]


def describe(exc: BaseException) -> str:
    return redact(f"{type(exc).__name__}: {exc}")


# ── the database, read once ──────────────────────────────────────────────────

class NotReadOnlyError(RuntimeError):
    """The transaction did not report read-only, so nothing else was read."""


@dataclass(frozen=True)
class Database:
    read_only: str
    applied: tuple[str, ...]
    dead: int
    failures: int
    dead_email: int = 0      # FS-078 SF-3: email apart, so an SMTP problem reads as one


async def read_database() -> Database:
    """Everything the checks need from the database, in one read-only
    transaction. Read as the connecting owner, with no claim and no role:
    `notification_failure` has no policy, so `app_role` would see none of it."""
    async with async_session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION READ ONLY"))
        mode = str((await session.execute(text("SHOW transaction_read_only"))).scalar_one())
        if mode != "on":
            raise NotReadOnlyError(f"transaction_read_only is {mode}, so nothing was read")
        applied = tuple(str(row[0]) for row in
                        await session.execute(text("SELECT version_num FROM alembic_version")))
        dead = int((await session.execute(text(
            "SELECT count(*) FROM notification_outbox "
            "WHERE state = 'dead' AND created_at > now() - interval '1 day'"))).scalar_one())
        dead_email = int((await session.execute(text(
            # answers, not failures (FS-078 SF-3): the same list as worker/jobs/email.py
            "SELECT count(*) FILTER (WHERE channel = 'email' AND coalesce(error, '') NOT IN "
            "('already read', 'recipient no longer eligible', 'email off')) "
            "FROM notification_outbox "
            "WHERE state = 'dead' AND created_at > now() - interval '1 day'"))).scalar_one())
        failures = int((await session.execute(text(
            "SELECT count(*) FROM notification_failure "
            "WHERE created_at > now() - interval '1 day'"))).scalar_one())
    return Database(read_only=mode, applied=applied, dead=dead, failures=failures,
                    dead_email=dead_email)


def script_heads() -> tuple[str, ...]:
    """The heads in the image's revision files. Files only: `alembic current`
    needs the sync driver, which the image leaves out (plan review B2). The
    script location is made absolute so the answer does not depend on the cwd."""
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "api" / "db" / "migrations"))
    # without it, newer alembic warns on every read of prepend_sys_path
    config.set_main_option("path_separator", "os")
    return tuple(ScriptDirectory.from_config(config).get_heads())


# ── the checks ───────────────────────────────────────────────────────────────

def check_migration_head(heads: Sequence[str], applied: Sequence[str]) -> Result:
    name = "migration_head"
    if len(heads) != 1:
        return Result(name, "fail", f"{len(heads)} heads in the image: {', '.join(heads)}")
    if list(applied) != [heads[0]]:
        return Result(name, "fail", f"the image's head is {heads[0]}, the database is at "
                                    f"{', '.join(applied) or 'no revision'}")
    return Result(name, "pass", heads[0])


def check_read_only(database: Database) -> Result:
    # read_database refuses anything but "on"; checked again so this result never
    # rests on that function alone
    if database.read_only != "on":
        return Result("read_only", "fail", f"transaction_read_only is {database.read_only}")
    return Result("read_only", "pass", "transaction_read_only is on")


def check_renderer() -> Result:
    problem = renderer_available()
    if problem:
        return Result("renderer", "fail", redact(problem))
    return Result("renderer", "pass", "WeasyPrint imports")


def check_company_profile(settings: Settings) -> Result:
    if not settings.quotation_profile_enabled:
        return Result("company_profile", "skip", "quotation_profile_enabled is off")
    problem = profile_problem()
    if problem:
        return Result("company_profile", "fail", redact(problem))
    return Result("company_profile", "pass", "the profile appends")


def check_sample_render(settings: Settings) -> Result:
    name = "sample_render"
    if settings.pdf_renderer != "weasyprint":
        return Result(name, "skip", f"pdf_renderer is {settings.pdf_renderer}, so there is no PDF")
    data, content_type = render_document(document(), settings)
    if content_type != "application/pdf":
        return Result(name, "fail", f"the render returned {content_type}")
    pages = PdfReader(io.BytesIO(data)).pages
    if not pages:
        return Result(name, "fail", "the PDF has no pages")
    first = pages[0].mediabox
    if float(first.width) >= float(first.height):
        return Result(name, "fail", "page 1 is not portrait")
    # the sample fits on one page; everything after it is the profile
    profile = len(PdfReader(io.BytesIO(company_profile())).pages) \
        if settings.quotation_profile_enabled else 0
    if len(pages) != 1 + profile:
        return Result(name, "fail", f"{len(pages)} pages, expected 1 and {profile} of profile")
    flat = " ".join((pages[0].extract_text() or "").split())
    missing = [figure for figure in PAGE_ONE_FIGURES if figure not in flat]
    if missing:
        return Result(name, "fail", f"page 1 is missing {', '.join(missing)}")
    return Result(name, "pass", f"{len(pages)} pages, every figure on page 1")


def check_storage(settings: Settings) -> Result:
    """Rule 4: the probe, three outcomes, no object written."""
    name = "storage"
    if not settings.storage_configured:
        return Result(name, "skip", "storage is not configured")
    storage = get_storage(settings)
    if storage.name != "r2":
        # the dev box's directory probe writes a marker file
        return Result(name, "skip", f"{storage.name} storage: its probe writes a file")
    problem = storage.probe()
    if problem is None:
        return Result(name, "pass", "ok")
    word = "denied" if _DENIED.search(problem) else "unreachable"
    return Result(name, "fail", redact(f"{word}: {problem}"))


async def check_redis(settings: Settings) -> Result:
    client = Redis.from_url(str(settings.redis_url), socket_timeout=5,
                            socket_connect_timeout=5)
    try:
        answered = await client.ping()
    finally:
        await client.aclose()
    if not answered:
        return Result("redis", "fail", "PING got no answer")
    return Result("redis", "pass", "PONG")


def check_outbox_dead(database: Database) -> Result:
    """A count to read, never a failure: one dead row is not an outage, and what
    is normal differs by box."""
    return Result("outbox_dead", "pass",
                  f"{database.dead} dead outbox rows ({database.dead_email} of them failed "
                  f"emails) and {database.failures} notification failures created in the last day")


# ── the run ──────────────────────────────────────────────────────────────────

async def guarded(name: str, check: Callable[[], Result | Awaitable[Result]]) -> Result:
    """One check, whose exception is its own fail and stops nothing else."""
    try:
        outcome = check()
        if inspect.isawaitable(outcome):
            outcome = await asyncio.wait_for(outcome, TIMEOUT_SECONDS)
        return outcome
    except Exception as exc:
        return Result(name, "fail", describe(exc))


async def collect(settings: Settings) -> list[Result]:
    database: Database | None = None
    unread: str = ""
    try:
        database = await asyncio.wait_for(read_database(), TIMEOUT_SECONDS)
    except Exception as exc:
        unread = describe(exc)

    def read() -> Database:
        if database is None:
            raise RuntimeError(f"the database was not read: {unread}")
        return database

    return [
        await guarded("migration_head",
                      lambda: check_migration_head(script_heads(), read().applied)),
        await guarded("read_only", lambda: check_read_only(read())),
        await guarded("renderer", check_renderer),
        await guarded("company_profile", lambda: check_company_profile(settings)),
        await guarded("sample_render", lambda: check_sample_render(settings)),
        await guarded("storage", lambda: check_storage(settings)),
        await guarded("redis", lambda: check_redis(settings)),
        await guarded("outbox_dead", lambda: check_outbox_dead(read())),
    ]


def main() -> int:
    out = sys.stdout
    # a library that logs to stdout would break the one-line-per-check contract
    with contextlib.redirect_stdout(sys.stderr):
        results = asyncio.run(collect(get_settings()))
    for result in results:
        print(result.line(), file=out, flush=True)
    return 1 if any(r.outcome == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
