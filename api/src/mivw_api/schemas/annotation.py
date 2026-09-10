"""Annotation schemas.

Geometry is always in patient coordinates (millimetres) against an explicit
frame of reference, so an annotation survives resampling and reorientation.
Pixel-index geometry is rejected at this boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from mivw_api.schemas.common import Schema


class AnnotationKind(StrEnum):
    MEASUREMENT = "measurement"
    ROI = "roi"
    NOTE = "note"
    LABEL_EDIT = "label_edit"


Point3 = tuple[float, float, float]


class AnnotationPayload(Schema):
    units: Literal["mm"] = Field(
        default="mm",
        description="Only millimetres are accepted; pixel indices break on resample.",
    )
    points: list[Point3] = Field(default_factory=list, max_length=4096)
    text: str | None = Field(default=None, max_length=4096)
    radius_mm: float | None = Field(default=None, gt=0)
    label_index: int | None = Field(default=None, ge=0)


class AnnotationCreate(Schema):
    kind: AnnotationKind
    payload: AnnotationPayload
    label: str | None = Field(default=None, max_length=128)
    frame_of_reference_uid: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _geometry_matches_kind(self) -> AnnotationCreate:
        required_points = {
            AnnotationKind.MEASUREMENT: 2,
            AnnotationKind.ROI: 3,
        }.get(self.kind)

        if required_points is not None and len(self.payload.points) < required_points:
            raise ValueError(f"{self.kind} requires at least {required_points} points in mm")
        if self.kind is AnnotationKind.NOTE and not self.payload.text:
            raise ValueError("note annotations require text")
        return self


class AnnotationUpdate(Schema):
    payload: AnnotationPayload | None = None
    label: str | None = Field(default=None, max_length=128)


class AnnotationDetail(Schema):
    id: uuid.UUID
    series_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str | None
    kind: AnnotationKind
    payload: AnnotationPayload
    label: str | None
    frame_of_reference_uid: str | None
    created_at: datetime
    updated_at: datetime
