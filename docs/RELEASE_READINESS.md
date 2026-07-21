# Release Readiness

Use this checklist before tagging or deploying the current MVP slice. This is an operator-ready private workflow baseline, not a full multi-tenant production release.

## Required Validation

- API tests pass locally and in CI: `api-tests`.
- Worker tests pass locally and in CI: `worker-tests`.
- Web production build passes locally and in CI: `web-build`.
- Shell scripts pass syntax and ShellCheck linting: `shell-scripts`.
- Docker Compose and Kubernetes manifests validate: `infra-validation`.
- `scripts/smoke-retention-cleanup.sh` runs successfully against a completed local smoke project.
- `docs/LOCAL_SMOKE_WORKFLOW.md` has been run end to end with synthetic private locators.

## Security Gates

- Branch protection on `main` requires the checks in `docs/BRANCH_PROTECTION.md`.
- Secret scanning and push protection are enabled.
- No `.env`, local databases, source media, staged renders, delivered outputs, OAuth tokens, or provider credentials are committed.
- `TOKEN_ENCRYPTION_KEY`, API tokens, OAuth client secrets, cloud credentials, and n8n credentials are stored outside the repository.
- Google Drive ingestion uses read-only scope unless Drive output delivery is explicitly enabled.
- Drive output folders, S3 buckets, and local private delivery roots are access-controlled and private.

## Operator Gates

- A project can be created through the API or dashboard.
- Media ingest rejects public URLs and unsafe filenames.
- Malware scan status is recorded before analysis.
- Analysis creates plans for `youtube_16x9` and `shorts_9x16`.
- Plans can be reviewed, approved, rejected, and regenerated.
- Render jobs can be queued for both variants.
- Worker completion callbacks create private output records and validation metadata.
- Outputs can be delivered to local private storage, S3, or Drive with private locators.
- Delivery failures are visible and retryable.
- Retention metadata is attached to delivered outputs.
- Retention report and due cleanup workflows work for local private outputs.

## Deployment Gates

- `.env.example` has every required runtime variable represented.
- Docker Compose starts with shared API/worker staging storage.
- Kubernetes manifests mount shared staging storage for API and worker pods.
- Drive write scopes are configured only when Drive output delivery is enabled.
- S3 IAM grants are limited to the configured private bucket and prefix.
- `AUTO_DELIVER_OUTPUTS` is enabled only after delivery credentials and staging mounts are verified.
- `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY` is enabled only after operators no longer need staged render inspection.

## Known Production Gaps

- RBAC is not complete.
- Rate limits and per-project quotas are not complete.
- SSO/VPN protection for n8n is deployment-owned.
- Full production renderer hardening still needs real workload tuning.
- Provider-native deletion for Drive and S3 retention cleanup is not automated by the API.
- Full Kubernetes/ECS production deployment remains a starter path, not a locked reference architecture.
- Branch protection settings must be applied in GitHub; this repository only documents them.

## Release Decision

Release only when:

1. Required validation is green.
2. Security gates have an owner and evidence.
3. Operator gates are verified against a local or staging project.
4. Known production gaps are accepted for the intended environment.
5. The release notes explicitly say media and outputs remain private and manual-upload only.

Use `docs/RELEASE_NOTES_TEMPLATE.md` for release notes and `docs/VERSIONING.md` for tag guidance.
