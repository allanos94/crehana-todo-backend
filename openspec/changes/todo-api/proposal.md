# Proposal: Todo Lists API (Crehana Backend Challenge)

> **This is a BOOTSTRAP change, not an incremental change.** The repository holds no source code, no `pyproject.toml`, and no installed stack. This change creates the planned stack (Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, PostgreSQL 16, Pydantic v2, uv, pytest, black/isort/flake8/mypy --strict, Docker, GitHub Actions) and the first full feature set on top of it. There is no existing behavior to preserve or migrate.

## Intent

Crehana's Backend Developer technical challenge (deadline 2026-10-08) requires a REST API for managing task lists and their tasks, built with Python, FastAPI, a real database, pytest (coverage ≥75%), flake8, black, a multistage Dockerfile, docker-compose, a README, and a `DECISION_LOG.md`, using a layered Domain / Application / Infrastructure architecture with Pydantic typing, custom exceptions, and business validations. Optional bonus items are JWT authentication, assigning a responsible user to a task, and a fake email invitation.

The goal is to deliver every mandatory requirement and the three chained bonus items (users → assignment → invitation) in a way an evaluator can review: small PRs through gitflow, specs with scenarios in `openspec/`, and a decision log that records both what was chosen and what was deliberately deferred.

## Scope

### In Scope

- **Project bootstrap**: uv project (PEP 621 `pyproject.toml` + `uv.lock`), `src/app/` layered skeleton, pydantic-settings config, app factory with `GET /health`, tool configs (`.flake8`, `pytest.ini` with `--cov-fail-under=75`, isort profile=black, mypy --strict, pre-commit), `.gitattributes` (LF), multistage Dockerfile (uv builder → slim, non-root, healthcheck), docker-compose (api + postgres, Alembic on start), base CI (lint + types + tests).
- **Users and authentication**: `User` entity, self-service `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /users/me`; PyJWT access token (15 min) + refresh token (7 days) with an enforced `type` claim; pwdlib[argon2] hashing; password policy of 8–128 characters with at least one letter and one digit.
- **Task lists (CRUD)**: owner-scoped `POST|GET /lists`, `GET|PATCH|DELETE /lists/{list_id}`. `name` is required, non-empty after trim, ≤120 characters, and unique per owner case-insensitively (duplicate → 409 Conflict). `description` is optional, ≤2000 characters. Deleting a list cascades its tasks (`ON DELETE CASCADE`).
- **Tasks (CRUD)**: `POST /lists/{list_id}/tasks`, `GET|PATCH|DELETE /lists/{list_id}/tasks/{task_id}`. `title` is required, non-empty after trim, ≤200 characters; `description` optional, ≤2000 characters; `priority` low/medium/high; optional `due_date` (calendar date, no time component), which must not be earlier than today (UTC, via an injected clock) on create or update (→ 422 business validation).
- **Status change**: `PATCH /lists/{list_id}/tasks/{task_id}/status` enforcing the domain state machine pending↔in_progress, in_progress→done, done→in_progress; pending→done is rejected with 409 (`InvalidStatusTransitionError`).
- **Filtered listing + completion**: `GET /lists/{list_id}/tasks?status=&priority=&limit=&offset=` returning `{items, total, completion_percentage}`; the percentage is computed over ALL tasks of the list regardless of filters (0.0 when empty, 2 decimals).
- **Assignment + fake invitation**: `PATCH /lists/{list_id}/tasks/{task_id}/assignee`; the assignee MUST be an existing registered user; assignment triggers a fake email invitation through a `NotificationService` port with a console/log adapter run via `BackgroundTasks`.
- **Assignee visibility (middle ground)**: an assignee who is not the list owner MAY list their assigned tasks via `GET /users/me/tasks` and MAY change the status of those tasks via the status endpoint. They MUST NOT edit or delete those tasks nor see the rest of the list. Any other non-owner receives 404 (never 403, no enumeration).
- **Error contract**: domain exception hierarchy mapped by FastAPI handlers to a consistent JSON body `{code, message}` with 401/404/409/422; no stack traces leak.
- **Testing**: unit tests (domain + use cases with in-memory fakes) and integration tests (API + repositories on Testcontainers Postgres); coverage gate ≥75% enforced in CI.
- **Documentation**: README (description, local setup, Docker, tests, security) and `DECISION_LOG.md` (the 13 plan decisions, the 8 post-explore product decisions, and pending items).
- **Security hardening (last slice, first to cut)**: rate limiting on `/auth`, security headers, strict CORS, error sanitizing, free-tier CI scanners (bandit, pip-audit, gitleaks, Trivy, CodeQL, Dependabot; Snyk and Fluid Attacks if the token/config is available), optional Sentry gated on `SENTRY_DSN` with `send_default_pii=False`.

