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

## Maintenance: Temporary Media Cleanup

1. Stop accepting new jobs.
2. Allow active render jobs to finish or timeout.
3. Delete expired temp directories by project/job ID.
4. Verify no output locator points to temporary storage.

