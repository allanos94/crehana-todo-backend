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

# Delete (cascades its tasks once Phase 5 ships)
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

Scaffolded here; hardened in slice 6a (`feature/security-hardening`) and
slice 6b (`feature/security-ci-scanners`):

- Security response headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Strict-Transport-Security`).
- Strict CORS allow-list.
- Rate limiting on authentication endpoints.
- CI security scanning (bandit, pip-audit, gitleaks, CodeQL, Dependabot).
- Optional Sentry integration gated on `SENTRY_DSN`.

See `DECISION_LOG.md` for the full rationale behind these and other choices.
