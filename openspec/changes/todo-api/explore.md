## Exploration: todo-api (Crehana Backend Challenge)

### Current State
Greenfield repo: only `.gitignore`, `openspec/config.yaml`, `openspec/specs/.gitkeep`, `openspec/changes/archive/.gitkeep`, `.atl/skill-registry.md` exist. Branches `main` and `develop` exist, no source code, no `pyproject.toml`. Stack is PLANNED only (Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, PostgreSQL 16, Pydantic v2, uv, pytest/pytest-asyncio/pytest-cov/testcontainers, black/isort/flake8/mypy --strict/pre-commit, Docker multistage + compose, GitHub Actions).

### Affected Areas (to be created — no existing code)
- `src/app/domain/` — entities, value objects, custom exceptions, state machine rules.
- `src/app/application/` — use cases (CRUD lists/tasks, status change, filtered listing + completion %, auth, notifications).
- `src/app/infrastructure/` — FastAPI routers, SQLAlchemy models/repositories, Alembic migrations, JWT/pwdlib adapters, fake notification adapter.
- `tests/unit/` — fake in-memory repos.
- `tests/integration/` — Testcontainers Postgres.
- `Dockerfile`, `docker-compose.yml`, `pytest.ini`, `.flake8`, `pyproject.toml`, `.pre-commit-config.yaml`, `README.md`, `DECISION_LOG.md`, `.github/workflows/`.

### 1. Requirements Traceability Matrix

| PDF Requirement | Satisfied By |
|---|---|
| Python | Python 3.12 runtime |
| FastAPI | `src/app/infrastructure/api` routers + app factory |
| Real DB | PostgreSQL 16 via SQLAlchemy 2.0 async + asyncpg |
| pytest | pytest + pytest-asyncio, `pytest.ini` |
| flake8 | `.flake8` config |
| black | formatter, enforced via pre-commit |
| isort | profile=black, pre-commit |
| ruff (mentioned, optional) | explicitly declined by user decision — flake8 only |
| mypy --strict (extra, not required) | pre-commit + CI gate |
| Docker | multistage `Dockerfile` |
| docker-compose | app + postgres services |
| README | description, local setup, docker run, test instructions |
| DECISION_LOG.md | technical decisions, incl. pending/deferred items per PDF's own allowance |
| Layered Domain/Application/Infrastructure | `src/app/{domain,application,infrastructure}` |
| Pydantic strong typing | API schemas (DTOs) + domain value objects |
| Custom exceptions | domain exception hierarchy mapped to HTTP via FastAPI exception handlers |
| Business validations | domain/use-case layer (state machine, ownership, field rules) |
| Unit + integration tests w/ pytest | unit = fake in-memory repos; integration = Testcontainers Postgres |
| Coverage ≥75% | pytest-cov gate, CI-enforced |
| CRUD task lists | `TaskList` entity + `/lists` endpoints |
| CRUD tasks within a list | `Task` entity + `/lists/{id}/tasks` endpoints |
| Change task status | `PATCH .../status` + state machine (pending↔in_progress, in_progress→done, done→in_progress; pending→done = 409) |
| List tasks filtered by status/priority + completion_percentage | `GET /lists/{id}/tasks?status=&priority=&limit=&offset=`, percentage computed over ALL tasks regardless of filters |
| JWT auth (bonus) | PyJWT + pwdlib[argon2], access 15m / refresh 7d with `type` claim |
| Assign responsible user (bonus) | `assignee_id` FK on `Task` |
| Fake email invitation (bonus) | `NotificationService` port + fake/log adapter via `BackgroundTasks` |

### 2. Domain Model Sketch

**Entities**
- `User`: id, email (unique), hashed_password, created_at.
- `TaskList`: id, owner_id (FK User), name, description?, created_at, updated_at.
- `Task`: id, list_id (FK TaskList), title, description?, status (pending/in_progress/done), priority (low/medium/high), assignee_id (FK User, nullable), created_at, updated_at.

**Decided invariants**
- Status state machine: pending↔in_progress; in_progress→done; done→in_progress; pending→done rejected with 409.
- `completion_percentage` = done tasks / ALL tasks in the list, unaffected by filters.
- Any resource belonging to another user → 404 (never 403).
- Priority: low/medium/high. Pagination: limit/offset.

### 3. Technical Risks / Pitfalls (Windows dev + Linux CI)

1. **Async SQLAlchemy lazy-loading** raises `MissingGreenlet`; eager-load (`selectinload`) and map to domain entities inside the session.
2. **pytest-asyncio loop scope vs session-scoped Testcontainers fixture** ("attached to a different loop"). Verify config via Context7 at apply.
3. **Windows Docker for Testcontainers**: Docker Desktop + WSL2; possible Ryuk workarounds locally. CI unaffected.
4. **CRLF**: add `.gitattributes` (`* text=auto eol=lf`).
5. **mypy --strict + SQLAlchemy 2.0**: native `Mapped[...]` typing, no legacy plugin.
6. **Alembic + async engine**: `env.py` needs `run_sync` bridge. Verify via Context7.
7. **uv on Windows**: never bake a Windows venv into the image; `uv sync` inside the Linux build stage.
8. **Coverage gate reliability**: unit tests with fakes should carry most of the threshold.
9. **JWT `type` claim enforcement**: reject refresh-as-access and vice versa.
10. **Exception → HTTP mapping**: one consistent error contract (404/409/422/401).
11. **Security tooling deferral**: lands after core; first to cut, documented as pending.

### 4. Change Slicing Recommendation

The full scope is ~2200–3200 authored lines, far above the 400-line review budget. Interpret `single-pr` as one PR per gitflow slice.

**ONE SDD change (`todo-api`)** with tasks grouped into phases, each phase = one `feature/*` branch = one PR into `develop`.

| Slice | Branch | Scope | Rough lines |
|---|---|---|---|
| 0 | `feature/bootstrap-project` | uv/pyproject, skeleton, settings, app factory + health, Docker, compose, tool configs, CI skeleton, `.gitattributes` | 350–450 |
| 1a | `feature/auth-foundation` | `User` model, Alembic + initial migration, domain exceptions base, repositories | 250–350 |
| 1b | `feature/auth-jwt` | PyJWT + pwdlib, register/login/refresh, auth dependency, tests | 350–450 |
| 2 | `feature/task-lists` | `TaskList` CRUD end to end + tests | 400–550 |
| 3 | `feature/tasks-status` | `Task` CRUD + state machine + assignee + tests | 450–600 |
| 4 | `feature/task-filters-completion` | filters, pagination, completion_percentage | 200–300 |
| 5 | `feature/notifications` | `NotificationService` port + fake adapter + BackgroundTasks | 150–250 |
| 6 | `feature/security-hardening` | scanners, Sentry — LAST, first to cut | 150–300 |

### 5. Open Product Questions (need user decision)

1. Length / non-empty constraints on `TaskList.name` and `Task.title`?
2. Is `TaskList.name` unique per owner?
3. Can an assignee who is not the list owner see the task?
4. Self-service registration endpoint or pre-seeded users?
5. Does the fake invitation target only registered users?
6. Deleting a `TaskList`: cascade its tasks or block?
7. `due_date` on tasks or out of scope?
8. Password policy beyond argon2 hashing?

### Recommendation
Single SDD change, multi-branch delivery. Proceed to `sdd-propose` once the open questions are answered or deferred with documented defaults.
