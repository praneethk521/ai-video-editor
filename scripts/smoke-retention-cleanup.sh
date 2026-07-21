#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://localhost:8000}"
TOKEN="${TOKEN:-}"
PROJECT_ID="${PROJECT_ID:-}"
RUN_RETENTION_CLEANUP="${RUN_RETENTION_CLEANUP:-false}"

if [[ -z "${TOKEN}" ]]; then
  echo "TOKEN is required" >&2
  exit 2
fi

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required" >&2
  exit 2
fi

command -v jq >/dev/null 2>&1 || {
  echo "jq is required" >&2
  exit 2
}

auth_header="Authorization: Bearer ${TOKEN}"
api_root="${API%/}"

echo "Loading retention report for project ${PROJECT_ID}"
report="$(
  curl -fsS "${api_root}/projects/${PROJECT_ID}/outputs/retention" \
    -H "${auth_header}"
)"

echo "${report}" | jq -e '
  .project_id and
  (.outputs | type == "array") and
  all(.outputs[]; has("id") and has("retention_due") and has("has_retention_metadata"))
' >/dev/null

due_count="$(echo "${report}" | jq '[.outputs[] | select(.retention_due == true)] | length')"
missing_metadata_count="$(echo "${report}" | jq '[.outputs[] | select(.has_retention_metadata == false)] | length')"

echo "Due outputs: ${due_count}"
echo "Outputs missing retention metadata: ${missing_metadata_count}"

echo "Previewing due local-private retention cleanup"
preview="$(
  curl -fsS -X POST "${api_root}/projects/${PROJECT_ID}/outputs/retention/cleanup" \
    -H "${auth_header}" \
    -H "Content-Type: application/json" \
    -d '{"dry_run":true}'
)"

echo "${preview}" | jq -e '
  .project_id and
  .dry_run == true and
  (.outputs | type == "array") and
  all(.outputs[]; has("id") and has("cleanup") and (.cleanup | has("status")))
' >/dev/null

echo "${preview}" | jq -r '.outputs[] | [.variant, .target, .retention_due, .cleanup.status, (.cleanup.reason // "")] | @tsv'

if [[ "${RUN_RETENTION_CLEANUP}" == "true" ]]; then
  echo "Running due local-private retention cleanup"
  cleanup="$(
    curl -fsS -X POST "${api_root}/projects/${PROJECT_ID}/outputs/retention/cleanup" \
      -H "${auth_header}" \
      -H "Content-Type: application/json" \
      -d '{"dry_run":false}'
  )"
  echo "${cleanup}" | jq -e '.dry_run == false and (.outputs | type == "array")' >/dev/null
  echo "${cleanup}" | jq -r '.outputs[] | [.variant, .target, .retention_due, .cleanup.status, (.cleanup.reason // "")] | @tsv'
else
  echo "Skipping actual cleanup. Set RUN_RETENTION_CLEANUP=true to delete due local-private artifacts."
fi
