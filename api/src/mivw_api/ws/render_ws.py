"""Render frame streaming.

Backpressure is latest-wins: if a newer camera state arrives while a frame is
in flight, the queued request is discarded rather than buffered. Buffering
would accumulate lag and make direct manipulation feel broken under GPU load.
"""

from __future__ import annotations

import asyncio
import struct
import time
from typing import Any

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from mivw_api.config import Mode, get_settings
from mivw_api.services.core_runtime import RenderSessionState, get_core_runtime

log = structlog.get_logger(__name__)

router = APIRouter()

FRAME_MAGIC = b"MIVW"
FRAME_VERSION = 1
_CODECS = {"h264": 1, "hevc": 2, "png": 3}

# magic(4) version(H) codec(H) seq(I) w(H) h(H) renderTimeUs(I) payloadLen(I) reserved(8)
_HEADER = struct.Struct("<4sHHIHHII8s")


def encode_frame_header(
    *, codec: str, sequence: int, width: int, height: int, render_time_us: int, payload_len: int
) -> bytes:
    return _HEADER.pack(
        FRAME_MAGIC,
        FRAME_VERSION,
        _CODECS.get(codec, 0),
        sequence,
        width,
        height,
        render_time_us,
        payload_len,
        b"\x00" * 8,
    )


@router.websocket("/ws/render")
async def render_stream(websocket: WebSocket, session: str = Query(...)) -> None:
    settings = get_settings()

    # A WebSocket upgrade is not covered by CORS, so the origin must be checked
    # explicitly or any page could open this socket.
    if settings.mode is Mode.SERVER:
        origin = websocket.headers.get("origin")
        if origin != settings.allowed_origin:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    core = get_core_runtime()
    state = await core.resolve_token(session)
    if state is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    log.info("render.stream_open", session_id=str(state.id))

    pending: dict[str, Any] | None = None
    wake = asyncio.Event()
    closing = False

    async def receive_loop() -> None:
        nonlocal pending, closing
        try:
            while True:
                message = await websocket.receive_json()
                # Latest wins: overwrite rather than append.
                pending = message
                wake.set()
        except WebSocketDisconnect:
            closing = True
            wake.set()

    async def render_loop() -> None:
        nonlocal pending
        still_pending = False

        while not closing:
            try:
                await asyncio.wait_for(wake.wait(), timeout=settings.render_still_delay_ms / 1000)
            except TimeoutError:
                # Input has gone quiet: send one full-quality frame. This is
                # server-driven so it adapts to real GPU load.
                if still_pending:
                    await _emit(websocket, state, {"type": "quality", "mode": "still"})
                    still_pending = False
                continue

            wake.clear()
            message, pending = pending, None
            if message is None or closing:
                continue

            state.touch()
            await _emit(websocket, state, message)
            still_pending = True

    try:
        await asyncio.gather(receive_loop(), render_loop())
    except WebSocketDisconnect:
        pass
    finally:
        log.info("render.stream_closed", session_id=str(state.id))


async def _emit(websocket: WebSocket, state: RenderSessionState, message: dict[str, Any]) -> None:
    started = time.perf_counter()
    state.sequence += 1

    try:
        payload, sequence, width, height, render_time_us, codec = state.renderer.render(
            _to_params(message, state), state.sequence
        )
    except Exception as exc:
        log.warning("render.failed", reason=type(exc).__name__)
        await websocket.send_json(
            {
                "type": "error",
                "title": "Render failed",
                "status": 500,
            }
        )
        return

    header = encode_frame_header(
        codec=codec,
        sequence=sequence,
        width=width,
        height=height,
        render_time_us=render_time_us or int((time.perf_counter() - started) * 1e6),
        payload_len=len(payload),
    )
    await websocket.send_bytes(header + payload)


def _to_params(message: dict[str, Any], state: RenderSessionState) -> Any:
    import mivw_core  # type: ignore[import-not-found]

    params = mivw_core.RenderParams()
    params.width = state.width
    params.height = state.height
    params.transfer_function_preset = getattr(state, "transfer_function_preset", "ct-soft-tissue")

    if message.get("type") == "camera":
        state.last_camera = {
            "eye": tuple(message.get("eye", (0, 0, -500))),
            "target": tuple(message.get("target", (0, 0, 0))),
            "up": tuple(message.get("up", (0, 1, 0))),
            "fov_degrees": float(message.get("fovDeg", 45.0)),
        }

    # Reapply the last known camera on every message, not just "camera" ones,
    # so idle "still"-quality refreshes and layer toggles don't reset the view.
    last_camera = getattr(state, "last_camera", None)
    if last_camera is not None:
        camera = mivw_core.Camera()
        camera.eye = last_camera["eye"]
        camera.target = last_camera["target"]
        camera.up = last_camera["up"]
        camera.fov_degrees = last_camera["fov_degrees"]
        params.camera = camera

    if message.get("type") == "layers":
        params.segmentation_visible = bool(message.get("segmentationVisible", True))
        params.segmentation_opacity = float(message.get("opacity", 0.45))

    params.quality = (
        mivw_core.Quality.Still if message.get("mode") == "still" else mivw_core.Quality.Interactive
    )
    return params
