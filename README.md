# AI Video Editor

Production-oriented AI video editing automation platform for private media ingestion, analysis, timeline planning, rendering, and review.

The repository is structured for a private GitHub repository and secure deployment. It does not publish to YouTube, Instagram, or any public destination. Outputs are stored privately and are intended for manual upload only.

## Architecture

- `apps/web`: Next.js dashboard.
- `apps/api`: FastAPI backend with authentication, audit logs, PostgreSQL models, and OpenAPI docs.
- `apps/worker`: isolated Python video worker using timeline JSON as the source of truth.
- `mcp/media-tools-server`: internal MCP-style tools exposed to n8n agents.
- `workflows/n8n`: self-hosted n8n workflow exports.
- `packages/shared`: shared JSON schemas and Python validation helpers.
- `infra`: Docker Compose, Kubernetes, and Terraform starter assets.
- `docs`: PRD, milestones, status, runbooks, and security checklist.

## Local Quickstart

1. Copy `.env.example` to `.env` and set `API_TOKEN` plus provider credentials.
2. Start services:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

3. Open the API docs at `http://localhost:8000/docs`.
4. Use the bearer token from `API_TOKEN` for all API calls.

## API Slice

The current executable slice supports:

- Create projects.
- Connect a private Google Drive folder record with least-privilege scope metadata.
- Validate and register uploaded or Drive media assets.
- Generate deterministic analysis metadata and timeline plans.
- Queue render jobs for landscape and vertical outputs.
- Register private outputs.
- Audit user actions without logging secrets, tokens, public URLs, or file contents.

## Security Defaults

- No real `.env` files are committed.
- OAuth scope defaults to Google Drive read-only.
- Public media URLs are rejected.
- Filenames are sanitized and path traversal is blocked.
- Upload types and sizes are validated before metadata persistence.
- All API endpoints require bearer authentication.
- Audit logs intentionally store metadata, not sensitive payloads.
- Workers are intended to run in locked-down containers with CPU, memory, disk, and duration limits.

## Private GitHub Setup

Create this repository as private and enable:

- Branch protection on `main`.
- Required PR reviews.
- GitHub secret scanning and push protection.
- Dependabot alerts and updates.
- GitHub Actions OIDC for cloud deploy credentials.

See `docs/SECURITY_CHECKLIST.md` for the full checklist.

## Tests

```bash
cd apps/api
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Status Tracking

- Product requirements: `docs/PRD.md`
- Milestones: `docs/MILESTONES.md`
- Current implementation status: `docs/status.md`

