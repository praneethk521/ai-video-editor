# Rate Limits and Quotas

This baseline protects expensive project workflows from repeated accidental or abusive requests. It uses per-project, per-action, per-caller fixed windows in API memory.

## Protected Actions

- Drive folder sync.
- Analysis and timeline regeneration.
- Render queueing.
- Retention cleanup preview and execution.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `RATE_LIMITS_ENABLED` | `true` | Enables API-side workflow rate limits. |
| `EXPENSIVE_WORKFLOW_RATE_LIMIT_PER_MINUTE` | `20` | Default limit for sync, analysis, and regeneration. |
| `RENDER_RATE_LIMIT_PER_MINUTE` | `10` | Limit for render queueing. |
| `RETENTION_CLEANUP_RATE_LIMIT_PER_MINUTE` | `6` | Limit for retention cleanup preview and execution. |

Requests over the limit return `429` with a `Retry-After` header.

## Production Notes

The in-memory limiter is intentionally small and local-friendly. Multi-instance production deployments should move counters to Redis, an API gateway, or a service mesh rate-limit provider so limits apply across all API replicas.

## Durable Project Quotas

The API also stores daily project quota counters in `project_usage_counters`.

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

## Remaining Production Work

The in-memory request limiter and read-then-update database quota counters are suitable for local and single-replica deployments. Multi-replica production should use Redis-backed fixed windows and atomic database counter updates so concurrent requests cannot bypass limits.
