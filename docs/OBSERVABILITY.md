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

## Initial Operational Signals

Monitor sustained HTTP `5xx` rates, p95 request and render latency, render queue growth, dependency availability, failed analysis or delivery events, denied quotas, rate-limit backend errors, and failed worker callbacks. Alert rules and distributed tracing remain the next observability slice.
