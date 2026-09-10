"""Study worklist and detail."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mivw_api.config import Settings, get_settings
from mivw_api.db import write_audit
from mivw_api.keys import get_hmac_key
from mivw_api.problems import NotFound
from mivw_api.repositories import StudyRepository, hash_patient_ref
from mivw_api.schemas import Page, StudyQuery, StudySummary
from mivw_api.schemas.study import SeriesDetail
from mivw_api.security import RequireAdmin, RequireViewer
from mivw_api.services.deps import TenantConn

router = APIRouter(prefix="/studies", tags=["studies"])


@router.get("", response_model=Page[StudySummary], summary="List studies")
async def list_studies(
    principal: RequireViewer,
    conn: TenantConn,
    settings: Annotated[Settings, Depends(get_settings)],
    modality: Annotated[str | None, Query(max_length=16)] = None,
    patient_ref: Annotated[str | None, Query(alias="patientRef", max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    after: Annotated[str | None, Query()] = None,
) -> Page[StudySummary]:
    query = StudyQuery(modality=modality, patient_ref=patient_ref, limit=limit, after=after)

    # The raw reference is HMAC'd immediately and never reaches SQL, logs or
    # error bodies in plaintext.
    mrn_hmac = hash_patient_ref(patient_ref, get_hmac_key(settings)) if patient_ref else None

    repo = StudyRepository(conn)
    studies, next_cursor = await repo.list_studies(query, mrn_hmac=mrn_hmac)

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="study.list",
        resource_type="study",
        outcome="success",
        context={"count": len(studies), "filtered": bool(patient_ref)},
    )

    return Page[StudySummary](items=studies, next_cursor=next_cursor)


@router.get("/{study_id}", response_model=StudySummary, summary="Get a study")
async def get_study(
    study_id: uuid.UUID, principal: RequireViewer, conn: TenantConn
) -> StudySummary:
    study = await StudyRepository(conn).get_study(study_id)

    if study is None:
        # RLS already filtered cross-tenant rows out. Answering 403 here would
        # confirm the study exists somewhere, which is itself a disclosure.
        await write_audit(
            conn,
            org_id=principal.org_id,
            actor_id=principal.user_id,
            action="study.read",
            resource_type="study",
            resource_id=study_id,
            outcome="denied",
        )
        raise NotFound("No such study")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="study.read",
        resource_type="study",
        resource_id=study_id,
        outcome="success",
    )
    return study


@router.get(
    "/{study_id}/series",
    response_model=list[SeriesDetail],
    summary="List the series in a study",
)
async def list_series(
    study_id: uuid.UUID, principal: RequireViewer, conn: TenantConn
) -> list[SeriesDetail]:
    repo = StudyRepository(conn)
    if await repo.get_study(study_id) is None:
        raise NotFound("No such study")

    series = await repo.list_series(study_id)
    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="series.list",
        resource_type="study",
        resource_id=study_id,
    )
    return series


@router.delete("/{study_id}", status_code=204, summary="Soft-delete a study")
async def delete_study(study_id: uuid.UUID, principal: RequireAdmin, conn: TenantConn) -> None:
    deleted = await StudyRepository(conn).soft_delete_study(study_id)
    if not deleted:
        raise NotFound("No such study")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="study.delete",
        resource_type="study",
        resource_id=study_id,
        context={"mode": "soft_delete", "erasure_job": "scheduled"},
    )
