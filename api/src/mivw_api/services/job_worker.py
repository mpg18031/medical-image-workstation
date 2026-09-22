"""Background worker that claims and executes queued jobs.

Runs inside the API process; there is no separate worker deployment yet. A job
must always resolve to `succeeded` or `failed` - never sit at `queued`/
`running` forever - so every failure mode here is caught and written back to
the `job` row rather than left to time out client-side.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any

import asyncpg  # type: ignore[import-untyped]
import structlog

from mivw_api.db import system_transaction, tenant_transaction
from mivw_api.repositories import ModelRepository
from mivw_api.schemas.job import Job, JobKind, JobStatus
from mivw_api.security.principal import Principal, Role
from mivw_api.services.core_runtime import CoreRuntime
from mivw_api.storage import ObjectStore

log = structlog.get_logger(__name__)

POLL_INTERVAL_S = 2.0

# Every statement below spells the `job` projection out in full instead of
# interpolating a shared column list: ruff S608 / bandit B608 reject SQL built
# from Python strings even when the fragment is a constant, and the project
# policy is to never suppress S608.


class JobWorker:
    """Polls the `job` table across tenants and runs queued inference jobs."""

    def __init__(
        self,
        pool: asyncpg.Pool[asyncpg.Record],
        core: CoreRuntime,
        storage: ObjectStore,
    ) -> None:
        self._pool = pool
        self._core = core
        self._storage = storage
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="job-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _loop(self) -> None:
        while True:
            try:
                claimed = await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("job_worker.tick_failed")
                claimed = False
            if not claimed:
                await asyncio.sleep(POLL_INTERVAL_S)

    async def _list_org_ids(self) -> list[uuid.UUID]:
        # `organisation` carries no RLS (it is the tenant boundary itself), so
        # a context-free transaction can enumerate it.
        async with system_transaction(self._pool) as conn:
            rows = await conn.fetch("SELECT id FROM organisation")
        return [row["id"] for row in rows]

    async def _poll_once(self) -> bool:
        for org_id in await self._list_org_ids():
            # Subject must be per-org: `app_user.subject` is globally unique,
            # so a shared subject across orgs would resolve every org's worker
            # identity to whichever org claimed it first.
            principal = Principal(
                user_id=uuid.uuid4(),
                org_id=org_id,
                subject=f"system:job-worker:{org_id}",
                role=Role.ADMIN,
            )
            claim = await self._claim_job(principal)
            if claim is None:
                continue
            job_id, payload = claim
            await self._execute(principal, job_id, payload)
            return True
        return False

    async def _claim_job(self, principal: Principal) -> tuple[uuid.UUID, dict[str, Any]] | None:
        async with tenant_transaction(self._pool, principal) as conn:
            claimed = await conn.fetchrow(
                """
                SELECT id, payload FROM job
                WHERE kind = 'inference' AND status = 'queued'
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            if claimed is None:
                return None

            row = await conn.fetchrow(
                """
                UPDATE job
                SET status = 'running', stage = 'loading', claimed_at = now(),
                    attempts = attempts + 1
                WHERE id = $1
                RETURNING id, kind, status, progress, stage, created_at, finished_at, error
                """,
                claimed["id"],
            )
            await conn.execute(
                "UPDATE inference_run SET status = 'running', started_at = now() WHERE id = $1",
                claimed["id"],
            )

        assert row is not None
        await self._publish(principal.org_id, row)
        raw_payload = claimed["payload"]
        payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        return claimed["id"], payload

    async def _execute(
        self, principal: Principal, job_id: uuid.UUID, payload: dict[str, Any]
    ) -> None:
        try:
            model_id = uuid.UUID(str(payload["modelId"]))
            volume_asset_id = uuid.UUID(str(payload["volumeAssetId"]))

            async with tenant_transaction(self._pool, principal) as conn:
                model = await ModelRepository(conn).get(model_id)
                asset = await conn.fetchrow(
                    "SELECT dims, spacing_mm, object_key, content_sha256 "
                    "FROM volume_asset WHERE id = $1",
                    volume_asset_id,
                )
            if model is None or asset is None:
                raise LookupError("model or volume asset no longer exists")

            artifact = await self._storage.get_object(
                model.artifact_key, expected_sha256=bytes.fromhex(model.artifact_sha256)
            )
            raw_volume = await self._storage.get_object(
                asset["object_key"], expected_sha256=bytes(asset["content_sha256"])
            )

            await self._update_progress(principal, job_id, stage="running", progress=0.3)

            segmentation, provenance, label_stats = await self._core.run_inference(
                model=model,
                artifact=artifact,
                raw_volume=raw_volume,
                dims=tuple(asset["dims"]),
                spacing_mm=tuple(asset["spacing_mm"]),
            )

            await self._update_progress(principal, job_id, stage="saving", progress=0.9)

            object_key = f"segmentations/{job_id.hex}.bin"
            content_sha256 = await self._storage.put_object(object_key, segmentation)

            async with tenant_transaction(self._pool, principal) as conn:
                await conn.execute(
                    """
                    INSERT INTO segmentation
                        (org_id, inference_run_id, object_key, content_sha256, dims, label_stats)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    """,
                    principal.org_id,
                    job_id,
                    object_key,
                    content_sha256,
                    list(asset["dims"]),
                    json.dumps(label_stats),
                )
                await conn.execute(
                    """
                    UPDATE inference_run
                    SET status = 'succeeded', finished_at = now(),
                        engine_cache_key = $2, gpu_name = $3,
                        driver_version = $4, runtime_version = $5
                    WHERE id = $1
                    """,
                    job_id,
                    provenance.get("engine_cache_key"),
                    provenance.get("gpu_name"),
                    provenance.get("driver_version"),
                    provenance.get("runtime_version"),
                )
                row = await conn.fetchrow(
                    """
                    UPDATE job
                    SET status = 'succeeded', progress = 1, stage = 'done', finished_at = now()
                    WHERE id = $1
                    RETURNING id, kind, status, progress, stage, created_at, finished_at, error
                    """,
                    job_id,
                )
            assert row is not None
            await self._publish(principal.org_id, row)
        except Exception as exc:
            log.warning("job_worker.job_failed", job_id=str(job_id), error=str(exc))
            await self._fail_job(principal, job_id, exc)

    async def _update_progress(
        self, principal: Principal, job_id: uuid.UUID, *, stage: str, progress: float
    ) -> None:
        async with tenant_transaction(self._pool, principal) as conn:
            row = await conn.fetchrow(
                "UPDATE job SET stage = $2, progress = $3 WHERE id = $1 "
                "RETURNING id, kind, status, progress, stage, created_at, finished_at, error",
                job_id,
                stage,
                progress,
            )
        assert row is not None
        await self._publish(principal.org_id, row)

    async def _fail_job(self, principal: Principal, job_id: uuid.UUID, exc: Exception) -> None:
        error = {"message": str(exc), "type": type(exc).__name__}
        async with tenant_transaction(self._pool, principal) as conn:
            row = await conn.fetchrow(
                """
                UPDATE job
                SET status = 'failed', error = $2::jsonb, finished_at = now()
                WHERE id = $1
                RETURNING id, kind, status, progress, stage, created_at, finished_at, error
                """,
                job_id,
                json.dumps(error),
            )
            await conn.execute(
                "UPDATE inference_run SET status = 'failed', error = $2::jsonb, "
                "finished_at = now() WHERE id = $1",
                job_id,
                json.dumps(error),
            )
        if row is not None:
            await self._publish(principal.org_id, row)

    async def _publish(self, org_id: uuid.UUID, row: asyncpg.Record) -> None:
        from mivw_api.ws.jobs_ws import broadcaster

        error = row["error"]
        job = Job(
            id=row["id"],
            kind=JobKind(row["kind"]),
            status=JobStatus(row["status"]),
            progress=row["progress"],
            stage=row["stage"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            error=json.loads(error) if isinstance(error, str) else error,
        )
        await broadcaster.publish(org_id, job.model_dump(mode="json", by_alias=True))
