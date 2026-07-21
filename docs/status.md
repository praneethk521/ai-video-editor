# Status

Last updated: 2026-07-16

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

## Verification

- API tests: passed locally (`17 passed`).
- Worker tests: passed locally (`4 passed`).
- Ruff checks: passed locally.
- Web build: passed locally with Next.js production build.

## Next

- Add version tagging guidance for MVP releases.
