# Todo Lists API

Crehana backend challenge: a Todo Lists API with authentication, task
assignment, and a fake email invitation, built with FastAPI, SQLAlchemy 2.0
(async), PostgreSQL, and a layered Domain / Application / Infrastructure
architecture.

## Status

Slice 2b (`feature/task-lists-api`). Phases 0-2 (bootstrap, auth
foundation, auth JWT) are complete. Phase 3 added the owner-scoped
`TaskList` domain entity and use cases against fakes; this slice persists
`TaskList` with SQLAlchemy and exposes the `/api/v1/lists` CRUD endpoints.
Remaining business features (tasks, filters, assignment, hardening) land
in later slices per `openspec/changes/todo-api/tasks.md`.

## Authentication

```bash
# Register
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email": "user@example.com", "password": "Passw0rd1"}'

# Login (returns an access token and a refresh token)
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "user@example.com", "password": "Passw0rd1"}'

# Refresh (exchange a refresh token for a fresh pair)
curl -s -X POST http://localhost:8000/api/v1/auth/refresh \
  -H 'Content-Type: application/json' \
  -d '{"refresh_token": "<refresh_token>"}'

# Authenticated identity
curl -s http://localhost:8000/api/v1/users/me \
  -H 'Authorization: Bearer <access_token>'
```

Access tokens expire after 15 minutes, refresh tokens after 7 days. Every
request to `POST /auth/login` with a wrong password or an unknown email
returns the same 401 message, so a client cannot enumerate registered
accounts by probing login. See `DECISION_LOG.md` for the JWT/`HTTPBearer`
rationale and known gaps (no rotation/denylist yet).

## Task Lists

Every request below requires `Authorization: Bearer <access_token>`.

```bash
# Create a list
curl -s -X POST http://localhost:8000/api/v1/lists \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"name": "Groceries", "description": "Weekly shopping"}'

# List your own task lists
curl -s http://localhost:8000/api/v1/lists \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Get one task list
curl -s http://localhost:8000/api/v1/lists/<list_id> \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Rename / re-describe (partial update; omitted fields are untouched)
curl -s -X PATCH http://localhost:8000/api/v1/lists/<list_id> \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"name": "Shopping"}'

# Delete (cascades its tasks at the DB level)
curl -s -X DELETE http://localhost:8000/api/v1/lists/<list_id> \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`name` must be non-blank after trimming and at most 120 characters;
`description` is optional and at most 2000 characters, with a blank value
normalized to `null`. A list's `name` is unique per owner, compared
case-insensitively (`Groceries` and `groceries` conflict for the same
owner, but not across different owners) — a conflict returns 409
`task_list_name_conflict`. A list owned by another user, or a nonexistent
list, both return 404 — never 403 — so ownership can never be probed.

## Tasks

Every request below requires `Authorization: Bearer <access_token>`.
This section covers CRUD, status changes, and filtered/paginated listing;
assignment and the assignee's own view are documented separately below.

```bash
# Create a task (priority defaults to "medium" when omitted)
curl -s -X POST http://localhost:8000/api/v1/lists/<list_id>/tasks \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"title": "Buy milk", "priority": "low", "due_date": "2026-12-31"}'

# Get one task
curl -s http://localhost:8000/api/v1/lists/<list_id>/tasks/<task_id> \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# Update (partial; omitted fields are untouched)
curl -s -X PATCH http://localhost:8000/api/v1/lists/<list_id>/tasks/<task_id> \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"title": "Buy oat milk"}'

# Change status (strict state machine; same-status and pending<->done are 409)
curl -s -X PATCH http://localhost:8000/api/v1/lists/<list_id>/tasks/<task_id>/status \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"status": "in_progress"}'

# Delete
curl -s -X DELETE http://localhost:8000/api/v1/lists/<list_id>/tasks/<task_id> \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# List, filtered and paginated
curl -s "http://localhost:8000/api/v1/lists/<list_id>/tasks?status=pending&priority=high&limit=20&offset=0" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`title` must be non-blank after trimming and at most 200 characters;
`description` is optional and at most 2000 characters. `priority` is one of
`low`, `medium`, `high`. `due_date` is an optional calendar date that must
not be earlier than today (UTC); it is re-validated only when a `PATCH`
actually touches it. The status state machine only allows
`pending -> in_progress`, `in_progress -> pending`, `in_progress -> done`,
and `done -> in_progress`; every other transition, including a same-status
request, returns 409 `invalid_status_transition`. A task in another user's
list, or a nonexistent task, both return 404 — never 403.

### Filtering, pagination, and completion

`GET /api/v1/lists/{list_id}/tasks` accepts optional `status` and
`priority` query filters, plus `limit` (1-100, default 20) and `offset`
(≥ 0, default 0); an invalid enum value, or a `limit`/`offset` outside
those bounds, returns 422 `validation_error`. The response is
`{items, total, completion_percentage}`:

- `items` and `total` reflect the applied filters and pagination — `total`
  is the full matching count, not the page size.
- `completion_percentage` is `done / total` over **every** task in the
  list, rounded to 2 decimals, regardless of any `status`/`priority`
  filter applied to `items`. An empty list reports `0.0`.

## Assignment

Only the list owner may assign or unassign a task; the target must be an
existing registered user.

```bash
# Assign (owner-only; assignee_id must be a registered user's id)
curl -s -X PATCH http://localhost:8000/api/v1/lists/<list_id>/tasks/<task_id>/assignee \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"assignee_id": "<user_id>"}'

# Unassign (null; no invitation is sent)
curl -s -X PATCH http://localhost:8000/api/v1/lists/<list_id>/tasks/<task_id>/assignee \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{"assignee_id": null}'

# The assignee's own cross-list view
curl -s http://localhost:8000/api/v1/users/me/tasks \
  -H "Authorization: Bearer $ASSIGNEE_ACCESS_TOKEN"
```

