"""The `verify` step of deploy_staging.py (FS-065): check a deployed box and end in
pass or fail.

Three parts, in order. The box checks run inside a one-off worker container and
print one JSON line each. The read-only HTTP checks and the staging journey are
the pytest files under live/, run from this machine against one base URL.

    production   https://APP_DOMAIN
    staging      an SSH tunnel to the box's API port, opened here

On staging the tunnel is the point: the journey's guard reads /health through the
same address its writes go to, so a wrong address fails the guard instead of
passing it (FS-065 rule 18).
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# the environment name each target's /health must report (api/config.py)
ENVIRONMENT = {"staging": "staging", "prod": "production"}
BOX_TIMEOUT = 300
# FS-065 rule 16. The live suite stops itself at 540 s, under the 15-minute access
# token. This outer limit is longer on purpose: the suite must reach its own
# teardown, which signs out, before this one kills the process.
RUN_BUDGET = 660
# what a production run does not prove, printed whether or not the HTTP checks ran
PRODUCTION_LIMITS = (
    "modules not released on production answer 403; their queries never run there",
    "the portal paths are not called",
    "scoping between users is checked on staging only",
    "no page is opened in a browser",
)
TUNNEL_WAIT = 20

# What must never reach the terminal: a URL's credentials, a bearer token, a JWT.
_SECRETS = (
    (re.compile(r"://[^/\s@]+@"), "://***@"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "***"),
    (re.compile(r"(?i)(bearer|password|token|secret)(\s*[=:]\s*|\s+)\S+"), r"\1\2***"),
)


@dataclass(frozen=True)
class Check:
    name: str
    outcome: str  # pass | fail | skip
    detail: str = ""

    def line(self) -> str:
        text = f"  {self.outcome.upper():<4} {self.name}"
        return text + (f": {self.detail}" if self.detail else "")


def scrub(text: str, *, limit: int = 300) -> str:
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())[:limit]


def parse_box_output(stdout: str, returncode: int, stderr: str = "") -> list[Check]:
    """The worker module's JSON lines, as checks. Anything it printed that is not
    one of its lines is ignored; no usable line at all is itself a failure, so a
    module that never started cannot read as a pass."""
    checks: list[Check] = []
    for raw in stdout.splitlines():
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(row, dict) or "check" not in row:
            continue
        outcome = str(row.get("outcome", "fail"))
        if outcome not in ("pass", "fail", "skip"):
            outcome = "fail"
        checks.append(Check("box." + str(row["check"]), outcome, scrub(str(row.get("detail", "")))))
    if not checks:
        why = scrub(stderr or stdout) or f"exit {returncode}, no output"
        return [Check("box", "fail", "the box checks did not run: " + why)]
    if returncode != 0 and not any(c.outcome == "fail" for c in checks):
        checks.append(Check("box", "fail", f"exit {returncode} with no failed check reported"))
    return checks


def box_command(compose: Callable[..., str], env: dict[str, str]) -> str:
    # A one-off container of the worker service: its settings, its own memory, and
    # the code the image was built with. --no-deps: nothing is started or recreated.
    return compose(env, "run", "--rm", "--no-deps", "-T", "worker",
                   "python", "-m", "worker.live_check")


def base_url(target: str, env: dict[str, str], local_port: int | None) -> str:
    if target == "prod":
        return "https://" + env["APP_DOMAIN"]
    if local_port is None:
        raise ValueError("staging is reached through a tunnel")
    return f"http://127.0.0.1:{local_port}"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def tunnel(ssh_argv: list[str], env: dict[str, str]) -> Iterator[int]:
    """Forward a free local port to the box's API port for the length of the run."""
    port = free_port()
    argv = [*ssh_argv[:-1], "-N", "-o", "ExitOnForwardFailure=yes",
            "-L", f"127.0.0.1:{port}:127.0.0.1:{env['API_HOST_PORT']}", ssh_argv[-1]]
    # stderr to a file, not a pipe: nobody reads a pipe while the run is going, and
    # a full one stalls ssh
    errors = tempfile.TemporaryFile()  # noqa: SIM115  closed in the finally below
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=errors)
    try:
        deadline = time.monotonic() + TUNNEL_WAIT
        while True:
            if proc.poll() is not None:
                errors.seek(0)
                err = errors.read().decode(errors="replace")
                raise RuntimeError("the tunnel closed: " + scrub(err))
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"no tunnel after {TUNNEL_WAIT}s") from None
                time.sleep(0.3)
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        errors.close()


def live_env(target: str, url: str, env: dict[str, str], *, journey: bool) -> dict[str, str]:
    """What a live pytest run is given. Only the values it needs: the box's own
    secrets in the env file (the database password, the JWT secret) stay out."""
    out = {"LIVE_BASE_URL": url, "LIVE_TARGET": ENVIRONMENT[target],
           "LIVE_CHECK_EMAIL": env["LIVE_CHECK_EMAIL"],
           "LIVE_CHECK_PASSWORD": env["LIVE_CHECK_PASSWORD"]}
    if journey:
        out["LIVE_TEST_MOBILE"] = env["LIVE_TEST_MOBILE"]
        out["DEMO_PASSWORD"] = env["DEMO_PASSWORD"]
    return out


