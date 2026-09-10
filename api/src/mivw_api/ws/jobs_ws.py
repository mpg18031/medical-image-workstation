"""Job progress push channel."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from mivw_api.config import Mode, get_settings

log = structlog.get_logger(__name__)

router = APIRouter()


class JobBroadcaster:
    """Fan-out of job events, partitioned by tenant.

    Partitioning is not cosmetic: a shared queue would let one tenant observe
    another's job identifiers and timing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, org_id: uuid.UUID) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._subscribers.setdefault(org_id, set()).add(queue)
        return queue

    async def unsubscribe(self, org_id: uuid.UUID, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(org_id)
            if subscribers:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscribers[org_id]

    async def publish(self, org_id: uuid.UUID, event: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.get(org_id, ()))

        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A slow client must not stall job processing; it will catch up
                # by polling the REST endpoint.
                log.warning("jobs.subscriber_lagging", org_id=str(org_id))


broadcaster = JobBroadcaster()


@router.websocket("/ws/jobs")
async def job_stream(websocket: WebSocket) -> None:
    settings = get_settings()

    if settings.mode is Mode.SERVER:
        origin = websocket.headers.get("origin")
        if origin != settings.allowed_origin:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    from mivw_api.problems import Unauthenticated
    from mivw_api.security.auth import TokenVerifier

    try:
        principal = await TokenVerifier(settings).verify(token)
    except Unauthenticated:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    queue = await broadcaster.subscribe(principal.org_id)
    log.info("jobs.stream_open", org_id=str(principal.org_id))

    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unsubscribe(principal.org_id, queue)
        log.info("jobs.stream_closed", org_id=str(principal.org_id))
