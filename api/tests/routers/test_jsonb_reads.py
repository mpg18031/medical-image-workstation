"""Reads of jsonb columns, against a real PostgreSQL.

asyncpg has no json/jsonb decoder registered (see create_pool in mivw_api.db),
so every jsonb column arrives as text. A fake connection returning dicts would
hide the resulting validation errors, which is why these seed rows and go
through the full HTTP stack instead.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import SeededOrgs

pytestmark = pytest.mark.asyncio

LABEL_STATS = '{"1": {"voxelCount": 607896.0, "volumeMl": 607.896}}'


async def _seed_completed_run(
    db, org_id: uuid.UUID, series_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a model, volume and a finished run with its segmentation.

    Returns (model_id, run_id). The caller must delete both, inference_run
    first: it references the model with ON DELETE RESTRICT, while the volume
    and segmentation rows cascade away with `series` in seeded_orgs' teardown.
    """
    model_id, run_id, volume_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO model (id, org_id, name, version, artifact_key, artifact_sha256,
                               output_kind, input_spec, label_map)
            VALUES ($1, $2, 'jsonb-read-test', '1', 'models/jsonb-read-test.onnx', $3,
                    'segmentation', $4::jsonb, $5::jsonb)
            """,
            model_id,
            org_id,
            bytes(32),
            '{"shape": [1, 128, 256, 256], "spacingMm": [1.0, 0.7, 0.7], "orientation": "RAS"}',
            '{"1": {"name": "Lesion", "color": "#ff0000"}}',
        )
        await db.execute(
            """
            INSERT INTO volume_asset (id, org_id, series_id, object_key, content_sha256,
                                      size_bytes, dims, spacing_mm, origin_mm, direction, dtype)
            VALUES ($1, $2, $3, 'volumes/jsonb-read-test.bin', $4, 16777216,
                    ARRAY[128, 256, 256], $5, $6, $7, 'int16')
            """,
            volume_id,
            org_id,
            series_id,
            bytes(32),
            [1.0, 0.7, 0.7],
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        )
        await db.execute(
            """
            INSERT INTO inference_run (id, org_id, model_id, volume_asset_id,
                                       input_sha256, model_sha256, status, metrics)
            VALUES ($1, $2, $3, $4, $5, $5, 'succeeded', '{"inferenceMs": 42.5}'::jsonb)
            """,
            run_id,
            org_id,
            model_id,
            volume_id,
            bytes(32),
        )
        await db.execute(
            """
            INSERT INTO segmentation (org_id, inference_run_id, object_key,
                                      content_sha256, dims, label_stats)
            VALUES ($1, $2, 'segmentations/jsonb-read-test.bin', $3,
                    ARRAY[128, 256, 256], $4::jsonb)
            """,
            org_id,
            run_id,
            bytes(32),
            LABEL_STATS,
        )
    return model_id, run_id


async def test_inference_run_and_segmentation_reads_decode_jsonb(
    client, viewer_token, seeded_orgs: SeededOrgs, db
):
    model_id, run_id = await _seed_completed_run(db, seeded_orgs.a, seeded_orgs.a_series_id)
    headers = {"Authorization": f"Bearer {viewer_token}"}
    try:
        resp = await client.get(f"/api/v1/inference-runs/{run_id}", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["metrics"] == {"inferenceMs": 42.5}

        resp = await client.get(f"/api/v1/inference-runs/{run_id}/segmentation", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["inferenceRunId"] == str(run_id)
        assert body["dims"] == [128, 256, 256]
        assert body["download"] == "segmentations/jsonb-read-test.bin"
        assert body["labelStats"] == {"1": {"voxelCount": 607896.0, "volumeMl": 607.896}}
    finally:
        await db.execute("DELETE FROM inference_run WHERE id = $1", run_id)
        await db.execute("DELETE FROM model WHERE id = $1", model_id)


async def test_ingest_session_read_decodes_payload(client, db, token_factory, seeded_orgs):
    session_id = uuid.uuid4()
    async with db.transaction():
        await db.execute(
            """
            INSERT INTO job (id, org_id, kind, status, payload)
            VALUES ($1, $2, 'ingest', 'queued',
                    '{"state": "processing", "accepted": 3, "rejected": 1}'::jsonb)
            """,
            session_id,
            seeded_orgs.a,
        )
    token = token_factory(org_id=seeded_orgs.a, role="researcher")
    try:
        resp = await client.get(
            f"/api/v1/ingest/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "processing"
        assert body["accepted"] == 3
        assert body["rejected"] == 1
    finally:
        await db.execute("DELETE FROM job WHERE id = $1", session_id)
