# Production Gap Tracker

This tracker captures remaining M4 hardening work before treating the platform as production-ready for multi-user or client-critical workflows.

| Area | Priority | Status | Acceptance Signal |
| --- | --- | --- | --- |
| RBAC | P0 | In progress | Roles restrict project, output, audit, and internal operations by user/team. |
| Rate limits and quotas | P0 | Planned | API rejects abusive or runaway requests by token, user, and project. |
| Cost controls | P0 | Planned | Analysis, render, storage, and delivery costs are tracked and capped per project. |
| n8n access control | P0 | Deployment-owned | n8n is behind SSO, VPN, or private network access with encrypted credentials. |
| Provider-native retention deletion | P1 | Planned | Drive and S3 due cleanup can be executed or reconciled safely with audit evidence. |
| Production renderer hardening | P1 | In progress | Renderer has real workload tests, resource limits, timeout handling, and reproducible output packages. |
| Full deployment reference | P1 | Planned | Kubernetes/ECS reference includes secrets, storage classes, health checks, autoscaling, and rollback notes. |
| Observability | P1 | Planned | Metrics, logs, traces, and alerts cover ingest, scan, analysis, render, delivery, retention, and queue health. |
| Backup and restore | P1 | Planned | Database and private metadata backups have tested restore procedures. |
| Data retention automation | P1 | In progress | Staged and local-private delivered output cleanup is automated; provider-backed cleanup is reconciled. |
| Security review | P1 | Planned | Threat model, dependency review, OAuth scope review, and secret-handling review are complete. |
| Load testing | P2 | Planned | Expected concurrent project, render, and dashboard workflows meet latency and reliability targets. |

## P0 Exit Criteria

- RBAC is enforced on all user-facing and internal endpoints.
- Rate limits and quotas protect analysis, render, delivery, and retention cleanup paths.
- Project-level cost controls are visible to operators.
- n8n is not publicly reachable without SSO, VPN, or equivalent private access.
- Branch protection and required CI checks are enabled on `main`.

## P1 Exit Criteria

- Provider-native retention cleanup for Drive and S3 is implemented or explicitly delegated to provider lifecycle policy with reconciliation evidence.
- Renderer hardening covers representative long-form and Shorts/Reels outputs.
- Deployment reference includes production-grade secrets, health checks, shared storage, and rollback steps.
- Observability covers API, worker, queue, delivery, and retention workflows.
- Backup and restore are tested.

## Review Cadence

Review this tracker before every MVP release and after any incident involving:

- private media exposure
- failed delivery
- failed retention cleanup
- runaway render or provider cost
- worker isolation failure
- authentication or authorization bypass
