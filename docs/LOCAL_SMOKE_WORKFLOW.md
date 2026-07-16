# Local Smoke Workflow

This workflow proves the private-media path from project creation through local private output delivery. It uses synthetic private locators and worker callbacks, so it does not require real source media, Google Drive write access, S3 credentials, or public URLs.

Use it after the Docker Compose stack is running. For this synthetic callback workflow, set `RENDER_QUEUE_BACKEND=database` before starting the stack so the API creates render jobs without enqueueing work for the live worker:

```bash
cp .env.example .env
perl -0pi -e 's/RENDER_QUEUE_BACKEND=.*/RENDER_QUEUE_BACKEND=database/' .env
docker compose -f infra/docker/docker-compose.yml up --build
```

The examples assume `jq` is installed and the API is available at `http://localhost:8000`.

## 1. Set Request Helpers

```bash
export API=http://localhost:8000
export TOKEN=replace-with-local-dev-token
export AUTH_HEADER="Authorization: Bearer ${TOKEN}"
```

The token must match `API_TOKEN` in `.env`.

## 2. Create A Project

```bash
PROJECT_ID="$(
  curl -fsS -X POST "${API}/projects" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d '{"name":"Local smoke edit"}' | jq -r '.id'
)"

echo "${PROJECT_ID}"
```

Expected result: a non-empty project ID and project status `created`.

## 3. Register Private Media

This registers metadata only. The locator uses the private Drive scheme accepted by the platform and does not expose public media.

```bash
MEDIA_ASSET_ID="$(
  curl -fsS -X POST "${API}/projects/${PROJECT_ID}/ingest" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d '{
      "assets": [
        {
          "filename": "hero clip.mp4",
          "mime_type": "video/mp4",
          "size_bytes": 123456,
          "duration_seconds": 12,
          "orientation": "landscape",
          "private_locator": "drive://private-smoke-folder/hero-clip"
        }
      ]
    }' | jq -r '.accepted_asset_ids[0]'
)"

echo "${MEDIA_ASSET_ID}"
```

Expected result: a non-empty media asset ID.

## 4. Record Malware Scan Result

Analysis is blocked until every media asset is clean.

```bash
curl -fsS -X POST "${API}/internal/media-assets/${MEDIA_ASSET_ID}/malware-scan" \
  -H "${AUTH_HEADER}" \
  -H "Content-Type: application/json" \
  -d '{"status":"clean","scanner":"local-smoke","details":{"mode":"synthetic"}}'
```

Expected result: HTTP `204`.

## 5. Analyze And Review Plans

```bash
ANALYZE_JSON="$(
  curl -fsS -X POST "${API}/projects/${PROJECT_ID}/analyze" \
    -H "${AUTH_HEADER}"
)"

echo "${ANALYZE_JSON}" | jq
```

Approve every generated plan so rendering can be queued:

```bash
echo "${ANALYZE_JSON}" | jq -r '.timeline_plan_ids[]' | while read -r PLAN_ID; do
  curl -fsS -X POST "${API}/projects/${PROJECT_ID}/plans/${PLAN_ID}/approve" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d '{"notes":"Approved for local smoke test."}' >/dev/null
done
```

Expected result: generated plan IDs for `youtube_16x9` and `shorts_9x16`, both approved.

## 6. Queue Render Jobs

```bash
RENDER_JSON="$(
  curl -fsS -X POST "${API}/projects/${PROJECT_ID}/render" \
    -H "${AUTH_HEADER}" \
    -H "Content-Type: application/json" \
    -d '{"variants":["youtube_16x9","shorts_9x16"]}'
)"

echo "${RENDER_JSON}" | jq
```

Expected result: two render job IDs.

## 7. Simulate Worker Completion

Create staged private files in the shared output volume used by the API and worker containers:

```bash
docker compose -f infra/docker/docker-compose.yml exec -T api sh -lc "
  mkdir -p /tmp/ai-video-editor/outputs/${PROJECT_ID}
  printf 'private rendered bytes' > /tmp/ai-video-editor/outputs/${PROJECT_ID}/youtube_16x9.mp4
  printf 'private rendered bytes' > /tmp/ai-video-editor/outputs/${PROJECT_ID}/shorts_9x16.mp4
"
```

