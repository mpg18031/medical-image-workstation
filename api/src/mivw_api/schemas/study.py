"""Study, series and volume schemas.

No direct identifier is ever exposed. The worklist shows a pseudonym; the raw
MRN exists only as ciphertext and a keyed HMAC in the database.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from mivw_api.schemas.common import Schema


class PatientSummary(Schema):
    id: uuid.UUID
    pseudonym: str
    birth_year: int | None = None
    sex: Literal["M", "F", "O", "U"] | None = None


class StudySummary(Schema):
    id: uuid.UUID
    patient: PatientSummary
    study_datetime: datetime | None
    description: str | None
    modalities: list[str]
    series_count: int


class SeriesGeometry(Schema):
    rows: int = Field(gt=0)
    columns: int = Field(gt=0)
    slice_count: int = Field(gt=0)
    pixel_spacing_mm: tuple[float, float]
    slice_thickness_mm: float | None
    image_orientation: tuple[float, float, float, float, float, float] | None
    image_position: tuple[float, float, float] | None
    rescale_slope: float = 1.0
    rescale_intercept: float = 0.0


class SeriesDetail(Schema):
    id: uuid.UUID
    study_id: uuid.UUID
    volume_asset_id: uuid.UUID | None = None
    series_number: int | None
    modality: str
    description: str | None
    frame_of_reference_uid: str | None
    geometry: SeriesGeometry
    is_quarantined: bool
    has_volume: bool


class VolumeAssetInfo(Schema):
    id: uuid.UUID
    series_id: uuid.UUID
    dims: tuple[int, int, int]
    spacing_mm: tuple[float, float, float]
    dtype: Literal["int16", "uint16", "float32"]
    size_bytes: int
    value_min: float | None
    value_max: float | None


class PresignedDownload(Schema):
    url: str
    expires_at: datetime
    content_sha256: str


class StudyQuery(Schema):
    modality: str | None = Field(default=None, max_length=16)
    from_date: datetime | None = None
    to_date: datetime | None = None
    # HMAC'd by the gateway before it reaches SQL; never logged.
    patient_ref: Annotated[str | None, Field(default=None, max_length=128)] = None
    limit: int = Field(default=50, ge=1, le=200)
    after: str | None = None
