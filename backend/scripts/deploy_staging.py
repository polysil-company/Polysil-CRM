#!/usr/bin/env python3
"""Deploy the backend to the staging box, for the frontend track to build against.

    python scripts/deploy_staging.py provision   # the role, the database, the grants
    python scripts/deploy_staging.py deploy      # sync, build, up, alembic upgrade head
    python scripts/deploy_staging.py seed        # demo users, masters, showcase dataset
    python scripts/deploy_staging.py templates   # order messages on only where 11za approved them
    python scripts/deploy_staging.py status      # containers, health, resource use
    python scripts/deploy_staging.py frontend-provision   # the deploy key and the webhook receiver
    python scripts/deploy_staging.py frontend    # pull integration and rebuild the frontend now
    python scripts/deploy_staging.py frontend-caddy   # polysil-test.pranayx.tech on the box's Caddy
    python scripts/deploy_staging.py logs [svc]
    python scripts/deploy_staging.py down

Every step is idempotent. `deploy` re-runs cleanly: the source tree is replaced,
the images rebuild from cache, compose reconciles, and `alembic upgrade head` on
an up-to-date database does nothing.

**It refuses to point at `appdb`.** That is the development database, shared by
everyone working on this project, and a migration or a seed against it is not
recoverable from a backup that does not exist. The guard reads DB_NAME, the DSN
and the development env file, and no flag overrides it.

Configuration is infra/.env.staging (see infra/.env.staging.example). Secrets are
never printed and never passed as command-line arguments on the box: what has to
reach it goes over stdin, or into one file written with mode 600.
"""

from __future__ import annotations

import argparse
import io
import shlex
import subprocess
import sys
import tarfile
import time
from pathlib import Path

import live_verify

ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra"
ENV_FILE = INFRA / ".env.staging"
# --target prod points the same steps at the Hostinger box (12 Oct 2026)
COMPOSE_FILE = "infra/docker-compose.staging.yml"
REMOTE_ENV = ".env.staging"
TARGET = "staging"
# production builds the frontend from this checkout of the shared repo (its Frontend/)
FRONTEND_SRC = ROOT / "scripts" / "local" / "reviewstaging" / "Frontend"
# the go-live menu (nav item ids in the frontend's navigation.ts); scripts/seed_prod.py
# RELEASED is the matching backend scope
RELEASED_NAV = ("dashboard", "messages", "leads", "qr-codes", "quotations", "sales-orders",
                "approvals", "tasks", "dispatch", "approval-limits", "products", "users",
                "channel-partners", "team-map", "duty", "visits")
# --source: the code comes from a checkout of the shared repo (its backend/ and
# Frontend/), the release branch; the client's data files always come from here
CODE_ROOT = ROOT
LOCAL_ONLY = ("data/", "tests/fixtures/subsidy/")


def set_source(checkout: Path) -> None:
    global CODE_ROOT, FRONTEND_SRC
    if not (checkout / "backend" / "api").is_dir() or not (checkout / "Frontend").is_dir():
        die(f"{checkout} is not a checkout of the shared repo (backend/ and Frontend/)")
    CODE_ROOT = checkout / "backend"
    FRONTEND_SRC = checkout / "Frontend"


def set_target(target: str) -> None:
    global ENV_FILE, COMPOSE_FILE, REMOTE_ENV, TARGET
    TARGET = target
    if target == "prod":
        ENV_FILE = INFRA / ".env.prod"
        COMPOSE_FILE = "infra/docker-compose.prod.yml"
        REMOTE_ENV = ".env.prod"
DEV_ENV_FILE = INFRA / ".env"

# The development database. One constant, so the guard cannot drift apart across
# the three places it is checked.
FORBIDDEN_DB = "appdb"

