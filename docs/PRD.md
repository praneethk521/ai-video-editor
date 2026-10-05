# Product Requirements Document

## Objective

Execution plan for the usable local trip-video release:
[PRD_TRIP_VIDEO.md](PRD_TRIP_VIDEO.md), including file-level work and acceptance gates.

Build a laptop-only trip video editor that imports owner-selected Google Photos
album media, chooses strong non-duplicate photos and video highlights using local
analysis, supports human review, and renders concise private videos locally.
The linked trip PRD is authoritative where older infrastructure documents differ.

## Non-Goals

- No automatic publishing to YouTube, Instagram, TikTok, or public CDNs.
- No hosted website, AWS, or other remote application deployment.
- No include-everything concatenation or external AI uploads by default.
- No public media URLs.
- No execution of user-provided scripts.
- No copyrighted music sourcing unless a user provides licensed assets.

## Primary Users

- The laptop owner, whose trip albums are in Google Photos.
- Local uploads/album exports for offline work; Google Drive is a separate optional source.

## Core Workflow

1. User creates a project.
2. User authorizes Google Photos Picker and selects their album's media.
3. System validates media MIME type, size, duration, malware scan status, and private locator.
4. Local content analysis ranks quality, duplicate alternatives, scenery and highlights.
5. Selection builds a concise story within the user's duration budget.
6. User reviews selections, reasons, alternatives and trims before approving.
7. Worker renders 1920x1080 and 1080x1920 outputs.
8. Review validates outputs and creates a manual upload package.
9. Outputs are saved privately on this laptop for playback and manual export.

## Functional Requirements

- React/Next.js dashboard.
- FastAPI backend with authenticated endpoints.
- Self-hosted n8n orchestration.
- MCP tools for safe internal operations.
- PostgreSQL data model for users, projects, assets, analysis, plans, jobs, outputs, audit logs, and OAuth connections.
- Redis-backed queue path for rendering.
- Docker Compose for local development.
- Laptop-only runtime; cloud deployment references are legacy, not release work.

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
- Google Photos selection imports media without logging tokens or private album URLs.
- Large albums yield short curated videos with quality/duplicate decisions and user overrides.
- Media ingest rejects public URLs and unsafe filenames.
- Analysis creates timeline plans for long-form and short-form.
- Render jobs are queued for both variants.
- Output metadata remains private and manual-upload only.
- CI runs tests.
