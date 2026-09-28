#!/usr/bin/env python3
"""Deploy the backend to the staging box, for the frontend track to build against.

    python scripts/deploy_staging.py provision   # the role, the database, the grants
    python scripts/deploy_staging.py deploy      # sync, build, up, alembic upgrade head
    python scripts/deploy_staging.py seed        # demo users, masters, showcase dataset
    python scripts/deploy_staging.py templates   # order messages on only where 11za approved them
    python scripts/deploy_staging.py status      # containers, health, resource use
    python scripts/deploy_staging.py frontend-provision   # the deploy key and the webhook receiver
    python scripts/deploy_staging.py frontend    # pull integration and rebuild the frontend now
    python scripts/deploy_staging.py frontend-caddy   # add polysil.pranayx.tech to the box's Caddy
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

ROOT = Path(__file__).resolve().parent.parent
INFRA = ROOT / "infra"
ENV_FILE = INFRA / ".env.staging"
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
]

# Replaced wholesale on every deploy, so a file deleted here disappears there.
REPLACE = ["api", "worker", "scripts", "data", "docs"]

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
        die("infra/.env.staging not found.",
            "cp infra/.env.staging.example infra/.env.staging  and fill it in")
    env = read_env(ENV_FILE)

    required = ["SSH_HOST", "SSH_USER", "SSH_KEY_PATH", "REMOTE_DIR",
                "DB_NAME", "DB_USER", "DB_PASSWORD", "JWT_SECRET",
                "PG_HOST", "PG_CONTAINER", "PG_SUPERUSER",
                # FS-005: the share link's origin; the API refuses to start without it
                "PUBLIC_WEB_URL"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        die("infra/.env.staging is missing: " + ", ".join(missing))

    guard(env)

    if not Path(env["SSH_KEY_PATH"]).exists():
        die(f"SSH key not found: {env['SSH_KEY_PATH']}")
    env.setdefault("API_HOST_PORT", "8100")
    env.setdefault("PGBOUNCER_HOST_PORT", "6432")
    return env


# -- the box ---------------------------------------------------------------


def ssh_argv(env: dict[str, str]) -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
            "-i", env["SSH_KEY_PATH"], env["SSH_USER"] + "@" + env["SSH_HOST"]]


def run_remote(env: dict[str, str], command: str, *, stdin: bytes | None = None,
               check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """One command on the box, through a non-interactive shell."""
    argv = [*ssh_argv(env), "bash", "-lc", shlex.quote(command)]
    return subprocess.run(
        argv, input=stdin, check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def compose(env: dict[str, str], *args: str, profile: str | None = None) -> str:
    """The compose invocation, as one shell string for run_remote."""
    d = env["REMOTE_DIR"]
    parts = ["docker", "compose",
             "--project-directory", d + "/infra",
             "-f", d + "/infra/docker-compose.staging.yml",
             "--env-file", d + "/infra/.env.staging"]
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
            path = ROOT / rel
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
    run_remote(env, f"umask 077 && cat > {d}/infra/.env.staging", stdin=body.encode())
    print("  env      .env.staging written, mode 600")


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


def status(env: dict[str, str]) -> None:
    run_remote(env, compose(env, "ps"))
    health(env, attempts=1)
    stats = ("docker stats --no-stream --format "
             "'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}'")
    run_remote(env, stats)


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
    """Put polysil.pranayx.tech in the Caddyfile the box's proxy serves, replacing
    the block if it is there already, so a change to the block reaches the box.
    The file belongs to another project: it is backed up first, and restored if
    Caddy refuses the result, so their site is never left on a broken config."""
    text = (INFRA / "caddy" / "polysil-app.caddy").read_text(encoding="utf-8")
    block = text[text.index("polysil.pranayx.tech {"):].rstrip() + "\n"
    f = shlex.quote(CADDYFILE)
    backup = shlex.quote(CADDYFILE + ".bak-polysil-app")
    c = CADDY_CONTAINER
    # drop the old block: from its opening line to the first closing brace at column 0
    strip = ("awk 'index($0, \"polysil.pranayx.tech {\") == 1 {skip=1} "
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
                                 "seed", "templates", "status", "logs", "down",
                                 "frontend-provision", "frontend", "frontend-caddy"])
    parser.add_argument("service", nargs="?", default=None, help="which service, for logs")
    parser.add_argument("--seed", action="store_true", help="deploy: run the seeds too")
    parser.add_argument("--no-showcase", action="store_true",
                        help="seed: skip the showcase dataset, demo users and masters only")
    parser.add_argument("--no-masters", action="store_true",
                        help="seed: the demo users only, not the workbooks")
    args = parser.parse_args(argv)

    env = load_config()
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
    elif args.step == "templates":
        sync_templates(env)
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
