# Status

Last updated: 2026-10-06

## Authoritative Scope

The app runs only on the owner's laptop. GitHub stores code, never media or
credentials. Google Photos albums are the required primary source; Drive folders
are different and optional. A curated short story, not an all-files montage, is
the goal. See [PRD_TRIP_VIDEO.md](PRD_TRIP_VIDEO.md) for the complete contract.
AWS, hosted websites, Kubernetes and cloud deployment are out of scope.

## Active Progress

| Gate | Status | Evidence / Remaining Work |
| --- | --- | --- |
| L1 Real local rendering | Working local baseline | Genuine HTTP uploads, ClamAV scans, Redis/RQ jobs, actual-source FFmpeg, original clip audio, private preview/download. JPEG/video color normalization and low-luma blue false-positive validation fixed. |
| L2 Curation foundation | Implemented, limited | Local decoded-frame sharpness/exposure heuristics, exact/conservative near-duplicate grouping, bounded quality selection, sampled video start, reasons, target-duration regeneration, approval invalidation. Not a semantic model. |
| L3 Google Photos | Implemented; live consent pending | Project-scoped OAuth with PKCE/one-use state, encrypted token/session state, refresh, Picker create/poll/delete, pagination, trusted-host byte downloads, one-item resumable scan/staging, skip/cancel/revoke, progress UI and tests. Needs owner OAuth credentials and a real album acceptance run. |
| L4 Local semantic model | Not implemented | Eye-state, occlusion, point-of-interest relevance, scene/event diversity and robust video highlight quality need a chosen local model and evaluation. Unknown fields stay unknown. |
| L5 Selection review | Partial | Duration controls, decision reasons and plan approval exist. Thumbnails, duplicate comparison, per-item override/trim, and all-low-quality review remain. |
| L6 Laptop acceptance | Partial | Yellowstone pipeline works; no real private Photos album or 500-file media workload tested. Phone formats/HDR, resumability/cancellation and disk limits remain. |

## Current Validation

- API suite: 97 passed. Worker suite: 10 passed in the host environment; three
  real FFmpeg tests are skipped there because FFmpeg is supplied by the worker
  container. The current container-backed run passed all 13, including real
  image/video/audio rendering and black/corrupt-output rejection.
- Ruff, TypeScript and Next.js production build pass. Desktop video decodes and
  the selection/duration UI fits a 390px mobile viewport without horizontal overflow.
- Latest real demo project: `47a3dfd7-56c7-43f7-8ac3-17912cd716cf`.
- Real exports: 26s landscape, 21s vertical, H.264/AAC. Waterfall trim starts at
  29.33s based on sampled technical quality. All six photos remain because the
  small sample has no detected duplicate/quality exclusion and fits the budget.
- Outputs, plans and report: ignored `outputs/Yellowstone/<project-id>/`.
- Visual frame contact sheet confirms the six photos and waterfall. This is not
  evidence of eye-state, landmark understanding, or subjective story quality.
- Local source analysis never calls an external provider. Metadata-only legacy
  providers remain for non-staged fixture/legacy paths; not Photos production support.
- 500-candidate selection is unit-tested, not a measured 500-file import benchmark.
- Git history: 53 commits scanned with Gitleaks; one reviewed example-placeholder
  false positive narrowly fingerprint-allowlisted. No real secrets found.
- Trivy working-tree secret scan: no findings. Staged changes are scanned before
  check-in; CI now includes full-history Gitleaks as well.
- Media and outputs remain gitignored. Docker context now excludes private data,
  credentials, local databases and model caches as well.

## Next Work (In Order)

1. Configure the owner's local Google OAuth client, complete interactive Picker
   consent, and validate a real selected album end to end. Do not reuse Drive
   scopes as Photos authorization or make albums public.
2. Choose/evaluate a local vision model for eyes, portrait quality, scene meaning,
   landmarks and highlights; add event diversity under the duration budget.
3. Build thumbnail/duplicate review, include/exclude/pin and trim overrides;
   preserve uncertain/low-quality memories for manual decisions.
4. Queue/cache analysis, resume/cancel imports, enforce total disk quotas; test
   phone formats, rotation/HDR and a large mixed album on this laptop.
5. Finish local startup/backup/cleanup UX and owner-approved trip acceptance.

## Historical Infrastructure Work

The list below records previous implementation, not current release completion.
Cloud deployment artifacts are retained as history but are not active work.

