# Decision Log — Todo Lists API

Records what was decided and why: the stack/architecture decisions from the
plan (`openspec/changes/todo-api/design.md`), the product decisions
confirmed with the user after the explore phase, what changed or was
discovered slice by slice, and what is deliberately deferred. Pending items
are tracked explicitly rather than silently dropped.

## A. Stack & Architecture Decisions

The 13 architecture/stack decisions from `design.md`'s ADR-01–ADR-13 (the
two remaining design ADRs — testing architecture and packaging/Docker/CI —
are implementation detail already covered by this README's "Running tests"
and "Local setup"/"Docker" sections and by the per-slice notes in Section C
below, so they are not duplicated here as top-level architecture decisions).

| # | Decision | Rationale | Alternatives considered | Source |
|---|----------|-----------|--------------------------|--------|
| 1 | Three layers (`domain` / `application` / `infrastructure`) under `src/app/`, with the dependency rule mechanically enforced by an AST test; all business routes under `/api/v1`, health probes unversioned | Layers stay visible to the evaluator, the rule can't silently rot, and per-feature application subpackages keep slices reviewable | Package-by-feature at the top level (challenge asks for visible layers); `import-linter` (extra dependency when a 30-line AST test suffices); repository Protocols living in `application` instead of `domain` | design.md ADR-01 |
| 2 | Domain entities are mutable, slotted dataclasses mutated only through intention-revealing methods; value objects are immutable `StrEnum`s and pure validator functions; the task status state machine is strict (4 valid edges only, same-status → 409, no implicit no-op) | Entities have identity and a lifecycle, so mutating methods keep invariants in one place; value objects have no identity, so immutability is free | Frozen dataclasses + `dataclasses.replace` (rebuild-and-reassign noise); Pydantic domain models (breaks the framework-free domain rule) | design.md ADR-02 |
| 3 | `AppError` base + four category classes (`NotFoundError`, `ConflictError`, `BusinessRuleViolationError`, `AuthenticationError`), resolved to an HTTP status via `type(exc).__mro__` — no domain class knows about HTTP | One table owns the contract, the domain stays HTTP-agnostic, and a new concrete error needs zero handler changes | Raising `HTTPException` from use cases (leaks the framework into the application layer); a status code on each domain exception (puts an HTTP concept in the domain) | design.md ADR-03 |
| 4 | One class per use case (`execute(command) -> result`); commands/results are frozen, slotted dataclasses; a typed `UNSET` sentinel distinguishes "untouched" from "clear" on PATCH | The smallest typed surface that keeps the application layer framework-free and testable with fakes | `__call__` instead of `execute` (less explicit, less mypy-friendly); Pydantic DTOs in the application layer (breaks framework independence); a dedicated output view model per use case (no payoff at this size) | design.md ADR-04 |
| 5 | Ports (`Clock`, `PasswordHasher`, `TokenService`, `NotificationService`, `UnitOfWork`, plus repositories) are `typing.Protocol`s, not ABCs; `PasswordHasher` is `async` | Protocols give structural typing, so fakes need no inheritance; Argon2 is deliberately CPU-heavy, so hashing is offloaded with `asyncio.to_thread` instead of blocking the event loop | ABCs (force inheritance on every fake); a synchronous hasher (blocks the loop under concurrent logins) | design.md ADR-05 |
| 6 | Authorization is one application-layer policy, `AccessPolicy` (`owned_list`, `owned_task`, `status_changeable_task`), not scattered per-router or per-repository checks | One testable place for the owner/assignee/stranger matrix — the proposal's main data-leak risk | Router-level dependencies (duplicate rules, can't unit-test with fakes); owner-scoped SQL baked into every repository method (spreads the policy across adapters; can't express the assignee rule uniformly) | design.md ADR-06 |
| 7 | One `AsyncSession` per use-case execution via an async Unit of Work (`async with self._uow:` commits or rolls back); `expire_on_commit=False`; no ORM `relationship()`s — cascades are database-level; `IntegrityError` is translated to domain errors by constraint name | Keeps lazy-loading structurally impossible (domain objects are never ORM instances) and makes "notify only after commit" unambiguous | A session dependency that commits in its own teardown (hides commit errors, makes post-commit notification ambiguous); exposing ORM models as entities (couples the domain to SQLAlchemy) | design.md ADR-07 |
| 8 | `VARCHAR` + `CHECK` for `status`/`priority` instead of native PostgreSQL `ENUM`; a deterministic `MetaData` naming convention; database-level cascades (`ON DELETE CASCADE` / `SET NULL`); a functional unique index for case-insensitive per-owner list names; no DB `CHECK` for `due_date >= today` (PostgreSQL `CHECK` constraints must be immutable, so that rule lives in the domain) | Keeps the same DB-level guarantee as a native enum with plain, autogenerate-friendly migrations | Native PostgreSQL `ENUM` (`ALTER TYPE` needed for value changes, Alembic autogenerate doesn't detect them, and create/drop ordering is a known downgrade pitfall) | design.md ADR-08 |
| 9 | `alembic.ini` at the repo root with a package-resource `script_location` (works from both an editable checkout and the non-editable installed image); one migration per schema slice, each with a working `downgrade()`; `docker/entrypoint.sh` runs `alembic upgrade head` before `uvicorn` starts | A real migration history with working rollbacks, which the challenge evaluates, without an extra moving part | `Base.metadata.create_all()` at startup (no history, no downgrade); a separate compose `migrate` service (one more moving part for a single-node demo) | design.md ADR-09 |
| 10 | `TaskRepository.search` runs two SQL statements: one `FILTER`-aggregate query for whole-list counts (backing `completion_percentage`, filter-independent) and one separate paged `SELECT` for `items`; the percentage itself is computed in the domain from the raw integers | Keeps the percentage rounding unit-testable without a database, and the SQL layer only ever returns integers | Computing the percentage over loaded rows in Python (loads the entire list); `count(*) OVER ()` (the total disappears once `offset` passes the end); three separate count queries (the `FILTER` clauses collapse them into one) | design.md ADR-10 |
| 11 | PyJWT HS256 (`sub`/`type`/`iat`/`exp`/`jti` claims); `HTTPBearer(auto_error=False)` so the auth dependency can distinguish "no header" from "bad header"; `pwdlib` Argon2 hashing with a module-level dummy hash so login timing never reveals whether an email is registered | Simplest correct option for a single service with no key-distribution need, and the dummy-hash trick closes a real timing side-channel for free | `OAuth2PasswordBearer` (forces a form-encoded `username` field; `HTTPBearer` keeps Swagger's "Authorize" box working with a pasted token); RS256 (no key distribution need for one service); `python-jose`/`passlib` (unmaintained) | design.md ADR-11 |
| 12 | `AssignTask` notifies only *after* a successful commit, and only when the new assignee is non-null and different from the previous one; notification delivery runs through `BackgroundTasks` so it never blocks the response | The ordering is a unit-tested application rule, the use case never imports FastAPI, and delivery is non-blocking | The router scheduling `BackgroundTasks` itself from a returned DTO (moves the "after commit" rule out of the tested use case); a transactional outbox (overkill for a fake email) | design.md ADR-12 |
| 13 | `register_exception_handlers(app)` plus one `ErrorResponse` schema (`{code, message, details?}`); `RequestValidationError` details drop Pydantic's `input`/`ctx` keys so a submitted password is never echoed back; every router declares `responses={...}` so `/docs` documents the contract | Keeps the error shape uniform across every failure path, including ones FastAPI itself raises, without ever leaking submitted values | (Folded into ADR-03's category-map design — see row 3; no separate alternative was evaluated beyond that mapping) | design.md ADR-13 |

## B. Post-Explore Product Decisions

Confirmed with the user during the explore/planning session (`explore.md`'s
8 open product questions, expanded as later slices raised new ones);
recorded here as they land in code, not as a batch at the end.

| # | Decision | Rationale / notes | Source |
|---|----------|---------------------|--------|
| 1 | Field limits: list `name` ≤ 120 chars, `description` ≤ 2000 chars (lists and tasks); task `title` ≤ 200 chars | Non-blank-after-trim, length-capped `InvalidFieldError` (422) on violation | explore.md Q1, proposal.md scope, `value_objects.py` |
| 2 | A task list's `name` is unique per owner, compared case-insensitively → 409 `task_list_name_conflict` | Checked in the application layer for a friendly error, backed by a functional unique index for race safety under concurrency | explore.md Q2, proposal.md scope, design.md ADR-08 |
| 3 | Assignee middle-ground permissions: a non-owner assignee may `GET /users/me/tasks` and `PATCH .../status` on their own assigned task only; every other verb, and the rest of the list, returns 404 | Avoids full shared-list semantics while still letting the assignee act on their one task; never 403, so ownership can't be probed | explore.md Q3, proposal.md "Assignee visibility (middle ground)", design.md ADR-06 |
| 4 | Self-service registration (`POST /auth/register`) — no pre-seeded users or admin-invite flow | Simplest onboarding that still satisfies the JWT-auth bonus | explore.md Q4, proposal.md "Users and authentication" |
| 5 | The fake invitation only ever targets an existing registered user; there is no invite-to-sign-up flow | An unknown `assignee_id` is rejected (422 `assignee_not_found`) before any notification is built | explore.md Q5, proposal.md Out of Scope, design.md ADR-12 |
| 6 | Deleting a task list cascades its tasks at the database level (`ON DELETE CASCADE`); deleting a user sets `tasks.assignee_id` to `NULL` (`ON DELETE SET NULL`) rather than blocking or cascading | Keeps deletion simple and avoids orphaned rows without silently deleting a task because its assignee's account was removed | explore.md Q6, proposal.md scope, design.md ADR-08 |
| 7 | `due_date` is an optional calendar date (no time component) that must not be earlier than **today in UTC**, read from an injected `Clock`, never the system wall clock directly | Keeps the rule deterministic and testable; re-validated only when a `PATCH` actually touches the field | explore.md Q7, proposal.md scope, design.md ADR-02, `ensure_due_date_not_past` |
| 8 | Password policy: 8–128 characters, at least one letter and one digit | A minimal policy beyond "hash with Argon2" that still blocks trivially weak passwords | explore.md Q8, proposal.md scope, design.md ADR-02/ADR-11 |
| 9 | A same-status transition (e.g. `pending → pending`) is a 409 `invalid_status_transition`, identical to any other invalid edge — there is **no implicit no-op success path** | An idempotent alternative (returning 200 with no state change for a same-status request) was explicitly considered and **rejected**: the state machine is strict by design, and a same-status PATCH is treated as a client error like every other invalid edge, not as a harmless no-op | tasks.md Phase 5 notes, design.md ADR-02 |
| 10 | An unknown `assignee_id` returns 422 `assignee_not_found`, not 404 | The bad value lives in the request *body*, not the URL path — 404 is reserved for path resources (list/task), 422 for a business-rule violation on a field | design.md ADR-03 |
| 11 | All business routes are versioned under `/api/v1` from day one; `/health` and `/health/ready` stay unversioned at the root | Versioning from day one avoids a breaking migration later; probes are infrastructure concerns, not API surface | design.md ADR-01 |
| 12 | `status`/`priority` are stored as `VARCHAR` + `CHECK`, not native PostgreSQL `ENUM` | Confirmed with the user as a product-facing tradeoff (schema evolvability over native-enum strictness), not just an internal implementation choice — see Section A, row 8, for the full rationale | design.md ADR-08 |
| 13 | `priority` defaults to `medium` when omitted on task creation | No default is specified anywhere in the challenge PDF, the spec, or the design doc for this field; every documented spec scenario supplies `priority` explicitly, so this default never contradicts a documented scenario. Filled as a product gap during Phase 6 (Tasks API), not a design deviation | tasks.md Phase 6 notes, `CreateTaskRequest` schema |

## C. Implementation Notes by Slice

Per-slice discoveries, deviations, and clarifications, in delivery order.
Decisions already captured in Sections A/B are not repeated here.

### Phase 0: Bootstrap (Slice 0, `feature/bootstrap-project`, PR 1)

- `uv_build` backend configured with `module-name = "app"`, `module-root =
  "src"` (the package name `app` differs from the distribution name
  `todo-api`).
- `pytest.ini` started at `--cov-fail-under=0` (no application code yet);
  raised to `75` starting Phase 1.
- A minimal async engine/session factory was added ahead of Phase 1's full
  persistence layer, strictly to back `/health/ready`'s `SELECT 1` check.
- `/health/ready` (readiness, runs `SELECT 1`) was added as a spec delta —
  a user-confirmed decision not present in the original spec (tasks.md 0.6,
  `specs/project-bootstrap/spec.md`).
- `docker/entrypoint.sh` conditionally ran `alembic upgrade head` only when
  `alembic.ini` existed at that point, so it was a true no-op until Phase 1
  added migrations.

### Phase 1: Auth Foundation (Slice 1a, `feature/auth-foundation`, PR 2)

- The full `AppError` hierarchy (ADR-03) was written once here, including
  concrete errors only used by later slices, so `domain/exceptions.py`
  never reopens per feature slice.
- `script_location = app.infrastructure.db:alembic` (package-resource
  syntax) was verified empirically (no Context7 access this session):
  `uv run alembic -c alembic.ini heads` resolves `0001_users` without a DB
  connection, and a full `docker compose up --build --wait` run proved it
  also works from the non-editable installed package inside the image.
- `IntegrityError` → domain-error translation reads
  `exc.orig.__cause__.constraint_name`, confirmed empirically against the
  real asyncpg driver.
- `docker/entrypoint.sh` now unconditionally runs `alembic upgrade head`
  (`alembic.ini` always exists from this slice on).
- `AuthenticationError` lives in `application/exceptions.py`, not
  `domain/exceptions.py`, even though it subclasses `AppError`:
  authentication is an application/infrastructure boundary concern, not a
  domain concept (design.md ADR-03).

### Phase 2: Auth JWT (Slice 1b, `feature/auth-jwt`, PR 3)

- Confirmed empirically: PyJWT validates `iat` against the real wall clock
  regardless of any injected `Clock` used to build the payload — an `iat`
  in the future raises `ImmatureSignatureError`. `JwtTokenService` still
  takes all times from the injected `Clock` (never `datetime.now()`
  directly); only the expired-token test case uses a `Clock` fixed in the
  past.
- Refresh-token rotation and a revocation denylist are explicitly **not**
  implemented in this slice (tracked in Section D). Every token already
  carries a `jti` claim so a future denylist has something to key on
  without another migration.
- `WWW-Authenticate: Bearer` is added to every `AuthenticationError`
  response (401) via `infrastructure/api/errors.py`.

### Phase 3: Task Lists Core (Slice 2a, `feature/task-lists-core`, PR 4)

- Per-owner, case-insensitive `TaskList` name uniqueness is enforced in the
  application layer (`_ensure_name_available`, shared by `CreateTaskList`
  and `UpdateTaskList`), not in the router — Phase 4's functional unique
  index backs it for race safety under concurrency.
- Renaming excludes the list's own id from the uniqueness check, so
  renaming `Work` to `work` succeeds.
- No DB/API surface exists yet for task lists at this point (fakes-only,
  per the 2a/2b split).

### Phase 4: Task Lists API (Slice 2b, `feature/task-lists-api`, PR 5)

- The functional unique index was **not** autogenerate-verified against
  SQLAlchemy/Alembic docs (no Context7 access this session either), so
  `versions/0002_task_lists.py` was written by hand:
  `op.create_index("uq_task_lists_owner_id_lower_name", "task_lists",
  ["owner_id", sa.text("lower(name)")], unique=True)`. **Verified
  empirically** against real Postgres 16: inserting `"Groceries"` then
  `"GROCERIES"` for the same owner through two separate
  `SqlAlchemyUnitOfWork` transactions confirms the second `commit()` raises
  `IntegrityError` translated to `DuplicateTaskListNameError`.
- Per-owner case-insensitive uniqueness is checked twice, by design: the
  application layer gives a friendly 409 on the common case, and the DB's
  functional unique index is the race-safety backstop under concurrency.
- `UpdateTaskListCommand.name` is typed `str | None | Unset` (not
  `str | Unset`): an explicit JSON `null` is a distinct, invalid state
  (`name` is required and cannot be cleared), rejected with
  `InvalidFieldError` (422) instead of crashing on `None.strip()`.

### Phase 5: Tasks Core (Slice 3a, `feature/tasks-core`, PR 6)

- `due_date` validation lives in the domain (`ensure_due_date_not_past`,
  called from both `Task.create` and `Task.reschedule`), compared against
  `Clock.today()`, never the system wall clock directly.
- `UpdateTask` only re-validates `due_date` when the PATCH actually touches
  it: an unrelated field update on a task whose stored `due_date` has since
  passed in real time does not fail.
- `AccessPolicy.owned_task` checks list ownership first
  (`TaskListNotFoundError`) and only then task membership
  (`TaskNotFoundError`); both map to 404, so the distinction is invisible
  over HTTP.
- `ChangeTaskStatus` in this slice is the **owner-only** path; the assignee
  path (`status_changeable_task`) is Phase 8, since `assignee_id` cannot be
  set before Phase 8's `AssignTask` use case exists.

### Phase 6: Tasks API (Slice 3b, `feature/tasks-api`, PR 7)

- `assignee_id` ships now (migration `0003_tasks`) even though assignment
  use cases land in Phase 8, per design ADR-08, so Phase 8 needs no further
  schema change.
- **CHECK-constraint naming gotcha** (confirmed empirically against real
  Postgres 16): under `MetaData`'s `naming_convention`, an explicitly-named
  `CheckConstraint` still has the `"ck"` convention template applied to it,
  substituting the *given* name as the `%(constraint_name)s` token — unlike
  `UniqueConstraint`/`ForeignKeyConstraint`/`Index`, where an explicit name
  bypasses the convention entirely. Passing an already-prefixed name (e.g.
  `name="ck_tasks_status"`) therefore doubles it in the real DB.
  `versions/0003_tasks.py` and `TaskModel.__table_args__` pass the bare
  token (`name="status"`, `name="priority"`, `name="title_not_blank"`)
  instead.
  - **Pre-existing, out-of-scope finding**: `0002_task_lists.py`'s
    constraint was named `name="ck_task_lists_name_not_blank"` (already
    prefixed), so the same convention doubles it in the real database to
    `ck_task_lists_ck_task_lists_name_not_blank`. Verified directly by
    reading the migration source. This is harmless in practice — the
    domain layer already rejects a blank `name` before any `INSERT` is
    attempted, and the `CHECK` still fires correctly regardless of its
    name — but it is flagged here rather than silently fixed, since
    `0002_task_lists.py` belongs to an already-merged, out-of-scope PR.
    See Section D.
- `SqlAlchemyUnitOfWork`'s constraint-error map is intentionally unchanged
  by this slice: no new *unique* constraint needs a friendly domain-error
  translation, and an unmapped constraint violation propagates as the raw
  `IntegrityError`, never silently swallowed.

### Phase 7: Filters, Pagination, Completion (Slice 4, `feature/task-filters-completion`, PR 8)

- `completion_percentage` uses `Decimal` arithmetic with `ROUND_HALF_UP`
  quantization to `0.01`, never Python floating-point division directly
  (`1/3 -> 33.33`, `2/3 -> 66.67`); `total == 0` is special-cased to `0.0`.
- `InMemoryTaskRepository.search` (the fake) mirrors the SQL semantics
  exactly, verified to produce identical results to the real repository
  against the same filter/pagination/count combinations over real
  Postgres.
- Query validation (`limit` 1-100 default 20, `offset` ≥ 0, invalid
  `status`/`priority` enum value) is enforced entirely by FastAPI/Pydantic
  `Query(...)` constraints and the existing `StrEnum`s — no additional
  domain validation layer was needed.

### Phase 8: Assignment and Invitation (Slice 5, `feature/notifications`, PR 9)

- `AccessPolicy.status_changeable_task` always raises the single
  `TaskNotFoundError` (never a two-stage list-then-task check, unlike
  `owned_task`): a missing list, a missing task, and a stranger must be
  indistinguishable per the no-enumeration requirement, so both are
  fetched up front and one boolean decides authorization.
- `BackgroundTaskNotifier.send_task_invitation` is `async def` (to satisfy
  the `NotificationService` Protocol) but does no `await`-worthy work: it
  schedules the real delivery via `background_tasks.add_task(...)` and
  returns immediately, so `AssignTask` never blocks on the actual
  notification.
- **Discovered and fixed two real logging gaps**, both found by the Docker
  smoke test, not by the unit/integration suite:
  1. `alembic/env.py`'s `fileConfig(...)` defaulted to
     `disable_existing_loggers=True`; since the integration harness runs
     Alembic in-process, the first test to run migrations permanently
     disabled every pre-existing `app.*` logger (including
     `app.notifications`) for the rest of the session. Fixed with
     `disable_existing_loggers=False` — safe because the real CLI runs
     `alembic upgrade head` in its own separate OS process anyway.
  2. The real running server never printed the invitation line at all:
     nothing in the app configured logging, so Python's root logger
     defaulted to `WARNING` with no handler. Fixed with one
     `logging.basicConfig(level=logging.INFO)` call at the top of
     `main.py`. Verified end-to-end via `docker compose logs api`.
- `GET /users/me/tasks`'s response has no `completion_percentage` field —
  completion is a per-list metric, not meaningful across lists the caller
  does not own.

### Phase 9: Code Hardening (Slice 6a, `feature/security-hardening`, PR 10)

- `X-Frame-Options: DENY` was chosen over a `Content-Security-Policy` frame
  directive, which would need a Swagger-UI allow-list exemption for no
  extra protection against clickjacking.
- `Strict-Transport-Security` is conditional on the request being HTTPS
  (directly, or via a trusted `X-Forwarded-Proto: https` header) — sending
  HSTS over plain HTTP would be misleading, and browsers ignore it anyway.
- Rate limiting is **off by default** (`rate_limit_enabled: bool = False`)
  rather than on with a high limit, so no existing test suite needs
  throttle-awareness; only `test_rate_limit.py` flips it on with a
  deliberately low limit, resetting the limiter state before/after.
- `slowapi`'s `Limiter` is a module-level singleton, not constructed inside
  `create_app()`: its `@limiter.limit(...)` decorator binds to the specific
  instance it decorates at import time, so a limiter built fresh inside the
  app factory would never be the one the decorated routes actually
  consult.
- **No `SlowAPIMiddleware`** registered: reading its source showed its
  synchronous fallback path silently substitutes `slowapi`'s own default
  exception handler for any *async* custom handler (ours is), which would
  have discarded the `{"code": "rate_limited", ...}` contract. The
  per-route `@limiter.limit(...)` decorator alone is sufficient since every
  rate-limited route is already decorated explicitly.
- `CORSMiddleware`'s `allow_credentials=True` with an empty
  `allow_origins` default is intentional: Starlette never adds
  `Access-Control-Allow-Origin` for a non-matching (or, with an empty list,
  any) origin, so an empty allow-list is the strictest possible default.

### Phase 10: CI Security Scanning (Slice 6b, `feature/security-ci-scanners`, PR 11)

- Bandit is **blocking** (medium+ severity on first-party code, cheap to
  react to immediately); pip-audit is **non-blocking** (a transitive
  dependency CVE may need time to triage or wait on an upstream patch).
  Both satisfy the spec's "surfaced without blocking merges unless
  explicitly configured" — bandit is the documented exception.
- Trivy scans the image built from the repository's own `Dockerfile`
  (not a registry image), so the scan reflects exactly what would ship.
  `ignore-unfixed: true` means only a vulnerability with an available
  upstream fix can fail the job.
- Snyk is gated entirely on the `SNYK_TOKEN` secret, with every step
  individually conditioned (not a single job-level `if`), so the job still
  appears in the Actions UI as skipped-to-no-op instead of disappearing
  silently. It is `continue-on-error: true` regardless.
- **Fluid Attacks is pending, not implemented, and not faked** — see
  Section D for the full reasoning and the explicit follow-up instruction.
- Dependabot uses the `pip` ecosystem (not a dedicated `uv` ecosystem
  value) because whether GitHub's native `uv.lock` Dependabot support
  applies to this repository's exact configuration could not be verified
  in this session (same web-access gap as Fluid Attacks) — recorded as a
  pending confirmation in Section D.
- Verification for this slice was static (actionlint + YAML parse + local
  `bandit`/`pip-audit` runs), not a live GitHub Actions run — pushing
  branches and observing CI runs was reserved for the orchestrator in this
  delivery, not the apply sessions.

### Phase 11: Sentry Integration (Slice 6c, `feature/sentry-integration`, PR 12)

- **Not cut**, despite the proposal naming this slice the first candidate
  to cut under time pressure — there was enough time/scope to complete it.
- `init_sentry()` lives in its own module
  (`infrastructure/observability/sentry.py`) purely so a monkeypatch-spy
  test can target `sentry_sdk.init` directly without reaching into
  `main`'s module namespace.
- Called at **module import time** in `main.py`, before `create_app()`,
  not inside the `lifespan` context manager — Sentry's own guidance is to
  initialize as early as possible, so it can also observe errors during
  app construction itself (router registration, middleware wiring), not
  just request handling.
- No test asserts against a real Sentry endpoint: both tests monkeypatch
  `sentry_sdk.init` with a call-recording lambda and inspect the captured
  kwargs.

## D. Pending / Deferred

| Item | Status | Notes |
|------|--------|-------|
| Refresh-token rotation and a revocation denylist | Deferred, documented as a known gap | Out of scope for this challenge; every token already carries a `jti` claim to key a future denylist on |
| Shared lists / collaboration (multiple owners or members of a list) | Out of scope | Only the single-assignee middle ground (Section B, #3) is provided |
| Real email delivery (SMTP or a provider) | Out of scope by design | Console/log notifier only — the challenge explicitly asks for a *fake* invitation |
| Fluid Attacks CI integration | Pending | No primary-source-verified free/open-source invocation could be confirmed (no web-research tool available in the apply sessions that worked on `security.yml`). A commented-out job stub in `security.yml` marks where an official pinned Docker image or GitHub Action would plug in. **Follow-up**: whoever next has web access should confirm the current free-tier invocation from `docs.fluidattacks.com`/`github.com/fluidattacks` and either complete the stub or explicitly drop it with rationale recorded here |
| Dependabot's `pip`-vs-`uv` ecosystem choice for `uv.lock` | Pending confirmation | Currently configured as `pip`; GitHub's native `uv` ecosystem support for Dependabot could not be verified against this repository's exact setup without web access — revisit once that can be confirmed |
| Cosmetic doubled CHECK-constraint name on `task_lists` | Known, not fixed | The real database name is `ck_task_lists_ck_task_lists_name_not_blank` (verified by reading `versions/0002_task_lists.py`: an already-prefixed `name="ck_task_lists_name_not_blank"` gets the naming convention's `"ck"` template applied again). Harmless — the domain layer rejects a blank name before any `INSERT` — and left alone because the migration that introduced it belongs to an already-merged, out-of-scope PR (Phase 4). See Section C, Phase 6, for the full discovery and the fix applied going forward in `0003_tasks.py` |
| Idempotent same-status transition | Considered and rejected, not pending | Noted here for completeness: an idempotent 200-with-no-change response for a same-status `PATCH .../status` was explicitly considered during Phase 5 and rejected in favor of treating it as any other invalid transition (409) — see Section B, #9 |
