# Todo Lists API

A Todo Lists REST API built for Crehana's Backend Developer technical
challenge: authentication, owner-scoped task lists and tasks, filtering,
pagination, and task assignment with a fake email invitation — on FastAPI,
SQLAlchemy 2.0 (async), and PostgreSQL, with a layered Domain / Application /
Infrastructure architecture.

## Features

- **Task lists & tasks**: owner-scoped CRUD, a strict task status state
  machine, due-date validation, and filtered/paginated listing with a
  `completion_percentage` summary.
- **(Bonus) JWT authentication**: register/login/refresh/me with Argon2
  password hashing and access/refresh tokens.
- **(Bonus) Task assignment**: assign a task to any registered user; the
  assignee can see and progress their own assigned tasks without owning the
  list.
- **(Bonus) Fake email invitation**: assigning a task logs one notification
  (no real email is ever sent) after the assignment commits.
- **Security hardening**: response security headers, a strict CORS
  allow-list, and rate-limited auth endpoints.
- **CI security scanning**: bandit, pip-audit, gitleaks, Trivy, GitHub
  CodeQL, optional Snyk, and Dependabot.
- **Optional observability**: Sentry error tracking, gated on `SENTRY_DSN`.

**Tech stack**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async) + asyncpg,
Alembic, PostgreSQL 16, Pydantic v2 / pydantic-settings, PyJWT, `pwdlib`
(Argon2), `slowapi`, `uv` (package manager + `uv_build` backend), pytest +
Testcontainers, black / isort / flake8 / mypy --strict.

## Quick start (Docker)

```bash
docker compose up --build
```

Open `http://localhost:8000/docs` for interactive Swagger UI, or walk through
the API with curl:

```bash
BASE=http://localhost:8000/api/v1

# 1. Register an owner and an assignee
curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' \
  -d '{"email": "owner@example.com", "password": "Passw0rd1"}'
curl -s -X POST $BASE/auth/register -H 'Content-Type: application/json' \
  -d '{"email": "assignee@example.com", "password": "Passw0rd1"}'
# copy the assignee's "id" into ASSIGNEE_ID below

# 2. Log in as the owner
ACCESS_TOKEN=$(curl -s -X POST $BASE/auth/login -H 'Content-Type: application/json' \
  -d '{"email": "owner@example.com", "password": "Passw0rd1"}' | python -c \
  "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 3. Create a list
LIST_ID=$(curl -s -X POST $BASE/lists -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"name": "Groceries", "description": "Weekly shopping"}' | python -c \
  "import sys,json;print(json.load(sys.stdin)['id'])")

# 4. Create a task
TASK_ID=$(curl -s -X POST $BASE/lists/$LIST_ID/tasks -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"title": "Buy milk", "priority": "low", "due_date": "2026-12-31"}' | python -c \
  "import sys,json;print(json.load(sys.stdin)['id'])")

# 5. Change its status (pending -> in_progress)
curl -s -X PATCH $BASE/lists/$LIST_ID/tasks/$TASK_ID/status \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"status": "in_progress"}'

# 5b. Repeating the same transition is rejected -> 409
curl -s -w '\nHTTP %{http_code}\n' -X PATCH $BASE/lists/$LIST_ID/tasks/$TASK_ID/status \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"status": "in_progress"}'

# 6. Filtered list with completion_percentage
curl -s "$BASE/lists/$LIST_ID/tasks?status=in_progress&limit=20&offset=0" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 7. Assign the task to the registered assignee (triggers one invitation)
curl -s -X PATCH $BASE/lists/$LIST_ID/tasks/$TASK_ID/assignee \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d "{\"assignee_id\": \"$ASSIGNEE_ID\"}"

# 8. See the invitation (no real email is sent)
docker compose logs api | grep notifications
# -> INFO:app.notifications:Task invitation: owner@example.com invited
#    assignee@example.com to 'Buy milk' (list 'Groceries')
```

```bash
docker compose down -v   # stop and remove the containers/volume
```

## Local setup (without Docker)

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv downloads
it automatically if missing).

```bash
uv sync                          # install dependencies into .venv
docker compose up db             # start only PostgreSQL
cp .env.example .env             # fill in DATABASE_URL / JWT_SECRET_KEY, etc.
uv run alembic upgrade head      # apply migrations
uv run uvicorn app.main:app --reload
```

The app expects `DATABASE_URL` and `JWT_SECRET_KEY` (see `.env.example` for
every configurable variable, including the security/observability ones
documented below). Without a reachable database, `/health` still returns 200
(liveness only); `/health/ready` returns 503 until the database is reachable.

### Database and migrations

```bash
uv run alembic upgrade head        # apply all pending migrations
uv run alembic downgrade -1        # roll back the most recent migration
uv run alembic revision -m "..."   # create a new migration (then edit it)
```

`alembic.ini` lives at the repo root and points `script_location` at the
installed `app` package (`app.infrastructure.db:alembic`), so migrations run
the same way from an editable checkout and from the image built by
`Dockerfile`. The database URL always comes from `Settings.database_url`
(`DATABASE_URL`), never from `alembic.ini`.

