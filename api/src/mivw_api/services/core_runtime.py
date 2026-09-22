"""Bridge to the C++/CUDA compute core.

`mivw_core` is an optional import: the gateway must still start on a machine
without a GPU or a built extension, so that schema work, authorisation tests and
the worklist remain usable. Render and inference endpoints then fail with a
clear 503 instead of an import error at startup.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from mivw_api.problems import GpuUnavailable, NotFound

if TYPE_CHECKING:
    from mivw_api.config import Settings

log = structlog.get_logger(__name__)

try:
    import mivw_core  # type: ignore[import-not-found]

    CORE_AVAILABLE = True
    CORE_IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover - depends on the build environment
    mivw_core = None
    CORE_AVAILABLE = False
    CORE_IMPORT_ERROR = str(exc)


@dataclass(slots=True)
class RenderSessionState:
    id: uuid.UUID
    token: str
    series_id: uuid.UUID
    owner_id: uuid.UUID
    org_id: uuid.UUID
    width: int
    height: int
    expires_at: datetime
    transfer_function_preset: str = "ct-soft-tissue"
    renderer: Any = None
    sequence: int = 0
    # Non-camera messages (e.g. the idle "still" refresh) carry no camera of
    # their own; without this, they'd snap the view back to the default pose.
    last_camera: dict[str, Any] | None = None
    last_used: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.last_used = datetime.now(UTC)


class CoreRuntime:
    """Owns GPU resources and render sessions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: dict[uuid.UUID, RenderSessionState] = {}
        self._by_token: dict[str, uuid.UUID] = {}
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task[None] | None = None

    @property
    def available(self) -> bool:
        return CORE_AVAILABLE

    async def warm_up(self) -> None:
        if not CORE_AVAILABLE:
            log.warning(
                "core.unavailable",
                reason=CORE_IMPORT_ERROR,
                impact="render and inference endpoints will return 503",
            )
            return

        log.info("core.ready", version=getattr(mivw_core, "__version__", "unknown"))
        self._reaper = asyncio.create_task(self._reap_idle_sessions())

    async def shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reaper

        async with self._lock:
            for session in list(self._sessions.values()):
                self._release(session)
            self._sessions.clear()
            self._by_token.clear()

    def require_core(self) -> None:
        if not CORE_AVAILABLE:
            raise GpuUnavailable("The compute core is not available in this deployment")

    async def create_session(
        self,
        *,
        series_id: uuid.UUID,
        owner_id: uuid.UUID,
        org_id: uuid.UUID,
        width: int,
        height: int,
        volume: Any = None,
        transfer_function_preset: str = "ct-soft-tissue",
    ) -> RenderSessionState:
        self.require_core()

        async with self._lock:
            self._reap_idle_sessions_locked()
            owned = [s for s in self._sessions.values() if s.owner_id == owner_id]
            # Sessions pin volume memory on the GPU; without a cap one user can
            # exhaust the device for everyone else.
            if len(owned) >= self._settings.render_max_sessions_per_user:
                raise GpuUnavailable(
                    f"At most {self._settings.render_max_sessions_per_user} "
                    "concurrent render sessions are allowed"
                )

            state = RenderSessionState(
                id=uuid.uuid4(),
                token=uuid.uuid4().hex,
                series_id=series_id,
                owner_id=owner_id,
                org_id=org_id,
                transfer_function_preset=transfer_function_preset,
                width=width,
                height=height,
                expires_at=datetime.now(UTC)
                + timedelta(seconds=self._settings.render_session_idle_timeout_s),
                renderer=mivw_core.Renderer(),
            )
            if volume is not None:
                state.renderer.set_volume(volume)
            self._sessions[state.id] = state
            self._by_token[state.token] = state.id
            return state

    async def resolve_token(self, token: str) -> RenderSessionState | None:
        async with self._lock:
            session_id = self._by_token.get(token)
            return self._sessions.get(session_id) if session_id else None

    async def close_session(self, session_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        async with self._lock:
            state = self._sessions.get(session_id)
            if state is None or state.owner_id != owner_id:
                return False
            self._release(state)
            del self._sessions[session_id]
            self._by_token.pop(state.token, None)
            return True

    def gpu_memory_bytes(self) -> int:
        return sum(getattr(s.renderer, "gpu_memory_bytes", 0) or 0 for s in self._sessions.values())

    async def run_inference(
        self,
        *,
        model: Any,
        artifact: bytes,
        raw_volume: bytes,
        dims: tuple[int, int, int],
        spacing_mm: tuple[float, float, float],
    ) -> tuple[bytes, dict[str, Any], dict[str, dict[str, float]]]:
        """Runs a registered model against a volume via `mivw_core.InferenceRuntime`.

        Returns (segmentation bytes, provenance fields, per-label voxel/volume
        stats). This is GPU-bound work, so it runs off the event loop.
        """
        self.require_core()
        return await asyncio.to_thread(
            self._run_inference_sync, model, artifact, raw_volume, dims, spacing_mm
        )

    def _run_inference_sync(
        self,
        model: Any,
        artifact: bytes,
        raw_volume: bytes,
        dims: tuple[int, int, int],
        spacing_mm: tuple[float, float, float],
    ) -> tuple[bytes, dict[str, Any], dict[str, dict[str, float]]]:
        import numpy as np

        volume = mivw_core.Volume(dims, spacing_mm, mivw_core.DType.Int16)
        voxels = np.frombuffer(raw_volume, dtype=np.int16)
        volume.as_array()[:] = voxels.reshape(tuple(reversed(dims)))

        runtime = mivw_core.InferenceRuntime()
        input_spec = model.input_spec.model_dump(by_alias=True)
        runtime.load_model_bytes(artifact, input_spec)

        output, provenance = runtime.run(input_spec, bytes.fromhex(model.artifact_sha256), volume)

        labels = np.asarray(output.as_array())
        voxel_volume_ml = (spacing_mm[0] * spacing_mm[1] * spacing_mm[2]) / 1000.0
        label_stats: dict[str, dict[str, float]] = {}
        for index in np.unique(labels):
            if index == 0:
                continue
            count = int(np.count_nonzero(labels == index))
            label_stats[str(int(index))] = {
                "voxelCount": float(count),
                "volumeMl": float(count) * voxel_volume_ml,
            }

        return labels.astype(np.int16).tobytes(), provenance, label_stats

    async def attach_segmentation(
        self,
        *,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        mask_bytes: bytes,
        dims: tuple[int, int, int],
        spacing_mm: tuple[float, float, float],
        label_colours: list[tuple[float, float, float, float]],
    ) -> None:
        """Composites a completed inference run's mask onto an open render session."""
        self.require_core()
        async with self._lock:
            state = self._sessions.get(session_id)
            if state is None or state.owner_id != owner_id:
                raise NotFound("No such render session")
            state.touch()
        await asyncio.to_thread(
            self._attach_segmentation_sync, state, mask_bytes, dims, spacing_mm, label_colours
        )

    def _attach_segmentation_sync(
        self,
        state: RenderSessionState,
        mask_bytes: bytes,
        dims: tuple[int, int, int],
        spacing_mm: tuple[float, float, float],
        label_colours: list[tuple[float, float, float, float]],
    ) -> None:
        import numpy as np

        mask = mivw_core.Volume(dims, spacing_mm, mivw_core.DType.Int16)
        labels = np.frombuffer(mask_bytes, dtype=np.int16)
        mask.as_array()[:] = labels.reshape(tuple(reversed(dims)))
        state.renderer.set_segmentation(mask, label_colours)

    def _release(self, state: RenderSessionState) -> None:
        state.renderer = None  # RAII on the C++ side frees the device memory

    def _reap_idle_sessions_locked(self) -> None:
        cutoff = datetime.now(UTC) - timedelta(seconds=self._settings.render_session_idle_timeout_s)
        stale = [s for s in self._sessions.values() if s.last_used < cutoff]
        for state in stale:
            log.info("render.session_expired", session_id=str(state.id))
            self._release(state)
            self._sessions.pop(state.id, None)
            self._by_token.pop(state.token, None)

    async def _reap_idle_sessions(self) -> None:
        while True:
            await asyncio.sleep(30)
            async with self._lock:
                self._reap_idle_sessions_locked()


_runtime: CoreRuntime | None = None


def set_core_runtime(runtime: CoreRuntime) -> None:
    global _runtime
    _runtime = runtime


def get_core_runtime() -> CoreRuntime:
    if _runtime is None:  # pragma: no cover - wired during app lifespan
        raise GpuUnavailable("Core runtime is not initialised")
    return _runtime
