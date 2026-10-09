# Local Trip Video Editor: Product Requirements

Updated 2026-10-09. Authoritative user scope; supersedes earlier montage-only
release and cloud-deployment assumptions in older documents.

## Product Contract

- The application runs in a user-controlled local environment: UI, database,
  queue, downloads, analysis, editing, and rendering. No public deployment or
  cloud storage is required for the primary workflow.
- GitHub stores source code, tests, and documentation only. Never commit tokens,
  API keys, OAuth client files, private album links, original media, thumbnails,
  embeddings, analysis caches, local databases, or rendered videos.
- Primary input is an existing **Google Photos album**, not a Google Drive folder.
  Drive is a separate optional adapter. Local album exports/uploads support
  offline use and testing; they do not replace Google Photos support.
- Output is a concise curated trip story, not every file concatenated together.
  Landscape default: 90 seconds, adjustable 15-300 seconds. Vertical default:
  30 seconds, adjustable 15-60 seconds. Never stretch weak content to fill time.
- The user reviews automatic selections, includes/excludes items, chooses a better
  duplicate, changes clip trims, and approves before final rendering.
- "Perfect" is an aspiration, not a guarantee. Release quality is measured by
  the acceptance tests below and user review of representative trip media.

## Google Photos Access

Existing personal albums cannot be enumerated with the old Library API scopes.
The Library API is now restricted to app-created content. Implement OAuth plus
the **Photos Picker API**: create session, open Google's picker, user selects
the album's media, respect polling intervals, paginate selected items, download
locally, scan/probe, then delete the completed Picker session. Do not promise
unattended album-link ingestion or scrape private share pages. An album name/link
may label a project but is not authorization.

Use `photospicker.mediaitems.readonly`, an approved loopback callback, one-use
expiring state, PKCE where supported, encrypted tokens, refresh/re-consent,
disconnect/revoke, bounded download retries, and resumable per-item import.
Google credentials and consent are required even without a hosted app. Never
ask the user to make an album public. Original Photos content is read-only.

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
9. Treat story construction as an ordered editorial problem, not a score sort.
   Build an opening, journey, highlights, human/activity or detail beats when
   evidence supports them, and a closing. Preserve chronology inside that arc
   unless the owner changes the order.
10. Suppress three kinds of repetition: byte-identical media, visually
    interchangeable photos/video samples, and excessive semantic repetition
    from one story group. A longer target must never be filled by near-identical
    moments. Keep the strongest representative and expose alternatives.
11. Analyze multiple frames from videos for visual similarity, semantic change,
    highlight interval choice, and story value. A single best frame is not enough
    evidence to call a video unique or representative.
12. Each generated plan must record story beats and a curation report with the
    number of exact/visual/semantic repetitions suppressed, story groups covered,
    and unresolved review items.

## Soundtrack Requirements

1. Every new plan has a soundtrack. If no user-provided audio is available, the
   renderer creates an original procedural score locally from approved presets.
   Generated scores must use an arranged chord progression, distinct musical
   sections, rhythmic and melodic movement, stereo variation, and smooth note
   envelopes; a sustained tone or static chord is not an acceptable fallback.
   The renderer never searches, scrapes, streams, or downloads third-party
   music. Uploaded audio must be licensed or otherwise permitted for the user's
   intended use.
2. New plans select the most relevant eligible soundtrack by default. Ranking
   uses story-theme overlap from safe filename/embedded title, genre, and mood
   metadata, useful duration, and recency as a tie-breaker. The plan records the
   selected file and reason. The review UI lists all eligible project audio and
   lets the user choose another soundtrack or explicitly choose no soundtrack.
   Changing it invalidates prior approval and requires a new render.
3. Soundtrack selection is independent for landscape and vertical plans. The
   selected asset ID, selection mode (`generated`, `auto`, `manual`, or `none`),
   and mix settings are stored in the versioned timeline plan.
4. Rendering loops or trims uploaded music to the visual duration, fades
   boundaries, and normalizes final loudness for YouTube. Source-video audio is
   muted in new plans so the selected or generated score is the only final audio.
   An explicit `none` choice produces a silent audio track for compatibility.
5. Output validation confirms an audio stream, expected duration, successful
   full decode, and soundtrack provenance in the private render metadata.

## Project Pipeline Requirements

1. Show one project flow: Import → Analyze → Curate → Review → Render → Ready.
   Each step displays pending, current, complete, or failed state with concise
   evidence such as imported count, review count, approved formats, or render
   progress.
2. Highlight exactly one current step and name the next actionable command. A
   failed step remains visible with a retry action. Completed historical render
   attempts must not make a successful retry appear unfinished.
3. Pipeline state is derived from persisted media, analysis, latest plans,
   approvals, latest render attempts, and validated outputs. Do not store a
   second mutable workflow status that can disagree with those records.
4. The flow must fit desktop and mobile without overlapping labels and must
   remain useful with either one or both output variants.

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
| L7 Story intelligence | local vision schema/prompt, `local_analysis.py`, shared `curation.py`, planning/tests | Multi-frame video evidence; exact/visual/semantic repetition report; bounded story beats; chronology and owner overrides preserved. |
| L8 Soundtrack | media probe/upload, plan schema/review routes, worker renderer/validation, dashboard | Relevant eligible local audio defaults with an original generated fallback and recorded provenance; manual/none choice; source audio muted; approval invalidation; validated output. |
| L9 Pipeline experience | derived project-progress module, status response, dashboard/CSS/tests | Import-to-ready flow names current/next action and accurately handles retries, failures, one/two variants, desktop, and mobile. |

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
- Story acceptance includes a fixture with bursts, repeated location views, a
  photo matching a video frame, several distinct trip events, and a weak ending.
  The plan must retain the strongest representative, cover distinct events, and
  produce opening/middle/highlight/closing beats without padding.
- Soundtrack acceptance uses multiple local audio fixtures with different
  semantic metadata and import times. The story-relevant one is selected by
  default, recency breaks equivalent ties, manual and none choices persist,
  source-video audio is absent from the final mix, and no network request is made
  to discover or retrieve music. A no-upload fixture receives a validated
  original generated score with explicit preset provenance. Automated waveform
  checks reject a static drone by requiring meaningful section-level dynamics
  and timbral movement; owner listening remains the final taste check.

## Current Evidence

Public fixtures and a private acceptance album have completed the import, review,
render, validation, preview, and download workflow in both formats. L3 is
accepted for the Picker-supported selection flow. L7 has a versioned story
selector with semantic repetition limits, story beats, and a suppression report;
multi-frame video evidence remains. L8 has a working local MP3/WAV selection and
render baseline with arranged procedural score v2, pending broader owner audio
and subjective listening acceptance. L9 has a retry-aware derived
pipeline in the status response and dashboard. The L4 model still needs
portrait/eye-state and large-album acceptance.
Current results and next actions live in
[status.md](status.md).
