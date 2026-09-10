from __future__ import annotations

import asyncio
import sys
import types
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect
from starlette.requests import Request
from starlette.responses import Response

from mivw_api import keys, middleware, storage
from mivw_api.config import Mode
from mivw_api.problems import (
    GpuUnavailable,
    NotFound,
    QuarantinedSeries,
    SpecMismatch,
)
from mivw_api.repositories.annotations import AnnotationRepository
from mivw_api.repositories.models import ModelRepository
from mivw_api.repositories.studies import StudyRepository, hash_patient_ref
from mivw_api.routers import health, inference, ingest, models, render, series, studies
from mivw_api.routers.inference import _assert_conforms
from mivw_api.schemas.annotation import AnnotationCreate, AnnotationKind, AnnotationPayload
from mivw_api.schemas.job import RenderSessionCreate
from mivw_api.schemas.model import InputSpec, LabelInfo, ModelCreate
from mivw_api.schemas.study import StudyQuery
from mivw_api.security import auth as security_auth
from mivw_api.security.principal import Principal, Role
from mivw_api.services import core_runtime
from mivw_api.ws import jobs_ws, render_ws
from mivw_api.ws.jobs_ws import JobBroadcaster


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class FakePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return AsyncContext(self.connection)


class FakeConnection:
    def __init__(self, result=1, error: Exception | None = None):
        self.result = result
        self.error = error

    async def fetchval(self, _query):
        if self.error:
            raise self.error
        return self.result


class FakeStorageClient:
    async def generate_presigned_url(self, operation, **kwargs):
        return f"{operation}:{kwargs['Params']['Key']}:{kwargs['ExpiresIn']}"

    async def get_object(self, **_kwargs):
        return {"Body": FakeBody(b"payload")}

    async def put_object(self, **_kwargs):
        return None


class FakeBody:
    def __init__(self, payload):
        self.payload = payload

    async def read(self):
        return self.payload


def request(path="/api/v1/test", *, headers=(), scheme="http"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
            "client": ("127.0.0.1", 1),
            "scheme": scheme,
            "server": ("localhost", 8000),
        }
    )


@pytest.mark.asyncio
async def test_healthz_and_readyz_states(monkeypatch):
    assert await health.healthz() == {"status": "ok"}

    class Core:
        available = True

    monkeypatch.setattr(health, "get_core_runtime", lambda: Core())
    response = Response()
    result = await health.readyz(response, FakePool(FakeConnection()))
    assert result == {"ready": True, "checks": {"database": "ok", "core": "ok"}}
    assert response.status_code == 200

    Core.available = False
    result = await health.readyz(response, FakePool(FakeConnection()))
    assert result["checks"]["core"] == "degraded"

    response = Response()
    result = await health.readyz(response, FakePool(FakeConnection(error=RuntimeError())))
    assert result["ready"] is False
    assert response.status_code == 503

    monkeypatch.setattr(health, "get_core_runtime", lambda: (_ for _ in ()).throw(RuntimeError()))
    result = await health.readyz(response, FakePool(FakeConnection()))
    assert result["checks"]["core"] == "degraded"


def test_key_resolution_local_and_kms(monkeypatch):
    keys.clear_cache()
    settings = SimpleNamespace(mode=Mode.LOCAL, hmac_key_id="hmac-key", encryption_key_id="enc-key")
    monkeypatch.setenv("MIVW_KEY_MATERIAL_HMAC_KEY", "local-secret")
    assert keys.get_hmac_key(settings) == b"local-secret"

    monkeypatch.delenv("MIVW_KEY_MATERIAL_HMAC_KEY")
    keys.clear_cache()
    fake_keyring = types.SimpleNamespace(get_password=lambda _service, _key: "keyring-secret")
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    assert keys.get_hmac_key(settings) == b"keyring-secret"

    boto3 = types.SimpleNamespace(
        client=lambda _name: types.SimpleNamespace(
            generate_data_key=lambda **_kwargs: {"Plaintext": b"kms-secret"}
        )
    )
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    keys.clear_cache()
    server_settings = SimpleNamespace(mode=Mode.SERVER, hmac_key_id="server-key")
    assert keys.get_hmac_key(server_settings) == b"kms-secret"