Post completion callbacks for each job. These callbacks mark outputs as private staged files and set the delivery target to `local_private`.

```bash
curl -fsS "${API}/projects/${PROJECT_ID}/status" -H "${AUTH_HEADER}" |
  jq -r '.render_jobs[] | [.id, .variant] | @tsv' |
  while IFS=$'\t' read -r JOB_ID VARIANT; do
    curl -fsS -X POST "${API}/internal/render-jobs/${JOB_ID}/running" \
      -H "${AUTH_HEADER}" >/dev/null

    if [ "${VARIANT}" = "youtube_16x9" ]; then
      WIDTH=1920
      HEIGHT=1080
    else
      WIDTH=1080
      HEIGHT=1920
    fi

    curl -fsS -X POST "${API}/internal/render-jobs/${JOB_ID}/complete" \
      -H "${AUTH_HEADER}" \
      -H "Content-Type: application/json" \
      -d "{
        \"variant\":\"${VARIANT}\",
        \"private_locator\":\"file://private/${PROJECT_ID}/${VARIANT}.mp4\",
        \"width\":${WIDTH},
        \"height\":${HEIGHT},
        \"duration_seconds\":12,
        \"file_size_bytes\":2048,
        \"upload_package\":{
          \"manual_upload_only\":true,
          \"delivery_target\":\"local_private\",
          \"delivery_status\":\"private_staging\"
        },
        \"validation\":{\"status\":\"passed\",\"checks\":{\"local_smoke\":true}}
      }" >/dev/null
  done
```

Expected result: project status moves to `ready`, and both outputs show `delivery.status` as `private_staging`.

## 8. Deliver To Local Private Storage

```bash
curl -fsS "${API}/projects/${PROJECT_ID}/outputs" -H "${AUTH_HEADER}" |
  jq -r '.outputs[].id' |
  while read -r OUTPUT_ID; do
    curl -fsS -X POST "${API}/internal/output-videos/${OUTPUT_ID}/deliver" \
      -H "${AUTH_HEADER}" \
      -H "Content-Type: application/json" \
      -d '{"target":"local_private"}' >/dev/null
  done
```

Expected result: HTTP `204` for each output.

## 9. Validate The Result

```bash
curl -fsS "${API}/projects/${PROJECT_ID}/status" -H "${AUTH_HEADER}" | jq
curl -fsS "${API}/projects/${PROJECT_ID}/outputs" -H "${AUTH_HEADER}" | jq
```

The final output response should show:

- project status `ready`
- one `youtube_16x9` output and one `shorts_9x16` output
- `upload_package.manual_upload_only` set to `true`
- `validation.status` set to `passed`
- `delivery.target` set to `local_private`
- `delivery.status` set to `delivered`
- delivered locators beginning with `file://private/delivered/`

To also validate staged source cleanup, set `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY=true` in `.env`, restart the API container, rerun the workflow, and confirm each output includes `delivery.details.staged_source_cleanup.status` as `deleted`.

Confirm the private files exist inside the local private delivery root:

```bash
docker compose -f infra/docker/docker-compose.yml exec -T api sh -lc "
  find /tmp/ai-video-editor/delivered -maxdepth 5 -type f -name '*.mp4'
"
```

## Failure And Retry Check

To verify failure recording, delete a staged file before step 8 and deliver that output. The API should return HTTP `422`, and `GET /projects/{project_id}/outputs` should show `delivery.status` as `failed` with an error in `delivery.details.details.error`.

After recreating the missing staged file, rerun the same delivery request. The output should move from `failed` to `delivered`.

## Cleanup

```bash
docker compose -f infra/docker/docker-compose.yml exec -T api sh -lc "
  rm -rf /tmp/ai-video-editor/outputs/${PROJECT_ID}
"
```

Keep delivered files only as long as needed for manual verification. Do not commit staged or delivered media artifacts.
