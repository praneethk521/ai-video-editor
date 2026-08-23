# Threat Model

Last reviewed: 2026-08-23

## Scope

This model covers the browser dashboard, FastAPI service, PostgreSQL and Redis state, RQ worker and FFmpeg processes, Google Drive OAuth and media access, private output delivery, n8n orchestration, observability, and the repository build pipeline. Source media, outputs, credentials, and deployment data are private even though the source repository is public.

## Security Objectives

| Asset | Required property |
| --- | --- |
| Source media and rendered outputs | Confidential, project-isolated, private at rest, and never published automatically. |
| OIDC, OAuth, and service credentials | Encrypted or hashed at rest, least privilege, never logged, and revocable. |
| Projects, plans, memberships, and audit records | Authorized access, integrity, and durable attribution. |
| Render workers and staging storage | Isolated execution, bounded resources, validated paths, and cleanup. |
| Provider calls and telemetry | Minimum necessary metadata, bounded egress, and no private locators by default. |
| Build and deployment artifacts | Reproducible dependencies, reviewed changes, and vulnerability-scanned non-root images. |

## Actors

- Project owners, operators, reviewers, and viewers authenticated by a trusted OIDC provider.
- Deployment administrators mapped from one explicit OIDC role value.
- Worker, orchestrator, and metrics workloads using distinct stored service tokens.
- Google Drive, private analysis providers, S3, and observability backends.
- Attackers with network access, a low-privilege account, a stolen token, or a crafted media file.
- A compromised dependency, CI action, container layer, or external provider.

## Trust Boundaries

1. Browser to dashboard and API: untrusted requests cross CORS, host, authentication, rate-limit, and schema-validation controls.
2. Identity provider to API: JWT claims are untrusted until issuer, audience, signature, algorithm, lifetime, and required claims validate against trusted JWKS.
3. API to PostgreSQL, Redis, and RQ: project IDs, authorization results, counters, and jobs must remain consistent across replicas.
4. API to Google and analysis providers: OAuth tokens and provider credentials cross an external network boundary; private media references are withheld unless explicitly enabled.
5. Worker to FFmpeg and staging storage: media and timeline metadata are untrusted inputs entering a resource-intensive native process.
6. API to Drive, S3, or local delivery: private outputs cross a provider boundary and must retain private ACL, encryption, and retention metadata.
7. Services to observability: logs, metrics, and traces cross an operations boundary and must not carry tokens, URLs, identifiers, media, or exception payloads.
8. Developer workstation and GitHub to images: public source and third-party dependencies cross the build supply-chain boundary.

## Threats And Controls

| Threat | Primary controls | Remaining risk |
| --- | --- | --- |
| Forged or confused identity token | Explicit asymmetric algorithms, issuer/audience/JWKS validation, required `exp`/`iat`/subject/email claims, stable subject mapping, production fail-closed startup. | Identity provider compromise and claim-mapping changes remain deployment risks. |
| Cross-project IDOR or privilege escalation | Server-derived project role, direct/team membership checks, role matrix, project-scoped service principals, authorization audit events, deny tests. | Deployment administrators retain global access by design. |
| Stolen workload token | Separate hashed service tokens, scope and optional project binding, legacy shared token rejected in production, secret-manager deployment guidance. | Rotation and revocation cadence is deployment-owned. |
| Browser-origin or Host-header abuse | Explicit CORS origins and methods, trusted hosts, no credentials in CORS, no-store and anti-framing headers, HTTPS-only production origin validation. | TLS termination and ingress header normalization are deployment-owned. |
| OAuth CSRF, replay, or scope escalation | Random one-time state stored as a hash, state cleared on success, encrypted token payload, incremental grants disabled, reported token scopes must exactly match the configured request. | `drive.readonly` is a restricted broad scope; migration to Google Picker plus `drive.file` is preferred when product UX supports it. |
| Malicious upload or media parser exploit | MIME and size allowlists, filename and locator validation, duplicate checks, ClamAV gate, non-root worker, read-only root filesystem, dropped capabilities, seccomp, time and disk limits. | FFmpeg remains a large native attack surface; representative fuzz and workload testing is incomplete. |
| Path traversal or command injection | Shared path/locator validation, sanitized filenames, fixed output roots, subprocess argument arrays, no user scripts or shell interpolation. | New renderer features must preserve these invariants. |
| SSRF or provider data exfiltration | Provider base URLs are deployment configuration, requests use fixed adapter paths, private locator sharing defaults off, bounded timeout/retry/circuit breaker. | Deployment egress allowlists and provider contractual retention are not represented in code. |
| Queue spoofing or callback tampering | Stored worker token, project-scoped authorization, server-owned job IDs and transitions, callback schema validation. | Redis transport encryption and network policy depend on deployment. |
| Shared staging disclosure | Private locator namespaces, project-specific output paths, private delivery adapters, non-root mounts, read-only containers, staged cleanup option. | ReadWriteMany storage encryption and tenant-level filesystem isolation depend on the storage class. |
| Public output publication | Public URLs rejected, Drive/S3/local private locators only, S3 encryption and privacy tags, manual-upload-only package. | Provider-side ACL drift requires reconciliation. |
| Secret or media leakage in logs/traces | Sensitive audit-key redaction, normalized route labels, bounded trace attributes, no payload/header/query recording, repository secret scan. | Third-party SDK logging must be re-reviewed when providers change. |
| Resource or cost exhaustion | Redis rate limits, atomic daily project quotas, render timeouts, pod CPU/memory/disk limits, provider cost accounting and circuit breaker. | Load-test targets and autoscaling policies are incomplete. |
| Dependency or CI compromise | npm lockfile, npm/pip audits, pinned GitHub Actions commits, read-only CI token, Trivy secret and image gates, patched OS layers, Dependabot. | Base images and scanner databases require continuous refresh; branch settings remain external state. |
| Data loss or retention failure | Retention metadata, staged/local cleanup, delivery audit records. | Provider-native deletion and tested backup/restore remain open P1 work. |
| Exposed n8n editor | Loopback-only local port, private Kubernetes service, encrypted credentials, non-root/read-only reference pod. | Production SSO/VPN/private ingress is deployment-owned and mandatory. |

## Assumptions

- Production runs only with validated OIDC and separate stored workload tokens.
- TLS, database encryption, private networking, secret storage, object-store public-access blocks, and storage encryption are supplied by the deployment platform.
- The selected analysis provider is approved for the data classification it receives.
- Operators do not place real media, outputs, databases, or credentials in the repository or CI artifacts.

## Open Risk Register

| Priority | Risk | Exit signal |
| --- | --- | --- |
| P1 | Provider-native Drive/S3 deletion is not reconciled. | Idempotent deletion or lifecycle-policy evidence with audit reconciliation. |
| P1 | Renderer hardening lacks representative real-media and adversarial workload evidence. | Long-form and vertical workload suite passes under production limits. |
| P1 | Backup and restore are untested. | Encrypted backup and timed restore drill completes in staging. |
| P1 | Production topology is a reference, not a deployed environment. | Ingress, network policy, autoscaling, secret manager, storage, rollback, and monitoring are exercised together. |
| P2 | Load and failover targets are undefined. | Documented concurrency/SLO targets pass sustained and failure-mode tests. |

Review this model when adding a media provider, renderer feature, public endpoint, new role, new delivery target, or new telemetry field, and after every security incident.
