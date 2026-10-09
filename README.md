# AI Video Editor

AI Video Editor is a local-first application that turns a collection of photos,
video clips, and optional music into a reviewable short-form video story. It is
designed for personal travel and event media while keeping source files and
rendered outputs under the user's control.

## What It Does

- Imports photos and videos from local files or a user-authorized media picker.
- Evaluates technical quality, visual similarity, and editorial relevance.
- Suppresses duplicate and repetitive moments.
- Builds landscape and vertical story plans with opening, journey, highlight,
  detail, and closing beats when the available media supports them.
- Lets the user review selections, alternatives, ordering, trims, and duration.
- Supports an optional user-provided soundtrack with automatic or manual
  selection.
- Renders validated video files suitable for preview and manual publishing.

## How It Works

1. **Import** - Add media to a project from an approved source.
2. **Analyze** - Inspect media quality and extract bounded visual evidence.
3. **Curate** - Select varied, high-quality moments and organize a story.
4. **Review** - Let the user adjust selections and approve each output format.
5. **Render** - Assemble visuals, original clip audio, and optional music.
6. **Ready** - Validate the finished files and make them available to the user.

The application displays this flow for every project, including the current
stage, completed work, failures, and the next available action.

## Project Structure

- `apps/web` - project dashboard and review interface.
- `apps/api` - project, media, analysis, review, and output services.
- `apps/worker` - isolated media rendering and output validation.
- `packages/shared` - timeline schemas and shared media logic.
- `infra` - development runtime and optional infrastructure definitions.
- `docs` - product requirements, milestones, security guidance, and runbooks.

## Privacy Model

- Source media, generated videos, local databases, and credentials are excluded
  from source control.
- Provider authorization is project-scoped and uses the minimum supported media
  permissions.
- Imported media is scanned and validated before analysis or rendering.
- Media is not published automatically. The user controls where finished files
  are stored or uploaded.
- External analysis is optional; local analysis is the default workflow.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and
[docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) for operational safety
guidance.

## Getting Started

The development environment requires Docker and a recent Python and Node.js
toolchain. Create a local configuration from `.env.example`, provide only the
credentials needed for the integrations you intend to use, and run:

```bash
./scripts/start-local.sh
```

The startup command prints the address for the user interface. Runtime secrets
belong only in the ignored local configuration and must never be committed.

For the end-user workflow, see [Make a Video](docs/USE_YOUR_TRIP.md). For
development and verification, see [Local Smoke Workflow](docs/LOCAL_SMOKE_WORKFLOW.md).

## Development Checks

```bash
cd apps/api
python -m pytest

cd ../web
npm run lint
npm run build
```

Worker rendering tests require FFmpeg and can also run in the provided worker
container.

## Project Documentation

- [Product requirements](docs/PRD_TRIP_VIDEO.md)
- [Milestones](docs/MILESTONES.md)
- [Implementation status](docs/status.md)
- [Security checklist](docs/SECURITY_CHECKLIST.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Retention policy](docs/RETENTION_POLICY.md)
