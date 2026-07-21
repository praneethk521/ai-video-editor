# RBAC Design

RBAC is a P0 production hardening requirement. The current API authenticates requests with bearer tokens and stores project ownership, but it does not yet enforce multi-role access across users or teams.

## Goals

- Restrict project, media, analysis, planning, rendering, output delivery, retention cleanup, and audit operations by role.
- Preserve the public-code/private-media model.
- Keep internal worker callbacks authenticated and narrowly scoped.
- Make authorization decisions auditable without logging private media locators or secrets.

## Proposed Roles

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

## Enforcement Plan

1. Add membership tables and migrations.
2. Expand `CurrentUser` to include role claims or load memberships from the database.
3. Replace owner-only checks with `require_project_role(project_id, user, minimum_role)`.
4. Add service-token checks for internal endpoints.
5. Include authorization outcomes in audit logs with role and project ID only.
6. Add tests for each endpoint group and for cross-project denial.
7. Update dashboard behavior to hide actions the current role cannot execute.

The draft schema lives in `apps/api/migrations/002_rbac.sql` and matching SQLAlchemy models. The helper skeleton lives in `apps/api/app/services/authorization.py`.

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
