# Retention Policy

This policy keeps source media, staged renders, delivered outputs, and metadata private while giving operators enough time to review and manually upload finished videos.

## Scope

- Source media registered from private Drive folders.
- Staged render files under `OUTPUT_DELIVERY_LOCAL_ROOT`.
- Delivered files in Drive, S3, or `LOCAL_PRIVATE_DELIVERY_ROOT`.
- Metadata in the API database, including private locators, validation results, delivery status, and audit logs.

## Default Retention Targets

| Artifact | Recommended retention | Owner | Notes |
| --- | ---: | --- | --- |
| Source media | Source-system policy | Drive owner | The platform stores private locators and metadata, not source media bytes. |
| Staged render files | Delete after confirmed private delivery | API/worker operators | Enable `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY=true` when post-delivery inspection is not required. |
| Delivered Drive outputs | 30-90 days after manual upload verification | Drive output folder owner | Keep folders private and remove share links before upload workflows begin. |
| Delivered S3 outputs | 30-90 days after manual upload verification | Bucket owner | Use private buckets, encryption, access logs, and lifecycle expiration rules. |
| Delivered local private outputs | 7-30 days after manual upload verification | Runtime/storage operator | Keep on encrypted private storage; do not back up to public or developer sync folders. |
| Audit logs and metadata | 180-365 days | Platform operator | Restrict access because private locators can reveal internal storage structure. |

Tune these defaults for contractual, legal, tax, and client-delivery requirements. Shorter retention is preferred when no external requirement exists.

## Staged Output Cleanup

Staged files are intermediate artifacts. They can be removed only after the output row shows:

- `delivery.status = delivered`
- `delivery.delivered_locator` starts with `drive://`, `s3://private/`, or `file://private/delivered/`
- `upload_package.manual_upload_only = true`

When `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY=true`, the API removes the staged source file after a delivery adapter succeeds and records `delivery_json.staged_source_cleanup.status`. If cleanup is disabled, operators should delete staged project directories manually after delivery validation.

## Delivered Output Retention

Delivered outputs are the private manual-upload package. Do not delete them until:

- the destination is confirmed private and access-controlled
- the operator has completed any required manual upload
- the uploaded platform copy has passed basic playback and caption checks
- the project owner no longer needs the private rendered file for re-upload

For local private delivery, store `LOCAL_PRIVATE_DELIVERY_ROOT` on encrypted storage outside the repository and outside consumer sync tools. For S3, configure a lifecycle expiration rule on `S3_PREFIX`. For Drive, use a restricted output folder with a periodic owner review.

Delivery adapters attach machine-readable retention metadata:

- Drive: file `appProperties`
- S3: object tags
- local private storage: sibling `.retention.json` sidecar

Set `DELIVERED_OUTPUT_RETENTION_DAYS` and `DELIVERED_OUTPUT_RETENTION_POLICY` to match the operator policy.

## Deletion Procedure

1. Export or review `/projects/{project_id}/outputs`.
2. Review `/projects/{project_id}/outputs/retention` for retention metadata, cleanup status, and due items.
3. Preview due local-private cleanup with `POST /projects/{project_id}/outputs/retention/cleanup` and `{"dry_run": true}`.
4. Confirm every output that will be deleted has `delivery.status = delivered`.
5. Confirm the manual upload is complete or explicitly waived.
6. Delete due local-private files with `POST /projects/{project_id}/outputs/retention/cleanup` and `{"dry_run": false}`.
7. For Drive and S3, use provider lifecycle rules or provider-native deletion after the same checks.
8. Keep API metadata and audit logs until their retention window expires.
9. Record the cleanup action in the operator change log or incident tracker.

Never delete a failed or `private_staging` output unless the project owner has confirmed the render is abandoned and no retry is needed.

## Public Repository Guardrails

Do not commit or attach:

- raw source media
- staged render files
- delivered outputs
- local database files
- `.env` files
- exported OAuth tokens or cloud credentials

Only commit documentation, tests, source code, manifests, and placeholder examples.
