"""Row-level security helpers for Alembic migrations.

Every tenant-scoped table calls all three of these (D3). Kept as three
explicit calls per migration rather than one combined helper — a migration is
something a DBA reads line by line before running against production, and
each statement here is independently meaningful.

Table and role names are always literals written by the migration's author,
never runtime or user-supplied data, so building the DDL with an f-string is
the normal, safe way to do this — Postgres does not support parameter
placeholders for identifiers in DDL at all.
"""

from __future__ import annotations

from alembic import op


def enable_rls(table: str) -> None:
    """Enable row-level security, and FORCE it.

    Without FORCE, the table's owner — the role Alembic runs migrations as —
    bypasses every policy on its own tables. A test suite that happens to run
    as the owner would then pass with the policies doing nothing at all.
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def create_tenant_isolation_policy(table: str, *, tenant_column: str = "tenant_id") -> None:
    """A row is visible, and writable, only when its tenant column matches the
    session's bound tenant.

    ``current_setting(..., true)`` returns NULL when the GUC has never been
    touched on this connection — but returns an **empty string**, not NULL,
    once a transaction has set it and then ended (proven empirically, not
    assumed: see the isolation test that pins one physical connection across
    two transactions). ``''::uuid`` raises rather than comparing false, so a
    bare cast would turn "no tenant bound" into a hard error on any pooled
    connection that previously handled a different tenant's request instead
    of the zero rows the fail-closed design requires. ``NULLIF(..., '')``
    normalises both cases to NULL before the cast, and ``{tenant_column} =
    NULL`` is never true in SQL either way.
    """
    policy = f"{table}_tenant_isolation"
    predicate = f"{tenant_column} = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    op.execute(f"CREATE POLICY {policy} ON {table} USING ({predicate}) WITH CHECK ({predicate})")


def grant_to_app_role(
    table: str,
    *,
    role: str = "softbox_app",
    privileges: str = "SELECT, INSERT, UPDATE, DELETE",
) -> None:
    """The application connects as this role (D3) — it owns nothing and has no
    privileges until a migration grants them explicitly."""
    op.execute(f"GRANT {privileges} ON {table} TO {role}")