# What the box needs to build and run. Tests, the rest of docs/, share/ and the
# git history stay off it.
INCLUDE = [
    "pyproject.toml",
    "alembic.ini",
    "api",
    "worker",
    "scripts",
    "infra/Dockerfile",
    "infra/docker-compose.staging.yml",
    "infra/docker-compose.prod.yml",
    # The prepared reverse-proxy site block, so it is on the box when the DNS
    # record lands and someone applies it. GAP-097.
    "infra/caddy",
    # the frontend's image, its compose file and the webhook receiver that
    # rebuilds it on a push to integration. The deploy key lives in
    # infra/frontend/keys on the box only.
    "infra/frontend",
    "docs/architecture/RBAC.md",
    # The client's workbooks, read by the two master loaders. Mounted read-only
    # into the one-shot container, never baked into an image.
    "data/boq",
    "data/masters",
    # FS-056: the CG, RJ and UP scheme tables and price lists, read by
    # load_state_masters (the samples file is withheld from the shared repo)
    "tests/fixtures/subsidy/states.json",
    "tests/fixtures/subsidy/states_samples.json",
]

# Replaced wholesale on every deploy, so a file deleted here disappears there.
REPLACE = ["api", "worker", "scripts", "data", "docs", "tests"]

EXCLUDE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".env"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".key", ".pem")


def die(msg: str, hint: str = "") -> None:
    print(f"\n  {msg}")
    if hint:
        print(f"  {hint}")
    sys.exit(1)


def read_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def guard(env: dict[str, str]) -> None:
    """Refuse anything pointed at the development database, or reusing its secrets.

    Three ways to arrive at `appdb` - the name, a pasted DSN, and the development
    env file's own values - so three checks rather than one.
    """
    name = env.get("DB_NAME", "")
    if name == FORBIDDEN_DB:
        die(f"DB_NAME is {FORBIDDEN_DB!r}, the development database.",
            "Staging gets a database of its own. No flag overrides this.")

    dsn = env.get("DATABASE_URL", "")
    if dsn and (dsn.rstrip("/").endswith("/" + FORBIDDEN_DB) or "/" + FORBIDDEN_DB + "?" in dsn):
        die(f"DATABASE_URL ends at {FORBIDDEN_DB!r}, the development database.")

    dev = read_env(DEV_ENV_FILE)
    if not dev:
        return
    if name and name == dev.get("DB_NAME"):
        die(f"DB_NAME {name!r} is the database infra/.env develops against.")
    if env.get("JWT_SECRET") and env["JWT_SECRET"] == dev.get("JWT_SECRET"):
        die("JWT_SECRET is the local development secret.",
            'Generate one:  python -c "import secrets; print(secrets.token_hex(32))"')
    if env.get("DB_PASSWORD") and env["DB_PASSWORD"] == dev.get("DB_PASSWORD"):
        die("DB_PASSWORD is the development role's password. Staging gets its own role.")


def load_config() -> dict[str, str]:
    if not ENV_FILE.exists():
        die(f"infra/{ENV_FILE.name} not found.",
            f"cp infra/.env.staging.example infra/{ENV_FILE.name}  and fill it in")
    env = read_env(ENV_FILE)

    required = ["SSH_HOST", "SSH_USER", "SSH_KEY_PATH", "REMOTE_DIR",
                "DB_NAME", "DB_USER", "DB_PASSWORD", "JWT_SECRET",
                "PG_HOST", "PG_CONTAINER", "PG_SUPERUSER",
                # FS-005: the share link's origin; the API refuses to start without it
                "PUBLIC_WEB_URL"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        die(f"infra/{ENV_FILE.name} is missing: " + ", ".join(missing))
    if TARGET == "prod":
        # the admin's email is checked by seed-prod (scripts/seed_prod.py), not here
        prod_missing = [k for k in ("APP_DOMAIN", "PG_SUPERUSER_PASSWORD") if not env.get(k)]
        if prod_missing:
            die("infra/.env.prod is missing: " + ", ".join(prod_missing))

    guard(env)

    if not Path(env["SSH_KEY_PATH"]).exists():
        die(f"SSH key not found: {env['SSH_KEY_PATH']}")
    env.setdefault("API_HOST_PORT", "8100")
    env.setdefault("PGBOUNCER_HOST_PORT", "6432")
    return env


# -- the box ---------------------------------------------------------------


def ssh_argv(env: dict[str, str]) -> list[str]:
    # the two timeouts: a box that does not answer fails the step instead of
    # hanging it (FS-065 rule 16)
    return ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15",
            "-i", env["SSH_KEY_PATH"], env["SSH_USER"] + "@" + env["SSH_HOST"]]


