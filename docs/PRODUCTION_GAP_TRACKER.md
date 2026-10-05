# Production Gap Tracker

Scope correction, 2026-10-05: production use means reliable operation on the
owner's laptop, not a hosted service. This old multi-user/cloud tracker is
historical. Active gates are L1-L6 in `PRD_TRIP_VIDEO.md` and `status.md`.

This tracker captures remaining M4 hardening work before treating the platform as production-ready for multi-user or client-critical workflows.

| Area | Priority | Status | Acceptance Signal |
| --- | --- | --- | --- |
| Real source-media editing | P0 | Blocked: placeholder renderer | Five or more actual images plus a video produce playable edits containing their source content and clip audio. |
| Usable trip workflow | P0 | Missing integration | Upload or authorized Drive sync proceeds through scan, staging, composition, and authenticated preview/download. |
| RBAC | P0 | Complete | Validated OIDC users, scoped orchestrators/workers, owner-managed direct/team membership, audited policy checks, and role-matrix tests protect project operations. |
| Rate limits and quotas | P0 | Complete | Shared Redis windows and atomic database quotas reject abusive or runaway requests by caller and project across API replicas. |
| Cost controls | P0 | Complete | Analysis, render, delivered storage, delivery attempts, and estimated provider spend are tracked and capped per project with operator summaries. |
| n8n access control | P0 | Deployment-owned | n8n is behind SSO, VPN, or private network access with encrypted credentials. |
| Provider-native retention deletion | P1 | Planned | Drive and S3 due cleanup can be executed or reconciled safely with audit evidence. |
| Production renderer hardening | P1 | In progress | Renderer has real workload tests, resource limits, timeout handling, and reproducible output packages. |
| Full deployment reference | P1 | In progress | Kubernetes reference includes private monitoring services, authenticated Collector ingress, health checks, resource limits, and secret wiring; autoscaling and a complete environment deployment remain. |
| Observability | P1 | Complete | Prometheus metrics and alerts, structured logs, privacy-safe traces, Collector boundaries, private scrape configuration, and a provisioned operations dashboard cover core workflows. |
| Backup and restore | P1 | Planned | Database and private metadata backups have tested restore procedures. |
| Data retention automation | P1 | In progress | Staged and local-private delivered output cleanup is automated; provider-backed cleanup is reconciled. |
| Security review | P1 | Complete | Threat model, OAuth and secret-handling review, clean application audits, clean fixable high/critical image scans, and CI security gates are documented. |
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
