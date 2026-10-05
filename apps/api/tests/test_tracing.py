from __future__ import annotations

from types import SimpleNamespace

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core import tracing
from app.core.tracing import normalized_route, operation_span, parse_exporter_headers, record_request_result
from app.services import rendering
from app.services.rendering import RenderQueueItem


def test_trace_configuration_parses_headers_and_uses_route_templates():
    assert parse_exporter_headers("authorization=Bearer%20secret,x-tenant=video") == {
        "authorization": "Bearer secret",
        "x-tenant": "video",
    }
    assert normalized_route(
        {"route": SimpleNamespace(path="/projects/{project_id}/outputs")}
    ) == "/projects/{project_id}/outputs"
    assert normalized_route({"path": "/projects/private-project-id/outputs"}) == "unmatched"


def test_request_trace_records_route_template_without_raw_identifier():
    class RecordingSpan:
        def __init__(self):
            self.attributes = {}
            self.name = ""

        def update_name(self, name: str) -> None:
            self.name = name

        def set_attribute(self, key: str, value) -> None:
            self.attributes[key] = value

        def set_status(self, status) -> None:
            self.status = status

    span = RecordingSpan()
    request = SimpleNamespace(
        method="GET",
        scope={
            "path": "/projects/private-project-id/outputs",
            "query_string": b"oauth_state=secret",
            "route": SimpleNamespace(path="/projects/{project_id}/outputs"),
        },
    )

    record_request_result(span, request, 200)

    assert span.name == "GET /projects/{project_id}/outputs"
    assert span.attributes == {
        "http.route": "/projects/{project_id}/outputs",
        "http.response.status_code": 200,
    }
    assert "private-project-id" not in repr(span.attributes)
    assert "secret" not in repr(span.attributes)


def test_operation_span_exports_error_type_without_exception_message(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing.settings, "tracing_enabled", True)
    monkeypatch.setattr(tracing.trace, "get_tracer", provider.get_tracer)

    with pytest.raises(ValueError, match="file://private/secret-output.mp4"):
        with operation_span("output.delivery", attributes={"delivery.target": "drive"}):
            raise ValueError("file://private/secret-output.mp4")

    span = exporter.get_finished_spans()[0]
    assert span.events == ()
    assert span.attributes == {
        "delivery.target": "drive",
        "error.type": "ValueError",
    }
    assert "secret-output" not in repr(span)


def test_rq_dispatch_propagates_trace_context_as_job_kwargs(monkeypatch):
    enqueued = []

    class FakeQueue:
        def __init__(self, name: str, connection):
            assert name == "renders"

        def enqueue_call(self, **kwargs):
            enqueued.append(kwargs)

    monkeypatch.setattr(rendering.settings, "render_queue_backend", "rq")
    monkeypatch.setattr(rendering.settings, "tracing_enabled", True)
    monkeypatch.setattr(rendering.Redis, "from_url", lambda url: object())
    monkeypatch.setattr(rendering, "Queue", FakeQueue)
    monkeypatch.setattr(
        rendering,
        "inject",
        lambda carrier: carrier.update(
            {"traceparent": "00-80e1afed08e019fc1110464cfa66635c-7a085853722dc6d2-01"}
        ),
    )

    rendering.dispatch_render_jobs(
        [RenderQueueItem(render_job_id="render-1", plan_json={"variant": "youtube_16x9"})]
    )

    assert enqueued[0]["func"] == "app.jobs.render_timeline_job"
    assert enqueued[0]["args"] == ("render-1", {"variant": "youtube_16x9"})
    assert enqueued[0]["kwargs"] == {
        "sources": {},
        "trace_context": {
            "traceparent": "00-80e1afed08e019fc1110464cfa66635c-7a085853722dc6d2-01"
        }
    }
