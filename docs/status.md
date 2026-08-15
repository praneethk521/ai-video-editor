# Status

Last updated: 2026-08-15

## Completed

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

## Verification

- API tests: passed locally (`40 passed`).
- Worker tests: passed locally (`6 passed`).
- Ruff checks: passed locally.
- Web build: passed locally with Next.js production build.
- Base and observability Docker Compose expansion: passed locally.
- Kubernetes and observability YAML plus Grafana dashboard JSON validation: passed locally.
- Prometheus config and alert rules: passed `promtool` validation (`9 rules found`).
- Local Collector configs: passed OpenTelemetry Collector `validate` on `0.158.0`.
- End-to-end telemetry check: a test span crossed the Collector into Jaeger with private URL and exception-message fields removed.
- Grafana provisioning check: Prometheus and Jaeger data sources plus the nine-panel operations dashboard loaded successfully.

## Next

- Add encrypted PostgreSQL backup and restore automation with a scheduled Kubernetes job, retention controls, and a documented restore drill.
