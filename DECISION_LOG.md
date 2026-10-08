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

## Task Lists Core Slice (Phase 3 / Slice 2a) Notes

- Per-owner, case-insensitive `TaskList` name uniqueness is enforced in the
  application layer (`_ensure_name_available`, shared by `CreateTaskList`
  and `UpdateTaskList`), not in the router — this is a confirmed design
  position (ADR-06/ADR-07), and slice 2b's functional unique index backs it
  for race safety under concurrency.
- Renaming excludes the list's own id from the uniqueness check
  (`UpdateTaskList` normalizes via `task_list.rename(...)` first, then
  checks `name_exists(..., exclude_id=task_list.id)`), so renaming `Work`
  to `work` succeeds.
- `AccessPolicy` (`application/authorization.py`) is the single place that
  resolves owner/non-owner/missing-resource into either the entity or
  `TaskListNotFoundError` (404) — a stranger and a missing list are
  indistinguishable to the caller, never 403, per the task-lists spec.
- `UnitOfWork.task_lists` and `FakeUnitOfWork`'s rollback snapshot were
  extended from a single-repository tuple to a two-repository tuple; the
  auth use cases/tests needed no changes because `FakeUnitOfWork()` still
  default-constructs both repositories.
- No DB/API surface exists yet for task lists (fakes-only, per the 2a/2b
  split) — `tests/integration/*` and the HTTP router land in Phase 4
  (slice 2b).

## Task Lists API Slice (Phase 4 / Slice 2b) Notes

- Context7 MCP tools were not present in this session's tool list (as in
  every prior slice), so the functional unique index was **not**
  autogenerate-verified against SQLAlchemy/Alembic docs. Per explicit
  orchestrator instruction, `versions/0002_task_lists.py` was written by
  hand — `op.create_index("uq_task_lists_owner_id_lower_name",
  "task_lists", ["owner_id", sa.text("lower(name)")], unique=True)` —
  rather than relying on Alembic autogenerate to detect it, and the model
  mirrors it with a standalone `Index("uq_task_lists_owner_id_lower_name",
  TaskListModel.owner_id, func.lower(TaskListModel.name), unique=True)`
  declared after the class body (a functional index cannot be expressed
  inside `__table_args__`, which has no name to reference the not-yet-built
  class). **Verified empirically** against real Postgres 16 (installed
  SQLAlchemy 2.1.4 / Alembic 1.20.0):
  `tests/integration/test_task_list_repository.py::test_functional_unique_index_raises_on_case_insensitive_collision`
  inserts `"Groceries"` then `"GROCERIES"` for the same owner through two
  separate `SqlAlchemyUnitOfWork` transactions and confirms the second
  `commit()` raises `IntegrityError` translated to
  `DuplicateTaskListNameError` — the same
  `exc.orig.__cause__.constraint_name` pattern already proven for
  `uq_users_email` in slice 1a. The migration round-trip test
  (`test_migrations.py::test_downgrade_base_then_upgrade_head`) also
  re-ran clean through `0001` + `0002`, confirming `0002`'s `downgrade()`
  drops both indexes before the table.
- Per-owner case-insensitive uniqueness is checked twice, by design: the
  application layer (`_ensure_name_available`, slice 2a) gives a friendly
  409 on the common case, and the DB's functional unique index is the
  race-safety backstop under concurrency — both paths raise the same
  `DuplicateTaskListNameError`.
- `TaskListRepository.update` loads the row via `session.get(...)` (SQLAlchemy's
  identity map) and assigns the three mutable fields, the same pattern
  ADR-07 describes; it does not use a bulk `UPDATE` statement.
- `UpdateTaskListCommand.name` is typed `str | None | Unset` (not
  `str | Unset`): the PATCH schema allows `name` to be absent (`UNSET`,
  untouched) or a string, but an explicit JSON `null` is a distinct,
  invalid state (`name` is a required field and cannot be cleared) that
  `UpdateTaskList` now rejects with `InvalidFieldError` (422) instead of
  crashing on `None.strip()`.
- `tests/integration/test_task_lists_flow.py`'s end-to-end flow test was
  not written against a confirmed-failing implementation (no RED
  observed) — the same honest "combined cycle" deviation documented for
  every prior slice's integration flow test: the use cases and HTTP layer
  were already complete and unit-tested by the time it was written, so
  there was no missing-code shape to fail against. It passed on first run
  against real Postgres; no prior failing run was discarded.

