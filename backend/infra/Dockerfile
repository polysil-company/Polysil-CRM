# syntax=docker/dockerfile:1
#
# The API and the worker, one image. A second stage adds what only the one-shot
# jobs need, so the image that serves traffic carries neither psycopg nor openpyxl.
#
#   docker build -f infra/Dockerfile --target runtime -t polysil-api:staging ..
#   docker build -f infra/Dockerfile --target tools   -t polysil-tools:staging ..
#
# Build context is the repository root. Both compose services name their target;
# a bare `docker build` with no --target gives `tools`, which is the superset.
#
# arm64 note: every wheel this installs (pydantic-core, asyncpg, argon2-cffi,
# uvloop, httptools, psycopg-binary) publishes a manylinux aarch64 build, so
# nothing compiles here and no toolchain is installed.

# ── dependencies, in a venv of their own ──────────────────────────────────
# There is no lockfile, so the dependency set comes from pyproject. The package
# itself is installed and then removed: that leaves exactly the dependencies,
# and the layer caches on pyproject.toml alone rather than on every source edit.
FROM python:3.12-slim-bookworm AS deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
RUN mkdir -p api worker \
 && : > api/__init__.py \
 && : > worker/__init__.py \
 && pip install . \
 && pip uninstall -y polysil-crm

# ── the image that serves traffic ─────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root. A fixed uid so a bind-mounted file's ownership is predictable.
RUN groupadd --system --gid 10001 polysil \
 && useradd --system --uid 10001 --gid polysil --home-dir /app --shell /usr/sbin/nologin polysil

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app
COPY --chown=polysil:polysil api ./api
COPY --chown=polysil:polysil worker ./worker
COPY --chown=polysil:polysil alembic.ini ./

USER polysil
EXPOSE 8000

# No curl in slim, and adding one to a runtime image to answer a health check is
# a poor trade. urllib is already there.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

# 0.0.0.0 is the container's interface, not the host's. Nothing is published
# beyond 127.0.0.1 by the compose file; this is what lets a reverse proxy on the
# same Docker network reach the API without a host port.
#
# --no-proxy-headers, and the application decides. Uvicorn's proxy-header
# middleware is on by default and trusts X-Forwarded-For from a loopback peer,
# so it rewrites request.client *before* api/routers/auth.py:_is_trusted_peer
# ever sees the real TCP peer. On a loopback connection our own allowlist then
# reads an address the caller chose, and an empty TRUSTED_PROXY_PEERS stops
# protecting anything: the caller picks their own rate-limit bucket
# (cross-vendor review, September). One layer, one policy, one place to read it.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

# ── migrations, seeds and the master loaders ──────────────────────────────
# psycopg because alembic's env.py runs migrations over the sync driver, and
# openpyxl because the two master loaders read the client's workbooks. Neither
# belongs in a process that serves requests.
FROM runtime AS tools
USER root
RUN pip install --no-cache-dir "psycopg[binary]>=3.2" "openpyxl>=3.1"
# scripts/seed_demo.py reads its database credentials from infra/.env and from
# nowhere else. The one-shot container writes that file itself, from its own
# environment, on the way into the seed - so the credentials never land on the
# host's filesystem a second time. This is the directory it writes into.
RUN install -d -o polysil -g polysil /app/infra
COPY --chown=polysil:polysil scripts ./scripts
# seed_demo parses the permission matrix out of RBAC.md at seed time (FS-002 5.3).
COPY --chown=polysil:polysil docs/architecture/RBAC.md ./docs/architecture/RBAC.md
USER polysil
CMD ["alembic", "upgrade", "head"]
