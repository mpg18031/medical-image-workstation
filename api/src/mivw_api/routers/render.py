"""Render session lifecycle.

Creating a session pins the volume into GPU memory, so sessions expire on idle
and are capped per user.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from mivw_api.db import write_audit
from mivw_api.problems import NotFound, QuarantinedSeries
from mivw_api.repositories import StudyRepository
from mivw_api.schemas.job import RenderSession, RenderSessionCreate
from mivw_api.security import RequireViewer
from mivw_api.services.core_runtime import get_core_runtime
from mivw_api.services.deps import Storage, TenantConn

router = APIRouter(prefix="/render", tags=["render"])


@router.post(
    "/sessions",
    response_model=RenderSession,
    status_code=status.HTTP_201_CREATED,
    summary="Open a render session",
)
async def create_render_session(
    payload: RenderSessionCreate,
    principal: RequireViewer,
    conn: TenantConn,
    storage: Storage,
) -> RenderSession:
    core = get_core_runtime()
    core.require_core()

    series = await StudyRepository(conn).get_series(payload.series_id)
    if series is None:
        raise NotFound("No such series")
    if series.is_quarantined:
        raise QuarantinedSeries("This series is awaiting burned-in annotation review")
    if not series.has_volume:
        raise NotFound("No volume has been reconstructed for this series")

    asset = await StudyRepository(conn).get_volume_asset(payload.series_id)
    if asset is None:
        raise NotFound("No volume has been reconstructed for this series")
    info, object_key, content_sha256 = asset

    import mivw_core  # type: ignore[import-not-found]

    raw_volume = await storage.get_object(object_key, expected_sha256=bytes(content_sha256))
    volume = mivw_core.Volume(tuple(info.dims), tuple(info.spacing_mm), mivw_core.DType.Int16)
    import numpy as np

    voxels = np.frombuffer(raw_volume, dtype=np.int16)
    expected_voxels = int(np.prod(info.dims))
    if voxels.size != expected_voxels:
        raise NotFound("Stored volume payload is incomplete")
    volume.as_array()[:] = voxels.reshape(tuple(reversed(info.dims)))

    state = await core.create_session(
        series_id=payload.series_id,
        owner_id=principal.user_id,
        org_id=principal.org_id,
        width=payload.width,
        height=payload.height,
        volume=volume,
        transfer_function_preset=(
            "ct-color"
            if "contrast" in (getattr(series, "description", None) or "").lower()
            else "ct-soft-tissue"
        ),
    )

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="render.session_open",
        resource_type="series",
        resource_id=payload.series_id,
    )

    return RenderSession(
        id=state.id,
        token=state.token,
        series_id=state.series_id,
        websocket_path=f"/ws/render?session={state.token}",
        expires_at=state.expires_at,
        gpu_memory_bytes=core.gpu_memory_bytes(),
    )


@router.delete("/sessions/{session_id}", status_code=204, summary="Close a render session")
async def close_render_session(
    session_id: uuid.UUID, principal: RequireViewer, conn: TenantConn
) -> None:
    closed = await get_core_runtime().close_session(session_id, principal.user_id)
    if not closed:
        raise NotFound("No such render session")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="render.session_close",
        resource_type="render_session",
        resource_id=session_id,
    )