### Out of Scope

- Shared lists / collaboration (multiple owners or members of a list). Only the assignee middle ground above is provided.
- Refresh-token rotation and token blacklist/revocation (documented as pending in `DECISION_LOG.md`).
- Real email delivery (SMTP or a provider); the invitation is logged only.
- Inviting non-registered users (no invitation-to-sign-up flow).
- Password reset, email verification, user profile editing, account deletion.
- Frontend, ruff (explicitly declined in favor of flake8 + isort), paid security tooling.
- Production deployment or hosting.

## Capabilities

`openspec/specs/` is empty (greenfield), so every capability is new.

### New Capabilities

- `project-bootstrap`: runnable skeleton, settings, health endpoint, tool configs, Docker/compose, CI quality and coverage gates.
- `user-auth`: registration with password policy, login, refresh, `GET /users/me`, JWT access/refresh with `type` claim enforcement, authenticated-user dependency.
- `task-lists`: owner-scoped CRUD of task lists, field validation, case-insensitive per-owner name uniqueness, cascade delete, 404 for non-owners.
- `tasks`: CRUD of tasks within an owned list, field validation including `due_date`, status state machine, filtered and paginated listing with `completion_percentage`.
- `task-assignment`: assigning an existing user to a task, fake email invitation via the notification port, assignee visibility through `GET /users/me/tasks`, assignee status changes, and the non-owner access rules.
- `api-error-contract`: domain exception hierarchy and the consistent `{code, message}` HTTP error mapping (401/404/409/422).
- `security-hardening`: rate limiting, security headers, CORS policy, error sanitizing, CI security scanning, optional Sentry.

### Modified Capabilities

None.

> Note: all endpoint paths in this proposal are relative to the `/api/v1` prefix; health probes (`/health`, `/health/ready`) live at the root.

## Approach

One SDD change (`todo-api`) delivered as multiple gitflow slices. The `single-pr` delivery strategy is interpreted as **one PR per slice**: each slice is one `feature/*` branch with one PR into `develop`, targeting the 400 changed-line review budget, with Conventional Commits and work-unit commits. After the last slice, `release/1.0.0` merges to `main` with tag `v1.0.0` and is back-merged into `develop`.

Architecture follows the plan: pure domain (entities, value objects, state machine, exceptions, repository Protocols) with no framework imports; application layer of one use-case class per action plus ports (UnitOfWork, PasswordHasher, TokenService, NotificationService); infrastructure implementing ports (SQLAlchemy 2.0 typed `Mapped[]` models + mappers, async sessions with eager loading, Alembic, PyJWT, pwdlib, console notifier, FastAPI routers/schemas/handlers). Library APIs are verified against current docs (Context7) before each slice.

Delivery slices (order matters; cut from the bottom if time runs out):

