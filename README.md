# Todo Lists API

Crehana backend challenge: a Todo Lists API with authentication, task
assignment, and a fake email invitation, built with FastAPI, SQLAlchemy 2.0
(async), PostgreSQL, and a layered Domain / Application / Infrastructure
architecture.

## Status

Bootstrap slice (`feature/bootstrap-project`). The runnable skeleton, health
endpoints, Docker/compose stack, and CI/quality gates exist; business
features land in later slices per `openspec/changes/todo-api/tasks.md`.

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

## Docker

```bash
docker compose up --build
curl http://localhost:8000/health
docker compose down -v
```

This starts the API alongside a PostgreSQL 16 container. Database migrations
run automatically on container start once Alembic lands (slice 1a).

## Tests

```bash
uv run pytest                        # full suite (integration tests need Docker)
uv run pytest -m "not integration"   # unit tests only, no Docker required
```

Coverage is enforced via `pytest.ini` (`--cov-fail-under`), currently `0`
during the bootstrap slice because there is no application code to
meaningfully cover yet; raised to `75` starting with slice 1a
(`feature/auth-foundation`).

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
