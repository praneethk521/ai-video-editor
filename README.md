# AI Video Editor

Production-oriented AI video editing automation platform for private media ingestion, analysis, timeline planning, rendering, and review.

The repository is structured for secure deployment. The source code can live in a public or private GitHub repository, but real secrets, raw media, local databases, and rendered outputs must stay private and untracked. It does not publish to YouTube, Instagram, or any public destination. Outputs are stored privately and are intended for manual upload only.

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

1. Copy `.env.example` to `.env` and set `API_TOKEN`, `TOKEN_ENCRYPTION_KEY`, plus provider credentials.
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
- Traverse connected Google Drive folders and skip duplicate media by checksum.
- Stream private Drive media through ClamAV before analysis/rendering.
- Generate privacy-safe scene, audio, subject, and highlight metadata through a configurable analysis provider.
- Optionally call an external private HTTP analysis provider with sanitized metadata only by default.
- Check analysis provider health and retry transient external analysis failures.
- Open a lightweight circuit breaker after repeated external analysis failures.
- Expose internal analysis provider metrics for requests, retries, failures, circuit opens, and latency.
- Generate deterministic timeline plans from analysis metadata.
- Review, reject, regenerate, and approve timeline plans before rendering.
- Use the dashboard project console to run the private workflow and review plans.
- Queue render jobs for landscape and vertical outputs.
- Validate rendered outputs with ffprobe, subtitle signals, black-frame scan signals, and private delivery targets.
- Register private output metadata.
- Record private output delivery state for Drive, S3, or local private targets.
- Deliver staged private outputs to Google Drive, private S3, or local private storage adapters.
- Optionally clean up staged render files after confirmed private output delivery.
- Optionally auto-deliver outputs when render completion callbacks arrive.
- Audit user actions without logging secrets, tokens, public URLs, or file contents.

## Security Defaults

- No real `.env` files are committed.
- OAuth scope defaults to Google Drive read-only.
- Drive output delivery requires an OAuth token with write permission and a private output folder.
- Public media URLs are rejected.
- Filenames are sanitized and path traversal is blocked.
- Upload types and sizes are validated before metadata persistence.
- All API endpoints require bearer authentication.
- Audit logs intentionally store metadata, not sensitive payloads.
- Workers are intended to run in locked-down containers with CPU, memory, disk, and duration limits.

## GitHub Setup

Create this repository and enable:

- Branch protection on `main`.
- Required PR reviews.
- GitHub secret scanning and push protection.
- Dependabot alerts and updates.
- GitHub Actions OIDC for cloud deploy credentials.

For public repositories, keep using `.env.example` only and never commit source media, rendered outputs, local databases, or provider credentials. See `docs/SECURITY_CHECKLIST.md` for the full checklist and `docs/BRANCH_PROTECTION.md` for required checks.

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
- Output delivery deployment: `docs/OUTPUT_DELIVERY_DEPLOYMENT.md`
- Local smoke workflow: `docs/LOCAL_SMOKE_WORKFLOW.md`
- Retention policy: `docs/RETENTION_POLICY.md`
- Branch protection: `docs/BRANCH_PROTECTION.md`
- Release readiness: `docs/RELEASE_READINESS.md`