## Tasks Core Slice (Phase 5 / Slice 3a) Notes

- The task status state machine is strict by design and is a **confirmed
  product decision, not an oversight**: only the four edges
  `pending -> in_progress`, `in_progress -> pending`, `in_progress -> done`,
  and `done -> in_progress` are valid. Every other request, including a
  same-status transition such as `pending -> pending`, raises
  `InvalidStatusTransitionError` (409). `can_transition()` and the
  `_TRANSITIONS` table in `value_objects.py` encode exactly this; there is
  no implicit "no-op success" path for a same-status PATCH.
- `due_date` validation lives in the domain (`ensure_due_date_not_past`,
  called from both `Task.create` and `Task.reschedule`) and is compared
  against `Clock.today()`, never the system wall clock directly, so tests
  stay deterministic and the rule is reusable on both create and update.
- `UpdateTask` only re-validates `due_date` when the PATCH actually
  touches it (`command.due_date is not UNSET`): an unrelated field update
  on a task whose stored `due_date` has since passed in real time does not
  fail, proven by
  `test_task_use_cases.py::test_update_task_due_date_validated_only_when_patched`.
- `AccessPolicy.owned_task` checks list ownership first
  (`owned_list`, raising `TaskListNotFoundError`) and only then task
  membership (`TaskNotFoundError`): a stranger who does not own the list at
  all never reaches the task-membership check. Both exceptions map to 404,
  so the distinction is invisible over HTTP — it only matters for which
  domain exception a use-case test asserts.
- `ChangeTaskStatus` in this slice is the **owner-only** path
  (`AccessPolicy.owned_task`). The assignee path
  (`AccessPolicy.status_changeable_task`, owner OR assignee) is Phase 8;
  until then, an assignee has no special status-change privilege yet
  because `assignee_id` cannot be set before Phase 8's `AssignTask` use
  case exists.
- "Invalid priority value" (tasks spec scenario) is validated at the API
  schema boundary (Pydantic enum field, Phase 6/6.4-6.5), not re-tested as
  a domain-level use-case scenario here: `CreateTaskCommand.priority` is
  already typed `Priority`, so an invalid string can never reach
  `CreateTask.execute` in the first place at this layer. This mirrors how
  `email` format validation works in the auth slices (`EmailStr` at the
  boundary, not re-validated in the domain).

## Tasks API Slice (Phase 6 / Slice 3b) Notes

- `assignee_id` ships now (migration `0003_tasks`, `TaskModel.assignee_id`)
  even though the assignment use cases land in Phase 8, per design ADR-08,
  so Phase 8 needs no further schema change: `UUID NULL FK users(id) ON
  DELETE SET NULL`.
- **Discovered CHECK-constraint naming gotcha** (SQLAlchemy, confirmed
  empirically against real Postgres 16): under `MetaData`'s
  `naming_convention` (`db/base.py`), an explicitly-named `CheckConstraint`
  still has the `"ck"` convention template applied to it, substituting the
  *given* name as the `%(constraint_name)s` token — unlike
  `UniqueConstraint`/`ForeignKeyConstraint`/`Index`, where an explicit name
  bypasses the convention entirely. Passing an already-prefixed name (e.g.
  `name="ck_tasks_status"`) therefore produces a doubled
  `ck_tasks_ck_tasks_status` constraint in the actual DB. `versions/0003_tasks.py`
  and `TaskModel.__table_args__` pass the bare token (`name="status"`,
  `name="priority"`, `name="title_not_blank"`) instead, consistent with how
  `TaskModel`'s `sa.Enum(..., name="status")` already worked correctly.
  Verified via
  `tests/integration/test_task_repository.py::test_status_check_constraint_rejects_invalid_value`
  and `::test_priority_check_constraint_rejects_invalid_value`, which bypass
  the ORM/domain entirely with a raw `INSERT` to prove the DB-level CHECK
  is the backstop.
  - **Pre-existing, out-of-scope finding**: `0002_task_lists.py`'s
    `ck_task_lists_name_not_blank` (Phase 4, already merged) has this exact
    same doubling in the real DB (`ck_task_lists_ck_task_lists_name_not_blank`),
    since it was also given an already-prefixed name under the same naming
    convention. This is harmless in practice — the domain layer already
    rejects a blank `name` before any INSERT is attempted, so the
    constraint's exact name only matters for a direct-SQL bypass, and the
    CHECK itself still fires correctly regardless of its name — but it is
    flagged here rather than silently fixed on this branch, since
    `0002_task_lists.py` belongs to an already-merged, out-of-scope PR.