| # | Branch | Scope | Rough lines |
|---|---|---|---|
| 0 | `feature/bootstrap-project` | uv/pyproject, skeleton, settings, app factory + health, Dockerfile, compose, tool configs, CI skeleton, `.gitattributes`, README stub | 350–450 |
| 1a | `feature/auth-foundation` | `User` entity/model, Alembic + initial migration, domain exception base + HTTP error contract, repositories, UoW | 250–350 |
| 1b | `feature/auth-jwt` | PyJWT + pwdlib, password policy, register/login/refresh/me, auth dependency, tests | 350–450 |
| 2 | `feature/task-lists` | `TaskList` CRUD end to end, uniqueness, cascade, tests | 400–550 |
| 3 | `feature/tasks-status` | `Task` CRUD, `due_date` rule, state machine, tests | 450–600 |
| 4 | `feature/task-filters-completion` | status/priority filters, pagination, `completion_percentage` | 200–300 |
| 5 | `feature/notifications` | assignee endpoint, `NotificationService` port + console adapter via BackgroundTasks, `GET /users/me/tasks`, assignee status permission | 250–350 |
| 6 | `feature/security-hardening` | rate limit, headers, CORS, sanitizing, CI scanners, optional Sentry | 150–300 |

`DECISION_LOG.md` and README are updated within the slice that introduces each decision, so documentation never lags behind code; a final docs pass happens before the release branch.

## Affected Areas

