# Local Vision Curation

The laptop runtime can enrich technical blur/exposure checks with a local
vision-language model. Media previews travel only from the API container to the
owner's Ollama process through Docker Desktop's host bridge. The configured URL
is restricted to localhost or `host.docker.internal`; redirects and proxies are
disabled. Original media is never sent to a cloud model.

## Install

On the Mac, from the repository root:

```bash
./scripts/setup-local-vision.sh
```

This installs the MIT-licensed Ollama runtime with Homebrew and pulls
`qwen2.5vl:7b`, an Apache-2.0 vision model of approximately 6 GB. Model files
live in Ollama's local cache, outside Git. The local Compose profile enables the
adapter and uses `http://host.docker.internal:11434`.

## Evidence Contract

For each asset, FFmpeg creates a bounded JPEG preview from the best technical
sample. Ollama must return the closed JSON schema in `services/local_vision.py`.
The app records scene category, people count, conservative eye state, occlusion,
point-of-interest category, optional unverified landmark hint, editorial scores,
tags and confidence. It never asks for or stores identity.

Scores expressed on a 0-10 scale are normalized to 0-1. Low-confidence face and
landmark claims are downgraded to uncertain. Confident closed-eye, mixed-eye or
major-occlusion frames remain available for review but are not automatically
selected. Selection takes a strong item from each semantic story group before
filling the remaining duration, then restores capture-time order when available.

Model evidence is fallible and remains visible for owner review. A malformed or
unavailable model response stops semantic analysis instead of silently claiming
success. Set `LOCAL_VISION_ENABLED=false` to retain technical-only curation.
