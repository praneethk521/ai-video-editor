# RBAC Deployment

Production uses OIDC bearer tokens for people and stored, hashed service tokens for workers, n8n, and metrics collectors. The local shared `API_TOKEN` bridge is intentionally rejected when `APP_ENV=production`.

## Identity Provider

Configure the deployment from `infra/k8s/auth-config.example.yaml`:

- `OIDC_ISSUER_URL` must exactly match the token `iss` claim.
- `OIDC_AUDIENCE` must identify this API and match `aud`.
- `OIDC_JWKS_URL` must be the provider's trusted HTTPS JWKS endpoint.
- `OIDC_ALGORITHMS` must be an explicit asymmetric allowlist such as `RS256`.
- Tokens must include `exp`, `iat`, a stable subject, and an email claim.
- Only the configured `OIDC_ADMIN_ROLE` value maps to deployment-wide `admin`; all other access comes from project or team membership.

The API hashes issuer plus subject into a stable local user ID and stores the normalized email. An email already mapped to another subject is rejected instead of silently relinking the account.

## Database

Apply migrations through `apps/api/migrations/004_oidc_user_roles.sql` before deploying the new API image. The API creates missing tables in local development, but production schema changes should run as a controlled migration step.

## Service Tokens

Create separate random tokens for each workload. Run from the repository root with the production `DATABASE_URL` available:

```bash
PYTHONPATH=apps/api .venv/bin/python scripts/create-service-token.py --name render-worker --scope worker
PYTHONPATH=apps/api .venv/bin/python scripts/create-service-token.py --name n8n-orchestrator --scope orchestrator
PYTHONPATH=apps/api .venv/bin/python scripts/create-service-token.py --name prometheus --scope metrics
```

The secret is printed once; only its SHA-256 hash is stored. Put each raw value directly into the corresponding secret manager entry:

- Worker `API_TOKEN`: worker token.
- n8n `API_TOKEN`: orchestrator token.
- Prometheus `metrics-token`: metrics token.

Use `--project-id` for dedicated worker or delivery tokens that must be limited to one project. Revoke a token by setting its database status to `inactive` and rotating the workload secret.

## Rollout Validation

1. Verify `/auth/me` accepts a provider token and returns the expected stable identity.
2. Have each user sign in once so their stable identity is provisioned, then add their exact email or a team through the dashboard Access panel or `/projects/{project_id}/members` APIs.
3. Confirm a viewer can read status but receives `403` for render and delivery operations.
4. Confirm worker, n8n, and metrics requests succeed with their distinct service tokens.
5. Confirm the old local `API_TOKEN` receives `401` on internal endpoints.