def missing(env: dict[str, str], keys: tuple[str, ...]) -> list[str]:
    return [k for k in keys if not env.get(k)]


def plan(target: str, env: dict[str, str], *, read_only: bool) -> tuple[list[str], list[Check]]:
    """Which live files run, and what is skipped with its reason. A skipped part is
    printed, never silent: a run that checked less must say so."""
    files: list[str] = []
    skips: list[Check] = []
    lacking = missing(env, ("LIVE_CHECK_EMAIL", "LIVE_CHECK_PASSWORD"))
    if lacking:
        skips.append(Check("http", "skip", "not set in the env file: " + ", ".join(lacking)))
    else:
        files.append("live/test_readonly.py")
    if target == "prod":
        skips.append(Check("journey", "skip", "production is read-only"))
    elif read_only:
        skips.append(Check("journey", "skip", "--read-only"))
    else:
        lacking = missing(env, ("LIVE_CHECK_EMAIL", "LIVE_CHECK_PASSWORD",
                                "LIVE_TEST_MOBILE", "DEMO_PASSWORD"))
        if lacking:
            skips.append(Check("journey", "skip",
                               "not set in the env file: " + ", ".join(lacking)))
        else:
            files.append("live/test_journey.py")
    return files, skips


def run_live(code_root: Path, files: list[str], extra: dict[str, str]) -> Check:
    """One pytest process over the live files; its own lines are the detail."""
    if not (code_root / "live").is_dir():
        return Check("http", "fail", f"no live/ folder in {code_root}")
    # --assert=plain: pytest's rewritten assertions print the values compared, and
    # on a live box those are names and numbers (rule 27). Each live assertion
    # carries its own message instead.
    argv = [sys.executable, "-m", "pytest", *files, "-q", "-rfEs", "--tb=short",
            "--assert=plain", "-p", "no:cacheprovider"]
    # no PYTEST_* from this shell: PYTEST_ADDOPTS could add files or options to a
    # production run
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTEST_")}
    try:
        done = subprocess.run(argv, cwd=code_root, env={**env, **extra}, timeout=RUN_BUDGET)
    except subprocess.TimeoutExpired:
        return Check("http", "fail", f"no result after {RUN_BUDGET}s")
    name = " + ".join(Path(f).stem.removeprefix("test_") for f in files)
    return Check(name, "pass" if done.returncode == 0 else "fail",
                 "" if done.returncode == 0 else f"pytest exit {done.returncode}, see above")


def load(target: str, env: dict[str, str], repo: Path, *, users: int, seconds: int,
         ssh_argv: Callable[[dict[str, str]], list[str]]) -> int:
    """Test build-out 7: scripts/load_test.py through the tunnel, with the check
    account in its environment as the live suite gets it. Staging only."""
    if target != "staging":
        print("  load runs against staging only")
        return 2
    lacking = missing(env, ("LIVE_CHECK_EMAIL", "LIVE_CHECK_PASSWORD"))
    if lacking:
        print("  not set in the env file: " + ", ".join(lacking))
        return 2
    base = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTEST_")}
    argv = [sys.executable, str(repo / "scripts" / "load_test.py"),
            "--users", str(users), "--seconds", str(seconds)]
    with tunnel(ssh_argv(env), env) as port:
        extra = live_env(target, base_url(target, env, port), env, journey=False)
        return subprocess.run(argv, cwd=repo, env={**base, **extra},
                              timeout=seconds + 300).returncode


def report(checks: list[Check], target: str = "staging") -> bool:
    print("\n  verify")
    for c in checks:
        print(c.line())
    if target == "prod":
        print("\n  not covered on production:")
        for line in PRODUCTION_LIMITS:
            print("    " + line)
    tally = {o: sum(1 for c in checks if c.outcome == o) for o in ("pass", "fail", "skip")}
    print(f"\n  {tally['pass']} passed, {tally['fail']} failed, {tally['skip']} skipped\n")
    return tally["fail"] == 0


def verify(target: str, env: dict[str, str], code_root: Path, *, read_only: bool,
           run_remote: Callable[..., subprocess.CompletedProcess],
           compose: Callable[..., str], ssh_argv: Callable[[dict[str, str]], list[str]]) -> bool:
    checks: list[Check] = []
    try:
        got = run_remote(env, box_command(compose, env), check=False, capture=True,
                         timeout=BOX_TIMEOUT)
        checks += parse_box_output(got.stdout.decode(errors="replace"), got.returncode,
                                   got.stderr.decode(errors="replace"))
    except subprocess.TimeoutExpired:
        checks.append(Check("box", "fail", f"no result after {BOX_TIMEOUT}s"))

    files, skips = plan(target, env, read_only=read_only)
    checks += skips
    if files:
        try:
            if target == "prod":
                checks.append(run_live(code_root, files,
                                       live_env(target, base_url(target, env, None), env,
                                                journey=False)))
            else:
                with tunnel(ssh_argv(env), env) as port:
                    checks.append(run_live(
                        code_root, files,
                        live_env(target, base_url(target, env, port), env,
                                 journey="live/test_journey.py" in files)))
        except (RuntimeError, OSError) as exc:
            checks.append(Check("http", "fail", scrub(str(exc))))
    return report(checks, target)