All paths are new (greenfield).

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml`, `uv.lock` | New | PEP 621 project, dependencies, tool configuration |
| `src/app/domain/` | New | Entities (User, TaskList, Task), value objects (TaskStatus, Priority), exceptions, repository Protocols |
| `src/app/application/` | New | Use cases, DTOs, ports (UnitOfWork, PasswordHasher, TokenService, NotificationService) |
| `src/app/infrastructure/db/` | New | SQLAlchemy models, async session, repositories, mappers, `alembic/` migrations |
| `src/app/infrastructure/security/` | New | JWT service (PyJWT), Argon2 hasher (pwdlib) |
| `src/app/infrastructure/notifications/` | New | Console email notifier |
| `src/app/infrastructure/api/` | New | v1 routers, Pydantic schemas, DI dependencies, exception handlers, middleware |
| `src/app/infrastructure/config.py`, `src/app/main.py` | New | Settings and app factory |
| `tests/unit/`, `tests/integration/` | New | Fake-repo unit tests; Testcontainers integration tests |
| `pytest.ini`, `.flake8`, `.pre-commit-config.yaml`, `.gitattributes` | New | Quality and test gates |
| `Dockerfile`, `docker-compose.yml` | New | Multistage image; api + postgres stack |
| `.github/workflows/`, `.github/dependabot.yml` | New | CI quality, tests, coverage, security scanning |
| `README.md`, `DECISION_LOG.md` | New | Required documentation |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Deadline (2026-10-08) with ~2200–3200 authored lines | High | Core-first slice order; cut from the bottom and document cuts as pending in `DECISION_LOG.md` |
| Slices 2 and 3 forecast above the 400-line budget | Med | `sdd-tasks` must forecast per slice and split (e.g. domain/use cases vs API) if the forecast exceeds budget |
| Slice 6 bundles code hardening, CI scanners, and Sentry and may exceed budget | Med | Split into sub-slices during `sdd-tasks` or cut its tail (Sentry, Snyk, Fluid Attacks first) |
| Async SQLAlchemy lazy loading (`MissingGreenlet`) | Med | `selectinload`, map to domain entities inside the session |
| pytest-asyncio loop scope vs session-scoped Testcontainers fixture | Med | Verify current config via Context7 at apply; integration-test the fixture in slice 1a |
| Windows Docker / Testcontainers (Ryuk) locally | Med | Docker Desktop + WSL2; CI on Linux is the source of truth |
| Coverage gate flakiness from integration-only paths | Low | Unit tests with fakes carry most of the threshold |
| Assignee permission rules leak data or enable enumeration | Med | Single authorization policy in the application layer; explicit scenarios for owner, assignee, and stranger (404) |
| JWT token confusion (refresh used as access) | Low | Enforce `type` claim with dedicated tests |
| `due_date` "not in the past" depends on clock and timezone | Low | Resolved: `due_date` is a calendar date; compared against today in UTC through an injected clock port (deterministic tests) |

## Rollback Plan

- Each slice is an isolated PR into `develop`; a defective slice is reverted with `git revert` of its merge commit on `develop` without touching earlier slices. Later slices depending on it are reverted in reverse order.
- `main` only receives `release/1.0.0`; if the release is defective, `main` is reset to its previous tag by a revert commit and the release is not tagged.
- Database: every Alembic migration ships with a working `downgrade()`; `alembic downgrade -1` reverts a slice's schema. Locally, `docker compose down -v` discards the database entirely (no production data exists).
- Optional integrations (Snyk, Sentry, Fluid Attacks) are gated by secrets/env vars and can be disabled by removing them without code changes.

## Dependencies

- Docker Desktop (WSL2) locally and Docker on CI runners for Testcontainers.
- Public GitHub repository created by the user (CodeQL and secret scanning free tier).
- Optional: `SNYK_TOKEN` secret, `SENTRY_DSN`, Fluid Attacks config.
- Current library docs via Context7 (FastAPI, SQLAlchemy async, PyJWT, pwdlib, testcontainers, slowapi, sentry-sdk).

## Success Criteria

Traceable to the challenge PDF (mandatory unless marked bonus):

- [ ] CRUD of task lists works end to end with owner scoping, validation, uniqueness (409), and cascade delete.
- [ ] CRUD of tasks within a list works end to end with validation, including `due_date` (422 when in the past).
- [ ] Task status changes follow the state machine; pending→done returns 409.
- [ ] Task listing filters by status and priority, paginates, and returns `completion_percentage` over all tasks of the list.
- [ ] Layered Domain / Application / Infrastructure structure under `src/app/` with the dependency rule respected (domain imports nothing).
- [ ] Pydantic-typed schemas, custom domain exceptions mapped to `{code, message}` errors, business validations in domain/use cases.
- [ ] Real PostgreSQL database with Alembic migrations applied on container start.
- [ ] `uv run pytest` green with unit and integration tests; coverage ≥75% enforced by `pytest.ini` and CI.
- [ ] `flake8`, `black --check`, `isort --check`, and `mypy --strict` pass locally and in CI.
- [ ] `docker compose up --build` starts the stack; `/health` is OK and `/docs` loads; smoke flow register → login → list → tasks → status (valid + 409) → filter → completion → assign → invitation logged.
- [ ] README and `DECISION_LOG.md` present, including pending/deferred items.
- [ ] (Bonus) JWT authentication with access/refresh tokens and password policy.
- [ ] (Bonus) Task assignee restricted to existing users, with assignee visibility via `GET /users/me/tasks` and assignee status changes; other non-owners get 404.
- [ ] (Bonus) Fake email invitation logged via `NotificationService` on assignment.
- [ ] Every slice merged into `develop` through its own PR within (or justified against) the 400-line budget; `v1.0.0` tagged on `main`.

## Pending If Time Runs Out (cut from the bottom)

Cut in this order, each documented in `DECISION_LOG.md` as pending:

1. Sentry integration.
2. Snyk and Fluid Attacks scanning.
3. Remaining OSS CI scanners (Trivy, CodeQL, gitleaks, pip-audit, bandit, Dependabot).
4. Code hardening (rate limiting on `/auth`, security headers, strict CORS).
5. Assignee visibility (`GET /users/me/tasks`, assignee status permission) and fake invitation (slice 5).
6. Filters, pagination, and completion percentage (slice 4) — **mandatory; cutting this fails the PDF**, so it is the last resort.

Slices 0 through 4 constitute the mandatory core and are not candidates for cutting under normal circumstances.