- Created monorepo structure.
- Added FastAPI API with authenticated project lifecycle endpoints.
- Added SQLAlchemy models and SQL migration for required entities.
- Added audit logging with sensitive metadata redaction.
- Added private media locator, MIME type, upload size, and filename validation.
- Added deterministic analysis and timeline plan generation.
- Added worker timeline validation and private output package generation.
- Added MCP-style internal tools for n8n orchestration.
- Added n8n workflow export.
- Added Docker Compose local stack.
- Added Kubernetes starter manifests.
- Added GitHub Actions CI and Dependabot.
- Added PRD, milestones, and security checklist.
- Wired API render job creation to Redis/RQ dispatch.
- Added authenticated internal worker callbacks for render running, completion, and failure states.
- Persisted private output metadata and manual upload packages when worker renders complete.
- Updated repository security guidance for a public-code, private-media model.
- Added Google OAuth authorization URL generation, callback handling, and encrypted token storage.
- Added malware scan status recording and blocked analysis until media assets are marked clean.
- Added Drive folder traversal using connected OAuth tokens and checksum-based duplicate detection.
- Added ClamAV-backed private Drive media scanning through authenticated internal scan endpoints.
- Added timeline plan listing, rejection, regeneration, approval, and render gating on approved plans.
- Added dashboard project console for Drive sync, analysis, plan review, approval, rendering, and outputs.
- Added ffprobe output validation metadata for rendered video resolution, duration, audio stream, and corruption checks.
- Added configurable analysis provider selection with privacy-safe scene, audio, subject, and highlight metadata.
- Added analysis review API and dashboard summary panel.
- Added external HTTP analysis provider adapter with opt-in private locator sharing.
- Added analysis provider health checks, transient retry/backoff, and structured provider failures.
- Added lightweight circuit-breaker behavior for repeated external analysis provider failures.
- Added internal analysis provider metrics for requests, retries, failures, health checks, circuit opens, and latency.
- Added render validation signals for embedded subtitles, planned captions, black frames, and private delivery targets.
- Added private output delivery state recording for Drive, S3, and local private locators.
- Added real Drive, S3, and local private output delivery adapters for staged private render files.
- Wired Docker Compose and Kubernetes for shared render staging between worker and API delivery.
- Added CI validation for Docker Compose and Kubernetes manifests.
- Added production output delivery deployment notes for Drive write scopes, S3 IAM, and shared staging storage.
- Added opt-in automatic output delivery on successful render completion.
- Added dashboard delivery controls for completed private outputs.
- Added delivery failure recording, retry support, and dashboard error details.
- Added end-to-end local smoke workflow documentation for project creation through private delivery.
- Added automated smoke coverage for the private delivery lifecycle.
- Added optional staged output cleanup after confirmed private delivery.
- Added retention policy documentation for delivered private output artifacts.
- Added retention metadata and lifecycle tags to delivered output adapters.
- Added operator-facing retention status display for delivered outputs.
- Added project-level output retention report API for delivered output review.
- Added dashboard action to load the output retention report.
- Added delivered-output retention cleanup workflow for due local-private artifacts.
- Added dashboard action to preview and run due retention cleanup.
- Added retention cleanup operations to the runbook.
- Added scripted smoke coverage for retention cleanup endpoints.
- Added CI shell linting for smoke scripts.
- Added branch protection and required check documentation for the public repo.
- Added release readiness checklist for the current MVP slice.
- Added release notes template for MVP deployments.
- Added version tagging guidance for MVP releases.
- Added deploy and rollback checklist for MVP releases.
- Added production gap tracker for M4 hardening work.
- Added RBAC design notes for the next production hardening slice.
- Added RBAC schema migration draft.
- Added RBAC authorization helper skeleton.
- Wired project read endpoints to RBAC viewer checks while keeping mutating project actions owner-only.
- Wired user-facing project mutation endpoints to explicit RBAC policies for operator, reviewer, owner, and admin roles.
- Added scoped service-token authorization for internal worker and orchestration callbacks.
- Added project authorization outcome audit events and dashboard role-aware controls.
- Added configurable project workflow rate limits for sync, analysis, regeneration, rendering, and retention cleanup.
- Added durable daily project quota counters for analysis requests and render jobs.
- Added durable delivered-storage, delivery-attempt, and estimated provider-cost accounting with configurable project caps.
- Added operator-only project usage summaries with current retained private-output storage totals.
- Added a role-aware dashboard usage panel with daily limit progress and automatic workflow refreshes.
- Added a shared Redis fixed-window rate-limit backend with atomic expiry, fail-closed outage handling, and deployment wiring.
- Made PostgreSQL and SQLite project quota increments atomic under concurrent requests.
- Added authenticated Prometheus-compatible API metrics for HTTP, workflows, quotas, rate limits, dependencies, and render queue depth.
- Added RQ multiprocess worker metrics for render outcomes, duration, and API callbacks with private scrape deployment wiring.
- Added observability deployment guidance and runbook triage procedures with privacy-safe label requirements.
- Added opt-in OpenTelemetry tracing for normalized API requests, analysis providers, RQ enqueue and worker render spans, callbacks, and private output delivery.
- Added W3C trace-context propagation through RQ using route-template and bounded workflow spans that omit URLs, queries, headers, identifiers, exception messages, and private locators.
- Added nine Prometheus alert rules for API reliability, dependencies, queue backlog, rendering, delivery, quota pressure, and rate-limit backend failures.
- Added CI validation for Prometheus rules plus tracing configuration for Docker Compose and Kubernetes workloads.
- Added a Compose observability overlay with a privacy-filtering OpenTelemetry Collector, Prometheus, Jaeger, and provisioned Grafana data sources.
- Added a nine-panel Grafana operations dashboard for API health, dependencies, queue state, rendering, workflow failures, quotas, and rate limits.
- Added an authenticated two-replica Kubernetes Collector reference with health probes, resource limits, private ingress policy, and secret-backed exporter configuration.
- Added Prometheus Operator ServiceMonitors for authenticated API, private worker, and Collector metrics scraping.
- Added CI validation for base and observability Compose expansion, Collector configs, Prometheus config and rules, Grafana provisioning YAML, and dashboard JSON.
- Added issuer-, audience-, signature-, algorithm-, expiration-, and required-claim validation for OIDC user identities with trusted JWKS key rotation.
- Added stable OIDC user provisioning, email collision protection, deployment-admin claim mapping, and a production fail-closed authentication guard.
- Disabled the legacy shared service-token bridge in production while retaining explicit local smoke compatibility.
- Added stored orchestrator principals with project-scoped operator access for n8n without granting human or owner administration rights.
- Added audited owner-managed direct project memberships, project team assignments, team rosters, and final-team-owner protection.
- Added a user-facing operator delivery endpoint so OIDC dashboard users no longer depend on an internal service token.
- Added server-derived project roles and project/team access management controls to the dashboard.
- Added production OIDC, service-token provisioning, Kubernetes configuration, and rollout documentation.
- Added a private-media threat model and security review with an explicit residual-risk register.
- Upgraded the web and API dependency graphs to resolve all known npm and pip audit findings at review time.
- Added explicit CORS origins, trusted hosts, browser/API security headers, and fail-closed production boundary validation.
- Disabled Google OAuth incremental grants and validate that reported token scopes exactly match the requested Drive scopes.
- Hardened API, worker, and n8n runtime references with non-root users, read-only filesystems, dropped capabilities, seccomp, bounded temporary storage, and loopback-only local ports.
- Added pinned GitHub Actions, working Python module test commands, Ruff gates, secret scanning, runtime image import checks, and Trivy image gates to CI.
- Added a root security disclosure policy for the public repository.

## Historical Verification (Before Local Curation)

- API tests: passed locally (`65 passed`).
- Worker tests: passed locally (`6 passed`).
- Ruff checks: passed locally.
- Web build: passed locally with Next.js production build.
- npm audit: no known vulnerabilities.
- API and worker `pip-audit`: no known vulnerabilities.
- Trivy repository secret scan: no findings.
- API and worker image scan: zero fixable high/critical findings after OS security upgrades; both images execute as UID/GID 10001 with read-only roots.
- Base and observability Docker Compose expansion: passed locally.
- Kubernetes and observability YAML plus Grafana dashboard JSON validation: passed locally.
- Prometheus config and alert rules: passed `promtool` validation (`9 rules found`).
- Local Collector configs: passed OpenTelemetry Collector `validate` on `0.158.0`.
- End-to-end telemetry check: a test span crossed the Collector into Jaeger with private URL and exception-message fields removed.
- Grafana provisioning check: Prometheus and Jaeger data sources plus the nine-panel operations dashboard loaded successfully.

Current priorities are the L1-L6 laptop gates above, not deployment hardening.
