# Observability

The platform exposes Prometheus-compatible operational metrics without using project IDs, user IDs, tokens, filenames, or private media locators as labels.

## API Metrics

`GET /metrics` requires a global service token with the `metrics` scope or an `admin`, `internal`, or `orchestrator` super-scope. Project-scoped service tokens are rejected because the endpoint contains platform-wide signals.

| Metric | Purpose |
| --- | --- |
| `ai_video_editor_api_http_requests_total` | HTTP request counts by method, normalized route template, and status. |
| `ai_video_editor_api_http_request_duration_seconds` | HTTP latency histogram by method and normalized route template. |
| `ai_video_editor_workflow_events_total` | Ingest, Drive sync, analysis, render, delivery, malware scan, and retention outcomes. |
| `ai_video_editor_rate_limit_decisions_total` | Allowed, limited, and backend-error decisions by backend and action. |
| `ai_video_editor_quota_decisions_total` | Allowed, denied, and unlimited quota decisions by metric. |
| `ai_video_editor_render_queue_depth` | Current RQ render queue depth. |
| `ai_video_editor_dependency_up` | Redis rate-limit and render-queue availability observed during collection. |

Set `METRICS_ENABLED=false` to return `404` from the API endpoint.

## Worker Metrics

The worker serves metrics on `WORKER_METRICS_PORT`, default `9100`.

| Metric | Purpose |
| --- | --- |
| `ai_video_editor_worker_render_jobs_total` | Render job outcomes by bounded output variant. |
| `ai_video_editor_worker_render_duration_seconds` | Render duration histogram by bounded output variant. |
| `ai_video_editor_worker_callbacks_total` | Running, completion, and failure callback outcomes. |

RQ runs jobs in child processes. Set `PROMETHEUS_MULTIPROC_DIR` to a writable worker-local path so child process metrics are aggregated by the parent scrape server. Docker and Kubernetes use `/tmp/ai-video-editor/prometheus`.

The worker metrics port is unauthenticated and must remain on a private container, pod, or service network. The Kubernetes manifest exposes it through pod scrape annotations only.

## Prometheus Scraping

Configure the API bearer token through a mounted secret file rather than inline configuration.

```yaml
scrape_configs:
  - job_name: ai-video-api
    metrics_path: /metrics
    bearer_token_file: /etc/prometheus/secrets/ai-video-metrics-token
    static_configs:
      - targets: [ai-video-api:8000]
  - job_name: ai-video-worker
    metrics_path: /metrics
    static_configs:
      - targets: [ai-video-worker:9100]
```

Load the versioned rules from `infra/observability/prometheus-alerts.yaml` through the Prometheus `rule_files` setting. The rules cover sustained API errors and latency, dependency outages, render backlog and failures, render latency, delivery failures, quota pressure, and rate-limit backend errors.

Validate rule changes before deployment:

```bash
docker run --rm --entrypoint promtool \
  -v "$PWD/infra/observability:/etc/ai-video-observability:ro" \
  prom/prometheus:v3.13.1 \
  check rules /etc/ai-video-observability/prometheus-alerts.yaml
```

## Distributed Tracing

Tracing is opt-in and disabled by default. The API and worker export OTLP/HTTP spans to an OpenTelemetry Collector when `TRACING_ENABLED=true`.

| Setting | Purpose |
| --- | --- |
| `TRACING_ENABLED` | Enables API and worker tracing. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector trace endpoint, default `http://otel-collector:4318/v1/traces`. |
| `OTEL_EXPORTER_OTLP_HEADERS` | Comma-separated, URL-encoded exporter headers. Store this value in a secret. |
| `OTEL_TRACE_SAMPLE_RATIO` | Parent-based root trace sampling ratio from `0` to `1`, default `0.1`. |
| `OTEL_SERVICE_NAME` | Distinguishes `ai-video-editor-api` from `ai-video-editor-worker`. |

API traces include route-template inbound requests plus explicit analysis-provider, render-enqueue, and output-delivery spans. W3C trace context is injected into RQ job kwargs so the worker render and bounded callback spans remain in the same distributed trace. The implementation does not use generic HTTP client instrumentation, so provider URLs and callback paths are not attached to spans.

Trace attributes and exception events must never include request or response bodies, captured headers, filenames, project or asset IDs, private locators, Drive folder/file IDs, S3 keys, OAuth data, raw URL paths, query strings, or exception messages. API spans use matched route templates, workflow attributes use bounded values, and failures export only the exception class.

Route OTLP traffic through an OpenTelemetry Collector in production rather than exposing a trace backend directly to application containers. Keep exporter authentication headers in the API and worker secret stores.

## Operational Signals

Monitor sustained HTTP `5xx` rates, p95 request and render latency, render queue growth, dependency availability, failed analysis or delivery events, denied quotas, rate-limit backend errors, and failed worker callbacks. Tune the versioned alert thresholds after collecting representative production traffic.
