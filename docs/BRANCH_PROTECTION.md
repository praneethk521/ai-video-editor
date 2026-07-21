# Branch Protection

Use branch protection on `main` before relying on this repository for production or client media workflows.

## Required Checks

Require the GitHub Actions checks from `.github/workflows/ci.yml`:

- `api-tests`
- `worker-tests`
- `web-build`
- `shell-scripts`
- `infra-validation`

When new CI jobs are added, update this list and the branch protection rule in the same pull request.

## Pull Request Rules

Recommended settings for `main`:

- Require a pull request before merging.
- Require at least one approving review.
- Dismiss stale approvals when new commits are pushed.
- Require conversation resolution before merging.
- Require status checks to pass before merging.
- Require branches to be up to date before merging when the queue is busy.
- Block force pushes.
- Block deletions.
- Include administrators unless an emergency break-glass process exists.

Prefer squash merges for routine feature work so public history stays readable. Use merge commits only when preserving a multi-commit integration history matters.

## Public Repo Guardrails

Keep source public and media private:

- Commit `.env.example`, never `.env`.
- Do not commit source media, staged renders, delivered outputs, local SQLite databases, OAuth token exports, or provider credentials.
- Keep GitHub secret scanning and push protection enabled.
- Keep Dependabot alerts and updates enabled.
- Store deploy credentials in GitHub Actions secrets or a cloud secret manager.
- Prefer GitHub Actions OIDC for cloud deploy roles instead of long-lived cloud keys.

## Required Review Focus

Reviewers should explicitly check:

- Private locators are not converted into public URLs.
- Logs and audit metadata do not include tokens, media bytes, or public share links.
- Delivery adapters only write to private Drive, `s3://private/`, or local private storage.
- Retention cleanup changes preserve dry-run behavior and audit metadata.
- New scripts are covered by `shell-scripts`.
- New infrastructure manifests are covered by `infra-validation`.

## Emergency Changes

For urgent fixes:

1. Keep the branch protection rule enabled whenever possible.
2. Use a short-lived emergency branch and require the fastest available reviewer.
3. Run the same local validation listed in `docs/status.md`.
4. Record the reason, risk, and follow-up cleanup in the pull request.
5. Re-enable any temporarily relaxed rule immediately after the fix.
