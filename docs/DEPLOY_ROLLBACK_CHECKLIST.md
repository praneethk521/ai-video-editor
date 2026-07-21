# Deploy And Rollback Checklist

Use this checklist for staging deployments, MVP releases, and rollback drills.

## Pre-Deploy

1. Confirm `main` is clean, pushed, and protected.
2. Confirm required CI checks passed for the target commit.
3. Confirm release readiness in `docs/RELEASE_READINESS.md`.
4. Create or select the release tag using `docs/VERSIONING.md`.
5. Complete release notes from `docs/RELEASE_NOTES_TEMPLATE.md`.
6. Confirm `.env.example` matches runtime configuration expectations.
7. Confirm real secrets are in the runtime secret manager, not in source control.
8. Confirm source media, staged renders, delivered outputs, and local databases are not in the release artifact.

## Deploy

1. Deploy API, worker, web, Redis, PostgreSQL, ClamAV, and n8n components for the target environment.
2. Confirm API and worker share the same private staging root.
3. Confirm `OUTPUT_DELIVERY_LOCAL_ROOT` and `LOCAL_PRIVATE_DELIVERY_ROOT` are private and encrypted where applicable.
4. Confirm Drive output scope and folder settings only when Drive delivery is enabled.
5. Confirm S3 bucket, prefix, encryption, and IAM permissions only when S3 delivery is enabled.
6. Confirm `AUTO_DELIVER_OUTPUTS` and `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY` are set deliberately.
7. Run the local or staging smoke workflow.
8. Run `scripts/smoke-retention-cleanup.sh` against the smoke project.
9. Verify the dashboard can load project status, outputs, retention report, and cleanup preview.

## Post-Deploy

1. Check API logs for authentication, validation, and delivery errors.
2. Check worker logs for render callback failures.
3. Check audit logs by release correlation IDs or smoke project ID.
4. Confirm no public media URLs or public delivered artifacts were created.
5. Confirm delivered output locators are private.
6. Confirm retention metadata is present on delivered outputs.
7. Record CI links, smoke evidence, release tag, and known exceptions.

## Rollback Triggers

Rollback if any of these occur:

- authenticated API project lifecycle is broken
- media validation accepts public URLs or unsafe filenames
- malware scan gating is bypassed
- render callbacks fail for known-good payloads
- delivery creates public URLs or loses private locator validation
- dashboard cannot load project outputs or retention status
- retention cleanup deletes non-due artifacts
- secrets or private media are exposed

## Rollback Procedure

1. Stop new render submissions.
2. Let active render jobs finish only if they are using the known-good worker and private staging remains safe.
3. Record active project IDs, render job IDs, staged output paths, and delivered locators.
4. Roll back API, worker, and web to the previous known-good tag.
5. Do not delete staged or delivered artifacts during rollback unless the retention policy says they are due.
6. Re-run API health checks and the private workflow smoke test.
7. Re-run retention report and cleanup preview.
8. Document the rollback reason, affected projects, artifacts preserved, and follow-up fix.

## Recovery Verification

After rollback or fix-forward:

- API tests and worker tests pass.
- Web build passes.
- CI required checks are green.
- A synthetic project can reach private delivery.
- Retention report and cleanup preview work.
- No new public media URLs, public outputs, or secrets are present.
