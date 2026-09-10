"""Model registry and inference schemas.

The input specification is a contract, not a hint: a volume that violates it is
rejected rather than resampled. See ADR 0005.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from mivw_api.schemas.common import ObjectKey, Schema, Sha256Hex


class OutputKind(StrEnum):
    SEGMENTATION = "segmentation"
    CLASSIFICATION = "classification"
    HEATMAP = "heatmap"
    LANDMARKS = "landmarks"


class Normalisation(Schema):
    kind: Literal["none", "zscore", "minmax"] = "zscore"
    clip_hu: tuple[float, float] | None = None

    @model_validator(mode="after")
    def _ordered_clip(self) -> Normalisation:
        if self.clip_hu and self.clip_hu[0] >= self.clip_hu[1]:
            raise ValueError("clipHu must be ordered [low, high]")
        return self


class InputSpec(Schema):
    shape: list[int] = Field(min_length=3, max_length=5)
    spacing_mm: tuple[float, float, float]
    orientation: Literal["RAS", "LPS", "RAI"] = "RAS"
    normalisation: Normalisation = Field(default_factory=Normalisation)
    spacing_tolerance_mm: float = Field(default=0.01, ge=0.0, le=1.0)

    @field_validator("shape")
    @classmethod
    def _positive_dims(cls, value: list[int]) -> list[int]:
        if any(dim <= 0 for dim in value):
            raise ValueError("every shape dimension must be positive")
        return value

    @field_validator("spacing_mm")
    @classmethod
    def _positive_spacing(cls, value: tuple[float, float, float]) -> tuple[float, float, float]:
        if any(s <= 0 for s in value):
            raise ValueError("every spacing component must be positive")
        return value


class LabelInfo(Schema):
    name: str = Field(min_length=1, max_length=64)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class ModelCreate(Schema):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(min_length=1, max_length=32)
    artifact_key: ObjectKey
    artifact_sha256: Sha256Hex
    output_kind: OutputKind
    input_spec: InputSpec
    label_map: dict[str, LabelInfo] = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=1024)

    @model_validator(mode="after")
    def _segmentation_needs_labels(self) -> ModelCreate:
        if self.output_kind is OutputKind.SEGMENTATION and not self.label_map:
            raise ValueError("segmentation models must declare a labelMap")
        return self


class ModelUpdate(Schema):
    description: str | None = Field(default=None, max_length=1024)
    is_enabled: bool | None = None


class ModelDetail(Schema):
    id: uuid.UUID
    name: str
    version: str
    artifact_key: str
    artifact_sha256: str
    output_kind: OutputKind
    input_spec: InputSpec
    label_map: dict[str, LabelInfo]
    description: str | None
    is_enabled: bool
    validated_at: datetime | None
    created_at: datetime


class ValidationReport(Schema):
    ok: bool
    loaded: bool
    digest_verified: bool
    dry_run_passed: bool
    messages: list[str] = Field(default_factory=list)


class InferenceRequest(Schema):
    model_id: uuid.UUID
    volume_asset_id: uuid.UUID


class RunProvenance(Schema):
    """Everything needed to reproduce or defend a result."""

    model_sha256: str
    input_sha256: str
    engine_cache_key: str | None
    gpu_name: str | None
    driver_version: str | None
    runtime_version: str | None


class InferenceRun(Schema):
    id: uuid.UUID
    model_id: uuid.UUID
    volume_asset_id: uuid.UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    started_at: datetime | None
    finished_at: datetime | None
    provenance: RunProvenance | None
    metrics: dict[str, float] = Field(default_factory=dict)


class SegmentationResult(Schema):
    id: uuid.UUID
    inference_run_id: uuid.UUID
    dims: tuple[int, int, int]
    label_stats: dict[str, dict[str, float]]
    download: str
