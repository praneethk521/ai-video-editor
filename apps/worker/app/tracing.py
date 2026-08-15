from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import parse_qsl

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode

from app.config import settings

_configured = False


def configure_worker_tracing() -> None:
    global _configured
    if _configured or not settings.tracing_enabled:
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
    _configured = True


@contextmanager
def operation_span(
    name: str,
    *,
    attributes: dict[str, str | bool] | None = None,
    trace_context: dict[str, str] | None = None,
):
    if not settings.tracing_enabled:
        yield
        return
    configure_worker_tracing()
    context = extract(trace_context or {}) if trace_context is not None else None
    tracer = trace.get_tracer("ai-video-editor.worker")
    with tracer.start_as_current_span(
        name,
        context=context,
        attributes=attributes or {},
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__qualname__)
            span.set_status(Status(StatusCode.ERROR))
            raise


@contextmanager
def render_job_span(*, variant: str, dry_run: bool, trace_context: dict[str, str] | None):
    with operation_span(
        "worker.render",
        trace_context=trace_context,
        attributes={"video.variant": normalized_variant(variant), "video.render.dry_run": dry_run},
    ):
        yield


def parse_exporter_headers(raw_headers: str) -> dict[str, str]:
    if not raw_headers.strip():
        return {}
    return dict(parse_qsl(raw_headers.replace(",", "&"), keep_blank_values=True))


def normalized_variant(variant: str) -> str:
    return variant if variant in {"youtube_16x9", "shorts_9x16"} else "unknown"
