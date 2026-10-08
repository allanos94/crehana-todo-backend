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
| 4 | The full `AppError` hierarchy (design ADR-03) is written once, in slice 1a, including concrete errors only used by later slices | Keeps `domain/exceptions.py` a stable file that never reopens per feature slice | tasks.md 1.4 |
| 5 | `AuthenticationError` lives in `application/exceptions.py`, not `domain/exceptions.py`, even though it subclasses `AppError` | Authentication is an application/infrastructure boundary concern, not a domain concept | design.md ADR-03 |
| 6 | VARCHAR(320)+`UniqueConstraint` for `users.email`, not a bare `unique=True` column flag | Deterministic, explicit constraint name (`uq_users_email`) that `SqlAlchemyUnitOfWork`'s `IntegrityError` translation depends on | design.md ADR-07/ADR-08 |
| 7 | Alembic `env.py` supports both an injected `config.attributes["connection"]` (used by tests, via `engine.begin()` + `run_sync`) and the async-engine path (used by the CLI) | Lets `command.upgrade`/`downgrade` run synchronously inside an already-open async connection without nesting `asyncio.run` inside a running loop | design.md ADR-09, Context7 verification items |

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

## Auth Foundation Slice (Phase 1 / Slice 1a) Notes

- Context7 MCP tools were not present in this session's tool list either (as
  in Phase 0). `script_location = app.infrastructure.db:alembic`
  (package-resource syntax) was verified empirically: `uv run alembic -c
  alembic.ini heads` resolves `0001_users` without a DB connection, and the
  full `docker compose up --build --wait` run proved it also works from the
  non-editable installed package inside the image (both containers reached
  `healthy`, and `psql \dt` showed `users` + `alembic_version` afterward).
- `sa.Enum(native_enum=False, create_constraint=True, values_callable=...)`
  is **not yet exercised**: migration `0001_users` has no enum columns
  (`TaskStatus`/`Priority` land in slice 3a/3b). Verification of that exact
  signature is deferred to Phase 5, where it is first needed.
- `IntegrityError` → domain-error translation reads
  `exc.orig.__cause__.constraint_name`, confirmed empirically by
  `tests/integration/test_user_repository.py::test_duplicate_email_raises_conflict`
  against the real asyncpg driver.
- `docker/entrypoint.sh` now unconditionally runs `alembic upgrade head`
  (no longer gated on `alembic.ini` existing — it always exists from this
  slice on). The Dockerfile's bracket-glob `COPY alembic.in[i]` was
  simplified to a plain `COPY alembic.ini` for the same reason.
- `tests/__init__.py` and `tests/unit/__init__.py` were added so
  `tests/unit/fakes.py` can be imported as `from tests.unit.fakes import
  ...` from multiple test modules (pytest's default "prepend" import mode
  needs real packages for dotted cross-module imports); `tests/integration`
  already had its own `__init__.py`.

## Auth JWT Slice (Phase 2 / Slice 1b) Notes

- Context7 check (task 2.2), verified by the orchestrator against installed
  versions `pwdlib==0.3.1`, `pyjwt==2.15.1`, `fastapi==0.142.4`:
  - `pwdlib`: `PasswordHash((Argon2Hasher(),))` with `.hash(pw) -> str` and
    `.verify(pw, hash) -> bool`. Both are CPU-bound/sync, wrapped in
    `asyncio.to_thread` in `Argon2PasswordHasher`.
  - PyJWT: `jwt.encode(payload, key, algorithm="HS256")`;
    `jwt.decode(token, key, algorithms=["HS256"], options={"require": [...]})`.
    `sub` must be a string (`str(user_id)`); `exp`/`iat` accept aware UTC
    `datetime` instances directly (PyJWT converts to Unix timestamps,
    truncating microseconds). Errors: catch the base `jwt.InvalidTokenError`
    (covers `ExpiredSignatureError`, `MissingRequiredClaimError`, signature
    and format failures) and map it to the app's `InvalidTokenError`.
  - FastAPI: `HTTPBearer()` with default `auto_error=True` now returns 401 (not
    403) with a `WWW-Authenticate: Bearer` header. The design still uses
    `HTTPBearer(auto_error=False)` so the dependency can distinguish "no
    header" (`NotAuthenticatedError`) from "bad header"
    (`InvalidTokenError`), both mapped to 401 by the existing error contract.
  - Confirmed empirically: PyJWT validates `iat` against the real wall clock
    regardless of any injected `Clock` used to build the payload — an `iat`
    in the future raises `ImmatureSignatureError`. `JwtTokenService` still
    takes all times from the injected `Clock` per design (never
    `datetime.now()` directly), but `tests/unit/test_jwt.py`'s "valid token"
    cases issue at the real current time, and only the expired-token case
    uses a `Clock` fixed to a date in the past, so `exp` is in the past too.
- All business routers mount under `/api/v1` (already a confirmed decision,
  design ADR-01); `auth`/`users` routers follow the same prefix.
- `HTTPBearer(auto_error=False)` was used over `OAuth2PasswordBearer` (design
  ADR-11 alternative): `OAuth2PasswordBearer` forces a form-encoded login
  with a `username` field, while `HTTPBearer` still gives `/docs` an
  "Authorize" box where a pasted token works, and `auto_error=False` lets
  `get_current_user_id` distinguish "no header" (`NotAuthenticatedError`)
  from "bad header" (`InvalidTokenError`).
- RS256 was rejected (design ADR-11 alternative): there is a single service
  and no key-distribution need, so HS256 with a shared secret is simpler.
- Refresh-token rotation and a revocation denylist are explicitly **not**
  implemented in this slice (tracked in the Pending/Deferred table below).
  `jti` is already included in every token's claims so a future denylist
  has something to key on without another migration.
- `WWW-Authenticate: Bearer` is added to every `AuthenticationError`
  response (401) via `infrastructure/api/errors.py`, beyond the "nice to
  have" note in the task — the change was a one-line conditional in the
  existing handler, so there was no reason to skip it.