@pytest.mark.asyncio
async def test_storage_helpers_and_integrity(monkeypatch):
    settings = SimpleNamespace(
        object_endpoint="http://object-store/",
        object_bucket="bucket",
        presigned_url_ttl_seconds=30,
        object_region="test",
    )
    store = storage.ObjectStore(settings)
    client = FakeStorageClient()

    async def fake_client():
        return client

    monkeypatch.setattr(store, "_client", fake_client)
    digest = store.digest(b"payload")
    assert store.content_key("volumes", digest, ".bin").endswith(".bin")
    assert store.bucket == "bucket"
    assert store.expiry().tzinfo is not None
    assert (await store.presign_get("key")).startswith("get_object:key")
    assert (await store.presign_put("key", max_bytes=7)).startswith("put_object:key")
    assert await store.get_object("key", expected_sha256=digest) == b"payload"
    assert await store.put_object("key", b"payload") == digest

    with pytest.raises(storage.IntegrityError):
        await store.get_object("key", expected_sha256=b"wrong")


@pytest.mark.asyncio
async def test_middleware_request_id_headers_size_and_rate_limit():
    async def endpoint(req):
        return Response("ok")

    request_id = middleware.RequestIdMiddleware(endpoint)
    req = request("/healthz", headers=(("X-Request-Id", "fixed"),))
    response = await request_id.dispatch(req, endpoint)
    assert response.headers["X-Request-Id"] == "fixed"

    security = middleware.SecurityHeadersMiddleware(endpoint)
    response = await security.dispatch(request("/healthz", scheme="https"), endpoint)
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" in response.headers

    size = middleware.BodySizeLimitMiddleware(endpoint, max_bytes=2)
    response = await size.dispatch(request("/upload", headers=(("content-length", "3"),)), endpoint)
    assert response.status_code == 413
    response = await size.dispatch(
        request("/upload", headers=(("content-length", "bad"),)), endpoint
    )
    assert response.status_code == 200

    limiter = middleware.RateLimitMiddleware(endpoint, capacity=1, refill_per_second=0)
    response = await limiter.dispatch(request("/api/v1/models"), endpoint)
    assert response.status_code == 200
    response = await limiter.dispatch(request("/api/v1/models"), endpoint)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_principal_role_is_stable():
    principal = Principal(uuid.uuid4(), uuid.uuid4(), "subject", Role.VIEWER)
    assert principal.has_at_least(Role.VIEWER)
    assert not principal.has_at_least(Role.ADMIN)


class FakeRepoConnection:
    def __init__(self, rows=()):
        self.rows = list(rows)

    async def fetch(self, _query, *_args):
        return self.rows

    async def fetchrow(self, _query, *_args):
        return self.rows[0] if self.rows else None

    async def execute(self, _query, *_args):
        return "UPDATE 1"


def _study_row(study_id, series_count=1):
    return {
        "id": study_id,
        "patient_id": uuid.uuid4(),
        "pseudonym": "PT-001",
        "birth_year": 1970,
        "sex": "O",
        "study_datetime": datetime.now(UTC),
        "description": "phantom",
        "modalities": ["CT"],
        "series_count": series_count,
    }


@pytest.mark.asyncio
async def test_study_repository_paths():
    study_id = uuid.uuid4()
    row = _study_row(study_id)
    conn = FakeRepoConnection([row, _study_row(uuid.uuid4())])
    repo = StudyRepository(conn)
    query = StudyQuery(limit=1)
    studies, cursor = await repo.list_studies(query, mrn_hmac=None)
    assert len(studies) == 1 and cursor
    decoded = StudyQuery(after=cursor)
    assert decoded.after == cursor
    assert (await repo.get_study(study_id)).id == study_id
    assert hash_patient_ref(" 123 ", b"key") == hash_patient_ref("123", b"key")

    series_id = uuid.uuid4()
    series = {
        "id": series_id,
        "study_id": study_id,
        "volume_asset_id": None,
        "series_number": None,
        "modality": "CT",
        "description": None,
        "frame_of_reference_uid": None,
        "rows": 2,
        "columns": 2,
        "slice_count": 1,
        "pixel_spacing_mm": [1.0, 1.0],
        "slice_thickness_mm": None,
        "image_orientation": None,
        "image_position": None,
        "rescale_slope": 1.0,
        "rescale_intercept": 0.0,
        "is_quarantined": False,
        "has_volume": False,
    }
    repo = StudyRepository(FakeRepoConnection([series]))
    assert (await repo.list_series(study_id))[0].id == series_id
    assert (await repo.get_series(series_id)).id == series_id
    volume = {
        "id": uuid.uuid4(),
        "series_id": series_id,
        "dims": [1, 2, 2],
        "spacing_mm": [1.0, 1.0, 1.0],
        "dtype": "int16",
        "size_bytes": 8,
        "value_min": -1.0,
        "value_max": 1.0,
        "object_key": "vol/key",
        "content_sha256": b"hash",
    }
    volume_repo = StudyRepository(FakeRepoConnection([volume]))
    info, key, digest = await volume_repo.get_volume_asset(series_id)
    assert info.dims == (1, 2, 2) and key == "vol/key" and digest == b"hash"
    assert await volume_repo.soft_delete_study(study_id)


