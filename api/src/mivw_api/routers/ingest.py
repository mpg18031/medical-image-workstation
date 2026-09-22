"""Ingest sessions.

Uploads go directly to the object store via presigned PUT. A multi-gigabyte
study must never occupy a gateway worker.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, status

from mivw_api.db import write_audit
from mivw_api.problems import NotFound, ValidationFailed
from mivw_api.schemas.job import (
    IngestSession,
    IngestSessionCreate,
    UploadTarget,
)
from mivw_api.security import RequireResearcher
from mivw_api.services.deps import Storage, TenantConn

router = APIRouter(prefix="/ingest", tags=["ingest"])

MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
MAX_SESSION_BYTES = 64 * 1024 * 1024 * 1024


@router.post(
    "/sessions",
    response_model=IngestSession,
    status_code=status.HTTP_201_CREATED,
    summary="Open an upload session",
)
async def create_session(
    payload: IngestSessionCreate,
    principal: RequireResearcher,
    conn: TenantConn,
    storage: Storage,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> IngestSession:
    if payload.total_bytes > MAX_SESSION_BYTES:
        raise ValidationFailed("Session exceeds the maximum permitted size")

    session_id = uuid.uuid4()

    # Object keys come from the session id and an index, never from the
    # client-supplied filename, so traversal is impossible by construction.
    targets = [
        UploadTarget(
            filename=name,
            url=await storage.presign_put(
                f"ingest/{session_id}/{index:06d}", max_bytes=MAX_FILE_BYTES
            ),
            expires_at=storage.expiry(),
            max_bytes=MAX_FILE_BYTES,
        )
        for index, name in enumerate(payload.filenames)
    ]

    await conn.execute(
        """
        INSERT INTO job (id, org_id, kind, status, payload, submitted_by, idempotency_key)
        VALUES ($1, $2, 'ingest', 'queued', $3::jsonb, $4, $5)
        """,
        session_id,
        principal.org_id,
        f'{{"fileCount": {len(payload.filenames)}, "state": "open"}}',
        principal.user_id,
        idempotency_key,
    )

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="ingest.session_open",
        resource_type="job",
        resource_id=session_id,
        context={"file_count": len(payload.filenames)},
    )

    return IngestSession(
        id=session_id,
        status="open",
        targets=targets,
        created_at=datetime.now(UTC),
    )


@router.post(
    "/sessions/{session_id}/complete",
    response_model=IngestSession,
    summary="Signal upload completion and queue processing",
)
async def complete_session(
    session_id: uuid.UUID, principal: RequireResearcher, conn: TenantConn
) -> IngestSession:
    row = await conn.fetchrow(
        "UPDATE job SET status = 'queued', "
        'payload = payload || \'{"state":"processing"}\'::jsonb '
        "WHERE id = $1 AND kind = 'ingest' RETURNING id, created_at",
        session_id,
    )
    if row is None:
        raise NotFound("No such ingest session")

    await write_audit(
        conn,
        org_id=principal.org_id,
        actor_id=principal.user_id,
        action="ingest.session_complete",
        resource_type="job",
        resource_id=session_id,
    )

    return IngestSession(id=row["id"], status="processing", created_at=row["created_at"])


@router.get(
    "/sessions/{session_id}",
    response_model=IngestSession,
    summary="Get ingest session state",
)
async def get_session(
    session_id: uuid.UUID, principal: RequireResearcher, conn: TenantConn
) -> IngestSession:
    row = await conn.fetchrow(
        "SELECT id, status, payload, created_at FROM job WHERE id = $1 AND kind = 'ingest'",
        session_id,
    )
    if row is None:
        raise NotFound("No such ingest session")

    # asyncpg hands jsonb back as text (no decoder codec is registered in
    # create_pool); decode before calling .get() on it.
    raw_payload = row["payload"]
    payload = json.loads(raw_payload) if isinstance(raw_payload, str) else (raw_payload or {})
    return IngestSession(
        id=row["id"],
        status=payload.get("state", "open"),
        accepted=payload.get("accepted", 0),
        rejected=payload.get("rejected", 0),
        quarantined=payload.get("quarantined", 0),
        created_at=row["created_at"],
    )
