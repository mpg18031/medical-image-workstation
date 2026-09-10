"""FastAPI dependency providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, cast

from fastapi import Depends, Request

from mivw_api.db import tenant_transaction
from mivw_api.security.rbac import CurrentPrincipal
from mivw_api.storage import ObjectStore

# asyncpg's classes are not subscriptable at runtime, but FastAPI resolves
# annotations eagerly, so the parameterised forms must stay type-check only.
type PgPool = Any
type PgConn = Any


def get_pool(request: Request) -> PgPool:
    return request.app.state.pool


def get_storage(request: Request) -> ObjectStore:
    return cast(ObjectStore, request.app.state.storage)


async def tenant_conn(
    principal: CurrentPrincipal,
    pool: Annotated[PgPool, Depends(get_pool)],
) -> AsyncIterator[PgConn]:
    """A transaction carrying the caller's identity for RLS.

    Yielding inside the context manager keeps the transaction open for the whole
    request, so the audit write and the data read commit or roll back together.
    """
    async with tenant_transaction(pool, principal) as conn:
        yield conn


TenantConn = Annotated[PgConn, Depends(tenant_conn)]
Storage = Annotated[ObjectStore, Depends(get_storage)]
