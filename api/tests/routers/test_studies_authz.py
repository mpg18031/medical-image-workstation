"""Authorisation tests.

These matter most in this codebase: a regression here is a PHI disclosure,
not a broken feature.
"""

from __future__ import annotations

import pytest

from tests.conftest import ALL_PROTECTED_PATHS, SeededOrgs

pytestmark = pytest.mark.asyncio

MALFORMED_MODEL_SPECS = [
    {"name": "m", "version": "1", "artifactKey": "k", "artifactSha256": "short"},
    {"name": "m", "version": "1", "artifactKey": "k", "inputSpec": {}},
    {"name": "", "version": "1", "artifactKey": "k"},
    {"name": "m", "version": "1", "artifactKey": "../../etc/passwd"},
    {"name": "m", "version": "1", "artifactKey": "k", "outputKind": "arbitrary_code"},
]

SQL_METACHARACTERS = [
    "'; DROP TABLE study; --",
    "' OR '1'='1",
    "\\'; SELECT pg_sleep(5); --",
    "%' UNION SELECT mrn_enc FROM patient --",
    "'; SET ROLE postgres; --",
]


async def test_study_from_other_org_returns_404_not_403(
    client, token_factory, seeded_orgs: SeededOrgs
):
    """Existence must not leak.

    RLS filters the row out. Answering 403 would confirm the study exists in
    some other tenant, which is itself a disclosure.
    """
    token = token_factory(org_id=seeded_orgs.a, role="viewer")
    resp = await client.get(
        f"/api/v1/studies/{seeded_orgs.b_study_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404
    body = resp.text.lower()
    assert "forbidden" not in body
    assert "org" not in body


async def test_viewer_sees_only_own_tenant_in_worklist(
    client, viewer_token, seeded_orgs: SeededOrgs
):
    resp = await client.get("/api/v1/studies", headers={"Authorization": f"Bearer {viewer_token}"})
    assert resp.status_code == 200
    returned = {item["id"] for item in resp.json()["items"]}
    assert str(seeded_orgs.a_study_id) in returned
    assert str(seeded_orgs.b_study_id) not in returned


@pytest.mark.parametrize("path", ALL_PROTECTED_PATHS)
async def test_every_endpoint_rejects_anonymous(client, path):
    resp = await client.get(path)
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "kind",
    ["expired", "wrong_audience", "wrong_issuer", "alg_none", "future_nbf", "garbage"],
)
async def test_malformed_tokens_are_rejected(client, malformed_tokens, kind):
    resp = await client.get(
        "/api/v1/studies",
        headers={"Authorization": f"Bearer {malformed_tokens[kind]}"},
    )
    assert resp.status_code == 401, f"{kind} token was accepted"


async def test_viewer_cannot_create_annotation(client, viewer_token, seeded_orgs: SeededOrgs):
    resp = await client.post(
        f"/api/v1/series/{seeded_orgs.a_series_id}/annotations",
        json={
            "kind": "measurement",
            "payload": {"units": "mm", "points": [[0, 0, 0], [10, 0, 0]]},
        },
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


async def test_non_admin_cannot_register_a_model(client, viewer_token):
    resp = await client.post(
        "/api/v1/models",
        json={"name": "m", "version": "1", "artifactKey": "k"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.parametrize("payload", MALFORMED_MODEL_SPECS)
async def test_model_registration_rejects_bad_spec(client, admin_token, payload):
    resp = await client.post(
        "/api/v1/models",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("probe", SQL_METACHARACTERS)
async def test_sql_metacharacters_are_inert(client, viewer_token, probe):
    """Parameterisation proof: hostile input is data, never syntax."""
    resp = await client.get(
        "/api/v1/studies",
        params={"patientRef": probe},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code in (200, 422)
    lowered = resp.text.lower()
    assert "syntax error" not in lowered
    assert "pg_" not in lowered
    assert "asyncpg" not in lowered


async def test_annotation_geometry_must_be_in_millimetres(
    client, token_factory, seeded_orgs: SeededOrgs
):
    """Pixel-index geometry would silently break after any resample."""
    token = token_factory(org_id=seeded_orgs.a, role="annotator")
    resp = await client.post(
        f"/api/v1/series/{seeded_orgs.a_series_id}/annotations",
        json={"kind": "measurement", "payload": {"units": "px", "points": [[0, 0, 0]]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_error_bodies_never_contain_phi(client, viewer_token, seeded_orgs: SeededOrgs):
    resp = await client.get(
        "/api/v1/studies/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    lowered = resp.text.lower()
    for marker in ("mrn", "birth", "patient_name", seeded_orgs.a_patient_mrn.lower()):
        assert marker not in lowered


async def test_phi_never_reaches_logs(client, viewer_token, seeded_orgs: SeededOrgs, caplog):
    await client.get(
        "/api/v1/studies",
        params={"patientRef": seeded_orgs.a_patient_mrn},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert seeded_orgs.a_patient_mrn not in caplog.text


async def test_phi_read_is_audited(client, viewer_token, seeded_orgs: SeededOrgs, db):
    await client.get(
        f"/api/v1/studies/{seeded_orgs.a_study_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    count = await db.fetchval(
        "SELECT count(*) FROM audit_log WHERE action = 'study.read' AND resource_id = $1",
        seeded_orgs.a_study_id,
    )
    assert count == 1


async def test_denied_access_is_also_audited(client, viewer_token, seeded_orgs: SeededOrgs, db):
    """A denial is exactly the event a reviewer needs to see."""
    await client.get(
        f"/api/v1/studies/{seeded_orgs.b_study_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    count = await db.fetchval(
        "SELECT count(*) FROM audit_log WHERE outcome = 'denied' AND resource_id = $1",
        seeded_orgs.b_study_id,
    )
    assert count == 1
