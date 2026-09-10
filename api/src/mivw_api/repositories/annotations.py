"""Annotation data access."""

from __future__ import annotations

import json
import uuid

import asyncpg  # type: ignore[import-untyped]

from mivw_api.schemas.annotation import (
    AnnotationCreate,
    AnnotationDetail,
    AnnotationPayload,
)

_INSERT = """
INSERT INTO annotation (org_id, series_id, author_id, kind, payload, label,
                        frame_of_reference_uid)
VALUES ($1, $2, $3, $4::annotation_kind, $5::jsonb, $6, $7)
RETURNING *
"""

_LIST = """
SELECT a.*, u.display_name AS author_name
FROM annotation a
LEFT JOIN app_user u ON u.id = a.author_id
WHERE a.series_id = $1 AND a.deleted_at IS NULL
ORDER BY a.created_at
"""

_GET = """
SELECT a.*, u.display_name AS author_name
FROM annotation a
LEFT JOIN app_user u ON u.id = a.author_id
WHERE a.id = $1 AND a.deleted_at IS NULL
"""

_UPDATE = """
UPDATE annotation
SET payload = COALESCE($2::jsonb, payload),
    label   = COALESCE($3, label)
WHERE id = $1 AND deleted_at IS NULL
RETURNING *
"""

# Soft delete: an annotation is clinical reasoning, and the audit trail must be
# able to show what was recorded and when it was withdrawn.
_DELETE = "UPDATE annotation SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL"


class AnnotationRepository:
    def __init__(self, conn: asyncpg.Connection[asyncpg.Record]) -> None:
        self._conn = conn

    async def create(
        self,
        org_id: uuid.UUID,
        series_id: uuid.UUID,
        author_id: uuid.UUID,
        payload: AnnotationCreate,
    ) -> AnnotationDetail:
        row = await self._conn.fetchrow(
            _INSERT,
            org_id,
            series_id,
            author_id,
            payload.kind.value,
            payload.payload.model_dump_json(by_alias=True),
            payload.label,
            payload.frame_of_reference_uid,
        )
        assert row is not None
        return _to_annotation(row)

    async def list_for_series(self, series_id: uuid.UUID) -> list[AnnotationDetail]:
        rows = await self._conn.fetch(_LIST, series_id)
        return [_to_annotation(row) for row in rows]

    async def get(self, annotation_id: uuid.UUID) -> AnnotationDetail | None:
        row = await self._conn.fetchrow(_GET, annotation_id)
        return _to_annotation(row) if row else None

    async def update(
        self,
        annotation_id: uuid.UUID,
        *,
        payload: AnnotationPayload | None,
        label: str | None,
    ) -> AnnotationDetail | None:
        row = await self._conn.fetchrow(
            _UPDATE,
            annotation_id,
            payload.model_dump_json(by_alias=True) if payload else None,
            label,
        )
        return _to_annotation(row) if row else None

    async def soft_delete(self, annotation_id: uuid.UUID) -> bool:
        result = await self._conn.execute(_DELETE, annotation_id)
        return bool(result.endswith(" 1"))


def _to_annotation(row: asyncpg.Record) -> AnnotationDetail:
    raw = row["payload"]
    payload = json.loads(raw) if isinstance(raw, str) else raw

    return AnnotationDetail(
        id=row["id"],
        series_id=row["series_id"],
        author_id=row["author_id"],
        author_name=row.get("author_name") if hasattr(row, "get") else None,
        kind=row["kind"],
        payload=AnnotationPayload.model_validate(payload),
        label=row["label"],
        frame_of_reference_uid=row["frame_of_reference_uid"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
