#!/usr/bin/env python3
"""One command for the local stack.

    python scripts/dev.py up        bring the stack up and wait until it is usable
    python scripts/dev.py down      stop it
    python scripts/dev.py status    what is running, and is the database reachable
    python scripts/dev.py psql      open a shell against the database through PgBouncer
    python scripts/dev.py validate  run the reference-SQL checks
    python scripts/dev.py check     up + validate, the W0/W1 gate

Everything reaches the database at 127.0.0.1:6432 (PgBouncer). Whether that is
a tunnelled remote Postgres or a local container is a profile choice, and
nothing downstream knows the difference.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra"
ENV = INFRA / ".env"
COMPOSE = ["docker", "compose", "--project-directory", str(INFRA),
           "-f", str(INFRA / "docker-compose.yml")]


def die(msg: str, hint: str = "") -> None:
    print(f"\n  {msg}")
    if hint:
        print(f"  {hint}")
    sys.exit(1)


def load_env() -> dict[str, str]:
    if not ENV.exists():
        die("infra/.env not found.", "cp infra/.env.example infra/.env  and fill it in")
    out: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def profile(env: dict[str, str]) -> str:
    return "local" if env.get("DB_HOST") == "postgres" else "tunnel"


def preflight(env: dict[str, str]) -> None:
    missing = [k for k in ("DB_USER", "DB_PASSWORD", "DB_NAME") if not env.get(k)]
    if missing:
        die(f"infra/.env is missing: {', '.join(missing)}")

    if profile(env) == "tunnel":
        for k in ("SSH_HOST", "SSH_USER", "SSH_KEY_PATH"):
            if not env.get(k):
                die(f"DB_HOST=db-tunnel but {k} is not set in infra/.env")
        key = Path(env["SSH_KEY_PATH"])
        if not key.exists():
            die(f"SSH key not found: {key}")

    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        die("Docker is not running.")


def compose(*args: str, env: dict[str, str] | None = None, check: bool = True):
    e = {**os.environ, **(env or {})}
    return subprocess.run([*COMPOSE, *args], env=e, check=check)


def db_ready(env: dict[str, str], timeout: int = 90) -> bool:
    """PgBouncer accepting connections AND the database behind it answering."""
    try:
        import psycopg
    except ImportError:
        die("psycopg is not installed.", "pip install 'psycopg[binary]'")

    dsn = (f"host=127.0.0.1 port=6432 user={env['DB_USER']} "
           f"password={env['DB_PASSWORD']} dbname={env['DB_NAME']}")
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as c:
                cur = c.cursor()
                cur.execute("SELECT version()")
                ver = cur.fetchone()[0].split(" on ")[0]
                cur.execute("SHOW server_version_num")
                if int(cur.fetchone()[0]) < 160000:
                    print(f"  WARNING: {ver} — the design targets PostgreSQL 16")
                print(f"  database reachable through PgBouncer: {ver}")
                return True
        except Exception as exc:
            last = str(exc).split("\n")[0][:80]
            time.sleep(2)
    print(f"  database not reachable after {timeout}s — {last}")
    return False


def cmd_up() -> None:
    env = load_env()
    preflight(env)
    p = profile(env)
    print(f"\n  profile: {p}" + ("  (remote Postgres over SSH)" if p == "tunnel"
                                 else "  (local container)"))
    compose("--profile", p, "up", "-d", env=env)
    print("\n  waiting for the database…")
    if not db_ready(env):
        print("\n  logs:")
        compose("--profile", p, "logs", "--tail", "30", check=False, env=env)
        sys.exit(1)
    print("\n  ready.  DATABASE_URL for host tools:")
    print(f"    postgresql+psycopg://{env['DB_USER']}:***@127.0.0.1:6432/{env['DB_NAME']}")


def cmd_down() -> None:
    env = load_env()
    compose("--profile", "tunnel", "--profile", "local", "--profile", "app",
            "down", env=env, check=False)


def cmd_status() -> None:
    env = load_env()
    compose("--profile", profile(env), "ps", env=env, check=False)
    print()
    db_ready(env, timeout=6)


def cmd_psql() -> None:
    env = load_env()
    os.environ["PGPASSWORD"] = env["DB_PASSWORD"]
    subprocess.run(["psql", "-h", "127.0.0.1", "-p", "6432",
                    "-U", env["DB_USER"], "-d", env["DB_NAME"]], check=False)


def cmd_validate() -> None:
    env = load_env()
    if not db_ready(env, timeout=10):
        die("Database not reachable.", "python scripts/dev.py up")
    sys.exit(subprocess.run([sys.executable, "-u",
                             str(ROOT / "scripts" / "validate_reference_sql.py")],
                            check=False).returncode)


def warn_pre_auth_containment(env: dict[str, str]) -> None:
    """Say plainly that the pre-auth path is unexercised here.

    With DB_ANON_ROLE unset, get_db_anon issues no SET LOCAL ROLE and the pre-auth
    functions run with the application role's full grants. Everything that could go
    wrong with those grants is invisible locally - which is how a missing GRANT on
    the OTP path reached a fourth review round unnoticed. FS-001 GAP-021.
    """
    role = env.get("DB_ANON_ROLE")
    if role:
        print(f"  pre-auth containment: active as {role}")
        return
    print("  pre-auth containment: NOT ACTIVE (DB_ANON_ROLE unset)")
    print("    Grants on the pre-auth path are not exercised here, so a missing one")
    print("    passes locally and fails in staging. docs/gaps/auth.md GAP-021.")
    print("    The roles exist on the dev cluster. Set DB_ANON_ROLE=app_anon")
    print("    in infra/.env and run alembic upgrade head (003b grants). local-environment.md.")


def cmd_check() -> None:
    cmd_up()
    print("\n" + "=" * 62)
    warn_pre_auth_containment(load_env())
    cmd_validate()


COMMANDS = {"up": cmd_up, "down": cmd_down, "status": cmd_status,
            "psql": cmd_psql, "validate": cmd_validate, "check": cmd_check}

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "up"
    if arg not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[arg]()