def run_remote(env: dict[str, str], command: str, *, stdin: bytes | None = None,
               check: bool = True, capture: bool = False,
               timeout: float | None = None) -> subprocess.CompletedProcess:
    """One command on the box, through a non-interactive shell."""
    argv = [*ssh_argv(env), "bash", "-lc", shlex.quote(command)]
    return subprocess.run(
        argv, input=stdin, check=check, timeout=timeout,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def compose(env: dict[str, str], *args: str, profile: str | None = None) -> str:
    """The compose invocation, as one shell string for run_remote."""
    d = env["REMOTE_DIR"]
    parts = ["docker", "compose",
             "--project-directory", d + "/infra",
             "-f", d + "/" + COMPOSE_FILE,
             "--env-file", d + "/infra/" + REMOTE_ENV]
    if profile:
        parts += ["--profile", profile]
    return " ".join(shlex.quote(p) for p in [*parts, *args])


# -- steps -----------------------------------------------------------------


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = Path(info.name).name
    if name in EXCLUDE_NAMES or name.endswith(EXCLUDE_SUFFIXES):
        return None
    # Ownership from a Windows working tree means nothing on the box, and every
    # process there runs as the image's user anyway.
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def sync(env: dict[str, str]) -> None:
    """Replace the source tree on the box. No git and no rsync: one tar over SSH."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in INCLUDE:
            path = (ROOT if rel.startswith(LOCAL_ONLY) else CODE_ROOT) / rel
            if not path.exists():
                die(f"{rel} not found in the repository.")
            tar.add(path, arcname=rel, filter=_tar_filter)
    payload = buf.getvalue()

    d = shlex.quote(env["REMOTE_DIR"])
    stale = " ".join(d + "/" + p for p in REPLACE)
    run_remote(env, f"mkdir -p {d}/infra && rm -rf {stale} && tar xzf - -C {d}",
               stdin=payload)
    print(f"  synced   {len(payload) / 1024:.0f} KiB -> {env['REMOTE_DIR']}")


def push_env(env: dict[str, str]) -> None:
    """The one env file the box holds, written with mode 600."""
    d = shlex.quote(env["REMOTE_DIR"])
    body = ENV_FILE.read_text(encoding="utf-8")
    run_remote(env, f"mkdir -p {d}/infra && umask 077 && cat > {d}/infra/{REMOTE_ENV}",
               stdin=body.encode())
    print(f"  env      {REMOTE_ENV} written, mode 600")


def provision(env: dict[str, str]) -> None:
    """The login role, its two role memberships, and the database.

    Cluster-level work no migration can do (docs/workflows/local-environment.md):
    CREATE ROLE is not per-database, and CREATE DATABASE cannot run inside a
    transaction. It runs as the cluster superuser through `docker exec`, which is
    socket auth - so no superuser password exists anywhere in this repository.
    """
    guard(env)
    pw = env["DB_PASSWORD"].replace("'", "''")
    role, db = env["DB_USER"], env["DB_NAME"]
    anon = env.get("DB_ANON_ROLE", "app_anon")
    app = env.get("DB_APP_ROLE", "app_role")

    sql = "\n".join([
        "DO $do$",
        "BEGIN",
        # a fresh cluster (production) has neither role; staging's already does
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app}') THEN",
        f"    EXECUTE format('CREATE ROLE %I NOLOGIN', '{app}');",
        "  END IF;",
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{anon}') THEN",
        f"    EXECUTE format('CREATE ROLE %I NOLOGIN', '{anon}');",
        "  END IF;",
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN",
        f"    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '{role}', '{pw}');",
        "  ELSE",
        f"    EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', '{role}', '{pw}');",
        "  END IF;",
        "END",
        "$do$;",
        f"GRANT {app} TO {role};",
        f"GRANT {anon} TO {role};",
        f"SELECT 'CREATE DATABASE {db} OWNER {role}'",
        f" WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '{db}')",
        "\\gexec",
        "",
    ])
    exec_psql = ("docker exec -i " + shlex.quote(env["PG_CONTAINER"]) +
                 " psql -q -U " + shlex.quote(env["PG_SUPERUSER"]) +
                 " -d postgres -v ON_ERROR_STOP=1")
    run_remote(env, exec_psql, stdin=sql.encode())
    print(f"  provisioned  role {role}, database {db}, member of {app} and {anon}")


def build(env: dict[str, str]) -> None:
    run_remote(env, compose(env, "build", "api", "tools", profile="tools"))


def up(env: dict[str, str]) -> None:
    run_remote(env, compose(env, "up", "-d", "--remove-orphans"))


def migrate(env: dict[str, str]) -> None:
    guard(env)
    run_remote(env, compose(env, "run", "--rm", "tools",
                            "alembic", "upgrade", "head", profile="tools"))
    # The api came up before the migration. A migration that changes a table's
    # columns leaves plans on the pooled connections that fail once each with
    # "cached statement plan is invalid" (ISS-100). Fresh connections plan anew.
    run_remote(env, compose(env, "restart", "pgbouncer", "api", "worker"))
    sync_templates(env)


def requeue_pdfs(env: dict[str, str]) -> None:
    """Failed quotation and order PDFs back in the render queue, once storage works
    (ISS-094). Sends nothing by itself; see scripts/requeue_pdfs.py."""
    guard(env)
    run_remote(env, compose(env, "run", "--rm", "tools", "python",
                            "scripts/requeue_pdfs.py", profile="tools"))


def sync_templates(env: dict[str, str]) -> None:
    """Switch each order message on only if 11za has approved its template (FS-012
    rule 3). A failed listing leaves the switches alone and the deploy goes on."""
    run_remote(env, compose(env, "run", "--rm", "tools", "python",
                            "scripts/sync_message_templates.py", profile="tools"), check=False)


# scripts/seed_demo.py reads DB_USER, DB_PASSWORD and DB_NAME out of infra/.env
# and from nowhere else, and connects to 127.0.0.1:6432 - which is PgBouncer
# inside the one-shot container, because that container shares its network
# namespace. So the container writes that file for itself, out of the environment
# compose already handed it, and the credentials never reach the box's disk a
# second time.
#
# The file names `ENVIRONMENT=staging`, honestly, because the guard no longer asks
# a file where it is running. It asks whether the password being written is the one
# published in the script and refuses that anywhere but a laptop; DEMO_PASSWORD
# comes from infra/.env.staging and is generated. ISS-083 closed.
SEED_DEMO = (
    "set -e; umask 077; "
    "printf 'DB_USER=%s\\nDB_PASSWORD=%s\\nDB_NAME=%s\\nENVIRONMENT=staging\\n' "
    '"$DB_USER" "$DB_PASSWORD" "$DB_NAME" > /app/infra/.env; '
    "python scripts/seed_demo.py"
)

# The showcase dataset: 33 districts, 17 offices, 19 staff across every role level,
# 10 partners and 55 leads over four stages and 45 days. It seeds through the API
# in-process, so it needs the same file and nothing else.
#
# Without it a frontend builds against two leads and one district, and never sees a
# district manager seeing more than a field officer - which is the behaviour most
# likely to surprise them later.
SEED_SHOWCASE = SEED_DEMO.replace("python scripts/seed_demo.py",
                                  "python scripts/seed_showcase.py")


def seed(env: dict[str, str], *, masters: bool = True, showcase: bool = True) -> None:
    guard(env)
    # The seeds sign partners in by reading their code from the outbox and create
    # leads on generated mobiles. On a real provider the first texts made-up numbers
    # and then fails (a sent code's payload is cleared), and the second texts one
    # stranger per lead.
    if env.get("WHATSAPP_PROVIDER", "mock").strip() != "mock":
        die("refusing to seed while WHATSAPP_PROVIDER is not mock",
            "set WHATSAPP_PROVIDER=mock in infra/.env.staging, deploy, seed, then switch back")
    run_remote(env, compose(env, "run", "--rm", "--entrypoint", "sh", "tools",
                            "-c", SEED_DEMO, profile="tools"))
    if masters:
        for script in ("scripts/load_subsidy_masters.py", "scripts/load_product_master.py"):
            run_remote(env, compose(env, "run", "--rm", "tools", "python", script,
                                    profile="tools"))
    if showcase:
        run_remote(env, compose(env, "run", "--rm", "--entrypoint", "sh", "tools",
                                "-c", SEED_SHOWCASE, profile="tools"))


def load_states(env: dict[str, str]) -> None:
    """FS-056: load or revise the CG, RJ and UP subsidy schemes. A re-run on the same
    date writes nothing; pass a later --effective-from to the script to revise."""
    guard(env)
    run_remote(env, compose(env, "run", "--rm", "tools", "python", "scripts/load_state_masters.py",
                            profile="tools"))


def frontend_sync(env: dict[str, str]) -> None:
    """Production: the shared repo's Frontend/ to the box, with the image's
    Dockerfile set to production, then build and start the frontend and Caddy."""
    if not (FRONTEND_SRC / "package.json").exists():
        die(f"no frontend source at {FRONTEND_SRC}")
    skip = {"node_modules", ".next", ".git", "test-results", "playwright-report", "coverage",
            "storybook-static", ".turbo"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def keep(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
            if set(Path(info.name).parts) & skip:
                return None
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            return info
        tar.add(FRONTEND_SRC, arcname=".", filter=keep)
        docker = (INFRA / "frontend" / "Dockerfile").read_text(encoding="utf-8")
        docker = docker.replace("NEXT_PUBLIC_APP_ENV=staging", "NEXT_PUBLIC_APP_ENV=production")
        # the release's menu: only these screens, whatever the role (the frontend's NAV_ONLY)
        anchor = "    NEXT_PUBLIC_API_BASE_URL=/api/v1"
        assert docker.count(anchor) == 1, "the Dockerfile's build ENV block moved"
        nav_only = ",".join(RELEASED_NAV)
        docker = docker.replace(anchor, f"    NEXT_PUBLIC_NAV_ONLY={nav_only} \\\n{anchor}")
        data = docker.encode()
        info = tarfile.TarInfo("Dockerfile.polysil")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    d = shlex.quote(env["REMOTE_DIR"])
    run_remote(env, f"rm -rf {d}/frontend-src && mkdir -p {d}/frontend-src && "
                    f"tar xzf - -C {d}/frontend-src", stdin=buf.getvalue())
    print(f"  synced   frontend {len(buf.getvalue()) / 1024:.0f} KiB")
    run_remote(env, compose(env, "build", "frontend"))
    run_remote(env, compose(env, "up", "-d", "frontend", "caddy"))


def deploy_prod(env: dict[str, str]) -> None:
    """The whole production deploy, first run included: database up, roles and
    database provisioned, images built, migrated, the frontend and Caddy up."""
    print(f"\n  deploying PRODUCTION to {env['SSH_USER']}@{env['SSH_HOST']}:{env['REMOTE_DIR']}")
    print(f"  database {env['DB_NAME']} as {env['DB_USER']}\n")
    sync(env)
    push_env(env)
    run_remote(env, compose(env, "up", "-d", "--wait", "postgres"))
    provision(env)
    build(env)
    run_remote(env, compose(env, "up", "-d", "--remove-orphans", "postgres", "pgbouncer",
                            "redis", "api", "worker"))
    migrate(env)
    frontend_sync(env)
    ok = health(env)
    print(f"\n  app:     https://{env['APP_DOMAIN']}   (once its A record points here)\n")
    # FS-065 rule 28: only once the API answers, and a failed check fails the
    # deploy's exit code. Nothing is rolled back: the release is already live.
    ok = ok and verify(env, read_only=True)
    sys.exit(0 if ok else 1)


def seed_prod(env: dict[str, str]) -> None:
    """Roles, the release-scope permissions, the stand-in thresholds, the states and
    the first administrator; then the product master. No demo data."""
    guard(env)
    run_remote(env, compose(env, "run", "--rm", "tools", "python", "scripts/seed_prod.py",
                            profile="tools"))
    run_remote(env, compose(env, "run", "--rm", "tools", "python",
                            "scripts/load_product_master.py", profile="tools"))
    # the company's GST registrations: a quotation or order is priced from one
    run_remote(env, compose(env, "run", "--rm", "tools", "python", "scripts/load_seller_gstins.py",
                            "--csv", "/app/data/masters/seller-gstins.csv", profile="tools"))
    # the districts under each state (the official LGD list): territories and leads pick them
    run_remote(env, compose(env, "run", "--rm", "tools", "python", "scripts/load_districts.py",
                            "--csv", "/app/data/masters/districts.csv", profile="tools"))


def health(env: dict[str, str], *, attempts: int = 30) -> bool:
    """Ask the box, not the container: this is the path an SSH tunnel takes."""
    port = env["API_HOST_PORT"]
    for _ in range(attempts):
        got = run_remote(env, f"curl -fsS --max-time 4 http://127.0.0.1:{port}/health",
                         check=False, capture=True)
        if got.returncode == 0:
            print("  health   " + got.stdout.decode().strip())
            return True
        time.sleep(2)
    print("  health   no answer")
    return False


def verify(env: dict[str, str], *, read_only: bool) -> bool:
    """FS-065: the box checks, the read-only HTTP checks, and on staging the
    journey. With --source the live suite comes from the tree that was deployed."""
    return live_verify.verify(TARGET, env, CODE_ROOT, read_only=read_only,
                              run_remote=run_remote, compose=compose, ssh_argv=ssh_argv)


def status(env: dict[str, str]) -> None:
    run_remote(env, compose(env, "ps"))
    health(env, attempts=1)
    stats = ("docker stats --no-stream --format "
             "'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'")
    run_remote(env, stats)
    # the bell's trigger logs a failed notification and lets the business write
    # through; this is the one place anyone reads that log (release review C)
    sql = ("SELECT count(*) AS last_day, max(created_at) AS latest FROM notification_failure "
           "WHERE created_at > now() - interval '1 day';")
    exec_psql = ("docker exec -i " + shlex.quote(env["PG_CONTAINER"]) +
                 " psql -q -U " + shlex.quote(env["PG_SUPERUSER"]) +
                 " -d " + shlex.quote(env["DB_NAME"]) + " -c " + shlex.quote(sql))
    print("  notification failures in the last day:")
    run_remote(env, exec_psql, check=False)


def deploy(env: dict[str, str], *, with_seed: bool) -> None:
    print(f"\n  deploying to {env['SSH_USER']}@{env['SSH_HOST']}:{env['REMOTE_DIR']}")
    print(f"  database {env['DB_NAME']} as {env['DB_USER']}\n")
    sync(env)
    push_env(env)
    build(env)
    up(env)
    migrate(env)
    if with_seed:
        seed(env)
    ok = health(env)
    print("\n  tunnel:  ssh -i <key> -L 8100:127.0.0.1:" + env["API_HOST_PORT"] +
          " " + env["SSH_USER"] + "@" + env["SSH_HOST"])
    print("           then http://127.0.0.1:8100/docs\n")
    sys.exit(0 if ok else 1)


HOOK_COMPOSE = "infra/frontend/docker-compose.hook.yml"


def _webhook_secret() -> None:
    """A WEBHOOK_SECRET in the local env file, made once and never printed. Paste it
    into the GitHub webhook from the file itself."""
    text = ENV_FILE.read_text(encoding="utf-8")
    if any(line.startswith("WEBHOOK_SECRET=") and line.strip() != "WEBHOOK_SECRET="
           for line in text.splitlines()):
        return
    import secrets
    with ENV_FILE.open("a", encoding="utf-8") as out:
        lead = "" if text.endswith("\n") else "\n"
        out.write(f"{lead}WEBHOOK_SECRET={secrets.token_hex(32)}\n")
    print("  secret   WEBHOOK_SECRET added to infra/.env.staging (not printed)")


def frontend_provision(env: dict[str, str]) -> None:
    """The deploy key (made on the box, the private half never leaves it), then the
    receiver. Prints the public key for GitHub. Idempotent."""
    _webhook_secret()
    env = load_config()
    sync(env)
    push_env(env)
    d = shlex.quote(env["REMOTE_DIR"])
    run_remote(env, f"mkdir -p {d}/infra/frontend/keys && chmod 700 {d}/infra/frontend/keys && "
                    f"[ -f {d}/infra/frontend/keys/deploy_key ] || ssh-keygen -q -t ed25519 -N '' "
                    f"-C polysil-staging-frontend -f {d}/infra/frontend/keys/deploy_key")
    run_remote(env, f"docker compose -f {d}/{HOOK_COMPOSE} --env-file {d}/infra/.env.staging "
                    f"up -d --build")
    print("\n  Add this as a READ-ONLY deploy key on github.com/polysil-company/Polysil-CRM "
          "(Settings > Deploy keys):\n")
    run_remote(env, f"cat {d}/infra/frontend/keys/deploy_key.pub")
    print("\n  Then: python scripts/deploy_staging.py frontend   (the first build)\n")


def frontend(env: dict[str, str]) -> None:
    """Pull integration and rebuild now, through the receiver's own script."""
    run_remote(env, "docker exec polysil-deploy-hook /opt/hook/redeploy.sh")


CADDYFILE = "/home/opc/Distributed-File-System/Caddyfile"
CADDY_CONTAINER = "distributed-file-system-web-1"


def frontend_caddy(env: dict[str, str]) -> None:
    """Put polysil-test.pranayx.tech in the Caddyfile the box's proxy serves,
    replacing our block if it is there already, so a change to it reaches the box.
    A block for the old name, polysil.pranayx.tech, is removed.
    The file belongs to another project: it is backed up first, and restored if
    Caddy refuses the result, so their site is never left on a broken config."""
    text = (INFRA / "caddy" / "polysil-app.caddy").read_text(encoding="utf-8")
    block = text[text.index("polysil-test.pranayx.tech {"):].rstrip() + "\n"
    f = shlex.quote(CADDYFILE)
    backup = shlex.quote(CADDYFILE + ".bak-polysil-app")
    c = CADDY_CONTAINER
    # drop our blocks: from an opening line to the first closing brace at column 0.
    # The comment between them in our file is dropped too; only the blocks go up.
    block = "\n".join(line for line in block.splitlines() if not line.startswith("#")) + "\n"
    strip = ("awk 'index($0, \"polysil.pranayx.tech {\") == 1 || "
             "index($0, \"polysil-test.pranayx.tech {\") == 1 {skip=1} "
             "skip && /^}/ {skip=0; next} !skip'")
    # `cat > file` keeps the inode: the Caddyfile is bind-mounted into the proxy
    script = (
        f"cp {f} {backup} && {strip} {backup} > {f}.new && printf '\\n' >> {f}.new && "
        f"cat >> {f}.new && cat {f}.new > {f} && rm -f {f}.new && "
        f"if docker exec {c} caddy validate --config /etc/caddy/Caddyfile "
        f"--adapter caddyfile >/dev/null 2>&1; "
        f"then echo '  caddy    block written and valid'; "
        f"else cp {backup} {f}; echo '  caddy    refused, the original is restored' >&2; "
        f"exit 1; fi && "
        f"docker exec {c} caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile && "
        f"echo '  caddy    reloaded'"
    )
    run_remote(env, script, stdin=block.encode())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("step", nargs="?", default="deploy",
                        choices=["provision", "deploy", "sync", "build", "up", "migrate",
                                 "seed", "seed-prod", "load-states", "templates", "requeue-pdfs",
                                 "status", "verify", "logs", "down", "frontend-prod",
                                 "frontend-provision", "frontend", "frontend-caddy"])
    parser.add_argument("service", nargs="?", default=None, help="which service, for logs")
    parser.add_argument("--seed", action="store_true", help="deploy: run the seeds too")
    parser.add_argument("--no-showcase", action="store_true",
                        help="seed: skip the showcase dataset, demo users and masters only")
    parser.add_argument("--no-masters", action="store_true",
                        help="seed: the demo users only, not the workbooks")
    parser.add_argument("--read-only", action="store_true",
                        help="verify: skip the staging journey, which creates records")
    parser.add_argument("--target", choices=["staging", "prod"], default="staging",
                        help="prod: the Hostinger box, infra/.env.prod and docker-compose.prod.yml")
    parser.add_argument("--source", type=Path, default=None,
                        help="a checkout of the shared repo to take the code from (e.g. at main)")
    args = parser.parse_args(argv)
    set_target(args.target)
    if args.source is not None:
        set_source(args.source.resolve())
        print(f"  source   code from {args.source} (backend/, Frontend/); data from this repo")
    staging_only = ("seed", "frontend-provision", "frontend", "frontend-caddy")
    if TARGET == "prod" and args.step in staging_only:
        die(f"{args.step} is a staging step", "production: deploy, seed-prod, frontend-prod")

    env = load_config()
    if TARGET == "prod" and args.step == "deploy":
        deploy_prod(env)
        return 0
    if args.step == "seed-prod":
        if TARGET != "prod":
            die("seed-prod is for --target prod")
        seed_prod(env)
        return 0
    if args.step == "frontend-prod":
        frontend_sync(env)
        return 0
    if args.step == "verify":
        return 0 if verify(env, read_only=args.read_only) else 1
    if args.step == "provision":
        provision(env)
    elif args.step == "deploy":
        deploy(env, with_seed=args.seed)
    elif args.step == "sync":
        sync(env)
        push_env(env)
    elif args.step == "build":
        build(env)
    elif args.step == "up":
        up(env)
        health(env)
    elif args.step == "migrate":
        migrate(env)
    elif args.step == "seed":
        seed(env, masters=not args.no_masters, showcase=not args.no_showcase)
    elif args.step == "load-states":
        load_states(env)
    elif args.step == "templates":
        sync_templates(env)
    elif args.step == "requeue-pdfs":
        requeue_pdfs(env)
    elif args.step == "status":
        status(env)
    elif args.step == "logs":
        tail = [args.service] if args.service else []
        run_remote(env, compose(env, "logs", "--tail", "120", *tail))
    elif args.step == "down":
        run_remote(env, compose(env, "down"))
    elif args.step == "frontend-provision":
        frontend_provision(env)
    elif args.step == "frontend":
        frontend(env)
    elif args.step == "frontend-caddy":
        frontend_caddy(env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
