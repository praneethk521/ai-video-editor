# Security Review

Review date: 2026-10-07

Baseline: `codex/local-trip-curation` plus the remediations described here.

## Outcome

The implemented private-media MVP has a defensible security baseline for its intended local-only, single-owner use. It is not an internet service and should not be exposed outside this laptop. A real Google Photos album acceptance run and larger/adversarial media testing remain open.

No known fixable high or critical findings remain in the built API and worker images at review time. Application dependency audits and repository secret scanning are clean.

## Review Coverage

- OIDC, service-token, project/team RBAC, CORS, trusted hosts, OAuth state and token handling.
- Ingest validation, malware gate, locator/path handling, FFmpeg invocation, queue callbacks, private delivery, audit logs, metrics, and traces.
- API and worker Python dependencies, web npm dependencies, GitHub Actions, Dockerfiles, Compose, Kubernetes, and n8n image pin.
- Public GitHub repository, Actions status, Dependabot presence, disclosure policy, and settings visibility through Chrome.

## Findings And Remediation

| Severity | Finding | Resolution |
| --- | --- | --- |
| Critical | Next 15.1.3 and React 19.0.0 dependency graph reported 2 critical and 14 high advisories, including React Flight RCE and Next middleware authorization issues. | Upgraded to Next 16.4.0 and React 19.2.8, committed an npm lockfile, and added `npm audit --audit-level=high`; audit now reports zero vulnerabilities. |
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

- API: 111 tests pass in a disposable writable container.
- Worker: 6 tests pass; Ruff clean.
- Web: TypeScript check and Next 16.4.0 production build pass; npm audit reports zero vulnerabilities.
- Python: API, worker, and MCP media server `pip-audit` report no known vulnerabilities.
- Images: API and worker execute as `10001:10001`; runtime imports pass with read-only roots; Trivy 0.74 reports zero fixable high/critical findings.
- Secrets: Trivy repository scan and full-history Gitleaks scan report no findings. The root `.env`, media, outputs, and local state are ignored; downloaded OAuth JSON was removed.
- Infrastructure: base and observability Compose expansion pass; Kubernetes YAML parses.

## OAuth Scope Decision

The production trip-import path uses only `photospicker.mediaitems.readonly`. It lets the app create and inspect Picker sessions and download only the photos and videos the owner explicitly selects. It does not grant library-wide browsing, modification, or deletion. The legacy optional Drive field is not the recommended private-album path.

The OAuth web client has one exact loopback redirect, `http://localhost:8001/oauth/google-photos/callback`. Authorization uses PKCE, a random one-use expiring state value, exact scope validation, and encrypted local token storage. The Google project is external/testing with one test user and no billing account. The first owner consent and real-album acceptance run remain unfinished.

References:

- https://developers.google.com/photos/overview/authorization
- https://developers.google.com/photos/picker/guides/media-items
- https://developers.google.com/identity/protocols/oauth2/resources/best-practices

## GitHub External State

The repository is intentionally public and Dependabot branches are present. Local full-history and working-tree scans are clean. GitHub Advanced Security, secret-scanning alert, push-protection, and branch-protection settings were not authenticated through an API during this review, so the local scans are the verified evidence.

## Residual Risks

- A thief or malware process with both the local database/Docker volumes and the root `.env` could decrypt and reuse the stored Google refresh token until access is disconnected or revoked.
- OAuth client credentials identify this installed local app but do not protect a compromised laptop. PKCE and one-use state reduce authorization-code interception and CSRF risk.
- Imported originals and rendered outputs are private files on this laptop; disk encryption, account security, backups, and deletion remain owner responsibilities.
- ClamAV and type checks reduce malicious-media risk but cannot eliminate parser or FFmpeg vulnerabilities. Large, unusual, and adversarial workloads need more evidence.
- Dependency and container vulnerabilities can appear after this point-in-time audit. Dependabot and the CI security gates must remain enabled and acted on.
- GitHub secret scanning, push protection, private vulnerability reporting, and branch protection should be confirmed in repository settings while signed in.

## Release Decision

Suitable for local single-owner trip editing with approved private media. Local-file import is ready. Google Photos is release-ready after the owner completes first consent and one real-album import/render acceptance run. Do not expose the local ports to another host or classify this as a hosted multi-tenant service.
