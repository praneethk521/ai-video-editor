# RBAC Design

RBAC is a P0 production hardening requirement. The API authenticates bearer tokens and enforces project roles, team and direct membership, and scoped internal service tokens.

## Goals

- Restrict project, media, analysis, planning, rendering, output delivery, retention cleanup, and audit operations by role.
- Preserve the public-code/private-media model.
- Keep internal worker callbacks authenticated and narrowly scoped.
- Make authorization decisions auditable without logging private media locators or secrets.

## Roles

| Role | Scope | Capabilities |
| --- | --- | --- |
| `owner` | project/team | Full project administration, deletion, retention cleanup, delivery configuration, user assignment. |
| `operator` | project/team | Ingest, scan, analyze, review plans, queue renders, deliver outputs, run retention reports and cleanup previews. |
| `reviewer` | project/team | View project metadata, analysis, plans, outputs, and approve/reject plans. |
| `viewer` | project/team | Read-only access to project status, plans, outputs, retention report, and audit summaries. |
| `worker` | internal | Render lifecycle callbacks and scan/delivery callbacks for assigned jobs only. |
| `admin` | deployment | Cross-project operational access for break-glass, audit, and support workflows. |

## Resource Model

Add explicit membership records:

- `teams`
- `team_members`
- `project_members`
- optional `service_tokens` for workers and orchestrators

Projects should remain owned by a user or team. A user receives access through direct project membership, team membership, or deployment admin role.

## Endpoint Policy

| Endpoint group | Minimum role |
| --- | --- |
| Create project | authenticated user |
| Read project/status/analysis/plans/outputs | `viewer` |
| Connect Drive/sync/ingest/scan/analyze | `operator` |
| Approve/reject/regenerate plans | `reviewer` for review, `operator` for regenerate |
| Queue renders | `operator` |
| Delivery and delivery retry | `operator` |
| Retention report | `viewer` |
| Retention cleanup dry-run | `operator` |
| Retention cleanup execution | `owner` or `admin` |
| Project deletion | `owner` or `admin` |
| Internal worker callbacks | `worker` service token scoped to job/project |
| Analysis provider health/metrics | `operator` or `admin` |
| Platform Prometheus metrics | global `metrics` service token or `admin`/`internal`/`orchestrator` super-scope |

## Enforcement

1. Membership tables and migrations model direct users, teams, and workload tokens.
2. OIDC tokens are validated against deployment trust settings and mapped to stable local users.
3. Project endpoints resolve owner, direct, team, deployment-admin, or scoped-orchestrator roles.
4. Internal endpoints require stored service tokens with project and operation scopes.
5. Authorization outcomes are audited with bounded identifiers and roles only.
6. Allow and deny tests cover human roles, cross-project access, workload scopes, and membership administration.
7. The dashboard derives the effective role from the API and gates controls accordingly.

The schema lives in `apps/api/migrations/002_rbac.sql` and `004_oidc_user_roles.sql` with matching SQLAlchemy models. User-facing project authorization is enforced through `apps/api/app/services/authorization.py`; internal callbacks use scoped service-token checks in `apps/api/app/core/security.py` and `apps/api/app/api/internal.py`. The shared API token remains available only for explicit local workflows. Project and team authorization decisions emit audit rows, and the dashboard uses server-derived roles for viewer, reviewer, operator, owner, and admin controls.

Production configuration and workload-token provisioning are documented in `docs/RBAC_DEPLOYMENT.md`.

## Audit Requirements

Audit logs should record:

- user ID or service token ID
- project ID
- requested action
- authorized role
- allow or deny result
- correlation ID

Audit logs must not record OAuth tokens, media bytes, raw public URLs, private media locators, delivered locators, or filesystem paths.

## Acceptance Criteria

- Cross-project access is denied by default.
- Viewer cannot mutate project state.
- Reviewer can approve/reject plans but cannot deliver outputs or run cleanup execution.
- Operator can run the private workflow but cannot delete projects or execute due retention cleanup.
- Owner can administer project membership and retention cleanup execution.
- Worker/service tokens cannot call user-facing project administration endpoints.
- Tests cover allow and deny cases for every endpoint group.
