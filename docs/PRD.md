# Product Requirements Document

## Objective

Build a secure AI video editing automation platform that ingests private media, analyzes it, generates edit plans, renders YouTube-ready landscape videos plus vertical Shorts/Reels variants, and stores outputs privately for manual upload.

## Non-Goals

- No automatic publishing to YouTube, Instagram, TikTok, or public CDNs.
- No public media URLs.
- No execution of user-provided scripts.
- No copyrighted music sourcing unless a user provides licensed assets.

## Primary Users

- Creators and teams that keep source media in private Google Drive folders.
- Operators who need repeatable private edit workflows with auditability.

## Core Workflow

1. User creates a project.
2. User connects a private Google Drive folder with OAuth read-only scope.
3. System validates media MIME type, size, duration, malware scan status, and private locator.
4. Analysis creates searchable metadata and highlight rankings.
5. Storytelling and editing agents create deterministic timeline JSON.
6. User may regenerate a plan before rendering.
7. Worker renders 1920x1080 and 1080x1920 outputs.
8. Review validates outputs and creates a manual upload package.
9. Outputs are saved privately to Drive or private S3.

## Functional Requirements

- React/Next.js dashboard.
- FastAPI backend with authenticated endpoints.
- Self-hosted n8n orchestration.
- MCP tools for safe internal operations.
- PostgreSQL data model for users, projects, assets, analysis, plans, jobs, outputs, audit logs, and OAuth connections.
- Redis-backed queue path for rendering.
- Docker Compose for local development.
- Kubernetes/ECS-ready production deployment path.

## Security Requirements

- GitHub repository may be public or private, but must never contain secrets, raw media, private outputs, or local environment files.
- No committed secrets.
- Least-privilege Google OAuth scopes.
- Encrypted credentials and media at rest.
- Temporary signed URLs only when needed.
- Structured logs with sensitive data redaction.
- Authenticated endpoints, RBAC, audit logs, upload validation, malware scanning, rate limits, worker isolation, and cleanup.

## Acceptance Criteria

- A developer can run the stack locally from the README.
- Authenticated user can create a project.
- Private Drive folder connection is recorded without storing or logging raw folder URLs.
- Media ingest rejects public URLs and unsafe filenames.
- Analysis creates timeline plans for long-form and short-form.
- Render jobs are queued for both variants.
- Output metadata remains private and manual-upload only.
- CI runs tests.
