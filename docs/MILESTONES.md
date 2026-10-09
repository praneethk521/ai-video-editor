# Milestones

## Active Laptop Roadmap (2026-10-09)

The authoritative scope is `PRD_TRIP_VIDEO.md`: laptop-only execution, Google
Photos albums, local intelligent curation and review. No public/cloud deployment.
L1: real-render validation; L2: bounded curation; L3: Photos Picker import;
L4: local semantic model; L5: selection review; L6: real large-album acceptance.
See `status.md` for live progress. The M0-M4 sections below are historical work,
not the current release checklist.

L4 has a working Ollama/Qwen 2.5 VL baseline with strict local inference,
confidence handling and semantic story diversity. Portrait/eye-state fixtures,
multi-frame semantic video scoring and large-album measurements remain.

Current gate status: L1-L6 have a working owner-trip path. L7 story intelligence,
L8 soundtrack selection/mixing, and L9 derived pipeline progress are the active
product milestones. L8 and L9 have working baselines; semantic repetition,
multi-frame video evidence, and owner quality acceptance remain active.
See `status.md` for the exact acceptance evidence.

## L7 - Story Intelligence

Status: In progress

- Suppress exact, visual, and excessive semantic repetition across photos and videos.
- Use multi-frame video evidence rather than one representative frame.
- Assign opening, journey, highlight, detail/people, and closing story beats.
- Preserve chronology and explicit owner overrides.
- Report coverage, repetition suppression, confidence, and review gaps.

## L8 - Local Soundtrack

Status: Working baseline

- Accept and safely probe owner-provided audio files.
- Select the most story-relevant eligible project soundtrack by default.
- Offer manual soundtrack and no-soundtrack choices in plan review.
- Generate an arranged original local score when the user supplies no audio.
- Mute source-video audio, apply fades, and meet YouTube loudness targets.
- Validate soundtrack provenance, output audio, duration, and decode.
- Complete owner listening acceptance across all generated presets and broader
  uploaded-audio fixtures.

## L9 - Project Pipeline Experience

Status: In progress

- Derive Import → Analyze → Curate → Review → Render → Ready from durable data.
- Return current and next steps from project status.
- Show complete/current/pending/failed states responsively in the dashboard.
- Keep retries and historical failed attempts from obscuring successful outputs.

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

Historical blocker resolved: the worker now composes actual source media,
replaces source audio with the selected soundtrack, validates
decode/resolution/duration/audio/black frames and produces private local
landscape and vertical MP4 outputs. Transitions and face-aware vertical crops
remain future quality work; soundtrack generation and selection now have a
working baseline.

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
