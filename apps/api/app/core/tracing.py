from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode

from app.core.config import settings

_provider_configured = False


def configure_api_tracing(app: FastAPI) -> None:
    if not settings.tracing_enabled:
        return
    configure_tracer_provider()

    @app.middleware("http")
    async def tracing_middleware(request: Request, call_next):
        if request.url.path in {"/healthz", "/metrics"}:
            return await call_next(request)

        tracer = trace.get_tracer("ai-video-editor.api")
        parent_context = extract(dict(request.headers))
        with tracer.start_as_current_span(
            "api.request",
            context=parent_context,
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            span.set_attribute("http.request.method", request.method)
            try:
                response = await call_next(request)
            except Exception as exc:
                record_request_result(span, request, 500)
                record_error_type(span, exc)
                raise
            record_request_result(span, request, response.status_code)
            return response


def configure_tracer_provider() -> None:
    global _provider_configured
    if _provider_configured:
        return
    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: settings.otel_service_name}),
        sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
    )
    exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        headers=parse_exporter_headers(settings.otel_exporter_otlp_headers),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _provider_configured = True


def parse_exporter_headers(raw_headers: str) -> dict[str, str]:
    if not raw_headers.strip():
        return {}
    return dict(parse_qsl(raw_headers.replace(",", "&"), keep_blank_values=True))


@contextmanager
def operation_span(name: str, *, attributes: dict[str, str | bool] | None = None):
    if not settings.tracing_enabled:
        yield
        return
    tracer = trace.get_tracer("ai-video-editor.api")
    with tracer.start_as_current_span(
        name,
        attributes=attributes or {},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield
        except Exception as exc:
            record_error_type(span, exc)
            raise


def normalized_route(scope: dict) -> str:
    route = getattr(scope.get("route"), "path", None)
    return route if isinstance(route, str) and route.startswith("/") else "unmatched"


def record_request_result(span, request: Request, status_code: int) -> None:
    route = normalized_route(request.scope)
    span.update_name(f"{request.method} {route}")
    span.set_attribute("http.route", route)
    span.set_attribute("http.response.status_code", status_code)
    if status_code >= 500:
        span.set_status(Status(StatusCode.ERROR))


def record_error_type(span, exc: Exception) -> None:
    span.set_attribute("error.type", type(exc).__qualname__)
    span.set_status(Status(StatusCode.ERROR))
