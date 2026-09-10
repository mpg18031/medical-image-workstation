"""Series detail, volume access and per-series annotations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from mivw_api.db import write_audit
from mivw_api.problems import Forbidden, NotFound, QuarantinedSeries
from mivw_api.repositories import AnnotationRepository, StudyRepository
from mivw_api.schemas.annotation import (
    AnnotationCreate,
    AnnotationDetail,
    AnnotationUpdate,
)
from mivw_api.schemas.study import PresignedDownload, SeriesDetail
from mivw_api.security import CurrentPrincipal, RequireAnnotator, RequireViewer
from mivw_api.security.principal import Role
from mivw_api.services.deps import Storage, TenantConn

router = APIRouter(prefix="/series", tags=["series"])


@router.get("/{series_id}", response_model=SeriesDetail, summary="Get a series")
async def get_series(
    series_id: uuid.UUID, principal: RequireViewer, conn: TenantConn
) -> SeriesDetail:
    series = await StudyRepository(conn).get_series(series_id)
    if series is None:
        raise NotFound("No such series")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="series.read",
        resource_type="series",
        resource_id=series_id,
    )
    return series


@router.get(
    "/{series_id}/volume",
    response_model=PresignedDownload,
    summary="Get a short-lived download URL for the resampled volume",
)
async def get_volume(
    series_id: uuid.UUID,
    principal: RequireViewer,
    conn: TenantConn,
    storage: Storage,
) -> PresignedDownload:
    repo = StudyRepository(conn)

    series = await repo.get_series(series_id)
    if series is None:
        raise NotFound("No such series")
    if series.is_quarantined:
        # Burned-in pixel annotation may still carry PHI that header scrubbing
        # could not remove.
        raise QuarantinedSeries("This series is awaiting burned-in annotation review")

    asset = await repo.get_volume_asset(series_id)
    if asset is None:
        raise NotFound("No volume has been reconstructed for this series")

    _info, object_key, content_sha256 = asset
    url = await storage.presign_get(object_key)

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="volume.download",
        resource_type="series",
        resource_id=series_id,
    )

    return PresignedDownload(
        url=url, expires_at=storage.expiry(), content_sha256=bytes(content_sha256).hex()
    )


@router.get(
    "/{series_id}/annotations",
    response_model=list[AnnotationDetail],
    summary="List annotations on a series",
)
async def list_annotations(
    series_id: uuid.UUID, principal: RequireViewer, conn: TenantConn
) -> list[AnnotationDetail]:
    if await StudyRepository(conn).get_series(series_id) is None:
        raise NotFound("No such series")
    return await AnnotationRepository(conn).list_for_series(series_id)


@router.post(
    "/{series_id}/annotations",
    response_model=AnnotationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create an annotation",
)
async def create_annotation(
    series_id: uuid.UUID,
    payload: AnnotationCreate,
    principal: RequireAnnotator,
    conn: TenantConn,
) -> AnnotationDetail:
    if await StudyRepository(conn).get_series(series_id) is None:
        raise NotFound("No such series")

    annotation = await AnnotationRepository(conn).create(
        principal.org_id, series_id, principal.user_id, payload
    )

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="annotation.create",
        resource_type="annotation",
        resource_id=annotation.id,
        context={"kind": payload.kind.value},
    )
    return annotation


annotations_router = APIRouter(prefix="/annotations", tags=["annotations"])


@annotations_router.patch(
    "/{annotation_id}", response_model=AnnotationDetail, summary="Update an annotation"
)
async def update_annotation(
    annotation_id: uuid.UUID,
    payload: AnnotationUpdate,
    principal: RequireAnnotator,
    conn: TenantConn,
) -> AnnotationDetail:
    repo = AnnotationRepository(conn)

    existing = await repo.get(annotation_id)
    if existing is None:
        raise NotFound("No such annotation")
    _assert_may_modify(existing, principal)

    updated = await repo.update(annotation_id, payload=payload.payload, label=payload.label)
    if updated is None:
        raise NotFound("No such annotation")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="annotation.update",
        resource_type="annotation",
        resource_id=annotation_id,
    )
    return updated


@annotations_router.delete("/{annotation_id}", status_code=204, summary="Withdraw an annotation")
async def delete_annotation(
    annotation_id: uuid.UUID, principal: RequireAnnotator, conn: TenantConn
) -> None:
    repo = AnnotationRepository(conn)

    existing = await repo.get(annotation_id)
    if existing is None:
        raise NotFound("No such annotation")
    _assert_may_modify(existing, principal)

    await repo.soft_delete(annotation_id)
    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="annotation.delete",
        resource_type="annotation",
        resource_id=annotation_id,
    )


def _assert_may_modify(annotation: AnnotationDetail, principal: CurrentPrincipal) -> None:
    """Authors own their annotations; admins may correct any within the tenant."""
    if annotation.author_id != principal.user_id and principal.role is not Role.ADMIN:
        raise Forbidden("Only the author or an admin may modify this annotation")
