# Decision Log — Todo Lists API

Records what was decided and why, across the plan (`openspec/changes/todo-api/`)
and anything confirmed with the user after the explore phase. Pending items are
tracked explicitly rather than silently dropped.

## Plan Decisions

| # | Decision | Rationale | Source |
|---|----------|-----------|--------|
| 1 | `uv_build` as the PEP 517 build backend for the `src` layout | Native to `uv`, no extra dependency | design.md ADR-15 |
| 2 | VARCHAR + CHECK instead of native PostgreSQL ENUM for `status`/`priority` | Alembic autogenerate does not detect enum value changes; plain migrations are simpler to evolve | design.md ADR-08 |
| 3 | `/health/ready` added as a spec delta in the bootstrap slice | User-confirmed decision not present in the original spec; readiness probe runs `SELECT 1` | tasks.md 0.6, specs/project-bootstrap/spec.md |

## Post-Explore Product Decisions

Confirmed with the user during the explore/planning session; recorded here as
they land in code, not as a batch at the end.

| # | Decision | Notes |
|---|----------|-------|
| 1 | API versioned under `/api/v1` from day one; `/health`, `/health/ready` stay unversioned at the root | design.md ADR-01 |
| 2 | Delivery via 11 gitflow slices (+1 optional), one PR per slice into `develop`, final `release/1.0.0` → `main` tagged `v1.0.0` | tasks.md Review Workload Forecast |

## Pending / Deferred

| Item | Status | Planned slice |
|------|--------|---------------|
| Refresh-token rotation and denylist | Deferred, documented as a known gap | n/a (out of scope) |
| Shared lists / collaboration | Out of scope | n/a |
| Real email delivery | Out of scope — console/log notifier only | Phase 8 |

## Bootstrap Slice (Phase 0) Notes

- `uv_build` backend configured with `module-name = "app"`, `module-root = "src"`
  (package name `app` differs from the distribution name `todo-api`).
- `pytest.ini` starts with `--cov-fail-under=0` since there is no application
  code to meaningfully cover yet; raised to `75` starting with slice 1a.
- A minimal async engine/session factory (`infrastructure/db/session.py`) was
  added ahead of slice 1a's full persistence layer, strictly to back
  `/health/ready`'s `SELECT 1` check. The declarative base, ORM models,
  mappers, repositories, and Unit of Work still land in slice 1a as planned.
- `testcontainers.postgres` emits a `DeprecationWarning` recommending
  `testcontainers.community.postgres` (observed against the pinned version
  in `uv.lock`); revisit the import path when slice 1a's integration harness
  is built.
- `docker/entrypoint.sh` conditionally runs `alembic upgrade head` only when
  `alembic.ini` exists, so it is a true no-op until slice 1a adds it — no
  entrypoint change needed then.
