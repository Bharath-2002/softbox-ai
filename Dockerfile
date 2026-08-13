# API, worker and poller share this one image (CHECKLIST.md, M1 Project
# setup) - only the API process (uvicorn) actually exists yet (M1-M4);
# worker (M5's TaskQueue consumer) and poller (M5's reconciler) are future
# CMD overrides at deploy time, not separate Dockerfiles, once those
# entry points are built. Nothing below is worker/poller-specific.
#
# NOT build-tested locally - this machine has no container runtime (the
# same reason docker-compose was dropped from M1's Project setup checklist
# item; see scripts/bootstrap_local_db.sh's header). The command this image
# runs (`uvicorn app.bootstrap.app:create_app --factory`) is verified: run
# directly with `uv run` against a local Postgres, it starts, and /health
# and /ready both return 200.

# ── Build stage: resolve dependencies with uv, nothing else ────────────────
FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

# Layer separated from the source copy below: changing application code
# should not invalidate the (slow) dependency-resolution layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --no-editable

COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable

# ── Runtime stage: no uv, no build toolchain, no source outside the venv ───
FROM python:3.12-slim AS runtime

# CLAUDE.md §11: the process must not run as root - a container escape or a
# dependency RCE then has no more privilege than this unprivileged account.
RUN groupadd --system softbox && useradd --system --gid softbox --create-home softbox

WORKDIR /app
COPY --from=build --chown=softbox:softbox /app/.venv /app/.venv
COPY --from=build --chown=softbox:softbox /app/src /app/src
COPY --from=build --chown=softbox:softbox /app/migrations /app/migrations
COPY --from=build --chown=softbox:softbox /app/alembic.ini /app/alembic.ini

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER softbox

EXPOSE 8000

# /health touches nothing (see api/health.py's docstring) - correct for a
# container HEALTHCHECK, which must not fail the whole container over a
# transient database hiccup /ready would legitimately report as degraded.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

# Migrations run as a separate step (the owner DSN this process must never
# hold - Settings has no field for it, see migrations/env.py's docstring),
# not as part of container startup.
CMD ["uvicorn", "app.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