An unknown `assignee_id` returns 422 `assignee_not_found`; a non-owner
caller returns 404. Assigning to a new, non-null user triggers one fake
email invitation (logged on `app.notifications`, e.g.
`INFO:app.notifications:Task invitation: owner@example.com invited
assignee@example.com to 'Buy milk' (list 'Groceries')`) after the
assignment commits — no real email is ever sent, and unassigning or
reassigning the same user again never triggers one.

A non-owner assignee may `PATCH .../status` on their own assigned task
(the same strict state machine as the owner), but gets 404 on every other
verb for that task (`GET`, `PATCH` on the task itself, `DELETE`,
`PATCH .../assignee`) and on the containing list's own endpoints — they
see only the one task they were assigned, never the rest of the list. A
stranger (neither owner nor assignee) gets 404 everywhere, identically to
a nonexistent resource.

## Architecture

```
src/app/
  domain/          # Framework-free entities, value objects, exceptions
  application/      # Use cases, ports (Protocols), authorization
  infrastructure/   # FastAPI, SQLAlchemy, Alembic, JWT, Argon2 adapters
```

`domain` imports only the standard library; `application` imports `domain`
and the standard library; `infrastructure` wires everything together. This
rule is mechanically enforced by `tests/unit/test_architecture.py`.

## Local Setup

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv downloads
it automatically if missing).

```bash
uv sync
uv run uvicorn app.main:app --reload
```

The app expects `DATABASE_URL` and `JWT_SECRET_KEY` (see `.env.example`).
Without a reachable database, `/health` still returns 200 (liveness only);
`/health/ready` returns 503 until the database is reachable.

## Database and Migrations

Schema changes are managed with Alembic. `alembic.ini` lives at the repo
root and points `script_location` at the installed `app` package
(`app.infrastructure.db:alembic`), so migrations run the same way from an
editable checkout and from the non-editable image built by `Dockerfile`.

```bash
uv run alembic upgrade head        # apply all pending migrations
uv run alembic downgrade -1        # roll back the most recent migration
uv run alembic revision -m "..."   # create a new migration (then edit it)
```

The database URL always comes from `Settings.database_url`
(`DATABASE_URL`), never from `alembic.ini`.

## Docker

```bash
docker compose up --build
curl http://localhost:8000/health
docker compose down -v
```

This starts the API alongside a PostgreSQL 16 container.
`docker/entrypoint.sh` runs `alembic upgrade head` before starting
`uvicorn`, so the schema is always current when the API container becomes
ready.

## Tests

```bash
uv run pytest                        # full suite (integration tests need Docker)
uv run pytest -m "not integration"   # unit tests only, no Docker required
```

Coverage is enforced via `pytest.ini` (`--cov-fail-under=75`), raised from
`0` now that there is real application code to meaningfully cover.
Integration tests use [Testcontainers](https://testcontainers.com/) to spin
up a real PostgreSQL 16 container; Docker must be running locally.

## Quality Gates

```bash
uv run black --check .
uv run isort --check-only .
uv run flake8
uv run mypy --strict src
```

All four run in CI (`.github/workflows/ci.yml`) on every pull request and on
pushes to `develop`/`main`.

## Security

Defense-in-depth layers on top of the core API, added across slices 6a-6c:

- **Security response headers** (`src/app/infrastructure/api/middleware.py`):
  every response gets `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, and `Referrer-Policy: no-referrer`. `Strict-Transport-Security` is
  added only when the request is HTTPS (directly, or via a trusted
  `X-Forwarded-Proto: https` header from a reverse proxy). `X-Frame-Options`
  is used instead of a `Content-Security-Policy` frame directive so Swagger
  UI at `/docs` keeps working without a CSP exemption list.
- **Strict CORS allow-list**: `Settings.cors_allowed_origins` (env var
  `CORS_ALLOWED_ORIGINS`, a JSON array, empty by default) feeds
  `CORSMiddleware`. An origin absent from the list never receives
  `Access-Control-Allow-Origin`, so credentialed cross-origin requests from
  unlisted origins are rejected by the browser.
- **Rate limiting on auth endpoints** (`slowapi`): `POST /auth/register`,
  `/auth/login`, and `/auth/refresh` are limited to `Settings.auth_rate_limit`
  (env var `AUTH_RATE_LIMIT`, default `10/minute`) per client IP. Limiting is
  off by default (`RATE_LIMIT_ENABLED=false`) so local development and the
  test suite are never throttled by accident; the compose stack turns it on
  (`RATE_LIMIT_ENABLED=true`). Exceeding the limit returns 429 with the same
  error contract as every other error (`{"code": "rate_limited", "message":
  ...}`) plus a `Retry-After` header.

  ```bash
  for i in $(seq 1 12); do
    curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/v1/auth/login \
      -H "Content-Type: application/json" \
      -d '{"email":"nobody@example.com","password":"Passw0rd1"}'
  done
  # first 10 -> 401 (bad credentials), remaining -> 429 (rate_limited)
  ```
- **CI security scanning** (slice 6b, `feature/security-ci-scanners`):
  `bandit`, `pip-audit`, `gitleaks`, GitHub CodeQL, and Dependabot.
- **Optional Sentry integration** (slice 6c, `feature/sentry-integration`):
  gated entirely on `SENTRY_DSN`; initialized with `send_default_pii=False`.

See `DECISION_LOG.md` for the full rationale behind these and other choices.
