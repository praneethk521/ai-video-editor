# Security Review

Review date: 2026-08-23

Baseline: `ae4a062` plus the remediations described here.

## Outcome

The implemented private-media MVP has a defensible application security baseline after remediation. It is not yet a production-complete multi-tenant service because provider-native retention, renderer workload hardening, backup/restore, a fully exercised deployment, n8n perimeter controls, and load testing remain open.

No known fixable high or critical findings remain in the built API and worker images at review time. Application dependency audits and repository secret scanning are clean.

## Review Coverage

- OIDC, service-token, project/team RBAC, CORS, trusted hosts, OAuth state and token handling.
- Ingest validation, malware gate, locator/path handling, FFmpeg invocation, queue callbacks, private delivery, audit logs, metrics, and traces.
- API and worker Python dependencies, web npm dependencies, GitHub Actions, Dockerfiles, Compose, Kubernetes, and n8n image pin.
- Public GitHub repository, Actions status, Dependabot presence, disclosure policy, and settings visibility through Chrome.

## Findings And Remediation

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Next 15.1.3 and React 19.0.0 dependency graph reported 2 critical and 14 high advisories, including React Flight RCE and Next middleware authorization issues. | Upgraded to Next 16.3.2 and React 19.2.8, committed an npm lockfile, and added `npm audit --audit-level=high`; audit now reports zero vulnerabilities. |
| High | API audit reported 25 known vulnerabilities across `python-multipart`, `cryptography`, unused `orjson`, and transitive Starlette. | Upgraded FastAPI, multipart, and cryptography, removed unused orjson, and verified API and worker `pip-audit` report no known vulnerabilities. |
| High | The current Debian base contained four fixable `util-linux` CVEs repeated across nine packages. | Both image builds apply available OS upgrades. Trivy 0.74 reports zero fixable high/critical findings for API and worker images. |
| High | Custom API and worker images ran as root; pod specs did not require a non-root UID or runtime-default seccomp. | Images now run as UID/GID 10001. Compose and Kubernetes enforce read-only roots, no privilege escalation, dropped capabilities, bounded temp storage, and Kubernetes seccomp/non-root pod policies. |
| High | API production image omitted `httpx`, so OAuth/provider imports failed even though development tests passed. | Moved `httpx` into runtime requirements and added CI image import checks under a read-only filesystem. |
| Medium | Dashboard/API cross-origin behavior had no explicit CORS policy or host allowlist. | Added explicit local origins/hosts, HTTPS and non-wildcard production validation, restrictive methods/headers, response hardening, and allow/deny tests. |
| Medium | Google OAuth enabled incremental authorization, which could include prior grants. | Disabled `include_granted_scopes` and reject reported scope sets that are not exactly the configured request. |
| Medium | Recent GitHub API/worker jobs failed because the `pytest` console script did not preserve the app import path. | CI now uses `python -m pytest`, enforces Ruff, and pins Node 24-compatible GitHub Actions by commit. Remote confirmation is required after push. |
| Medium | The public repository had no GitHub-detected security policy. | Added root `SECURITY.md` with private reporting and data-handling guidance. |
| Medium | Local database, Redis, ClamAV, API, worker metrics, and n8n ports listened on all host interfaces. | Compose host ports now bind to `127.0.0.1`; n8n was updated from 1.73.1 to maintained 1.123.65 and hardened. |

## Evidence

- API: 65 tests pass; Ruff clean.
- Worker: 6 tests pass; Ruff clean.
- Web: TypeScript check and Next 16.3.2 production build pass; npm audit reports zero vulnerabilities.
- Python: API and worker `pip-audit` report no known vulnerabilities.
- Images: API and worker execute as `10001:10001`; runtime imports pass with read-only roots; Trivy 0.74 reports zero fixable high/critical findings.
- Secrets: Trivy repository secret scan reports no findings.
- Infrastructure: base and observability Compose expansion pass; Kubernetes YAML parses.

## OAuth Scope Decision

The current folder-URL workflow uses `drive.readonly`, which Google classifies as a restricted scope because it can read all Drive files the user can access. It matches the PRD's read-only ingestion behavior but may trigger verification and security-assessment requirements when restricted data is stored or transmitted. A future Google Picker flow should prefer `drive.file`, which Google recommends for per-file access. Drive output delivery remains opt-in and requires an explicit write-capable scope and private output folder.

References:

- https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- https://developers.google.com/identity/protocols/oauth2/web-server

## GitHub External State

Chrome confirmed the repository is public, Dependabot is active, and the latest pre-remediation CI run failed in API and worker jobs. The available Chrome session was signed out, so branch protection, private vulnerability reporting, secret scanning, and push-protection settings could not be read or changed. These controls remain deployment/repository-owner gates in `docs/BRANCH_PROTECTION.md` and `docs/RELEASE_READINESS.md`.

## Residual Risks

- Provider-native Drive/S3 retention deletion and ACL reconciliation are incomplete.
- OAuth access-token refresh is not implemented; expired Drive sessions require reconnection.
- The FFmpeg renderer still needs real and adversarial workload evidence.
- Production n8n must be behind SSO, VPN, or private ingress.
- Backup/restore, autoscaling, network policies, full environment deployment, and load/failover testing need operational evidence.
- GitHub branch and security settings need authenticated verification after this remediation is pushed.

## Release Decision

Suitable for continued local development and a controlled private staging deployment with synthetic or approved data. Do not classify it as a completed production launch until the P1 exit criteria in `docs/PRODUCTION_GAP_TRACKER.md` are satisfied and the external GitHub/deployment gates are verified.
