# Runbook

## Incident: Suspected Secret Leak

1. Revoke the leaked credential immediately.
2. Rotate dependent credentials.
3. Search audit logs by correlation ID and action.
4. Confirm logs do not contain raw tokens or private media bytes.
5. Open a private security issue and document remediation.

## Incident: Failed Render

1. Check `render_jobs.status` and `error_message`.
2. Fetch worker logs by correlation ID.
3. Validate timeline JSON against `packages/shared/schemas/timeline.schema.json`.
4. Requeue only after confirming media locators are private and malware scan status is clean.

## Incident: Failed Output Delivery

1. Check `output_videos.delivery_status` and `delivery_json.details`.
2. Confirm the staged `file://private/...` locator resolves under `OUTPUT_DELIVERY_LOCAL_ROOT`.
3. For Drive, verify the connected OAuth token has write scope and `GOOGLE_DRIVE_OUTPUT_FOLDER_ID` is private.
4. For S3, verify `S3_BUCKET`, `S3_REGION`, `S3_PREFIX`, and encryption settings.
5. Retry delivery only after confirming the destination locator will remain private.

## Maintenance: Temporary Media Cleanup

1. Stop accepting new jobs.
2. Allow active render jobs to finish or timeout.
3. Delete expired temp directories by project/job ID.
4. Verify delivered output locators point to Drive, `s3://private/`, or private local storage before deleting staged files.
5. For automatic staged-file cleanup, enable `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY=true` and verify `delivery_json.staged_source_cleanup.status` is `deleted`.

## Maintenance: Delivered Output Retention Cleanup

1. Confirm the project owner has completed manual upload or explicitly waived upload.
2. Review retention state with `GET /projects/{project_id}/outputs/retention`.
3. Confirm due rows have `retention_due = true`, `status = delivered`, and retention metadata.
4. Preview local-private cleanup with `POST /projects/{project_id}/outputs/retention/cleanup` and `{"dry_run": true}`.
5. Confirm preview rows show `cleanup.status = would_delete` only for files that should be removed.
6. Run local-private cleanup with `POST /projects/{project_id}/outputs/retention/cleanup` and `{"dry_run": false}`.
7. Verify `delivery_json.delivered_artifact_cleanup.status` is `deleted` or `missing`.
8. For Drive and S3 due rows, use provider lifecycle rules or provider-native deletion workflows; the API skips them as provider-managed retention.
9. Do not clean up outputs with `private_staging`, `failed`, or missing retention metadata unless the project owner has abandoned the render.
10. Record the cleanup action in the operator change log.