- `priority` has no default specified anywhere in the spec, design, or
  proposal. This slice fills that gap with `Priority.MEDIUM` as the
  `CreateTaskRequest` schema default when the field is omitted — every
  spec scenario for creation supplies `priority` explicitly, so this
  default never contradicts a documented scenario; it is a product-gap
  decision made here, not a design deviation.
- `SqlAlchemyUnitOfWork`'s `_CONSTRAINT_ERRORS` map is intentionally
  unchanged by this slice: no new *unique* constraint needs a friendly
  domain-error translation (the task table's new FKs and CHECKs are not in
  the map), and task 6.7's regression test
  (`test_unmapped_constraint_violation_is_re_raised_unmodified`) confirms
  an unmapped constraint violation (`fk_tasks_list_id_task_lists`)
  propagates as the raw `IntegrityError`, never silently swallowed.
- `tests/integration/test_tasks_flow.py`'s end-to-end flow test was not
  written against a confirmed-failing implementation (no RED observed) —
  the same honest "combined cycle" deviation documented for every prior
  slice's integration flow test: it passed on first run against real
  Postgres; no prior failing run was discarded.

## Filters, Pagination, Completion Slice (Phase 7 / Slice 4) Notes

- `completion_percentage` is computed with `Decimal` arithmetic and
  `ROUND_HALF_UP` quantization to `0.01`, never Python floating-point
  division directly, so rounding is deterministic (`1/3 -> 33.33`,
  `2/3 -> 66.67`) regardless of binary float representation. `total == 0`
  is special-cased to return `0.0` rather than raising or dividing by zero.
- `TaskRepository.search` runs exactly the two-statement shape design
  ADR-10 specifies: one `count(*) ... FILTER (WHERE ...)` aggregate query
  over the whole list for `total_all`/`done_all` (always filter-independent,
  backing `completion_percentage`) and `total_filtered` (respects
  `TaskFilter`), plus one separate paged `SELECT` for `items`. This was a
  genuine two-query design, not a simplification: a single query computing
  both the unfiltered completion counts and the filtered, paginated items
  would need either a window function (losing the exact `total_filtered`
  once `offset` passes the end, the same reason design ADR-10 rejected
  `count(*) OVER ()`) or duplicating the full-list scan inline — two
  focused queries stay simpler and each is independently indexable on
  `(list_id, created_at)`.
- `completion_percentage` is computed in the domain (`value_objects.py`)
  from the repository's raw `done_all`/`total_all` integers, never in SQL,
  so the rounding rule stays unit-testable without a database and the SQL
  layer only ever returns integers.
- `InMemoryTaskRepository.search` (the fake) mirrors the SQL semantics
  exactly: counts are computed over every task in the list regardless of
  `TaskFilter`, while `items` (sorted by `(created_at, id)`, matching the
  real `ORDER BY`) and `total_filtered` both respect it. This was verified
  to produce identical results to the real repository via
  `tests/integration/test_task_repository.py::test_search_counts_and_filters`,
  which exercises the same filter/pagination/count combinations against
  real Postgres.
- `ListTasks` (and its `GET /api/v1/lists/{list_id}/tasks` route) is a
  read-only use case that still opens the full `async with self._uow:`
  transaction, matching `GetTask`'s existing pattern (ADR-07), rather than
  adding a separate read-only session path — there is no commit to make,
  but `AccessPolicy.owned_list`'s 404 check must still run inside one
  consistent session.
- Query validation (`limit` 1-100 default 20, `offset` >= 0, invalid
  `status`/`priority` enum value) is enforced entirely by FastAPI/Pydantic
  `Query(ge=..., le=...)` constraints and the existing `TaskStatus`/
  `Priority` `StrEnum`s at the router boundary — no additional domain
  validation was needed, since an out-of-range or invalid-enum query
  parameter never reaches `ListTasksCommand` in the first place, the same
  pattern already established for `priority` on task creation (Phase 6).

## Assignment and Invitation Slice (Phase 8 / Slice 5) Notes

