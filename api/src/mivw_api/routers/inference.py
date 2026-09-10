"""Inference runs."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Header, status

from mivw_api.db import write_audit
from mivw_api.problems import NotFound, SpecMismatch
from mivw_api.repositories import ModelRepository
from mivw_api.schemas.job import Job, JobKind, JobStatus
from mivw_api.schemas.model import InferenceRequest, InferenceRun, SegmentationResult
from mivw_api.security import RequireResearcher, RequireViewer
from mivw_api.services.core_runtime import get_core_runtime
from mivw_api.services.deps import TenantConn

router = APIRouter(tags=["inference"])


@router.post(
    "/inference-runs",
    response_model=Job,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an inference run",
)
async def create_inference_run(
    payload: InferenceRequest,
    principal: RequireResearcher,
    conn: TenantConn,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Job:
    core = get_core_runtime()
    core.require_core()

    model = await ModelRepository(conn).get(payload.model_id)
    if model is None or not model.is_enabled:
        raise NotFound("No such model")

    asset = await _find_volume(conn, payload.volume_asset_id)
    if asset is None:
        raise NotFound("No such volume")

    _assert_conforms(model, asset)

    row = await conn.fetchrow(
        """
        INSERT INTO job (org_id, kind, status, payload, submitted_by, idempotency_key)
        VALUES ($1, 'inference', 'queued', $2::jsonb, $3, $4)
        ON CONFLICT (org_id, idempotency_key) DO UPDATE SET kind = EXCLUDED.kind
        RETURNING id, kind, status, progress, stage, created_at, finished_at, error
        """,
        principal.org_id,
        f'{{"modelId": "{payload.model_id}", "volumeAssetId": "{payload.volume_asset_id}"}}',
        principal.user_id,
        idempotency_key,
    )
    assert row is not None

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="inference.submit",
        resource_type="job",
        resource_id=row["id"],
        context={"model": f"{model.name}:{model.version}"},
    )

    return Job(
        id=row["id"],
        kind=JobKind(row["kind"]),
        status=JobStatus(row["status"]),
        progress=row["progress"],
        stage=row["stage"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
        error=row["error"],
    )


@router.get("/inference-runs/{run_id}", response_model=InferenceRun, summary="Get a run")
async def get_run(run_id: uuid.UUID, principal: RequireViewer, conn: TenantConn) -> InferenceRun:
    row = await conn.fetchrow(
        """
        SELECT id, model_id, volume_asset_id, status, started_at, finished_at,
               metrics, model_sha256, input_sha256, engine_cache_key,
               gpu_name, driver_version, runtime_version
        FROM inference_run WHERE id = $1
        """,
        run_id,
    )
    if row is None:
        raise NotFound("No such inference run")

    from mivw_api.schemas.model import RunProvenance

    return InferenceRun(
        id=row["id"],
        model_id=row["model_id"],
        volume_asset_id=row["volume_asset_id"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        provenance=RunProvenance(
            model_sha256=bytes(row["model_sha256"]).hex(),
            input_sha256=bytes(row["input_sha256"]).hex(),
            engine_cache_key=row["engine_cache_key"],
            gpu_name=row["gpu_name"],
            driver_version=row["driver_version"],
            runtime_version=row["runtime_version"],
        ),
        metrics=row["metrics"] or {},
    )


@router.get(
    "/inference-runs/{run_id}/segmentation",
    response_model=SegmentationResult,
    summary="Get the segmentation produced by a run",
)
async def get_segmentation(
    run_id: uuid.UUID, principal: RequireViewer, conn: TenantConn
) -> SegmentationResult:
    row = await conn.fetchrow(
        "SELECT id, inference_run_id, dims, label_stats, object_key "
        "FROM segmentation WHERE inference_run_id = $1",
        run_id,
    )
    if row is None:
        raise NotFound("No segmentation for this run")

    return SegmentationResult(
        id=row["id"],
        inference_run_id=row["inference_run_id"],
        dims=tuple(row["dims"]),
        label_stats=row["label_stats"] or {},
        download=row["object_key"],
    )


async def _find_volume(conn: Any, volume_asset_id: uuid.UUID) -> Any:
    return await conn.fetchrow(
        "SELECT id, dims, spacing_mm, direction FROM volume_asset WHERE id = $1",
        volume_asset_id,
    )


def _assert_conforms(model: Any, asset: Any) -> None:
    """Reject a non-conforming volume instead of silently resampling it.

    Adapting the input here would turn a loud failure into a quiet, plausible,
    wrong result - the worst outcome for a clinical imaging tool. See ADR 0005.
    """
    expected = model.input_spec.spacing_mm
    actual = tuple(asset["spacing_mm"])
    tolerance = model.input_spec.spacing_tolerance_mm

    if any(abs(e - a) > tolerance for e, a in zip(expected, actual, strict=True)):
        raise SpecMismatch(
            f"Model expects spacing {expected} mm within {tolerance} mm; volume is {actual} mm"
        )

    patch = model.input_spec.shape[-3:]
    dims = tuple(asset["dims"])
    if any(d < p for d, p in zip(dims, patch, strict=True)):
        raise SpecMismatch(f"Volume {dims} is smaller than the model patch size {tuple(patch)}")
