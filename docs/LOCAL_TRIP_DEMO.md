# Local Trip Demo

This app runs on this laptop. Google Photos import is implemented and awaits a
real owner-album acceptance run; semantic selection is still being built. See
`status.md`. No AWS or public website is needed.

## Start the Local Runtime

From the repository root:

```bash
docker compose -f infra/docker/docker-compose.local.yml up -d --build
cd apps/web
npm ci --ignore-scripts
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 npm run dev -- --hostname 127.0.0.1 --port 3001
```

Docker Desktop must be running. ClamAV's first signature download can take a few
minutes. API is loopback-only on 8001; web is loopback-only on 3001. Redis/ClamAV
have no published host ports. Docker stores the private local media/database
volume on this laptop. Protect the disk with encryption; gitignore is not encryption.

The isolated demo uses `dev-only-token`, a public non-secret test default, unless
`API_TOKEN` is set in the local environment. Replace it with a private local token
before using personal media. Do not expose these services to a network.

## Browser Workflow

1. Open http://localhost:3001/ and enter the API URL and local bearer token.
2. Enter a project name and click New. Select local photos/videos and Upload.
3. Analyze. Actual staged bytes are inspected locally; no cloud AI call occurs.
4. Review plans and Selection decisions. Change duration targets and Regenerate
   when needed, then approve both formats and Render.
5. Status polls during rendering. Under Outputs, Preview fetches the video using
   authentication; Download MP4 saves it locally. No credentials enter URLs.

Current curation is technical-quality screening, not semantic AI. Low-detail,
dark/bright items are withheld for future manual review; noisy photos can fool
sharpness metrics. Near-duplicate grouping is conservative whole-image comparison.
Eyes, identity, landmarks, storytelling, face-aware crop, music and transitions
are not implemented. All-low-quality input currently returns a review-required
error; a manual override UI is still pending. Keep originals unchanged.

## Repeat the Yellowstone Acceptance Run

With Python and API dependencies installed:

```bash
python scripts/download-yellowstone.py
python scripts/demo-local-media.py
```

The script auto-approves test plans; it is a demo harness, not a substitute for
reviewing a personal album. NPS inputs/credits live under ignored
`media/Yellowstone/`. Each run creates a new project and ignored
`outputs/Yellowstone/<project-id>/` containing two videos, plans and report.

Completed local project: `47a3dfd7-56c7-43f7-8ac3-17912cd716cf`.
Open http://localhost:3001/?project=47a3dfd7-56c7-43f7-8ac3-17912cd716cf,
enter the local token, then Refresh and Preview. This run samples the waterfall
at 29.33s rather than taking only the opening footage.

## Google Photos Is Next

Google Photos Picker import is implemented, but live consent needs a local Google
OAuth client. In Google Cloud Console, enable **Google Photos Picker API**, create
an OAuth web client, and register this exact redirect URI:

```text
http://localhost:8001/oauth/google-photos/callback
```

Generate a local Fernet key without printing it into Git-tracked files, then set
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `TOKEN_ENCRYPTION_KEY` in your
ignored root `.env` or shell environment before starting Compose. A key can be
generated with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`.
Restart the API, open a project, load Google Photos status, check the consent box,
connect, complete Google consent, choose album media, and import it locally.

An album URL is not authorization. Picker requires you to select the album media
in Google's interface. Imports are resumable one item at a time, locally scanned,
and limited to 500 items. Disconnect revokes the Google credential. Drive
Connect/Sync is a separate legacy adapter. Never publish an album or paste a
Google password into this application.