@pytest.mark.asyncio
async def test_annotation_and_model_repository_paths():
    now = datetime.now(UTC)
    annotation_row = {
        "id": uuid.uuid4(),
        "series_id": uuid.uuid4(),
        "author_id": uuid.uuid4(),
        "author_name": "Researcher",
        "kind": "note",
        "payload": '{"text":"ok"}',
        "label": None,
        "frame_of_reference_uid": None,
        "created_at": now,
        "updated_at": now,
    }
    annotation_repo = AnnotationRepository(FakeRepoConnection([annotation_row]))
    payload = AnnotationCreate(kind=AnnotationKind.NOTE, payload=AnnotationPayload(text="ok"))
    assert (
        await annotation_repo.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), payload)
    ).kind == AnnotationKind.NOTE
    assert len(await annotation_repo.list_for_series(uuid.uuid4())) == 1
    assert (await annotation_repo.get(annotation_row["id"])).author_name == "Researcher"
    assert (
        await annotation_repo.update(annotation_row["id"], payload=payload.payload, label="x")
    ).label is None
    assert await annotation_repo.soft_delete(annotation_row["id"])

    model_row = {
        "id": uuid.uuid4(),
        "name": "demo",
        "version": "1",
        "artifact_key": "a/key",
        "artifact_sha256": b"\x01" * 32,
        "output_kind": "segmentation",
        "input_spec": '{"shape":[2,2,2],"spacingMm":[1,1,1]}',
        "label_map": '{"1":{"name":"lesion","color":"#ffffff"}}',
        "description": None,
        "is_enabled": True,
        "validated_at": None,
        "created_at": now,
    }
    model_repo = ModelRepository(FakeRepoConnection([model_row]))
    model = ModelCreate(
        name="demo",
        version="1",
        artifact_key="a/key",
        artifact_sha256=("01" * 32),
        output_kind="segmentation",
        input_spec=InputSpec(shape=[2, 2, 2], spacing_mm=(1, 1, 1)),
        label_map={"1": LabelInfo(name="lesion", color="#ffffff")},
    )
    assert (await model_repo.create(uuid.uuid4(), model, uuid.uuid4())).name == "demo"
    assert len(await model_repo.list()) == 1
    assert (await model_repo.get(model_row["id"])).name == "demo"
    assert (
        await model_repo.update(model_row["id"], description="x", is_enabled=False)
    ).name == "demo"
    assert (await model_repo.mark_validated(model_row["id"])).name == "demo"


@pytest.mark.asyncio
async def test_core_runtime_and_job_broadcaster(monkeypatch):
    class Renderer:
        gpu_memory_bytes = 128

    monkeypatch.setattr(core_runtime, "CORE_AVAILABLE", True)
    monkeypatch.setattr(core_runtime, "mivw_core", SimpleNamespace(Renderer=Renderer))
    settings = SimpleNamespace(render_max_sessions_per_user=1, render_session_idle_timeout_s=60)
    runtime = core_runtime.CoreRuntime(settings)
    await runtime.warm_up()
    owner, org, series_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session = await runtime.create_session(
        series_id=series_id, owner_id=owner, org_id=org, width=2, height=2
    )
    assert await runtime.resolve_token(session.token) is session
    assert runtime.gpu_memory_bytes() == 128
    with pytest.raises(GpuUnavailable):
        await runtime.create_session(
            series_id=series_id, owner_id=owner, org_id=org, width=2, height=2
        )
    assert not await runtime.close_session(session.id, uuid.uuid4())
    assert await runtime.close_session(session.id, owner)
    await runtime.shutdown()

    broadcaster = JobBroadcaster()
    queue = await broadcaster.subscribe(org)
    await broadcaster.publish(org, {"id": "job"})
    assert await queue.get() == {"id": "job"}
    await broadcaster.publish(uuid.uuid4(), {"id": "other"})
    await broadcaster.unsubscribe(org, queue)


