# Rate Limits and Quotas

This baseline protects expensive project workflows from repeated accidental or abusive requests. It uses per-project, per-action, per-caller fixed windows with a shared Redis backend for Docker and Kubernetes deployments. A process-local memory backend remains available for isolated development and tests.

## Protected Actions

- Drive folder sync.
- Analysis and timeline regeneration.
- Render queueing.
- Retention cleanup preview and execution.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `RATE_LIMITS_ENABLED` | `true` | Enables API-side workflow rate limits. |
| `RATE_LIMIT_BACKEND` | `memory` | Selects `memory` or shared `redis` fixed windows. Docker and Kubernetes set `redis`. |
| `RATE_LIMIT_REDIS_PREFIX` | `ai-video-editor:rate-limit` | Namespaces limiter keys in the configured Redis database. |
| `EXPENSIVE_WORKFLOW_RATE_LIMIT_PER_MINUTE` | `20` | Default limit for sync, analysis, and regeneration. |
| `RENDER_RATE_LIMIT_PER_MINUTE` | `10` | Limit for render queueing. |
| `RETENTION_CLEANUP_RATE_LIMIT_PER_MINUTE` | `6` | Limit for retention cleanup preview and execution. |

Requests over the limit return `429` with a `Retry-After` header.

## Production Notes

The Redis backend increments and starts key expiry in one Lua operation, so every API replica observes the same window. If Redis is unavailable, protected workflows fail closed with `503` instead of running without a limit. Production Redis should require authentication, TLS, private networking, persistence appropriate to the deployment, and availability monitoring.

## Durable Project Quotas

The API also stores daily project quota counters in `project_usage_counters`. PostgreSQL and SQLite use atomic `INSERT ... ON CONFLICT DO UPDATE` statements with limit conditions, preventing concurrent requests from incrementing a counter beyond its configured cap.

| Metric | Setting | Default |
| --- | --- | --- |
| `analysis_requests` | `ANALYSIS_REQUESTS_PER_PROJECT_PER_DAY` | `50` |
| `render_jobs` | `RENDER_JOBS_PER_PROJECT_PER_DAY` | `40` |
| `delivered_storage_bytes` | `DELIVERED_STORAGE_BYTES_PER_PROJECT_PER_DAY` | `10737418240` (10 GiB) |
| `delivery_attempts` | `DELIVERY_ATTEMPTS_PER_PROJECT_PER_DAY` | `40` |
| `provider_cost_cents` | `PROVIDER_COST_CENTS_PER_PROJECT_PER_DAY` | `2500` ($25) |

Quota failures return `429` with the metric, limit, and current usage in the response body. Counters are consumed before the expensive work starts so repeated invalid attempts cannot bypass quota controls.

`ANALYSIS_PROVIDER_ESTIMATED_COST_CENTS_PER_REQUEST` records a deployment-configured estimate before each analysis request. Its local default is `0`; production deployments should set a conservative provider-specific amount and revise it when provider pricing changes.

Delivery attempts are counted even when delivery fails. Delivered storage is recorded once when an output first reaches `delivered`, and repeat callbacks or requests do not duplicate the storage charge. The operator-only `GET /projects/{project_id}/usage` endpoint returns the current UTC daily counters plus the bytes and count of delivered outputs that remain retained.
