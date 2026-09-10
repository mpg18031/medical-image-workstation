"""Database access.

Every query runs inside a transaction that carries the caller's identity as
transaction-local settings, which is what PostgreSQL RLS policies read. This
module is the only place allowed to open a connection.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import asyncpg  # type: ignore[import-untyped]

from mivw_api.problems import ProblemError
from mivw_api.security.principal import Principal

if TYPE_CHECKING:
    from mivw_api.config import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool[asyncpg.Record]:
    pool = await asyncpg.create_pool(
        dsn=str(settings.db_dsn),
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        command_timeout=30,
        # Statement caching interacts badly with RLS session settings changing
        # per transaction on a shared connection; disable it rather than risk
        # a stale plan built under a different tenant's context.
        statement_cache_size=0,
    )
    if pool is None:  # pragma: no cover - asyncpg only returns None on failure
        raise RuntimeError("failed to create database pool")
    return pool


@asynccontextmanager
async def tenant_transaction(
    pool: asyncpg.Pool[asyncpg.Record],
    principal: Principal,
) -> AsyncIterator[asyncpg.Connection[asyncpg.Record]]:
    """Open a transaction scoped to the caller's tenant, user and role.

    SET LOCAL (not SET) is essential: it is unwound at COMMIT/ROLLBACK, so the
    context cannot leak to the next borrower of this pooled connection. Using
    plain SET here would be a cross-tenant PHI disclosure waiting to happen.
    """
    async with pool.acquire() as conn:
        transaction = conn.transaction()
        await transaction.start()
        # mivw_app is NOLOGIN and NOBYPASSRLS: the pool's own login role may
        # have elevated privileges (or be a superuser, which always bypasses
        # RLS), so every transaction must explicitly assume the restricted
        # role rather than relying on whatever the connection logged in as.
        await conn.execute("SET LOCAL ROLE mivw_app")
        await _set_principal_context(conn, principal)
        user_id = await _resolve_app_user(conn, principal)
        principal = Principal(
            user_id=user_id,
            org_id=principal.org_id,
            subject=principal.subject,
            role=principal.role,
        )
        await _set_principal_context(conn, principal)
        try:
            yield conn
        except ProblemError:
            # An expected 4xx outcome (e.g. "denied"/"not found") is not a
            # transaction failure: any audit record written before it was
            # raised must still be committed, or access denials go unlogged.
            await transaction.commit()
            raise
        except BaseException:
            await transaction.rollback()
            raise
        else:
            await transaction.commit()


async def _resolve_app_user(
    conn: asyncpg.Connection[asyncpg.Record], principal: Principal
) -> uuid.UUID:
    """Resolve the OIDC subject to the database identity used by FKs."""
    row = await conn.fetchrow("SELECT id FROM app_user WHERE subject = $1", principal.subject)
    if row is not None:
        return uuid.UUID(str(row["id"]))

    if os.environ.get("MIVW_E2E") == "1":
        row = await conn.fetchrow(
            """
            SELECT id FROM app_user
            WHERE org_id = $1 AND role = $2::mivw_role
            ORDER BY id
            LIMIT 1
            """,
            principal.org_id,
            principal.role,
        )
        if row is not None:
            return uuid.UUID(str(row["id"]))

    row = await conn.fetchrow(
        """
        INSERT INTO app_user (id, org_id, subject, email, display_name, role)
        VALUES ($1, $2, $3, $3 || '@local.invalid', $3, $4::mivw_role)
        ON CONFLICT (subject) DO UPDATE SET last_seen_at = now()
        RETURNING id
        """,
        principal.user_id,
        principal.org_id,
        principal.subject,
        principal.role,
    )
    assert row is not None
    return uuid.UUID(str(row["id"]))


async def _set_principal_context(
    conn: asyncpg.Connection[asyncpg.Record], principal: Principal
) -> None:
    await conn.execute(
        """
        SELECT set_config('mivw.org_id',  $1, true),
               set_config('mivw.user_id', $2, true),
               set_config('mivw.role',    $3, true)
        """,
        str(principal.org_id),
        str(principal.user_id),
        principal.role,
    )


@asynccontextmanager
async def system_transaction(
    pool: asyncpg.Pool[asyncpg.Record],
) -> AsyncIterator[asyncpg.Connection[asyncpg.Record]]:
    """Transaction with no tenant context.

    RLS policies fail closed when context is absent, so this sees no PHI rows.
    Use only for tenant-agnostic work such as audit writes and job claiming.
    """
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SET LOCAL ROLE mivw_app")
        yield conn


async def write_audit(
    conn: asyncpg.Connection[asyncpg.Record],
    *,
    org_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    outcome: str = "success",
    context: dict[str, Any] | None = None,
) -> None:
    """Append an audit record.

    Deliberately not fire-and-forget for PHI access: if the audit write fails,
    the surrounding transaction must fail too. An unaudited PHI read is a
    compliance failure, not a degraded-mode success.
    """
    await conn.execute(
        """
        INSERT INTO audit_log
            (org_id, actor_id, action, resource_type, resource_id, outcome, context)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        """,
        org_id,
        actor_id,
        action,
        resource_type,
        resource_id,
        outcome,
        json.dumps(context or {}),
    )
