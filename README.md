# Softbox AI

Softbox turns a handful of raw product photos into a complete, publishable catalog.

A business defines its own categories, custom fields and product variants — nothing in the
platform knows what it is selling. For each category it declares which reference photos its staff
will capture and which catalog images it needs produced from them. Staff then photograph a product
a few times on a phone; Softbox generates every catalog image against the scene templates, writes
per-channel copy, runs an automated quality pass, and publishes to the storefront and connected
social accounts — with an approval queue that can be switched on or off per category.

Sarees are the first vertical, not a special case.

---

## Status

**M1 (Foundations) in progress.** Layer skeleton, settings, structured logging, health probes,
and the database foundation with row-level tenant isolation are in place and tested against a
real Postgres.

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 24 numbered decisions, schema, layering rules,
  pipeline state machines, delivery plan
- [docs/DIAGRAMS.md](docs/DIAGRAMS.md) — application flow, state machines, architecture and ER
  diagrams
- [CHECKLIST.md](CHECKLIST.md) *(not tracked in git — local working file)* — build progress

## Stack

| | |
|---|---|
| Runtime | Python 3.12+, FastAPI |
| Packaging | uv |
| Database | PostgreSQL 16 — row-level security, composite tenant foreign keys |
| ORM / migrations | SQLAlchemy 2.0 (imperative mapping), Alembic |
| Validation | Pydantic v2 |
| Queue | Postgres-backed (`FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`); Redis/ARQ is a documented upgrade path |
| Storage | S3-compatible object storage behind a CDN |
| Image generation | Nano Banana 2 |
| Auth | OIDC (Google Workspace / Entra), behind an identity port |

## Architecture in one paragraph

Six layers — `api → agents → features → services → entities → shared` — where a layer may only
import from layers below it. All ports are declared as `typing.Protocol` in `services`; their
implementations live in `infrastructure`, which **only the composition root may import**. This is
enforced by `import-linter` contracts in CI, not by convention. See
[ARCHITECTURE.md D5–D9](docs/ARCHITECTURE.md).

## Development

Requires a local Postgres 16 and [uv](https://docs.astral.sh/uv/). No Docker — see
[ARCHITECTURE.md D19](docs/ARCHITECTURE.md) for why the queue and local dev are Postgres-only.

```sh
uv sync                                                            # install dependencies
PGHOST=localhost PGUSER=<your-superuser> ./scripts/bootstrap_local_db.sh  # roles + databases, idempotent
cp .env.example .env
uv run alembic upgrade head                                        # migrate softbox (dev)
SOFTBOX_MIGRATIONS_DATABASE_URL=postgresql+asyncpg://softbox_owner:softbox_owner_dev_only@localhost:5432/softbox_test \
    uv run alembic upgrade head                                    # migrate softbox_test (tests)
make check                                                          # lint, types, contracts, tests
```

`make check` runs everything CI runs: `ruff` format + lint, `mypy --strict`, the `import-linter`
architectural contracts, and the full test suite — including the tenant-isolation tests, which
connect as the non-owner `softbox_app` role against real row-level security policies rather than
a mock. See [CLAUDE.md](CLAUDE.md) for the engineering rules this codebase follows.
