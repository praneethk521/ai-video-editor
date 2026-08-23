from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.internal import router as internal_router
from app.api.identity import router as identity_router
from app.api.projects import router as projects_router
from app.api.teams import router as teams_router
from app.core.config import comma_separated_values, settings, validate_auth_configuration
from app.core.logging import configure_logging
from app.core.security import CurrentServiceToken, get_current_service_token, require_service_scope
from app.core.tracing import configure_api_tracing, normalized_route
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
    validate_auth_configuration(settings)
    app = FastAPI(
        title="AI Video Editor API",
        version="0.1.0",
        openapi_url=None if settings.app_env.lower() == "production" else "/openapi.json",
        docs_url=None if settings.app_env.lower() == "production" else "/docs",
        redoc_url=None if settings.app_env.lower() == "production" else "/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=comma_separated_values(settings.trusted_hosts),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=comma_separated_values(settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID"],
        max_age=600,
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
            route = normalized_route(request.scope)
            record_http_request(
                method=request.method,
                route=route,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                elapsed_seconds=elapsed_seconds,
            )
            raise
        elapsed_seconds = time.perf_counter() - start
        elapsed_ms = round(elapsed_seconds * 1000, 2)
        route = normalized_route(request.scope)
        record_http_request(
            method=request.method,
            route=route,
            status_code=response.status_code,
            elapsed_seconds=elapsed_seconds,
        )
        response.headers["x-correlation-id"] = correlation_id
        response.headers["cache-control"] = "no-store"
        if request.url.path not in {"/docs", "/redoc", "/openapi.json"}:
            response.headers["content-security-policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["permissions-policy"] = "camera=(), geolocation=(), microphone=()"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        logger.info(
            "http_request",
            method=request.method,
            path=route,
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
    app.include_router(identity_router)
    app.include_router(teams_router)
    app.include_router(internal_router)
    configure_api_tracing(app)
    return app


app = create_app()
