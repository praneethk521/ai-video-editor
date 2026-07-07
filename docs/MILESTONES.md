# Milestones

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

Status: Completed

- Full OAuth callback.
- Token encryption in secret manager or encrypted DB field.
- Drive folder traversal with least-privilege scopes.
- Malware scanning with ClamAV or provider scanner.
- Media checksum and duplicate detection.

## M2 - AI Analysis and Planning

Status: In progress

- Configurable model providers.
- Scene detection, blur detection, face/subject metadata, audio quality.
- Storytelling agent prompts.
- Plan regeneration and human review.
- JSON schema validation and versioning.

## M3 - Rendering and Review

Status: Planned

- FFmpeg/Remotion production renderer.
- Captions, transitions, audio normalization, vertical subject crop.
- Output validation for resolution, duration, audio, subtitles, black frames, and corruption.
- Private Drive/S3 output delivery.

## M4 - Production Hardening

Status: Planned

- SSO/VPN-protected n8n.
- RBAC.
- Rate limits and quotas.
- Cost controls per project.
- Full Kubernetes/ECS deployment.
- Branch protection and required PR reviews.
