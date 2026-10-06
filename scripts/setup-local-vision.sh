#!/usr/bin/env bash
set -euo pipefail

model="${LOCAL_VISION_MODEL:-qwen2.5vl:7b}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script currently supports the macOS laptop runtime only." >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required to install the local Ollama runtime." >&2
  exit 1
fi
if ! brew list ollama >/dev/null 2>&1; then
  brew install ollama
fi
brew services start ollama >/dev/null 2>&1 || brew services restart ollama >/dev/null

for _ in {1..30}; do
  if curl --fail --silent --show-error http://127.0.0.1:11434/api/version >/dev/null; then
    break
  fi
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:11434/api/version >/dev/null
ollama pull "$model"
ollama list
