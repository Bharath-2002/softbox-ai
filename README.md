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

**Architecture approved. Implementation not started.**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 24 numbered decisions, schema, layering rules,
  pipeline state machines, delivery plan
- [docs/DIAGRAMS.md](docs/DIAGRAMS.md) — application flow, state machines, architecture and ER
  diagrams

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

Not yet scaffolded. Milestone M1 in the delivery plan covers project setup, the layer skeleton,
CI contracts, database and RLS harness, and SSO.