## Running tests

```bash
uv run pytest                        # full suite (286 tests)
uv run pytest -m "not integration"   # unit tests only, no Docker required
```

Integration tests use [Testcontainers](https://testcontainers.com/) to spin
up a real PostgreSQL 16 container, so **Docker must be running locally** to
run the full suite. Coverage is enforced via `pytest.ini`
(`--cov-fail-under=75`); current coverage is **~94%**.

### Quality gates

```bash
uv run black --check .
uv run isort --check-only .
uv run flake8
uv run mypy --strict src
uv run pre-commit run --all-files   # runs all four via git hooks
```

All four lint/type checks, plus `uv run pytest`, run in CI
(`.github/workflows/ci.yml`) on every pull request and on pushes to
`develop`/`main`.

## Architecture

```
src/app/
  domain/          # Framework-free entities, value objects, exceptions
  application/     # Use cases, ports (Protocols), authorization
  infrastructure/  # FastAPI, SQLAlchemy, Alembic, JWT, Argon2 adapters
```

`domain` imports only the standard library; `application` imports `domain`
and the standard library; `infrastructure` wires everything together. This
dependency rule is mechanically enforced by
`tests/unit/test_architecture.py`, which walks every module's AST and fails
the build if `domain`/`application` ever import a framework
(FastAPI/SQLAlchemy/Pydantic/PyJWT/`pwdlib`) or `app.infrastructure`.

## API reference

All business routes are versioned under `/api/v1`; `/health` and
`/health/ready` stay unversioned at the root. A resource owned by another
user, or a resource that does not exist, both return **404 — never 403** —
so ownership can never be probed by comparing status codes.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/health` | none | Liveness only — always 200 while the process runs |
| GET | `/health/ready` | none | Readiness — runs `SELECT 1`; 503 if the DB is unreachable |
| POST | `/api/v1/auth/register` | none | Rate-limited; 201 / 409 (email taken) / 422 (password policy) |
| POST | `/api/v1/auth/login` | none | Rate-limited; identical 401 for a wrong password or an unknown email |
| POST | `/api/v1/auth/refresh` | refresh token | Rate-limited; rejects an access token used as a refresh token |
| GET | `/api/v1/users/me` | access token | The caller's own identity |
| GET | `/api/v1/users/me/tasks` | access token | Tasks assigned to the caller, across every list, paginated |
| POST | `/api/v1/lists` | access token | 409 on a case-insensitive name collision for the same owner |
| GET | `/api/v1/lists` | access token | The caller's own lists only |
| GET \| PATCH \| DELETE | `/api/v1/lists/{list_id}` | access token (owner) | 404 for a non-owner or nonexistent list |
| POST | `/api/v1/lists/{list_id}/tasks` | access token (owner) | `due_date`, if given, must not be before today (UTC) |
| GET | `/api/v1/lists/{list_id}/tasks` | access token (owner) | Filters below |
| GET \| PATCH \| DELETE | `/api/v1/lists/{list_id}/tasks/{task_id}` | access token (owner) | 404 for a non-owner or nonexistent task |
| PATCH | `/api/v1/lists/{list_id}/tasks/{task_id}/status` | access token (**owner or assignee**) | Strict state machine; same-status and any other invalid transition → 409 |
| PATCH | `/api/v1/lists/{list_id}/tasks/{task_id}/assignee` | access token (owner only) | `null` unassigns; an unknown `assignee_id` → 422 |

### Filtering, pagination, and completion

`GET /api/v1/lists/{list_id}/tasks` accepts optional `status` and `priority`
query filters, plus `limit` (1-100, default 20) and `offset` (≥ 0, default
0). The response is `{items, total, completion_percentage}`:

- `items`/`total` reflect the applied filters and pagination — `total` is
  the full matching count, not the page size.
- `completion_percentage` is `done / total` over **every** task in the
  list, rounded to 2 decimals, regardless of any filter on `items`. An empty
  list reports `0.0`.

### Field limits and validation

| Field | Rule |
|-------|------|
| `name` (list) | Non-blank after trimming, ≤ 120 chars; unique per owner, case-insensitive → 409 |
| `description` (list/task) | Optional, ≤ 2000 chars; a blank value normalizes to `null` |
| `title` (task) | Non-blank after trimming, ≤ 200 chars |
| `priority` | One of `low`, `medium`, `high`; defaults to `medium` if omitted |
| `due_date` | Optional calendar date, must not be earlier than today (UTC); re-validated only when a `PATCH` touches it |
| `password` | 8-128 characters, at least one letter and one digit |
| Status transitions | Only `pending↔in_progress`, `in_progress↔done`; every other request, including same-status, → 409 |

### Error contract

Every error response (including unhandled exceptions) has the same shape:

```json
{"code": "task_list_not_found", "message": "Task list not found"}
```

A 422 raised by request validation additionally includes `details` (one
entry per invalid field):

```json
{"code": "validation_error", "message": "Request validation failed",
 "details": [{"field": "body.name", "message": "...", "type": "..."}]}
```

| Status | Meaning | Example `code` |
|--------|---------|-----------------|
| 401 | Not authenticated / invalid credentials or token | `not_authenticated`, `invalid_credentials`, `invalid_token` |
| 404 | Not found, or not owned by the caller (never 403) | `task_list_not_found`, `task_not_found` |
| 409 | Conflict (uniqueness, invalid state transition) | `task_list_name_conflict`, `invalid_status_transition` |
| 422 | Business-rule or schema validation failure | `weak_password`, `due_date_in_past`, `assignee_not_found`, `validation_error` |
| 429 | Rate limit exceeded | `rate_limited` |
| 500 | Unhandled error — no internal detail is ever leaked | `internal_error` |

### Authorization model

Three roles exist per task, resolved identically to a 404 whenever the
caller does not qualify (never a 403, so ownership can never be probed):

- **Owner** (the list's creator): full CRUD and status/assignee control over
  every task in their lists.
- **Assignee** (set via the `assignee` endpoint): may only
  `PATCH .../status` on the one task assigned to them; every other verb on
  that task, and the rest of the list, returns 404.
- **Stranger** (neither): 404 on every verb, identical to a nonexistent
  resource.

## Security

Defense-in-depth layers on top of the core API:

- **Security response headers**: every response gets `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`.
  `Strict-Transport-Security` is added only when the request is HTTPS
  (directly, or via a trusted `X-Forwarded-Proto: https` header).
- **Strict CORS allow-list**: `CORS_ALLOWED_ORIGINS` (a JSON array, empty by
  default) feeds `CORSMiddleware`; an origin absent from the list never
  receives `Access-Control-Allow-Origin`.
- **Rate limiting on auth endpoints**: `register`/`login`/`refresh` are
  limited to `AUTH_RATE_LIMIT` (default `10/minute`) per client IP, off by
  default (`RATE_LIMIT_ENABLED=false`) so local development and tests are
  never throttled by accident; the compose stack turns it on. Exceeding the
  limit returns 429 with the same error contract plus `Retry-After`.
- **CI security scanning** (`.github/workflows/security.yml` +
  `codeql.yml` + `dependabot.yml`), all free-tier:
  - `bandit` (SAST on `src`, medium+ severity) — **blocking**.
  - `pip-audit` (dependency CVEs against the locked `uv.lock`) —
    non-blocking (surfaced in the run output; a CVE may need patch time).
  - `gitleaks` (secret scanning) — **blocking**.
  - Trivy (the repo's own built image, HIGH/CRITICAL with a known fix) —
    **blocking**.
  - GitHub CodeQL (Python, weekly + every push/PR) — free on public repos.
  - Snyk — optional, gated entirely on a `SNYK_TOKEN` secret; a no-op
    without one, non-blocking when it runs.
  - Dependabot: weekly updates for the `pip`, `github-actions`, and
    `docker` ecosystems, targeting `develop`.
  - **Fluid Attacks: pending** — no primary-source-verified free/open-source
    invocation could be confirmed in the apply session (no web-research
    tool available). A commented-out job stub marks where it would plug in;
    see `DECISION_LOG.md`.
- **Optional Sentry integration**: set `SENTRY_DSN` to enable error
  tracking; unset, `init_sentry()` is a complete no-op (no import side
  effect, no network call). When enabled, `send_default_pii=False` always —
  no personally identifiable information is ever sent. `SENTRY_TRACES_SAMPLE_RATE`
  (default `0.0`) and `ENVIRONMENT` (default `development`) are also
  configurable.

See `DECISION_LOG.md` for the full rationale behind these and every other
choice in this project.

## Git workflow

Gitflow with [Conventional Commits](https://www.conventionalcommits.org/):
the work was delivered as 12 slice-scoped feature branches off `develop`,
one pull request per slice, merged in order, then `release/1.0.0` → `main`
tagged `v1.0.0`, back-merged into `develop`. All pull requests:
<https://github.com/allanos94/crehana-todo-backend/pulls?q=is%3Apr>.

The full plan — proposal, specs (Given/When/Then scenarios), design (ADRs),
and the task-by-task implementation log — lives under
`openspec/changes/todo-api/`.

## Pending / future work

| Item | Status |
|------|--------|
| Refresh-token rotation and a revocation denylist | Deferred — out of scope for this challenge; every token already carries a `jti` claim so a future denylist has something to key on |
| Shared lists / collaboration beyond single-assignee | Out of scope |
| Real email delivery | Out of scope by design — console/log notifier only |
| Fluid Attacks CI integration | Pending — no verified free-tier invocation found; see `DECISION_LOG.md` |
| Cosmetic doubled CHECK-constraint name on `task_lists` (`ck_task_lists_ck_task_lists_name_not_blank`) | Harmless (the domain layer rejects a blank name before any `INSERT`); flagged, not fixed, since it belongs to an already-merged migration — see `DECISION_LOG.md` |

See `DECISION_LOG.md` for every decision and deferral recorded in full.
