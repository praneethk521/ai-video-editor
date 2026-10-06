# Local Trip Video Editor: Product Requirements

Updated 2026-10-06. Authoritative user scope; supersedes earlier montage-only
release and cloud-deployment assumptions in older documents.

## Product Contract

- The entire application runs on the owner's laptop: UI, database, queue,
  downloads, analysis, editing, and rendering. No AWS, hosted website, public API,
  Kubernetes deployment, or cloud storage is required.
- GitHub stores source code, tests, and documentation only. Never commit tokens,
  API keys, OAuth client files, private album links, original media, thumbnails,
  embeddings, analysis caches, local databases, or rendered videos.
- Primary input is an existing **Google Photos album**, not a Google Drive folder.
  Drive is a separate optional adapter. Local album exports/uploads support
  offline use and testing; they do not replace Google Photos support.
- Output is a concise curated trip story, not every file concatenated together.
  Landscape default: 90 seconds, adjustable 15-300 seconds. Vertical default:
  30 seconds, adjustable 15-60 seconds. Never stretch weak content to fill time.
- Owner reviews automatic selections, includes/excludes items, chooses a better
  duplicate, changes clip trims, and approves before final rendering.
- "Perfect" is an aspiration, not a guarantee. Release quality is measured by
  the acceptance tests below and owner review of a real trip album.

## Google Photos Access

Existing personal albums cannot be enumerated with the old Library API scopes.
The Library API is now restricted to app-created content. Implement OAuth plus
the **Photos Picker API**: create session, open Google's picker, user selects
the album's media, respect polling intervals, paginate selected items, download
locally, scan/probe, then delete the completed Picker session. Do not promise
unattended album-link ingestion or scrape private share pages. An album name/link
may label a project but is not authorization.

Use `photospicker.mediaitems.readonly`, a fixed localhost callback, one-use
expiring state, PKCE where supported, encrypted tokens, refresh/re-consent,
disconnect/revoke, bounded download retries, and resumable per-item import.
Google credentials and consent are required even without a hosted app. Never
ask the owner to make an album public. Original Photos content is read-only.

References checked 2026-10-05:
- [API changes](https://developers.google.com/photos/support/updates)
- [Picker workflow](https://developers.google.com/photos/picker/guides/get-started-picker)
- [User data policy](https://developers.google.com/photos/support/api-policy)

## Curation Requirements

1. Inspect actual decoded images and sampled video frames. Filename heuristics
   are not visual understanding and must never be presented as such.
2. Measure focus, exposure, resolution, corruption, motion/shake, and audio
   quality. Reject clearly unusable files; flag uncertain quality for review.
   Do not discard an irreplaceable memory purely because a heuristic is low.
3. Group exact duplicates and near-duplicate bursts using whole-image similarity
   plus capture time. Pick the sharpest/best-exposed representative; consider open
   eyes, visible faces, composition, and occlusion when a validated local model
   supports them. Never create face-identity clusters.
4. Recognize meaningful scenery, landmarks, activities, and background details
   with a local vision model. Include scenic images without people. Preserve
   different places/days/events, rather than selecting only portraits. Unknown
   landmark/eye state is unknown, not an invented confident label.
5. Sample videos throughout their duration, identify strong usable intervals,
   and trim to those intervals. Do not always select the first few seconds.
6. Combine quality, event coverage, novelty, and user preferences under an
   explicit duration budget. Preserve a coherent trip order and balanced pacing.
7. Return per-item evidence, confidence, selected/rejected/review status,
   duplicate group, reason codes, alternatives, and estimated duration.
8. Manual choices override automatic taste judgments, but not corrupt/unsafe
   inputs. Forced inclusions exceeding the budget require a budget/selection
   change; never silently ignore the budget or user choices.

## Privacy and Runtime

Local inference is the default. No personal bytes or derivatives are sent to an
external AI provider without separate explicit opt-in describing provider/data.
Models are inference-only; no training on album media. Whole-scene duplicate
detection is not face recognition. Keep originals unchanged.

Bind UI/API to loopback; retain authentication and private file paths. Secrets
live outside Git in an OS keychain/encrypted local store or ignored local env.
Require encrypted laptop storage for personal media and document cleanup,
disconnect, backup/restore, and disk-space limits. Gitignore is not encryption.
Album/download URLs stay out of logs and Git. Secret scanning, including history,
is a release gate before pushing code.

## Delivery Milestones and File Map

| Milestone | Files | Acceptance |
| --- | --- | --- |
| L1 Real local rendering | worker `render.py`, `validation.py`, `tests/test_real_render.py`, local Compose | Stills, video and audio survive; full decode; stable color/range; both formats; failed jobs never report success. |
| L2 Bounded curation | shared `curation.py`, API `services/local_analysis.py`, `services/planning.py`, shared `timeline.py`, config | Actual pixel quality, duplicate suppression, bounded selection, explicit unknown semantic/eye fields; tests with large candidate sets. |
| L3 Photos import | `services/google_photos.py`, OAuth/session models and migration, project routes, config, dashboard | Picker transport, OAuth, paginated download/scan/staging, progress, resume, disconnect; real owner-selected album acceptance. |
| L4 Semantic local model | local vision provider, model manifest/cache config | Validated open-eye/blur/burst decisions, landmark/scenery relevance, video highlights; resource measurements and uncertain-case review. |
| L5 Selection review | dashboard, project schemas/routes, selection persistence | Thumbnail comparisons, include/exclude/pin, duplicate alternatives, trims, target duration; versioned decisions and approval invalidation. |
| L6 Laptop acceptance | demo scripts, local runbook, privacy/secret check, status | Large Photos trip album imported, curated, reviewed, rendered, played; no cloud execution or media in GitHub. |

## Acceptance Datasets and Gates

- Yellowstone: six NPS photos and one video under ignored `media/Yellowstone/`,
  with provenance. This proves rendering, not human portrait/eye quality.
- Curation fixtures: exact/near duplicates, sharp/blurred pairs, dark/bright
  frames, scenery, portraits with uncertain/closed eyes, short videos, nonzero
  highlight trims, and all-low-quality albums. Synthetic colors or mock scores
  alone cannot establish model quality.
- Scale target: 500 candidates including phone orientations and long clips;
  bounded concurrency/disk, restartable import/analysis, progress and cancellation.
  This is a target until measured on this laptop.
- A 500-item album must produce a bounded highlight reel, never a very long
  concatenation. Empty/weak selection offers review, not a bogus success.
  Each chosen source is traceable to evidence.
- HEIC/HEIF, Live Photos, rotation and HDR normalization need tested support
  before claiming general phone-album compatibility.
- No public deployment gate. Local installation, reliability, privacy, album
  access and owner-approved editing quality are the release gates.

## Current Evidence

Earlier Yellowstone HTTP upload -> ClamAV -> Redis/RQ -> FFmpeg -> private download
completed with 26-second landscape and 21-second portrait outputs. These were
all-input montages, not completion of this curation PRD. The L3 Picker transport,
OAuth, encrypted state, private resumable ingest and dashboard flow are now
implemented and unit-tested; L3 remains open until a real private album completes
the workflow on this laptop. The L4 baseline now runs an Apache-2.0 local vision
model through a strict loopback-only schema and has completed a seven-asset
Yellowstone analysis; portrait/eye-state and large-album acceptance remain.
Current results and next actions live in
[status.md](status.md).
