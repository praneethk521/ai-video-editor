from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import ORJSONResponse

from app.api.internal import router as internal_router
from app.api.projects import router as projects_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.security import CurrentServiceToken, get_current_service_token, require_service_scope
from app.db.session import Base, engine
from app.models import entities  # noqa: F401
from app.services.metrics import record_http_request, render_metrics

configure_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Video Editor API",
        version="0.1.0",
        default_response_class=ORJSONResponse,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_seconds = time.perf_counter() - start
            route = getattr(request.scope.get("route"), "path", "unmatched")
            record_http_request(
                method=request.method,
                route=route,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                elapsed_seconds=elapsed_seconds,
            )
            raise
        elapsed_seconds = time.perf_counter() - start
        elapsed_ms = round(elapsed_seconds * 1000, 2)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        record_http_request(
            method=request.method,
            route=route,
            status_code=response.status_code,
            elapsed_seconds=elapsed_seconds,
        )
        response.headers["x-correlation-id"] = correlation_id
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            correlation_id=correlation_id,
        )
        return response

    @app.get("/healthz", tags=["health"])
    def healthz():
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    def metrics(token: CurrentServiceToken = Depends(get_current_service_token)):
        if not settings.metrics_enabled:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="metrics disabled")
        if token.project_id is not None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="global service token required")
        require_service_scope(token, required_scope="metrics")
        payload, content_type = render_metrics()
        return Response(content=payload, headers={"Content-Type": content_type})

    app.include_router(projects_router)
    app.include_router(internal_router)
    return app


app = create_app()
