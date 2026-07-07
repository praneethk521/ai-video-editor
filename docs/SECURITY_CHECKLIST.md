# Security Checklist

## Repository

- Public or private source repositories are acceptable only if media, outputs, local databases, and real secrets remain untracked.
- Enable branch protection on `main`.
- Require at least one approving review.
- Enable secret scanning and push protection.
- Enable dependency scanning and Dependabot.
- Use GitHub Actions OIDC for cloud deploy permissions.

## Secrets

- Store real secrets in AWS Secrets Manager, Doppler, Vault, or GitHub Actions secrets.
- Commit only `.env.example`.
- Rotate Google OAuth, AI provider, database, and n8n secrets regularly.
- Set `TOKEN_ENCRYPTION_KEY` before storing OAuth credentials outside local/test.
- Never log OAuth tokens, media locators, raw URLs, or file contents.

## Google Drive

- Use OAuth.
- Default to `https://www.googleapis.com/auth/drive.readonly`.
- Download only authorized files from the selected folder.
- Store Drive file identifiers and checksums as metadata, not raw public URLs.
- Store encrypted tokens only if refresh access is required.

## Media Handling

- Reject public media URLs.
- Validate MIME type, size, duration, and extension.
- Sanitize filenames and block path traversal.
- Scan all files for malware before rendering.
- Use the internal scan endpoint to stream private media bytes to ClamAV before analysis.
- Store source and output media privately with encryption at rest.
- Use short-lived signed URLs only for temporary internal access.
- Cleanup temporary files after each job.

## Runtime

- Require authentication on every endpoint.
- Add RBAC before multi-user production rollout.
- Add rate limits and cost quotas.
- Run workers with no unnecessary Linux capabilities.
- Use read-only filesystems and temp volumes with size limits.
- Do not execute user-provided scripts.
- Isolate jobs by project and user.

## n8n

- Self-host n8n.
- Keep the editor behind SSO, VPN, or a private network.
- Encrypt n8n credentials.
- Do not perform heavy rendering inside n8n.
- Use n8n for orchestration and MCP/API calls only.
