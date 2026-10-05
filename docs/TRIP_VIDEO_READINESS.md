# Trip Video Readiness Review

Historical baseline review, not current status. Local source rendering and the
Yellowstone demo were subsequently implemented. The authoritative target is now
the laptop-only Google Photos curation workflow in `PRD_TRIP_VIDEO.md`; consult
`status.md` for current evidence and remaining work.

Reviewed 2026-10-05 against commit `f03c907` and the actual worker, API, UI,
PRD, milestones, Compose stack, and n8n export.

## Decision

Not ready to make a real trip video or launch as a complete editing product.
Authentication, project records, plan review, queue dispatch, private delivery
adapters, and operational controls exist. Source-media editing does not.
Earlier API health and CRUD checks only verified application plumbing.

## Blocking Findings

1. **P0: source footage is never rendered.** `apps/worker/app/render.py:32`
   writes text with an MP4 extension in dry-run mode. Its real mode calls
   `_render_placeholder_with_ffmpeg`, which produces black video and silence.
   It never resolves clip asset IDs, opens source photos/videos, or applies the
   planned crops, effects, captions, or transitions.
2. **P1: success can describe unusable output.** `apps/worker/app/config.py`
   defaults to dry-run, and `apps/api/app/services/rendering.py` marks completion
   as succeeded without requiring passed validation. Black-frame rejection is
   disabled by default. The real renderer diagnostic returned passed validation
   while reporting almost the entire output as black.
3. **P1: analysis does not inspect the trip.**
   `apps/api/app/services/analysis_providers.py:95` explicitly records
   `media_bytes_used: false`. Local scene, subject, and highlight values come
   from metadata/filename heuristics. An external HTTP adapter exists, but no
   complete media-understanding provider is supplied or configured here.
4. **P1: dashboard Drive sync cannot proceed directly to analysis.** New assets
   start with a pending malware status. Sync registers metadata but does not
   schedule scanning; the dashboard has no scan action. Analysis requires all
   assets clean. The internal ClamAV scan endpoint exists but must be invoked
   separately for each accepted asset. Do not mark real trip files clean by hand.
5. **P1: Google authorization needs integration work.** The default redirect URI
   contains a project ID, so each concrete project callback must be registered
   with Google. Use a fixed callback and server-side state-to-project lookup.
   Tokens are encrypted, but there is no refresh-token exchange when an access
   token expires. Local configuration inspected from `apps/api` has no Google
   client ID, client secret, or explicit encryption key configured.
6. **P1: local upload and finished-video playback/download are missing.**
   `/ingest` accepts JSON metadata, not file bytes; the dashboard has no file
   picker. Output rows show metadata and delivery actions, not a player or
   authenticated download. Drive sync lists immediate folder children only;
   it does not recursively traverse subfolders. HEIC is not in the MIME allowlist.

The n8n export also jumps from analysis to rendering without plan approval and
reads `project_id` from an analysis response that does not contain that field.
It is not a working unattended trip-edit workflow.

## Google Drive: URL Plus Authorization

The intended flow is:

1. Configure a Google Cloud OAuth web client with Drive API enabled, consent
   settings, an allowed test user where applicable, and an exact callback URI.
2. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
   `GOOGLE_OAUTH_REDIRECT_URI`, and a private `TOKEN_ENCRYPTION_KEY` on the API.
3. Create a project, paste its private Drive folder URL, and click Connect.
4. Sign in to Google and grant access in the Google consent screen. The backend
   exchanges the authorization code and encrypts the token payload in the DB.
5. Click Sync to register supported files in that folder. Scanning, analysis,
   plan approval, source retrieval, rendering, and private download must form the
   remaining usable workflow.

A folder URL is an identifier, not a credential. The folder need not be public,
and the app should never ask for a Google password. Application login and Google
Drive permission are separate. Current `drive.readonly` permission can read all
Drive files accessible to the account; selecting a folder limits the app's query,
not the OAuth grant. It cannot upload finished videos back to Drive. Prefer local
private downloads for the first release; later consider Picker plus `drive.file`
for narrower access.

Google requires the redirect URI to match a registered URI exactly. With today's
implementation a one-project experiment requires registering the literal
`http://localhost:8001/projects/PROJECT_ID/connect-drive/callback` and configuring
the matching template on the API. This still does not make rendering functional.

Sources: [Google OAuth web-server flow](https://developers.google.com/identity/protocols/oauth2/web-server)
and [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).

## Reproducible Diagnostic

`scripts/check-render-readiness.py` generates five colored PNG test images and
one moving test-pattern MP4 with sound. These are synthetic fixtures, not travel
photos. No media is downloaded, uploaded, or sent to a model. It builds two plans
with the shared planner, runs the current worker in both modes, and probes the
results. The source manifest cannot be consumed by today's worker because the
asset resolver is missing. This is a renderer diagnostic, not an end-to-end demo.

From the repository root, using the already installed worker image on this machine:

```bash
docker run --rm --network none --read-only --tmpfs /tmp:rw,size=512m \
  --mount "type=bind,source=$PWD,target=/repo" --workdir /repo \
  --entrypoint python ai-video-editor-worker:security-review \
  scripts/check-render-readiness.py --output /repo/tmp/my-readiness-check
```

Use a new output directory on each run. The script imports current repository
source; the existing image supplies Python dependencies and FFmpeg. On a machine
without that local image, build it with:

```bash
docker build -t ai-video-editor-worker:security-review -f apps/worker/Dockerfile .
```

Alternatively, with worker dependencies and FFmpeg/ffprobe installed locally:

```bash
python scripts/check-render-readiness.py --output tmp/my-readiness-check
```

Current expected exit code: **2**, meaning the basic non-placeholder check failed.
Even a future zero exit code would not alone prove the full product workflow.
Artifacts from this review are in `tmp/readiness-2026-10-05/`, ignored by Git.

Observed results:

| Check | Result |
| --- | --- |
| Existing API tests | 65 passed |
| Existing worker tests | 6 passed |
| Dry-run landscape and vertical | Text files; ffprobe rejects both as invalid MP4 |
| FFmpeg landscape | Playable 1920x1080 container; black video and silence |
| FFmpeg vertical | Playable 1080x1920 container; black video and silence |
| Black content | 9.44 seconds detected in each 9.5-second output |
| Current application validation | Passed for both black outputs |
| Real source composition | Not implemented |
| Authenticated Google consent/download | Not tested; local Google credentials absent |

The older `LOCAL_SMOKE_WORKFLOW.md` deliberately simulates callbacks and writes
placeholder bytes. Use it only to test metadata, delivery, and retention plumbing.

## Smallest Useful Release

Prioritize a vertical product slice before further infrastructure:

1. Local multi-file upload with validated image/video bytes, private project
   storage, metadata probing, thumbnails, malware scanning, and visible failures.
2. Worker asset resolution, photo durations, video trimming, mixed orientation
   fitting, original clip audio, and actual concatenation into an H.264/AAC MP4.
3. Authenticated preview/download, progress, cancellation/failure state, and retry.
4. A repeatable 5-10 photo plus one-video acceptance run that proves distinctive
   source frames survive in both outputs and video audio remains audible.
5. Fixed Google callback, token refresh, automatic scan/download staging, and
   the same acceptance run with a private Drive folder.
6. Real visual/audio analysis and story-based selection, with explicit provider
   choice and privacy settings before sending personal media to any provider.

For the user's first trip, a reliable local photo/video montage is the shortest
path to value. It can operate without Google credentials or an AI provider.
Public production deployment should follow the product acceptance run and the
remaining deployment/security gates, not precede them.
