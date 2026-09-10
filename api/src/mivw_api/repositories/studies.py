"""Study and series data access.

Every statement is parameterised. String-built SQL is banned here and the ban
is enforced by ruff's S608 rule plus the injection tests.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Any

import asyncpg  # type: ignore[import-untyped]

from mivw_api.schemas.common import decode_cursor, encode_cursor
from mivw_api.schemas.study import (
    PatientSummary,
    SeriesDetail,
    SeriesGeometry,
    StudyQuery,
    StudySummary,
    VolumeAssetInfo,
)

_LIST_STUDIES = """
SELECT s.id,
       s.study_datetime,
       s.description,
       s.modalities,
       p.id           AS patient_id,
       p.pseudonym,
       p.birth_year,
       p.sex,
       (SELECT count(*) FROM series se WHERE se.study_id = s.id) AS series_count
FROM study s
JOIN patient p ON p.id = s.patient_id
WHERE s.deleted_at IS NULL
  AND ($1::text IS NULL OR $1 = ANY(s.modalities))
  AND ($2::timestamptz IS NULL OR s.study_datetime >= $2)
  AND ($3::timestamptz IS NULL OR s.study_datetime <= $3)
  AND ($4::bytea IS NULL OR p.mrn_hmac = $4)
  AND ($5::timestamptz IS NULL OR (s.study_datetime, s.id) < ($5, $6::uuid))
ORDER BY s.study_datetime DESC, s.id DESC
LIMIT $7
"""

_GET_STUDY = """
SELECT s.id,
       s.study_datetime,
       s.description,
       s.modalities,
       p.id AS patient_id,
       p.pseudonym,
       p.birth_year,
       p.sex,
       (SELECT count(*) FROM series se WHERE se.study_id = s.id) AS series_count
FROM study s
JOIN patient p ON p.id = s.patient_id
WHERE s.id = $1 AND s.deleted_at IS NULL
"""

_LIST_SERIES = """
SELECT se.*, va.id AS volume_asset_id, (va.id IS NOT NULL) AS has_volume
FROM series se
LEFT JOIN volume_asset va ON va.series_id = se.id
WHERE se.study_id = $1
ORDER BY se.series_number NULLS LAST, se.id
"""

_GET_SERIES = """
SELECT se.*, va.id AS volume_asset_id, (va.id IS NOT NULL) AS has_volume
FROM series se
LEFT JOIN volume_asset va ON va.series_id = se.id
WHERE se.id = $1
"""

_GET_VOLUME = """
SELECT id, series_id, dims, spacing_mm, dtype, size_bytes,
       value_min, value_max, object_key, content_sha256
FROM volume_asset
WHERE series_id = $1
"""


class StudyRepository:
    def __init__(self, conn: asyncpg.Connection[asyncpg.Record]) -> None:
        self._conn = conn

    async def list_studies(
        self, query: StudyQuery, *, mrn_hmac: bytes | None
    ) -> tuple[list[StudySummary], str | None]:
        after_datetime: datetime | None = None
        after_id: uuid.UUID | None = None
        if query.after:
            raw_datetime, raw_id = decode_cursor(query.after)
            after_datetime = datetime.fromisoformat(raw_datetime)
            after_id = uuid.UUID(raw_id)

        rows = await self._conn.fetch(
            _LIST_STUDIES,
            query.modality,
            query.from_date,
            query.to_date,
            mrn_hmac,
            after_datetime,
            after_id,
            query.limit + 1,  # one extra row tells us whether a next page exists
        )

        has_more = len(rows) > query.limit
        page = rows[: query.limit]
        studies = [_to_study(row) for row in page]

        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_cursor(last["study_datetime"], last["id"])

        return studies, next_cursor

    async def get_study(self, study_id: uuid.UUID) -> StudySummary | None:
        row = await self._conn.fetchrow(_GET_STUDY, study_id)
        return _to_study(row) if row else None

    async def list_series(self, study_id: uuid.UUID) -> list[SeriesDetail]:
        rows = await self._conn.fetch(_LIST_SERIES, study_id)
        return [_to_series(row) for row in rows]

    async def get_series(self, series_id: uuid.UUID) -> SeriesDetail | None:
        row = await self._conn.fetchrow(_GET_SERIES, series_id)
        return _to_series(row) if row else None

    async def get_volume_asset(
        self, series_id: uuid.UUID
    ) -> tuple[VolumeAssetInfo, str, bytes] | None:
        row = await self._conn.fetchrow(_GET_VOLUME, series_id)
        if row is None:
            return None
        info = VolumeAssetInfo(
            id=row["id"],
            series_id=row["series_id"],
            dims=tuple(row["dims"]),
            spacing_mm=tuple(row["spacing_mm"]),
            dtype=row["dtype"],
            size_bytes=row["size_bytes"],
            value_min=row["value_min"],
            value_max=row["value_max"],
        )
        return info, row["object_key"], row["content_sha256"]

    async def soft_delete_study(self, study_id: uuid.UUID) -> bool:
        result = await self._conn.execute(
            "UPDATE study SET deleted_at = now() WHERE id = $1 AND deleted_at IS NULL",
            study_id,
        )
        return bool(result.endswith(" 1"))


def hash_patient_ref(raw: str, key: bytes) -> bytes:
    """Keyed HMAC of an MRN.

    Deterministic encryption would leak frequency, and searching ciphertext is
    impossible, so equality lookups go through this instead. The raw value is
    never logged or persisted.
    """
    return hmac.new(key, raw.strip().encode(), hashlib.sha256).digest()


def _to_study(row: asyncpg.Record) -> StudySummary:
    return StudySummary(
        id=row["id"],
        patient=PatientSummary(
            id=row["patient_id"],
            pseudonym=row["pseudonym"],
            birth_year=row["birth_year"],
            sex=row["sex"],
        ),
        study_datetime=row["study_datetime"],
        description=row["description"],
        modalities=list(row["modalities"] or []),
        series_count=row["series_count"],
    )


def _to_series(row: asyncpg.Record) -> SeriesDetail:
    def optional_tuple(value: Any) -> tuple[Any, ...] | None:
        return tuple(value) if value else None

    return SeriesDetail(
        id=row["id"],
        study_id=row["study_id"],
        volume_asset_id=row["volume_asset_id"],
        series_number=row["series_number"],
        modality=row["modality"],
        description=row["description"],
        frame_of_reference_uid=row["frame_of_reference_uid"],
        geometry=SeriesGeometry(
            rows=row["rows"],
            columns=row["columns"],
            slice_count=row["slice_count"],
            pixel_spacing_mm=tuple(row["pixel_spacing_mm"]),
            slice_thickness_mm=row["slice_thickness_mm"],
            image_orientation=optional_tuple(row["image_orientation"]),
            image_position=optional_tuple(row["image_position"]),
            rescale_slope=row["rescale_slope"],
            rescale_intercept=row["rescale_intercept"],
        ),
        is_quarantined=row["is_quarantined"],
        has_volume=row["has_volume"],
    )
