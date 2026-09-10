"""Liveness and readiness.

Unauthenticated, so the bodies stay deliberately thin: an outsider learns
nothing about internal topology from them.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from mivw_api.services.core_runtime import get_core_runtime
from mivw_api.services.deps import PgPool, get_pool

router = APIRouter(tags=["operational"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readyz(
    response: Response,
    pool: Annotated[PgPool, Depends(get_pool)],
) -> dict[str, Any]:
    checks: dict[str, str] = {}

    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    try:
        # A missing core degrades the service; it does not make it unready,
        # because the worklist and annotation paths still work.
        checks["core"] = "ok" if get_core_runtime().available else "degraded"
    except Exception:
        checks["core"] = "degraded"

    ready = checks["database"] == "ok"
    if not ready:
        response.status_code = 503

    return {"ready": ready, "checks": checks}
