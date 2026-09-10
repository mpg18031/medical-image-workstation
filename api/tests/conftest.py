"""Shared test fixtures.

The whole suite runs against an ephemeral PostgreSQL seeded by the real
migrations, so the migration path itself is exercised on every run.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import asyncpg
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jwt.algorithms import RSAAlgorithm
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((REPO_ROOT / "db" / "migrations").glob("*.sql"))

AUDIENCE = "mivw-workstation"
TEST_KID = "test-signing-key-1"

ALL_PROTECTED_PATHS = [
    "/api/v1/studies",
    "/api/v1/studies/00000000-0000-0000-0000-000000000001",
    "/api/v1/series/00000000-0000-0000-0000-000000000001",
    "/api/v1/series/00000000-0000-0000-0000-000000000001/annotations",
    "/api/v1/models",
    "/api/v1/inference-runs/00000000-0000-0000-0000-000000000001",
    "/api/v1/ingest/sessions/00000000-0000-0000-0000-000000000001",
]


# ---------------------------------------------------------------- signing keys
@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _OidcRequestHandler(BaseHTTPRequestHandler):
    """Serves OIDC discovery + JWKS documents backed by `signing_key`.

    A real HTTP server, not a mock, so token verification exercises the same
    httpx/PyJWKClient code paths it does in production.
    """

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # Silence the default per-request access log.

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.endswith("/.well-known/openid-configuration"):
            body = json.dumps(
                {
                    "issuer": self.server.issuer,  # type: ignore[attr-defined]
                    "jwks_uri": f"{self.server.issuer}/protocol/openid-connect/certs",  # type: ignore[attr-defined]
                }
            ).encode()
        elif self.path.endswith("/protocol/openid-connect/certs"):
            jwk = json.loads(
                RSAAlgorithm.to_jwk(self.server.signing_key.public_key())  # type: ignore[attr-defined]
            )
            jwk.update({"kid": TEST_KID, "use": "sig", "alg": "RS256"})
            body = json.dumps({"keys": [jwk]}).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="session")
def oidc_issuer(signing_key: rsa.RSAPrivateKey) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OidcRequestHandler)
    port = server.server_address[1]
    issuer = f"http://127.0.0.1:{port}/realms/mivw"
    server.issuer = issuer  # type: ignore[attr-defined]
    server.signing_key = signing_key  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield issuer
    finally:
        server.shutdown()
        thread.join()


def _encode(key: rsa.RSAPrivateKey, claims: dict[str, object], **kwargs: object) -> str:
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": TEST_KID}, **kwargs)  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def token_factory(signing_key: rsa.RSAPrivateKey, oidc_issuer: str):
    def issue(
        *,
        org_id: uuid.UUID,
        role: str = "viewer",
        user_id: uuid.UUID | None = None,
        expires_in: timedelta = timedelta(minutes=10),
        issuer: str = oidc_issuer,
        audience: str = AUDIENCE,
    ) -> str:
        now = datetime.now(UTC)
        return _encode(
            signing_key,
            {
                "sub": str(user_id or uuid.uuid4()),
                "iss": issuer,
                "aud": audience,
                "iat": now,
                "nbf": now,
                "exp": now + expires_in,
                "org_id": str(org_id),
                "role": role,
            },
        )

    return issue


@pytest.fixture
def malformed_tokens(signing_key: rsa.RSAPrivateKey, oidc_issuer: str, seeded_orgs: SeededOrgs):
    """Every token an attacker would realistically try."""
    now = datetime.now(UTC)
    base = {
        "sub": str(uuid.uuid4()),
        "iss": oidc_issuer,
        "aud": AUDIENCE,
        "iat": now,
        "org_id": str(seeded_orgs.a),
        "role": "admin",
    }
    return {
        "expired": _encode(signing_key, {**base, "exp": now - timedelta(minutes=1)}),
        "wrong_audience": _encode(
            signing_key, {**base, "aud": "some-other-app", "exp": now + timedelta(minutes=5)}
        ),
        "wrong_issuer": _encode(
            signing_key, {**base, "iss": "https://evil.local", "exp": now + timedelta(minutes=5)}
        ),
        "alg_none": jwt.encode({**base, "exp": now + timedelta(minutes=5)}, "", algorithm="none"),
        "future_nbf": _encode(
            signing_key,
            {**base, "nbf": now + timedelta(hours=1), "exp": now + timedelta(hours=2)},
        ),
        "garbage": "not.a.jwt",
    }


# ---------------------------------------------------------------- database
@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver=None) as container:
        yield container


@pytest.fixture(scope="session")
def migrated_dsn(postgres: PostgresContainer) -> str:
    dsn = postgres.get_connection_url()
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "migrate.py"), "apply"],
        check=True,
        env={"MIVW_DB_DSN": dsn, "PATH": "/usr/bin:/bin"},
    )
    return dsn


@pytest.fixture
async def db(migrated_dsn: str) -> AsyncIterator[asyncpg.Connection]:
    conn = await asyncpg.connect(migrated_dsn)
    try:
        yield conn
    finally:
        await conn.close()


# ---------------------------------------------------------------- fixtures data
@dataclass(frozen=True)
class SeededOrgs:
    a: uuid.UUID
    b: uuid.UUID
    a_user_id: uuid.UUID
    a_study_id: uuid.UUID
    a_series_id: uuid.UUID
    b_study_id: uuid.UUID
    a_patient_mrn: str


@pytest.fixture
async def seeded_orgs(db: asyncpg.Connection) -> AsyncIterator[SeededOrgs]:
    """Two tenants with imaging data, used to prove cross-tenant isolation.

    All identifiers are fabricated. No real patient data exists anywhere in
    this repository.
    """
    data = SeededOrgs(
        a=uuid.uuid4(),
        b=uuid.uuid4(),
        a_user_id=uuid.uuid4(),
        a_study_id=uuid.uuid4(),
        a_series_id=uuid.uuid4(),
        b_study_id=uuid.uuid4(),
        a_patient_mrn="FAKE-MRN-000123",
    )

    async with db.transaction():
        for org_id, slug in ((data.a, "org-a"), (data.b, "org-b")):
            await db.execute(
                "INSERT INTO organisation (id, name, slug) VALUES ($1, $2, $3)",
                org_id,
                f"Test {slug}",
                slug,
            )

        await db.execute(
            """
            INSERT INTO app_user (id, org_id, subject, email, display_name, role)
            VALUES ($1, $2, $3, $4, $5, 'researcher')
            """,
            data.a_user_id,
            data.a,
            f"test|{data.a_user_id}",
            "researcher@example.invalid",
            "Test Researcher",
        )

        patient_a, patient_b = uuid.uuid4(), uuid.uuid4()
        for pid, org, pseudonym in (
            (patient_a, data.a, "PT-A-001"),
            (patient_b, data.b, "PT-B-001"),
        ):
            await db.execute(
                """
                INSERT INTO patient (id, org_id, pseudonym, key_id, birth_year, sex)
                VALUES ($1, $2, $3, 'test-key', 1970, 'O')
                """,
                pid,
                org,
                pseudonym,
            )

        for sid, org, pid, uid in (
            (data.a_study_id, data.a, patient_a, "1.2.826.0.1.TEST.A"),
            (data.b_study_id, data.b, patient_b, "1.2.826.0.1.TEST.B"),
        ):
            await db.execute(
                """
                INSERT INTO study (id, org_id, patient_id, study_uid, modalities)
                VALUES ($1, $2, $3, $4, ARRAY['CT'])
                """,
                sid,
                org,
                pid,
                uid,
            )

        await db.execute(
            """
            INSERT INTO series (id, org_id, study_id, series_uid, modality,
                                rows, columns, slice_count, pixel_spacing_mm)
            VALUES ($1, $2, $3, '1.2.826.0.2.TEST.A', 'CT',
                    512, 512, 120, ARRAY[0.7, 0.7])
            """,
            data.a_series_id,
            data.a,
            data.a_study_id,
        )

    yield data

    # Deleted in FK dependency order: organisation is referenced by app_user,
    # patient, study and series, none of which cascade on delete.
    async with db.transaction():
        await db.execute("DELETE FROM series WHERE org_id = ANY($1::uuid[])", [data.a, data.b])
        await db.execute("DELETE FROM study WHERE org_id = ANY($1::uuid[])", [data.a, data.b])
        await db.execute("DELETE FROM patient WHERE org_id = ANY($1::uuid[])", [data.a, data.b])
        await db.execute("DELETE FROM app_user WHERE org_id = ANY($1::uuid[])", [data.a, data.b])
        # audit_log is immutable by design and intentionally left in place.
        await db.execute("DELETE FROM organisation WHERE id = ANY($1::uuid[])", [data.a, data.b])


# ---------------------------------------------------------------- HTTP client
@pytest.fixture
async def client(migrated_dsn: str, oidc_issuer: str, monkeypatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("MIVW_DB_DSN", migrated_dsn)
    monkeypatch.setenv("MIVW_OIDC_ISSUER", oidc_issuer)
    monkeypatch.setenv("MIVW_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("MIVW_ENCRYPTION_KEY_ID", "test-key")
    monkeypatch.setenv("MIVW_HMAC_KEY_ID", "test-hmac")
    # keys._resolve() reads material directly from these in local mode,
    # bypassing the OS keychain (which local dev containers rarely have).
    monkeypatch.setenv("MIVW_KEY_MATERIAL_TEST_KEY", "test-encryption-key-material")
    monkeypatch.setenv("MIVW_KEY_MATERIAL_TEST_HMAC", "test-hmac-key-material")

    from mivw_api.config import get_settings
    from mivw_api.keys import clear_cache
    from mivw_api.main import create_app

    get_settings.cache_clear()
    clear_cache()
    app = create_app()
    # The GPU core is not under test here; render paths have their own suites.
    app.dependency_overrides.update(_stub_core_dependencies())

    # httpx's ASGITransport never sends the ASGI lifespan protocol, so startup
    # (which populates app.state.pool) must be driven explicitly here.
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client,
    ):
        yield http_client


@pytest.fixture
def viewer_token(token_factory, seeded_orgs: SeededOrgs) -> str:
    return token_factory(org_id=seeded_orgs.a, role="viewer")


@pytest.fixture
def admin_token(token_factory, seeded_orgs: SeededOrgs) -> str:
    return token_factory(org_id=seeded_orgs.a, role="admin")


def _stub_core_dependencies() -> dict[object, object]:
    from mivw_api.services.core_runtime import get_core_runtime

    class StubCore:
        async def warm_up(self) -> None: ...
        async def shutdown(self) -> None: ...

    return {get_core_runtime: lambda: StubCore()}
