# Local Trip Demo

This app runs on this laptop. Google Photos import is implemented and awaits a
real owner-album acceptance run; local semantic selection has a working baseline. See
`status.md`. No AWS or public website is needed.

## Start the Local Runtime

From the repository root:

```bash
./scripts/start-local.sh
```

For the shortest owner workflow, follow [USE_YOUR_TRIP.md](USE_YOUR_TRIP.md).

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
3. Analyze. Actual staged bytes are inspected by technical checks and the local
   Ollama vision model; no cloud AI call occurs.
4. Review plans and Selection decisions. Change duration targets and Regenerate
   when needed, then approve both formats and Render.
5. Status polls during rendering. Under Outputs, Preview fetches the video using
   authentication; Download MP4 saves it locally. No credentials enter URLs.

Current curation combines technical quality with strict local-model evidence for
scene, people, eyes, occlusion, points of interest and story diversity. The model
never performs identity recognition; uncertain faces and unverified landmark
hints remain review items. The dashboard now loads authenticated thumbnails and
persists include, exclude, pin and trim overrides before approval. Robust
portrait/closed-eye and multi-frame video acceptance, duplicate comparison,
all-low-quality recovery, face-aware crop, music and transitions remain. Keep
originals unchanged.

## Repeat the Yellowstone Acceptance Run

Install the local semantic model once before analyzing media:

```bash
./scripts/setup-local-vision.sh
```

See [LOCAL_VISION.md](LOCAL_VISION.md) for its private data path, evidence
contract and limitations.

With Python and API dependencies installed:

```bash
python scripts/download-yellowstone.py
python scripts/demo-local-media.py
```

The script auto-approves test plans; it is a demo harness, not a substitute for
reviewing a personal album. NPS inputs/credits live under ignored
`media/Yellowstone/`. Each run creates a new project and ignored
`outputs/Yellowstone/<project-id>/` containing two videos, plans and report.

Open the dashboard using the address printed by the startup script and select the
newly created project. Enter the local token, then refresh and preview the
results. The fixture verifies that analysis can choose a useful interval rather
than always taking the opening footage.

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
