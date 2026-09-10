"""Model registry data access."""

from __future__ import annotations

import uuid

import asyncpg  # type: ignore[import-untyped]

from mivw_api.schemas.model import InputSpec, LabelInfo, ModelCreate, ModelDetail

_INSERT = """
INSERT INTO model (org_id, name, version, artifact_key, artifact_sha256,
                   output_kind, input_spec, label_map, description, created_by)
VALUES ($1, $2, $3, $4, $5, $6::model_output_kind, $7::jsonb, $8::jsonb, $9, $10)
RETURNING *
"""

_LIST = """
SELECT * FROM model
WHERE ($1::boolean IS NULL OR is_enabled = $1)
ORDER BY name, version DESC
"""

_GET = "SELECT * FROM model WHERE id = $1"

_UPDATE = """
UPDATE model
SET description = COALESCE($2, description),
    is_enabled  = COALESCE($3, is_enabled)
WHERE id = $1
RETURNING *
"""

_MARK_VALIDATED = """
UPDATE model SET validated_at = now() WHERE id = $1 RETURNING *
"""


class ModelRepository:
    def __init__(self, conn: asyncpg.Connection[asyncpg.Record]) -> None:
        self._conn = conn

    async def create(
        self, org_id: uuid.UUID, payload: ModelCreate, created_by: uuid.UUID
    ) -> ModelDetail:
        row = await self._conn.fetchrow(
            _INSERT,
            org_id,
            payload.name,
            payload.version,
            payload.artifact_key,
            bytes.fromhex(payload.artifact_sha256),
            payload.output_kind.value,
            payload.input_spec.model_dump_json(by_alias=True),
            _dump_labels(payload.label_map),
            payload.description,
            created_by,
        )
        assert row is not None
        return _to_model(row)

    async def list(self, *, enabled_only: bool | None = None) -> list[ModelDetail]:
        rows = await self._conn.fetch(_LIST, enabled_only)
        return [_to_model(row) for row in rows]

    async def get(self, model_id: uuid.UUID) -> ModelDetail | None:
        row = await self._conn.fetchrow(_GET, model_id)
        return _to_model(row) if row else None

    async def update(
        self, model_id: uuid.UUID, *, description: str | None, is_enabled: bool | None
    ) -> ModelDetail | None:
        row = await self._conn.fetchrow(_UPDATE, model_id, description, is_enabled)
        return _to_model(row) if row else None

    async def mark_validated(self, model_id: uuid.UUID) -> ModelDetail | None:
        row = await self._conn.fetchrow(_MARK_VALIDATED, model_id)
        return _to_model(row) if row else None


def _dump_labels(labels: dict[str, LabelInfo]) -> str:
    import json

    return json.dumps({key: value.model_dump(by_alias=True) for key, value in labels.items()})


def _to_model(row: asyncpg.Record) -> ModelDetail:
    import json

    raw_spec = row["input_spec"]
    spec = json.loads(raw_spec) if isinstance(raw_spec, str) else raw_spec

    raw_labels = row["label_map"]
    labels = json.loads(raw_labels) if isinstance(raw_labels, str) else raw_labels

    return ModelDetail(
        id=row["id"],
        name=row["name"],
        version=row["version"],
        artifact_key=row["artifact_key"],
        artifact_sha256=bytes(row["artifact_sha256"]).hex(),
        output_kind=row["output_kind"],
        input_spec=InputSpec.model_validate(spec),
        label_map={k: LabelInfo.model_validate(v) for k, v in (labels or {}).items()},
        description=row["description"],
        is_enabled=row["is_enabled"],
        validated_at=row["validated_at"],
        created_at=row["created_at"],
    )
