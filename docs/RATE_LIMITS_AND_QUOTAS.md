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

Quota enforcement should be expanded next to track project-level usage totals for analysis requests, render jobs, delivered storage, and provider delivery attempts.

## Durable Project Quotas

The API also stores daily project quota counters in `project_usage_counters`.

| Metric | Setting | Default |
| --- | --- | --- |
| `analysis_requests` | `ANALYSIS_REQUESTS_PER_PROJECT_PER_DAY` | `50` |
| `render_jobs` | `RENDER_JOBS_PER_PROJECT_PER_DAY` | `40` |

Quota failures return `429` with the metric, limit, and current usage in the response body. Counters are consumed before the expensive work starts so repeated invalid attempts cannot bypass quota controls.

Next quota slices should add delivered storage bytes, delivery attempts, provider-cost estimates, and operator-visible usage summaries.
