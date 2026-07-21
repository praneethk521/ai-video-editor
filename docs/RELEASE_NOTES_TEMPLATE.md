# Release Notes Template

Use this template for MVP deployments, staging releases, or GitHub releases.

## Summary

- Release:
- Date:
- Commit or tag:
- Environment:
- Release owner:

One-paragraph summary of the workflow or operator capability being released.

## Validation

- API tests:
- Worker tests:
- Web build:
- Shell script linting:
- Infrastructure validation:
- Local smoke workflow:
- Retention cleanup smoke script:

Link the CI run and any local smoke evidence.

## Changes

### Added

- 

### Changed

- 

### Fixed

- 

### Removed

- 

## Private Media And Output Handling

Confirm:

- No source media, staged renders, delivered outputs, local databases, `.env` files, OAuth tokens, or provider credentials are included in the release.
- Outputs remain private and manual-upload only.
- Delivery targets are private Drive, `s3://private/`, or local private storage.
- Retention metadata is attached to delivered outputs.
- Retention cleanup dry-run behavior was preserved.

## Configuration Changes

List new or changed environment variables:

| Variable | Required | Default | Notes |
| --- | --- | --- | --- |
|  |  |  |  |

## Deployment Notes

- Database migration needed:
- Secret changes needed:
- OAuth scope changes needed:
- Shared staging storage changes needed:
- Rollback plan:

## Known Gaps

- 

## Operator Checklist

1. Confirm branch protection checks passed.
2. Confirm release readiness checklist is satisfied or exceptions are approved.
3. Deploy to the target environment.
4. Run the local or staging smoke workflow.
5. Verify output delivery and retention report behavior.
6. Confirm no public media URLs or public delivered artifacts were created.
7. Record release evidence and exceptions.
