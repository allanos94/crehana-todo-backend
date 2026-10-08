# Todo Lists API

Crehana backend challenge: a Todo Lists API with authentication, task
assignment, and a fake email invitation, built with FastAPI, SQLAlchemy 2.0
(async), PostgreSQL, and a layered Domain / Application / Infrastructure
architecture.

## Status

Slice 1a (`feature/auth-foundation`). The runnable skeleton, health
endpoints, Docker/compose stack, and CI/quality gates exist (Phase 0). This
slice adds the domain exception hierarchy, the `User` entity, the stable
error contract, the async SQLAlchemy persistence foundation, and the first
Alembic migration (`0001_users`). Remaining business features land in later
slices per `openspec/changes/todo-api/tasks.md`.

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
