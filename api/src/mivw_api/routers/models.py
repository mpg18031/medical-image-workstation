"""Model registry.

Registration verifies the artefact digest before the row is written, so a
substituted ONNX file is rejected at the boundary rather than at inference time.
"""

from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, status

from mivw_api.db import write_audit
from mivw_api.problems import DigestMismatch, NotFound
from mivw_api.repositories import ModelRepository
from mivw_api.schemas.model import (
    ModelCreate,
    ModelDetail,
    ModelUpdate,
    ValidationReport,
)
from mivw_api.security import RequireAdmin, RequireViewer
from mivw_api.services.core_runtime import get_core_runtime
from mivw_api.services.deps import Storage, TenantConn

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelDetail], summary="List registered models")
async def list_models(
    principal: RequireViewer, conn: TenantConn, enabled_only: bool = True
) -> list[ModelDetail]:
    return await ModelRepository(conn).list(enabled_only=enabled_only or None)


@router.get("/{model_id}", response_model=ModelDetail, summary="Get a model")
async def get_model(model_id: uuid.UUID, principal: RequireViewer, conn: TenantConn) -> ModelDetail:
    model = await ModelRepository(conn).get(model_id)
    if model is None:
        raise NotFound("No such model")
    return model


@router.post(
    "",
    response_model=ModelDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Register an uploaded ONNX artefact",
)
async def register_model(
    payload: ModelCreate,
    principal: RequireAdmin,
    conn: TenantConn,
    storage: Storage,
) -> ModelDetail:
    declared = bytes.fromhex(payload.artifact_sha256)

    try:
        artifact = await storage.get_object(payload.artifact_key)
    except Exception as exc:
        raise NotFound("Artifact not found in object storage") from exc

    actual = hashlib.sha256(artifact).digest()
    if actual != declared:
        await write_audit(
            conn,
            org_id=principal.org_id,
            actor_id=principal.user_id,
            action="model.register",
            resource_type="model",
            outcome="denied",
            context={"reason": "digest_mismatch"},
        )
        raise DigestMismatch("The uploaded artifact does not match the declared SHA-256 digest")

    model = await ModelRepository(conn).create(principal.org_id, payload, principal.user_id)

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="model.register",
        resource_type="model",
        resource_id=model.id,
        context={"name": model.name, "version": model.version},
    )
    return model


@router.patch("/{model_id}", response_model=ModelDetail, summary="Update a model")
async def update_model(
    model_id: uuid.UUID,
    payload: ModelUpdate,
    principal: RequireAdmin,
    conn: TenantConn,
) -> ModelDetail:
    model = await ModelRepository(conn).update(
        model_id, description=payload.description, is_enabled=payload.is_enabled
    )
    if model is None:
        raise NotFound("No such model")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="model.update",
        resource_type="model",
        resource_id=model_id,
        context={"is_enabled": payload.is_enabled},
    )
    return model


@router.post(
    "/{model_id}/validate",
    response_model=ValidationReport,
    summary="Dry-run load and synthetic inference",
)
async def validate_model(
    model_id: uuid.UUID,
    principal: RequireAdmin,
    conn: TenantConn,
    storage: Storage,
) -> ValidationReport:
    """Discover a broken model at registration, not at clinical use."""
    repo = ModelRepository(conn)

    model = await repo.get(model_id)
    if model is None:
        raise NotFound("No such model")

    core = get_core_runtime()
    core.require_core()

    messages: list[str] = []

    artifact = await storage.get_object(
        model.artifact_key, expected_sha256=bytes.fromhex(model.artifact_sha256)
    )
    digest_verified = True
    messages.append(f"artifact verified ({len(artifact)} bytes)")

    loaded = False
    dry_run_passed = False
    try:
        import mivw_core  # type: ignore[import-not-found]

        runtime = mivw_core.InferenceRuntime()
        runtime.load_model_bytes(artifact, model.input_spec.model_dump(by_alias=True))
        loaded = True
        messages.append("model loaded")

        runtime.dry_run()
        dry_run_passed = True
        messages.append("synthetic inference succeeded")
    except Exception as exc:
        messages.append(f"validation failed: {type(exc).__name__}")

    ok = digest_verified and loaded and dry_run_passed
    if ok:
        await repo.mark_validated(model_id)

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="model.validate",
        resource_type="model",
        resource_id=model_id,
        outcome="success" if ok else "error",
    )

    return ValidationReport(
        ok=ok,
        loaded=loaded,
        digest_verified=digest_verified,
        dry_run_passed=dry_run_passed,
        messages=messages,
    )
