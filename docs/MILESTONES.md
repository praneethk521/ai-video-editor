# Milestones

## Active Laptop Roadmap (2026-10-05)

The authoritative scope is `PRD_TRIP_VIDEO.md`: laptop-only execution, Google
Photos albums, local intelligent curation and review. No public/cloud deployment.
L1: real-render validation; L2: bounded curation; L3: Photos Picker import;
L4: local semantic model; L5: selection review; L6: real large-album acceptance.
See `status.md` for live progress. The M0-M4 sections below are historical work,
not the current release checklist.

## M0 - Secure Foundation

Status: Completed

- Repository structure.
- API authentication and OpenAPI.
- Core database schema.
- Audit log baseline.
- Private locator validation.
- Docker Compose.
- CI tests.

## M1 - Google Drive OAuth and Ingestion

Status: Partial; reopened after 2026-10-05 product readiness review

- Remaining: fixed registered callback, access-token refresh, automatic scan and
  staging integration, and authenticated real-folder acceptance evidence.

- Full OAuth callback.
- Token encryption in secret manager or encrypted DB field.
- Drive folder traversal with least-privilege scopes.
- Malware scanning with ClamAV or provider scanner.
- Media checksum and duplicate detection.

## M2 - AI Analysis and Planning

Status: In progress

- Configurable model providers.
- External private analysis provider adapter.
- Scene detection, blur detection, face/subject metadata, audio quality.
- Storytelling agent prompts.
- Plan regeneration and human review.
- JSON schema validation and versioning.

## M3 - Rendering and Review

Status: In progress

Product blocker: current worker writes placeholder bytes or a black/silent MP4;
source retrieval and actual media composition are not implemented. Existing smoke
tests do not demonstrate a usable edit. See `TRIP_VIDEO_READINESS.md`.

- FFmpeg/Remotion production renderer.
- Captions, transitions, audio normalization, vertical subject crop.
- Output validation for resolution, duration, audio stream, subtitles, black-frame signals, delivery target, and corruption.
- Private Drive/S3 output delivery state recording.
- Real Drive/S3/local private output delivery adapters.

## M4 - Production Hardening

Status: In progress

- SSO/VPN-protected n8n.
- RBAC (complete).
- Rate limits and quotas.
- Cost controls per project.
- Full Kubernetes/ECS deployment.
- Prometheus metrics and alerts plus privacy-safe OpenTelemetry traces.
- Threat model, dependency/OAuth review, secret scan, and container vulnerability gates (complete).
- Branch protection and required PR reviews.
- Production gap tracking with exit criteria.
