"""Ingest, job and render-session schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from mivw_api.schemas.common import Schema, Sha256Hex


class JobKind(StrEnum):
    INGEST = "ingest"
    INFERENCE = "inference"
    EXPORT = "export"
    ERASURE = "erasure"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Schema):
    id: uuid.UUID
    kind: JobKind
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    stage: str | None
    created_at: datetime
    finished_at: datetime | None
    error: dict[str, object] | None


class UploadTarget(Schema):
    filename: str
    url: str
    expires_at: datetime
    max_bytes: int


class IngestSessionCreate(Schema):
    filenames: list[str] = Field(min_length=1, max_length=10_000)
    total_bytes: int = Field(gt=0)


class IngestSession(Schema):
    id: uuid.UUID
    status: Literal["open", "uploading", "processing", "completed", "failed"]
    # Uploads bypass the gateway entirely; a multi-gigabyte study must never
    # occupy an API worker.
    targets: list[UploadTarget] = Field(default_factory=list)
    accepted: int = 0
    rejected: int = 0
    quarantined: int = 0
    created_at: datetime


class IngestFileResult(Schema):
    filename: str
    status: Literal["accepted", "rejected", "quarantined"]
    reason: str | None = None
    series_id: uuid.UUID | None = None
    content_sha256: Sha256Hex | None = None


class RenderSessionCreate(Schema):
    series_id: uuid.UUID
    inference_run_id: uuid.UUID | None = None
    width: int = Field(default=1024, ge=64, le=4096)
    height: int = Field(default=1024, ge=64, le=4096)


class RenderSession(Schema):
    id: uuid.UUID
    token: str
    series_id: uuid.UUID
    websocket_path: str
    expires_at: datetime
    gpu_memory_bytes: int
