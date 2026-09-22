"""FastAPI application factory."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mivw_api.config import Mode, get_settings
from mivw_api.logging import configure_logging
from mivw_api.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from mivw_api.problems import ProblemDetail, ProblemError
from mivw_api.routers import (
    annotations as annotations_router,
)
from mivw_api.routers import (
    health,
    inference,
    ingest,
    models,
    render,
    series,
    studies,
)
from mivw_api.ws import jobs_ws, render_ws

log = structlog.get_logger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    from mivw_api.db import create_pool
    from mivw_api.services.core_runtime import CoreRuntime, set_core_runtime
    from mivw_api.services.job_worker import JobWorker
    from mivw_api.storage import ObjectStore

    app.state.pool = await create_pool(settings)
    app.state.storage = ObjectStore(settings)
    app.state.core = CoreRuntime(settings)
    set_core_runtime(app.state.core)
    await app.state.core.warm_up()

    app.state.job_worker = JobWorker(app.state.pool, app.state.core, app.state.storage)
    app.state.job_worker.start()

    log.info("api.started", mode=settings.mode, gpu_device=settings.gpu_device)
    try:
        yield
    finally:
        await app.state.job_worker.stop()
        await app.state.core.shutdown()
        await app.state.pool.close()
        log.info("api.stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.mode is Mode.SERVER)

    app = FastAPI(
        title="MIVW API",
        version="1.0.0",
        description=(
            "Real-Time AI-Powered Medical Image Workstation. "
            "RESEARCH USE ONLY - not a cleared medical device."
        ),
        lifespan=lifespan,
        # Interactive docs are a needless attack surface in server deployments.
        docs_url="/docs" if settings.mode is Mode.LOCAL else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.mode is Mode.LOCAL else None,
    )

    # Outermost first.
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            max_age=600,
        )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=1_048_576)

    app.include_router(health.router)
    for module in (studies, series, ingest, models, inference, annotations_router, render):
        app.include_router(module.router, prefix="/api/v1")

    app.include_router(render_ws.router)
    app.include_router(jobs_ws.router)

    _register_exception_handlers(app)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem_handler(request: Request, exc: ProblemError) -> JSONResponse:
        problem = exc.to_problem(instance=request.url.path)
        problem.request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=problem.status,
            content=problem.model_dump(by_alias=True, exclude_none=True),
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names and constraint codes only. Echoing the rejected value
        # would put unvalidated input - potentially PHI - into a response body.
        errors = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "code": err["type"]}
            for err in exc.errors()
        ]
        problem = ProblemDetail(
            type="https://mivw.local/problems/validation-failed",
            title="Request validation failed",
            status=422,
            instance=request.url.path,
            requestId=getattr(request.state, "request_id", None),
            errors=errors,  # type: ignore[arg-type]
        )
        return JSONResponse(
            status_code=422,
            content=problem.model_dump(by_alias=True, exclude_none=True),
            media_type="application/problem+json",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        # Log the detail; never return it. Internal messages can contain
        # identifiers, file paths, or query fragments.
        log.exception("api.unhandled", request_id=request_id, path=request.url.path)
        problem = ProblemDetail(
            type="https://mivw.local/problems/internal-error",
            title="Internal server error",
            status=500,
            instance=request.url.path,
            requestId=request_id,
        )
        return JSONResponse(
            status_code=500,
            content=problem.model_dump(by_alias=True, exclude_none=True),
            media_type="application/problem+json",
        )
