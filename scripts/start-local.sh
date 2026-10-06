#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The one-command launcher currently supports macOS only." >&2
  exit 1
fi
for command in docker curl python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "$command is required before starting the editor." >&2
    exit 1
  fi
done
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running. Open it, then run this command again." >&2
  exit 1
fi

umask 077
touch .env
chmod 600 .env
api_token="$(awk -F= '$1 == "API_TOKEN" {sub(/^[^=]*=/, ""); print; exit}' .env)"
if [[ -z "$api_token" ]]; then
  api_token="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  printf '\nAPI_TOKEN=%s\n' "$api_token" >>.env
fi
encryption_key="$(awk -F= '$1 == "TOKEN_ENCRYPTION_KEY" {sub(/^[^=]*=/, ""); print; exit}' .env)"
if [[ -z "$encryption_key" ]]; then
  encryption_key="$(python3 -c 'import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
  printf 'TOKEN_ENCRYPTION_KEY=%s\n' "$encryption_key" >>.env
fi

model="${LOCAL_VISION_MODEL:-qwen2.5vl:7b}"
if ! command -v ollama >/dev/null 2>&1 \
    || ! curl --fail --silent http://127.0.0.1:11434/api/version >/dev/null 2>&1 \
    || ! ollama show "$model" >/dev/null 2>&1; then
  "$root/scripts/setup-local-vision.sh"
fi

API_TOKEN="$api_token" TOKEN_ENCRYPTION_KEY="$encryption_key" \
  docker compose -f infra/docker/docker-compose.local.yml up -d --build

for _ in {1..90}; do
  if curl --fail --silent http://127.0.0.1:8001/healthz >/dev/null \
      && curl --max-time 3 --fail --silent http://127.0.0.1:3001/ | grep -q "AI Video Editor"; then
    break
  fi
  sleep 1
done
curl --fail --silent http://127.0.0.1:8001/healthz >/dev/null
curl --max-time 3 --fail --silent http://127.0.0.1:3001/ | grep -q "AI Video Editor"

echo
echo "AI Video Editor is ready: http://localhost:3001/"
echo "Bearer token: $api_token"
echo "Keep this terminal output private. Stop later with ./scripts/stop-local.sh"

if [[ "${1:-}" != "--no-open" ]]; then
  open -a "Google Chrome" http://localhost:3001/ 2>/dev/null || open http://localhost:3001/
fi
