# Output Delivery Deployment

This project keeps rendered outputs private. Delivery adapters only write to private Drive, S3, or local private storage targets and must not create public URLs.

## Shared Staging

The worker writes staged files under:

```text
VIDEO_TEMP_ROOT=/tmp/ai-video-editor
```

The API delivery adapter reads staged files from:

```text
OUTPUT_DELIVERY_LOCAL_ROOT=/tmp/ai-video-editor/outputs
```

In Docker Compose, both services mount the `output-staging` volume at `/tmp/ai-video-editor`.

In Kubernetes, both services mount the `ai-video-output-staging` PVC at `/tmp/ai-video-editor`. The starter manifest requests `ReadWriteMany`; choose a storage class that supports multi-pod read/write access, such as EFS, Filestore, Azure Files, or an equivalent private shared filesystem.

## Google Drive Delivery

Drive ingestion defaults to read-only:

```text
GOOGLE_DRIVE_SCOPES=https://www.googleapis.com/auth/drive.readonly
```

Drive output delivery needs a write-capable token. Use an explicit scope only for deployments that enable Drive output delivery, for example:

```text
GOOGLE_DRIVE_SCOPES=https://www.googleapis.com/auth/drive.file
GOOGLE_DRIVE_OUTPUT_FOLDER_ID=<private-output-folder-id>
OUTPUT_STORAGE_PROVIDER=drive
```

Operational notes:

- Keep the output folder private and access-controlled.
- Reconnect OAuth after changing scopes so the encrypted token has the correct grant.
- Store OAuth client credentials and `TOKEN_ENCRYPTION_KEY` in a secret manager, not in source control.
- Audit delivered locators as Drive file IDs, not public share links.

## S3 Delivery

Use a bucket with public access blocked and default encryption enabled.

```text
OUTPUT_STORAGE_PROVIDER=s3
AUTO_DELIVER_OUTPUTS=false
S3_BUCKET=<private-render-output-bucket>
S3_REGION=us-east-1
S3_PREFIX=ai-video-editor/outputs
MEDIA_ENCRYPTION_KMS_KEY_ID=<optional-kms-key-id>
```

Minimum IAM shape for API delivery:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::<private-render-output-bucket>/ai-video-editor/outputs/*"
    },
    {
      "Effect": "Allow",
      "Action": ["kms:Encrypt", "kms:GenerateDataKey"],
      "Resource": "<kms-key-arn>",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "s3.us-east-1.amazonaws.com"
        }
      }
    }
  ]
}
```

If no KMS key is configured, the adapter requests SSE-S3 (`AES256`).

## Kubernetes Secrets

Create separate API and worker secrets. Keep sensitive values in your secret manager or sealed-secret workflow.

```bash
kubectl create secret generic ai-video-api-secrets \
  --from-literal=API_TOKEN=... \
  --from-literal=DATABASE_URL=... \
  --from-literal=REDIS_URL=... \
  --from-literal=TOKEN_ENCRYPTION_KEY=... \
  --from-literal=GOOGLE_CLIENT_ID=... \
  --from-literal=GOOGLE_CLIENT_SECRET=... \
  --from-literal=GOOGLE_DRIVE_SCOPES=https://www.googleapis.com/auth/drive.file \
  --from-literal=GOOGLE_DRIVE_OUTPUT_FOLDER_ID=... \
  --from-literal=OUTPUT_STORAGE_PROVIDER=drive
```

For S3 delivery, prefer workload identity/OIDC over static AWS keys. If static keys are unavoidable, store them only in the secret manager backing the runtime environment.

## Delivery Runbook

1. Render jobs complete and create `file://private/<project>/<variant>.mp4` source locators.
2. Confirm the staged file exists under `OUTPUT_DELIVERY_LOCAL_ROOT`.
3. Call `POST /internal/output-videos/{output_video_id}/deliver` with the target, or let orchestration call it after render completion.
4. Verify `/projects/{project_id}/outputs` shows `delivery.status = delivered`.
5. Cleanup staged files only after delivered locators point to Drive, `s3://private/`, or local private storage.

Set `CLEANUP_STAGED_OUTPUTS_AFTER_DELIVERY=true` to let the API remove the staged `file://private/...` source file after a delivery adapter succeeds. Keep it disabled when operators need to inspect staged render files after delivery.

Set `AUTO_DELIVER_OUTPUTS=true` only when the API can read the shared staging volume and the selected delivery target has working credentials. Leave it `false` when n8n or another orchestrator should decide when to deliver.