- `AccessPolicy.status_changeable_task` always raises the single
  `TaskNotFoundError` (never `TaskListNotFoundError` first, unlike
  `owned_task`'s two-stage check): a missing list, a missing task, and a
  stranger must be indistinguishable per the task-assignment spec's
  no-enumeration requirement, so both the list and the task are fetched
  up front and a single boolean decides authorization. `ChangeTaskStatus`
  now calls this policy instead of `owned_task`, so the owner OR the
  task's assignee may change status; every other task use case
  (`GetTask`, `UpdateTask`, `DeleteTask`, `AssignTask`) stays owner-only
  via `owned_task`, so a non-owner assigning or editing the task itself
  still gets the two-stage `TaskListNotFoundError`/`TaskNotFoundError`
  (both 404 over HTTP — the existing Phase 5/6 non-owner test pattern).
- `AssignTask` implements design ADR-12's exact five-step sequence inside
  one `async with self._uow:` block: `owned_task` -> load the assignee by
  id (missing -> `AssigneeNotFoundError`, 422) -> `task.assign(...)` ->
  `commit()` -> only then, when the new assignee is non-null and differs
  from the previous one, build and send one `TaskInvitation`. The owner's
  and new assignee's emails are read from the same open session before
  committing (needed for the invitation's content), never after, so no
  extra round trip or detached-entity risk.
- `AssignTask`'s result is the `Task` entity directly (same shape as
  `ChangeTaskStatus`), not a dedicated `AssignTaskResult` — the design
  doc's ADR-04 lists `AssignTaskResult` as an example of a composite
  result, but nothing about assignment actually needs extra fields beyond
  the updated task; returning `Task` directly avoids an empty wrapper
  dataclass. This is a deviation from that one sentence in the design,
  not from any ADR-12 behavior.
- `BackgroundTaskNotifier.send_task_invitation` is `async def` (satisfying
  the `NotificationService` Protocol) but does no `await`-worthy work: it
  calls the synchronous `BackgroundTasks.add_task(...)` to schedule the
  real delivery, then returns immediately, so `AssignTask`'s `await
  self._notifier.send_task_invitation(...)` never blocks on the actual
  notification — FastAPI runs the scheduled task only after the response
  is sent (task-assignment spec: "without waiting for the notification to
  finish").
- **Discovered and fixed two real logging gaps, both found by the Docker
  smoke test, not by the unit/integration suite alone:**
  1. `alembic/env.py` called `fileConfig(config.config_file_name)` with
     its default `disable_existing_loggers=True`. In the test suite,
     Alembic's `env.py` runs in the *same process* as the API code (the
     integration harness drives migrations in-process), so the first
     integration test to run migrations permanently disabled every
     pre-existing `app.*` logger (including `app.notifications`) for the
     rest of the session — any instance already created at that point
     gets `logger.disabled = True`, which `caplog.at_level(...)` does not
     undo. This surfaced as a flaky `test_console_notifier_logs_...`
     failure that passed in isolation but failed when the full suite ran
     (order-dependent on which test first created the `app.notifications`
     `Logger` object relative to the first integration test). Fixed by
     passing `disable_existing_loggers=False` — safe because the real
     `alembic upgrade head` CLI runs in its own separate OS process via
     `docker/entrypoint.sh` anyway, so this flag never mattered there.
  2. Independently, the real running server (verified via
     `docker compose logs api`) never printed the invitation line at all:
     nothing in the app ever configures logging, so Python's root logger
     defaults to `WARNING` with no handler, silently dropping every
     `INFO`-level `app.notifications`/`app.infrastructure.api.errors`
     call outside of tests (where `caplog` or `pytest`'s own handler
     masked the gap). Fixed with one `logging.basicConfig(level=logging.INFO)`
     call at the top of `main.py`, which runs at import time, before
     uvicorn's own `dictConfig` (which only configures `uvicorn.*` loggers
     and explicitly sets `disable_existing_loggers=False`, so it does not
     re-trigger gap #1). Verified end-to-end: `docker compose logs api`
     now shows `INFO:app.notifications:Task invitation: ... invited ...
     to '...' (list '...')` after a real assignment over HTTP.
- `GET /users/me/tasks`'s response schema (`AssignedTaskPageResponse`) has
  no `completion_percentage` field, matching design ADR-10's wording
  exactly (`{items, total}`) — completion is a per-list metric and is not
  meaningful across lists the caller does not own.