@pytest.mark.asyncio
async def test_series_and_ingest_handlers(monkeypatch):
    principal = Principal(uuid.uuid4(), uuid.uuid4(), "subject", Role.RESEARCHER)
    series_id = uuid.uuid4()
    detail = SimpleNamespace(id=series_id, is_quarantined=False)

    class Repo:
        def __init__(self, _conn):
            pass

        async def get_series(self, _id):
            return detail

        async def get_volume_asset(self, _id):
            return (SimpleNamespace(), "volume/key", b"\x01")

    class Store:
        async def presign_get(self, key):
            return f"https://store/{key}"

        def expiry(self):
            return datetime.now(UTC)

        async def presign_put(self, key, *, max_bytes):
            return f"https://store/{key}/{max_bytes}"

    monkeypatch.setattr(series, "StudyRepository", Repo)
    monkeypatch.setattr(series, "write_audit", _async_noop)
    result = await series.get_volume(series_id, principal, object(), Store())
    assert result.url.endswith("volume/key")
    with pytest.raises(QuarantinedSeries):
        detail.is_quarantined = True
        await series.get_volume(series_id, principal, object(), Store())
    detail.is_quarantined = False

    class Conn:
        async def execute(self, *_args):
            return "INSERT 0 1"

        async def fetchrow(self, *_args):
            return {"id": series_id, "created_at": datetime.now(UTC)}

    payload = ingest.IngestSessionCreate(total_bytes=1, filenames=["a.dcm"])
    monkeypatch.setattr(ingest, "write_audit", _async_noop)
    result = await ingest.create_session(payload, principal, Conn(), Store())
    assert result.targets[0].filename == "a.dcm"


