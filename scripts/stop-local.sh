#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

docker compose -f infra/docker/docker-compose.local.yml down
echo "AI Video Editor stopped. Private media and outputs remain in the local Docker volume."
