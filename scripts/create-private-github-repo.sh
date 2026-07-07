#!/usr/bin/env bash
set -euo pipefail

repo_name="${1:-ai-video-editor}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required: https://cli.github.com/" >&2
  exit 1
fi

gh repo create "$repo_name" --private --source=. --remote=origin --push
gh repo edit "$repo_name" --enable-secret-scanning --enable-dependabot-alerts
echo "Enable branch protection and required reviews in GitHub settings for main."