async def _async_noop(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_render_ws_and_inference_validation(monkeypatch):
    class Params:
        pass

    class Camera:
        pass

    fake_core = SimpleNamespace(
        RenderParams=Params,
        Camera=Camera,
        Quality=SimpleNamespace(Still="still", Interactive="interactive"),
    )
    monkeypatch.setitem(sys.modules, "mivw_core", fake_core)
    state = SimpleNamespace(width=4, height=5)
    params = render_ws._to_params({"type": "camera", "eye": [1, 2, 3], "mode": "still"}, state)
    assert params.width == 4 and params.camera.eye == (1, 2, 3)
    layer_params = render_ws._to_params({"type": "layers", "opacity": 0.5}, state)
    assert layer_params.segmentation_opacity == 0.5
    header = render_ws.encode_frame_header(
        codec="png", sequence=2, width=4, height=5, render_time_us=6, payload_len=3
    )
    assert header[:4] == b"MIVW" and len(header) == 32

    class Renderer:
        def render(self, _params, sequence):
            return b"abc", sequence, 4, 5, 0, "png"

    frame_state = SimpleNamespace(renderer=Renderer(), sequence=0, width=4, height=5)

    class Socket:
        def __init__(self):
            self.sent = []

        async def send_bytes(self, payload):
            self.sent.append(payload)

        async def send_json(self, payload):
            self.sent.append(payload)

    socket = Socket()
    await render_ws._emit(socket, frame_state, {"type": "quality"})
    assert socket.sent[0].startswith(b"MIVW")

    class Broken:
        def render(self, *_args):
            raise RuntimeError("broken")

    frame_state.renderer = Broken()
    await render_ws._emit(socket, frame_state, {})
    assert socket.sent[-1]["status"] == 500

    model = SimpleNamespace(
        input_spec=SimpleNamespace(
            spacing_mm=(1.0, 1.0, 1.0), spacing_tolerance_mm=0.01, shape=[2, 2, 2]
        )
    )
    _assert_conforms(model, {"spacing_mm": [1.005, 1.0, 1.0], "dims": [2, 2, 2]})
    with pytest.raises(SpecMismatch):
        _assert_conforms(model, {"spacing_mm": [2.0, 1.0, 1.0], "dims": [2, 2, 2]})
    with pytest.raises(SpecMismatch):
        _assert_conforms(model, {"spacing_mm": [1.0, 1.0, 1.0], "dims": [1, 2, 2]})


@pytest.mark.asyncio
async def test_router_error_paths(monkeypatch):
    principal = Principal(uuid.uuid4(), uuid.uuid4(), "subject", Role.ADMIN)
    missing = uuid.uuid4()

    class MissingRepo:
        def __init__(self, _conn):
            pass

        async def get_series(self, _id):
            return None

        async def get_volume_asset(self, _id):
            return None

        async def get(self, _id):
            return None

        async def update(self, _id, **_kwargs):
            return None

    monkeypatch.setattr(series, "StudyRepository", MissingRepo)
    with pytest.raises(NotFound):
        await series.get_series(missing, principal, object())
    with pytest.raises(NotFound):
        await series.get_volume(missing, principal, object(), object())
    with pytest.raises(NotFound):
        await series.list_annotations(missing, principal, object())

    class MissingConn:
        async def fetchrow(self, *_args):
            return None

    with pytest.raises(NotFound):
        await ingest.complete_session(missing, principal, MissingConn())
    with pytest.raises(NotFound):
        await ingest.get_session(missing, principal, MissingConn())

    monkeypatch.setattr(models, "ModelRepository", MissingRepo)
    with pytest.raises(NotFound):
        await models.get_model(missing, principal, object())
    with pytest.raises(NotFound):
        await models.update_model(missing, models.ModelUpdate(), principal, object())
    with pytest.raises(NotFound):
        await models.validate_model(missing, principal, object(), object())

    monkeypatch.setattr(
        inference, "get_core_runtime", lambda: SimpleNamespace(require_core=lambda: None)
    )
    monkeypatch.setattr(inference, "ModelRepository", MissingRepo)
    request = inference.InferenceRequest(model_id=missing, volume_asset_id=missing)
    with pytest.raises(NotFound):
        await inference.create_inference_run(request, principal, MissingConn())
    with pytest.raises(NotFound):
        await inference.get_run(missing, principal, MissingConn())
    with pytest.raises(NotFound):
        await inference.get_segmentation(missing, principal, MissingConn())

    class NoStudy:
        def __init__(self, _conn):
            pass

        async def soft_delete_study(self, _id):
            return False

    monkeypatch.setattr(studies, "StudyRepository", NoStudy)
    with pytest.raises(NotFound):
        await studies.delete_study(missing, principal, object())


@pytest.mark.asyncio
async def test_render_router_branches(monkeypatch):
    principal = Principal(uuid.uuid4(), uuid.uuid4(), "subject", Role.VIEWER)
    series_id = uuid.uuid4()
    payload = RenderSessionCreate(series_id=series_id, width=64, height=64)

    class Core:
        def require_core(self):
            return None

        async def create_session(self, **kwargs):
            return SimpleNamespace(
                id=uuid.uuid4(),
                token="token",
                series_id=kwargs["series_id"],
                expires_at=datetime.now(UTC),
            )

        async def close_session(self, _session_id, _owner_id):
            return True

        def gpu_memory_bytes(self):
            return 123

    class Repo:
        result = SimpleNamespace(is_quarantined=False, has_volume=True)

        def __init__(self, _conn):
            pass

        async def get_series(self, _id):
            return self.result

        async def get_volume_asset(self, _id):
            return (
                SimpleNamespace(dims=(1, 1, 1), spacing_mm=(1.0, 1.0, 1.0)),
                "volume/key",
                b"\x00" * 2,
            )

    class Store:
        async def get_object(self, _key, *, expected_sha256):
            return b"\x00" * 2

    monkeypatch.setattr(render, "get_core_runtime", lambda: Core())
    monkeypatch.setattr(render, "StudyRepository", Repo)
    monkeypatch.setattr(render, "write_audit", _async_noop)

    result = await render.create_render_session(payload, principal, object(), Store())
    assert result.token == "token" and result.gpu_memory_bytes == 123
    assert await render.close_render_session(result.id, principal, object()) is None

    Repo.result = None
    with pytest.raises(NotFound):
        await render.create_render_session(payload, principal, object(), Store())
    Repo.result = SimpleNamespace(is_quarantined=True, has_volume=True)
    with pytest.raises(QuarantinedSeries):
        await render.create_render_session(payload, principal, object(), Store())
    Repo.result = SimpleNamespace(is_quarantined=False, has_volume=False)
    with pytest.raises(NotFound):
        await render.create_render_session(payload, principal, object(), Store())

    class UnavailableCore(Core):
        def require_core(self):
            raise GpuUnavailable("core unavailable")

    monkeypatch.setattr(render, "get_core_runtime", lambda: UnavailableCore())
    Repo.result = SimpleNamespace(is_quarantined=False, has_volume=True)
    with pytest.raises(GpuUnavailable):
        await render.create_render_session(payload, principal, object(), Store())

    class ClosedCore(Core):
        async def close_session(self, _session_id, _owner_id):
            return False

    monkeypatch.setattr(render, "get_core_runtime", lambda: ClosedCore())
    with pytest.raises(NotFound):
        await render.close_render_session(uuid.uuid4(), principal, object())


@pytest.mark.asyncio
async def test_job_websocket_rejection_and_delivery(monkeypatch):
    org_id = uuid.uuid4()
    principal = Principal(uuid.uuid4(), org_id, "subject", Role.VIEWER)
    settings = SimpleNamespace(mode=Mode.LOCAL, allowed_origin=None)
    monkeypatch.setattr(jobs_ws, "get_settings", lambda: settings)

    class Socket:
        def __init__(self, token=None, origin=None):
            self.query_params = {} if token is None else {"token": token}
            self.headers = {} if origin is None else {"origin": origin}
            self.closed = []
            self.events = []

        async def close(self, code):
            self.closed.append(code)

        async def accept(self):
            self.events.append("accepted")

        async def send_json(self, event):
            self.events.append(event)
            raise WebSocketDisconnect()

    denied = Socket()
    await jobs_ws.job_stream(denied)
    assert denied.closed

    class Verifier:
        def __init__(self, _settings):
            pass

        async def verify(self, _token):
            return principal

    monkeypatch.setattr(security_auth, "TokenVerifier", Verifier)
    original = jobs_ws.broadcaster

    class Broadcaster:
        async def subscribe(self, _org):
            self.queue = asyncio.Queue()
            await self.queue.put({"job": "done"})
            return self.queue

        async def unsubscribe(self, _org, _queue):
            self.unsubscribed = True

    broadcaster = Broadcaster()
    monkeypatch.setattr(jobs_ws, "broadcaster", broadcaster)
    delivered = Socket(token="valid")
    await jobs_ws.job_stream(delivered)
    assert delivered.events == ["accepted", {"job": "done"}]
    assert broadcaster.unsubscribed
    monkeypatch.setattr(jobs_ws, "broadcaster", original)


@pytest.mark.asyncio
async def test_render_websocket_rejection_and_disconnect(monkeypatch):
    settings = SimpleNamespace(mode=Mode.SERVER, allowed_origin="https://allowed")
    monkeypatch.setattr(render_ws, "get_settings", lambda: settings)

    class Socket:
        def __init__(self, origin):
            self.headers = {"origin": origin}
            self.closed = []
            self.accepted = False

        async def close(self, code):
            self.closed.append(code)

        async def accept(self):
            self.accepted = True

        async def receive_json(self):
            raise WebSocketDisconnect()

    rejected = Socket("https://wrong")
    await render_ws.render_stream(rejected, "token")
    assert rejected.closed and not rejected.accepted

    class Core:
        async def resolve_token(self, _token):
            return None

    monkeypatch.setattr(render_ws, "get_core_runtime", lambda: Core())
    missing = Socket("https://allowed")
    await render_ws.render_stream(missing, "missing")
    assert missing.closed

    class ValidCore:
        async def resolve_token(self, _token):
            return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(render_ws, "get_core_runtime", lambda: ValidCore())
    connected = Socket("https://allowed")
    await render_ws.render_stream(connected, "valid")
    assert connected.accepted
