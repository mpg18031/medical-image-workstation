"""Render session lifecycle.

Creating a session pins the volume into GPU memory, so sessions expire on idle
and are capped per user.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, status

from mivw_api.db import write_audit
from mivw_api.problems import NotFound, QuarantinedSeries
from mivw_api.repositories import ModelRepository, StudyRepository
from mivw_api.schemas.job import AttachSegmentationRequest, RenderSession, RenderSessionCreate
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


@router.post(
    "/sessions/{session_id}/segmentation",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Composite a completed run's segmentation onto an open session",
)
async def attach_segmentation(
    session_id: uuid.UUID,
    payload: AttachSegmentationRequest,
    principal: RequireViewer,
    conn: TenantConn,
    storage: Storage,
) -> None:
    core = get_core_runtime()
    core.require_core()

    row = await conn.fetchrow(
        """
        SELECT s.object_key, s.content_sha256, s.dims, r.model_id, va.spacing_mm
        FROM segmentation s
        JOIN inference_run r ON r.id = s.inference_run_id
        JOIN volume_asset va ON va.id = r.volume_asset_id
        WHERE s.inference_run_id = $1
        """,
        payload.inference_run_id,
    )
    if row is None:
        raise NotFound("No segmentation for this run")

    model = await ModelRepository(conn).get(row["model_id"])
    if model is None:
        raise NotFound("No such model")

    mask_bytes = await storage.get_object(
        row["object_key"], expected_sha256=bytes(row["content_sha256"])
    )

    await core.attach_segmentation(
        session_id=session_id,
        owner_id=principal.user_id,
        mask_bytes=mask_bytes,
        dims=tuple(row["dims"]),
        spacing_mm=tuple(row["spacing_mm"]),
        label_colours=_label_colours(model.label_map),
    )

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="render.segmentation_attach",
        resource_type="render_session",
        resource_id=session_id,
        context={"inference_run_id": str(payload.inference_run_id)},
    )


def _label_colours(label_map: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    """Builds a dense colour LUT indexed by label id; index 0 (background) stays transparent."""
    if not label_map:
        return [(0.0, 0.0, 0.0, 0.0)]

    max_index = max(int(key) for key in label_map)
    colours = [(0.0, 0.0, 0.0, 0.0)] * (max_index + 1)
    for key, info in label_map.items():
        colours[int(key)] = _hex_to_rgba(info.color)
    return colours


def _hex_to_rgba(hex_color: str) -> tuple[float, float, float, float]:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, 1.0)
