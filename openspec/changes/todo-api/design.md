# Design: Todo Lists API (Crehana Backend Challenge)

> Bootstrap change. There is no existing code to follow; every pattern below is established by this design and becomes the project convention.

## Technical Approach

A framework-free domain core wrapped by an application layer of single-purpose use cases. An infrastructure layer implements the ports and hosts FastAPI. All of it lives under `src/app/`. Requests flow router → use case → domain entities → repository/port Protocols → SQLAlchemy/PyJWT/pwdlib/console adapters. The use case owns the transaction through an async Unit of Work, one `AsyncSession` per use-case execution, which means one per request. Authorization (owner / assignee / stranger) is a single application-layer policy. Errors are domain exception classes, and one handler module maps them to a stable `{code, message[, details]}` JSON contract. Delivery follows the proposal's slice order, with slices 2, 3 and 6 split to respect the 400-line budget (see the last section).

## Architecture Decisions

### ADR-01: Package layout and dependency rule

**Choice**: Three layers under `src/app/`, with `main.py` as the composition root:

```
src/app/
  __init__.py
  main.py                              # create_app() factory, lifespan, router + handler registration
  domain/
    __init__.py
    exceptions.py                      # AppError base + category classes + concrete errors
    value_objects.py                   # TaskStatus (+transitions), Priority, text/email/password rules, completion_percentage()
    user.py                            # User entity
    task_list.py                       # TaskList entity
    task.py                            # Task entity
    repositories.py                    # UserRepository, TaskListRepository, TaskRepository Protocols + TaskFilter, TaskCounts
  application/
    __init__.py
    ports.py                           # UnitOfWork, Clock, PasswordHasher, TokenService, NotificationService Protocols
    exceptions.py                      # AuthenticationError family (not a domain concept)
    common.py                          # UNSET sentinel / Unset type for PATCH commands
    authorization.py                   # AccessPolicy: owner / assignee / stranger resolution -> 404
    auth/dto.py, auth/use_cases.py     # RegisterUser, LoginUser, RefreshTokens, GetCurrentUser
    task_lists/dto.py, task_lists/use_cases.py   # Create/List/Get/Update/DeleteTaskList
    tasks/dto.py, tasks/use_cases.py   # Create/Get/Update/DeleteTask, ChangeTaskStatus, ListTasks
    assignment/dto.py, assignment/use_cases.py   # AssignTask, ListMyAssignedTasks
  infrastructure/
    __init__.py
    config.py                          # Settings (pydantic-settings), get_settings()
    clock.py                           # SystemClock (UTC)
    db/base.py                         # DeclarativeBase + MetaData naming convention
    db/models.py                       # UserModel, TaskListModel, TaskModel (Mapped[])
    db/session.py                      # create_engine(), create_session_factory()
    db/mappers.py                      # ORM <-> domain functions
    db/repositories.py                 # SqlAlchemy*Repository
    db/unit_of_work.py                 # SqlAlchemyUnitOfWork + IntegrityError translation
    db/alembic/env.py, script.py.mako, versions/0001_users.py, 0002_task_lists.py, 0003_tasks.py
    security/password.py               # Argon2PasswordHasher (pwdlib)
    security/jwt.py                    # JwtTokenService (PyJWT)
    notifications/console.py           # ConsoleEmailNotifier, BackgroundTaskNotifier
    api/dependencies.py                # DI providers (session factory, uow, clock, hasher, tokens, notifier, CurrentUserId)
    api/errors.py                      # exception handlers + ErrorResponse schema
    api/middleware.py                  # security headers (slice 6a)
    api/schemas/common.py, auth.py, users.py, task_lists.py, tasks.py
    api/routers/health.py, auth.py, users.py, task_lists.py, tasks.py
alembic.ini                            # repo root; script_location points at the package
```

Dependency rule: `domain` imports only the stdlib. `application` imports `domain` and the stdlib. `infrastructure` imports everything plus frameworks. `main.py` wires `infrastructure.api`. The rule is enforced by `tests/unit/test_architecture.py`, which walks `src/app/domain` and `src/app/application` with `ast` and fails on any import of `fastapi`, `sqlalchemy`, `pydantic`, `jwt`, `pwdlib`, `starlette`, or `app.infrastructure`.

All business routers are mounted under the `/api/v1` prefix (decision confirmed by the user: version the API from day one). Paths in the proposal and specs are relative to that prefix (e.g. `/api/v1/lists`, `/api/v1/auth/register`). Probes stay unversioned at the root: `/health` (liveness, no DB) and `/health/ready` (readiness, runs `SELECT 1`).

**Alternatives considered**: package-by-feature at the top level (`app/tasks/{domain,app,infra}`) was rejected because the challenge PDF asks for visible Domain/Application/Infrastructure layers. `import-linter` was rejected as an extra dependency when a 30-line AST test does the job. Putting repository Protocols in `application` was rejected because the plan fixes them in the domain.
**Rationale**: the layers are visible to the evaluator, the rule is mechanically enforced, and per-feature application subpackages keep slices reviewable.

### ADR-02: Domain entities are mutable slotted dataclasses; value objects are immutable

**Choice**: Entities use `@dataclass(slots=True, kw_only=True)` (not frozen). Fields change only through intention-revealing methods (`task.change_status(new, now)`, `task_list.rename(name, now)`, `task.assign(user_id, now)`), each of which validates its invariants. IDs are `uuid.UUID` generated by entity factories (`Task.create(...)` via `uuid4()`), so entities exist with identity before persistence. Value objects are `StrEnum`s (`TaskStatus`, `Priority`) and pure validator functions that return normalized values.

**Alternatives considered**: frozen dataclasses with `dataclasses.replace` were rejected because every mutation becomes rebuild-and-reassign noise in use cases and the invariants get scattered. Pydantic domain models were rejected because they break the "domain imports nothing" rule.
**Rationale**: entities have identity and a lifecycle, and mutating methods keep the state machine and field rules inside the entity. Value objects have no identity, so immutability is free.

Rules (in `value_objects.py`, with constants exported for API schemas):

| Rule | Implementation |
|---|---|
| List `name` | `normalize_required_text(value, field="name", max_len=120)`: strip; empty → `InvalidFieldError`; len > 120 → `InvalidFieldError` |
| Task `title` | same, `max_len=200` |
| `description` | `normalize_optional_text(value, max_len=2000)`: strip; blank → `None`; len > 2000 → `InvalidFieldError` |
| `email` | strip + lowercase (format is validated at the API boundary with `EmailStr`) |
| Password | `validate_password_policy(raw)`: 8–128 chars, at least one letter (`str.isalpha` on any char), at least one digit → `PasswordPolicyError` |
| `due_date` | `ensure_due_date_not_past(due, today)`: `due < today` → `DueDateInPastError`. `today` is a parameter, never read from the system |
| Completion | `completion_percentage(done, total) -> float`: `0.0` if total == 0, else `Decimal(done*100)/total` quantized to `0.01` with `ROUND_HALF_UP` |

State machine:

```python
_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.IN_PROGRESS}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.PENDING, TaskStatus.DONE}),
    TaskStatus.DONE: frozenset({TaskStatus.IN_PROGRESS}),
}
def can_transition(src: TaskStatus, dst: TaskStatus) -> bool: ...
```

`Task.change_status(dst)`: any transition outside the table raises `InvalidStatusTransitionError(src, dst)` (→ 409), including a same-status request (`dst == current`). Decision confirmed by the user: the state machine is strict; only the four listed edges are valid.

### ADR-03: Exception hierarchy and HTTP mapping

**Choice**: `domain/exceptions.py` defines `AppError(Exception)` with class attributes `code: str` and `message` (instance). The category classes carry the HTTP semantics, but the domain knows nothing about HTTP:

| Category (domain/application) | HTTP | Concrete errors → `code` |
|---|---|---|
| `NotFoundError` | 404 | `TaskListNotFoundError` → `task_list_not_found`; `TaskNotFoundError` → `task_not_found`; `UserNotFoundError` → `user_not_found` |
| `ConflictError` | 409 | `DuplicateTaskListNameError` → `task_list_name_conflict`; `EmailAlreadyRegisteredError` → `email_already_registered`; `InvalidStatusTransitionError` → `invalid_status_transition` |
| `BusinessRuleViolationError` | 422 | `InvalidFieldError` → `invalid_field`; `PasswordPolicyError` → `weak_password`; `DueDateInPastError` → `due_date_in_past`; `AssigneeNotFoundError` → `assignee_not_found` |
| `AuthenticationError` (application/exceptions.py, subclasses `AppError`) | 401 | `InvalidCredentialsError` → `invalid_credentials`; `InvalidTokenError` → `invalid_token`; `NotAuthenticatedError` → `not_authenticated` |
| Pydantic `RequestValidationError` | 422 | `validation_error` (+ `details`) |
| Starlette `HTTPException` (unknown route, method) | as raised | `not_found`, `method_not_allowed`, … |
| Unhandled `Exception` | 500 | `internal_error` (generic message; traceback logged server-side only) |

The `infrastructure/api/errors.py` mapping is `dict[type[AppError], int]` keyed by category and resolved through `type(exc).__mro__`, so new concrete errors need no handler changes. 403 is never emitted. A missing referenced assignee is a 422 because the bad value is in the request body, while 404 is reserved for path resources.

**Alternatives considered**: `HTTPException` raised from use cases was rejected because it leaks the framework into the application layer. A status code on each domain exception was rejected because it puts an HTTP concept in the domain.
**Rationale**: one table owns the contract, the domain stays HTTP-agnostic, and category inheritance keeps the handler at O(1) maintenance.

### ADR-04: Use case shape, DTOs, and PATCH semantics

**Choice**: one class per action. Dependencies come in through `__init__`, and the single entry point is `async def execute(self, command: XCommand) -> XResult`. Commands and results are `@dataclass(frozen=True, slots=True)` in `application/<feature>/dto.py`, and every command carries `actor_id: UUID`. Use cases return domain entities directly (pure dataclasses, safe outside the session). A dedicated result dataclass is used only when the result is composite (`TaskPage`, `TokenPair`, `AssignTaskResult`). API schemas convert with `model_validate(entity, from_attributes=True)`.

PATCH partial updates use a typed sentinel in `application/common.py`:

```python
class Unset(enum.Enum):
    TOKEN = enum.auto()
UNSET: Final = Unset.TOKEN
# UpdateTaskCommand.description: str | None | Unset = UNSET   (None = clear, UNSET = untouched)
```

Routers build commands from `schema.model_dump(exclude_unset=True)`.

Field rules applied on PATCH:
- `due_date` is validated against `clock.today()` only when it is present in the patch. An unrelated update to a task whose stored `due_date` has since passed must not fail.
- The list-name uniqueness check excludes the list's own id, so renaming `Work` to `work` is allowed.

**Alternatives considered**: `__call__` was rejected because `execute` reads more explicitly and is friendlier to mypy and grep. Pydantic DTOs in the application layer were rejected because they break framework independence. Separate output view models for every use case were rejected because they double the mapping code without a payoff at this size.
**Rationale**: the smallest typed surface that keeps the application layer free of frameworks and testable with fakes.

### ADR-05: Ports as `typing.Protocol`

**Choice** (`application/ports.py`; repository Protocols in `domain/repositories.py`):

```python
class Clock(Protocol):
    def now(self) -> datetime: ...          # tz-aware UTC
    def today(self) -> date: ...            # now().date() in UTC

class PasswordHasher(Protocol):
    async def hash(self, raw: str) -> str: ...
    async def verify(self, raw: str, hashed: str) -> bool: ...

class TokenService(Protocol):
    def issue_pair(self, user_id: UUID) -> TokenPair: ...
    def decode(self, token: str, expected_type: TokenType) -> UUID: ...   # raises InvalidTokenError

class NotificationService(Protocol):
    async def send_task_invitation(self, message: TaskInvitation) -> None: ...

class UnitOfWork(Protocol):
    users: UserRepository
    task_lists: TaskListRepository
    tasks: TaskRepository
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...   # rolls back if not committed
    async def commit(self) -> None: ...                     # may raise ConflictError (constraint translation)

class TaskListRepository(Protocol):
    async def add(self, task_list: TaskList) -> None: ...
    async def update(self, task_list: TaskList) -> None: ...
    async def get(self, list_id: UUID) -> TaskList | None: ...
    async def list_by_owner(self, owner_id: UUID) -> list[TaskList]: ...
    async def name_exists(self, owner_id: UUID, name: str, exclude_id: UUID | None = None) -> bool: ...
    async def delete(self, list_id: UUID) -> None: ...

class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...
    async def update(self, task: Task) -> None: ...
    async def get(self, task_id: UUID) -> Task | None: ...
    async def delete(self, task_id: UUID) -> None: ...
    async def search(self, list_id: UUID, filters: TaskFilter, limit: int, offset: int) -> tuple[list[Task], TaskCounts]: ...
    async def list_by_assignee(self, user_id: UUID, limit: int, offset: int) -> tuple[list[Task], int]: ...
```

`PasswordHasher` is async because Argon2 is deliberately CPU-heavy (~50 ms), so the adapter offloads it with `asyncio.to_thread` instead of blocking the event loop.

**Alternatives considered**: ABCs were rejected because Protocols allow structural typing, so fakes need no inheritance. A sync hasher was rejected because it blocks the loop under concurrent logins.

### ADR-06: Authorization lives in the application layer (single policy)

**Choice**: `application/authorization.py` exposes `AccessPolicy(uow)`:

| Method | Allowed actor | Failure |
|---|---|---|
| `owned_list(list_id, actor)` | list owner | `TaskListNotFoundError` (missing or not owner) |
| `owned_task(list_id, task_id, actor)` | list owner; task must belong to `list_id` | list 404 first, then `TaskNotFoundError` |
| `status_changeable_task(list_id, task_id, actor)` | list owner OR `task.assignee_id == actor` | always `TaskNotFoundError` (a missing list, a missing task, and a stranger look identical, so nothing can be enumerated) |

Repositories expose plain `get(id)`, and ownership is compared in the policy. Every owner-only use case (list CRUD, task CRUD, assign, list tasks) calls `owned_list` / `owned_task`. Only `ChangeTaskStatus` calls `status_changeable_task`. `ListMyAssignedTasks` is scoped by `assignee_id = actor` in the query itself, and its results include `list_id` so the assignee can call the status endpoint.

**Alternatives considered**: router-level dependencies were rejected because they duplicate rules and cannot be unit-tested with fakes. Owner-scoped SQL in every repository method was rejected because it spreads the policy across adapters, and the assignee rule cannot be expressed uniformly that way.
**Rationale**: one testable place for the owner/assignee/stranger matrix, which is the proposal's main data-leak risk.

### ADR-07: Async engine and session lifecycle (Unit of Work)

**Choice**:
- `create_app()` lifespan: `engine = create_async_engine(settings.database_url, pool_pre_ping=True)`, `session_factory = async_sessionmaker(engine, expire_on_commit=False)`, both stored on `app.state`. On shutdown it calls `await engine.dispose()`.
- `get_uow(factory) -> SqlAlchemyUnitOfWork` is a per-request dependency that only constructs the object. The use case opens the transaction with `async with self._uow:`, which creates one `AsyncSession` and binds the repositories to it, and closes it with `await self._uow.commit()`. `__aexit__` rolls back whenever commit was not reached, then closes the session.
- `expire_on_commit=False`, and every row is mapped to a domain dataclass inside the session. Domain objects are never ORM instances, so lazy loading (`MissingGreenlet`) is structurally impossible.
- No ORM `relationship()`s are declared: the flat domain does not need them. Cascades are database-level (`ON DELETE CASCADE`). `TaskListRepository.delete` issues `delete(TaskListModel).where(...)`, and PostgreSQL removes the tasks.
- Updates: `update(entity)` loads the row with `session.get(Model, id)` (identity map) and applies the mapper. `add(entity)` uses `session.add(to_model(entity))`.
- Constraint races: `commit()` catches `sqlalchemy.exc.IntegrityError`, reads the constraint name from the asyncpg cause, and translates it through `{"uq_task_lists_owner_id_lower_name": DuplicateTaskListNameError, "uq_users_email": EmailAlreadyRegisteredError}`. Unknown constraints are re-raised. The use case's pre-check gives the friendly path, and the constraint translation guarantees correctness under concurrency.
- Timestamps (`created_at`, `updated_at`) are set by use cases from `Clock.now()`, which keeps tests deterministic. Columns are `TIMESTAMP WITH TIME ZONE NOT NULL`.

**Alternatives considered**: a session dependency with commit inside the dependency teardown was rejected because the commit then happens after the response is built, which hides commit errors and makes "notify after commit" ambiguous. Exposing ORM models as entities was rejected because it couples the domain to SQLAlchemy and brings lazy-load hazards.

### ADR-08: Schema, constraints, enum storage

**Choice**: `MetaData(naming_convention=...)` gives deterministic constraint names (Alembic and the IntegrityError translation both depend on them). Enums are stored as `VARCHAR(20)` + CHECK through `sa.Enum(TaskStatus, native_enum=False, create_constraint=True, length=20, values_callable=lambda e: [m.value for m in e])`.

| Table | Columns / constraints |
|---|---|
| `users` | `id UUID PK`, `email VARCHAR(320) NOT NULL` + `uq_users_email`, `hashed_password VARCHAR(255) NOT NULL`, `created_at timestamptz NOT NULL` |
| `task_lists` | `id UUID PK`, `owner_id UUID NOT NULL FK users(id) ON DELETE CASCADE`, `name VARCHAR(120) NOT NULL` + `CHECK (length(btrim(name)) > 0)`, `description VARCHAR(2000) NULL`, `created_at`, `updated_at`; functional unique index `uq_task_lists_owner_id_lower_name ON (owner_id, lower(name))`; index on `owner_id` |
| `tasks` | `id UUID PK`, `list_id UUID NOT NULL FK task_lists(id) ON DELETE CASCADE`, `title VARCHAR(200) NOT NULL` + non-blank CHECK, `description VARCHAR(2000) NULL`, `status VARCHAR(20) NOT NULL` + CHECK in (pending, in_progress, done), `priority VARCHAR(20) NOT NULL` + CHECK in (low, medium, high), `due_date DATE NULL`, `assignee_id UUID NULL FK users(id) ON DELETE SET NULL`, `created_at`, `updated_at`; indexes `ix_tasks_list_id_created_at (list_id, created_at)`, `ix_tasks_assignee_id` |

There is no CHECK for `due_date >= today`, because it is time-dependent and PostgreSQL CHECK constraints must be immutable. That rule lives in the domain. `assignee_id` ships in migration 0003 so the assignment slice needs no schema change.

**Alternatives considered**: native PG ENUM was rejected because changing its values needs `ALTER TYPE`, Alembic autogenerate does not detect value changes, and create/drop ordering is a known downgrade pitfall. VARCHAR + CHECK keeps the same database-level guarantee with plain migrations.

### ADR-09: Alembic strategy

**Choice**: `alembic.ini` sits at the repo root with `script_location = app.infrastructure.db:alembic` (a package-resource path, so it works from the installed, non-editable package in the image). `env.py` follows the async template:
- The URL comes from `get_settings().database_url`, never from the ini. `target_metadata = Base.metadata` after importing `db.models`.
- Online: `async_engine_from_config(..., poolclass=NullPool)` → `async with engine.connect() as conn: await conn.run_sync(do_run_migrations)` → `asyncio.run(run_async_migrations())`.
- Offline mode is supported (`context.configure(url=..., literal_binds=True)`).
- Migrations are autogenerated, then reviewed by hand. There is one migration per schema slice (0001 users, 0002 task_lists, 0003 tasks), each with a working `downgrade()`. Revision ids are fixed, readable strings (`0001_users`).
- Container start: `docker/entrypoint.sh` runs `alembic upgrade head`, then `exec uvicorn app.main:app --host 0.0.0.0 --port 8000`. This is safe for the single-replica compose stack. Multi-replica deployments would move it to a one-off job (documented as pending).

**Alternatives considered**: `Base.metadata.create_all` at startup was rejected because it has no history and no downgrade, and the PDF evaluates migrations. A separate compose `migrate` service was rejected as one more moving part for a single-node demo.

### ADR-10: Listing query and `completion_percentage`

**Choice**: SQL aggregates plus a domain formula. `TaskRepository.search` runs two statements in the same session:
1. Counts, as one aggregate over the whole list:
   `SELECT count(*) AS total_all, count(*) FILTER (WHERE status='done') AS done_all, count(*) FILTER (WHERE <status/priority filters>) AS total_filtered FROM tasks WHERE list_id = :id`
2. Page: `SELECT ... WHERE list_id = :id AND <filters> ORDER BY created_at, id LIMIT :limit OFFSET :offset`.

The domain `completion_percentage(done_all, total_all)` produces the number, so rounding is unit-testable. The response is `{items, total: total_filtered, completion_percentage}`. API query validation: `limit` 1–100 (default 20) and `offset` ≥ 0. `status` and `priority` accept enum values, and an invalid value is a 422 `validation_error`. `GET /users/me/tasks` returns `{items, total}` with the same `limit`/`offset` and is ordered the same way.

**Alternatives considered**: computing the percentage in Python over loaded rows was rejected because it loads the entire list. `count(*) OVER ()` was rejected because the total disappears when `offset` passes the end. Three separate count queries were rejected because the `FILTER` clauses collapse them into one.

### ADR-11: Authentication

**Choice**:
- Tokens are PyJWT HS256 signed with `settings.jwt_secret_key` (`SecretStr`, required, at least 32 characters, validated at startup). Claims: `sub` (user UUID string), `type` (`access` | `refresh`), `iat`, `exp` (15 min / 7 days), `jti` (`uuid4().hex`). `jti` is cheap now and is what a future denylist would key on. Decoding uses `jwt.decode(token, key, algorithms=["HS256"], options={"require": ["sub", "type", "iat", "exp"]})`, then checks `type == expected_type`. Any failure raises `InvalidTokenError` (401).
- Endpoints:
  - `POST /auth/register` takes JSON `{email, password}` and returns 201 with `{id, email, created_at}` (no tokens).
  - `POST /auth/login` takes JSON `{email, password}` and returns `{access_token, refresh_token, token_type: "bearer", expires_in}`.
  - `POST /auth/refresh` takes `{refresh_token}`, checks the user still exists, and returns a fresh pair. There is no rotation or denylist (pending).
  - `GET /users/me` returns the user.
- Dependency chain: `HTTPBearer(auto_error=False)` → `get_current_user_id(credentials, tokens: TokenService = Depends(get_token_service)) -> UUID`. A missing header raises `NotAuthenticatedError`, and an invalid, expired, or refresh-typed token raises `InvalidTokenError`. The handler adds `WWW-Authenticate: Bearer` to 401 responses. Routers declare `CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]`. The dependency does not hit the database: use cases receive `actor_id`, and ownership checks prove the rest. Users cannot be deleted in this scope.
- Hashing: `pwdlib.PasswordHash((Argon2Hasher(),))` wrapped by `Argon2PasswordHasher` with `asyncio.to_thread`. Login against an unknown email still runs `verify` against a module-level dummy hash, so response timing does not reveal registered emails. Both failure cases return `invalid_credentials`.

**Alternatives considered**: the `OAuth2PasswordBearer` form flow was rejected because it forces a form-encoded login with a `username` field. `HTTPBearer` still gives Swagger an "Authorize" box where a pasted token works. RS256 was rejected because there is a single service and no key distribution need. python-jose and passlib were rejected as unmaintained (verify FastAPI's current docs via Context7).

### ADR-12: Notifications after commit

**Choice**: the application port is `NotificationService.send_task_invitation(TaskInvitation)`. `TaskInvitation` is a frozen dataclass with `to_email`, `task_title`, `list_name`, and `invited_by_email`. `AssignTask` performs this sequence:

1. `owned_task`
2. load the assignee by id (missing → `AssigneeNotFoundError` 422)
3. `task.assign(...)`
4. `await uow.commit()`
5. only then, when the new assignee is non-null and differs from the previous one, `await notifier.send_task_invitation(...)`

Any exception before or during commit means no notification. `assignee_id: null` unassigns without a notification. Infrastructure:
- `ConsoleEmailNotifier` logs one structured INFO line on logger `app.notifications`. It contains the recipient and the task title, never secrets.
- `BackgroundTaskNotifier(background_tasks, delegate)` implements the same port, and its `send_task_invitation` calls `background_tasks.add_task(delegate.send_task_invitation, message)`.
- `get_notifier(background_tasks: BackgroundTasks)` builds it per request. FastAPI runs the task after the response is sent.

**Alternatives considered**: the router scheduling `BackgroundTasks` itself from a returned DTO was rejected because the "after commit" rule would move out of the tested use case. A transactional outbox was rejected as overkill for a fake email.
**Rationale**: the ordering is a unit-tested application rule, the use case never imports FastAPI, and delivery is non-blocking.

### ADR-13: Error contract implementation

**Choice**: `infrastructure/api/errors.py` provides `register_exception_handlers(app)` and the `ErrorResponse` schema `{code: str, message: str, details: list[ErrorDetail] | None}`, where `details` is omitted when `None`.
- `AppError` → status from the category map → `{code, message}`.
- `RequestValidationError` → 422 `{code: "validation_error", message: "Request validation failed", details: [{field: "body.name", message: err["msg"], type: err["type"]}]}`. The `input` and `ctx` keys are dropped so submitted values, such as passwords, are never echoed back.
- `StarletteHTTPException` → `{code: <slug of status phrase>, message: detail}`, which keeps the shape uniform for unknown routes and 405.
- `Exception` → 500 `internal_error`, with `logger.exception` server-side.
- Routers declare `responses={404: {"model": ErrorResponse}, ...}` so `/docs` documents the contract.

Pydantic schemas reuse the domain length constants (`Field(max_length=TITLE_MAX_LENGTH)`) so the limits appear in OpenAPI. The domain stays the source of truth: whitespace-only values pass Pydantic and are rejected by the domain with 422 `invalid_field`.

### ADR-14: Testing architecture

**Choice**:
- **Unit** (`tests/unit/`, no Docker, carries most of the coverage):
  - `fakes.py`: `InMemoryUserRepository`, `InMemoryTaskListRepository` (enforces case-insensitive uniqueness), `InMemoryTaskRepository` (implements filters, ordering, counts), `FakeUnitOfWork` (`committed` flag, rollback restores a snapshot), `FixedClock`, `FakePasswordHasher` (`"hashed:" + raw`), `RecordingNotifier`.
  - Domain tests cover the transitions table (parametrized over all 9 pairs), field rules, password policy, `completion_percentage` rounding, and the due-date rule.
  - Use-case tests cover the authorization matrix and "no notification when commit fails".
  - Adapter tests cover the real `JwtTokenService` (expiry with tampered `iat`/`exp`, wrong type, bad signature) and the real `Argon2PasswordHasher`.
  - **API-without-DB tests**: `httpx.AsyncClient(transport=ASGITransport(app))` with `app.dependency_overrides[get_uow] = lambda: fake_uow` and `get_clock`/`get_password_hasher`. These cover routers, schemas, and error handlers.
  - The architecture test.
- **Integration** (`tests/integration/`, marker `integration`):
  - Session-scoped sync fixture `PostgresContainer("postgres:16-alpine", driver="asyncpg")`.
  - Session-scoped sync fixture that sets `DATABASE_URL` and runs `alembic.command.upgrade(cfg, "head")`. Because it is sync, no loop is running when `env.py` calls `asyncio.run`.
  - Session-scoped async engine.
  - Per test: `conn = await engine.connect(); trans = await conn.begin()`, then `async_sessionmaker(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")` is injected by overriding `get_session_factory`, so a use case's `commit()` only releases a savepoint. Teardown calls `await trans.rollback()`.
  - Covers repository tests (unique index, cascade, `SET NULL`, search counts), the end-to-end API flow, the IntegrityError translation, and a migration round-trip (`downgrade base` → `upgrade head`) in a dedicated test that uses its own fresh database (`CREATE DATABASE` on the container).
- **pytest.ini**: `asyncio_mode = auto`, `asyncio_default_fixture_loop_scope = session`, `asyncio_default_test_loop_scope = session`, `markers = integration`, `addopts = --strict-markers --cov=app --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=75`, `testpaths = tests`.
- **Coverage** (`[tool.coverage]` in pyproject): `source = ["app"]`, `omit = ["*/alembic/versions/*"]`, `exclude_also = ["if TYPE_CHECKING:", "\\.\\.\\."]`.
- Local runs without Docker use `uv run pytest -m "not integration" --cov-fail-under=0`. CI always runs the full suite.

**Alternatives considered**: per-test `TRUNCATE` was rejected because it is slower and order-sensitive. SQLite for tests was rejected because the plan fixes same-engine testing and `FILTER` / functional indexes would diverge. A function-scoped container was rejected as far too slow.

### ADR-15: Packaging, Docker, compose, CI

**Choice**:
- `pyproject.toml`: PEP 621, `requires-python = ">=3.12,<3.13"`, `src` layout, build backend `uv_build` so `uv sync` installs the `app` package. Runtime deps: fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings, email-validator, pyjwt, pwdlib[argon2]. Dev group: pytest, pytest-asyncio, pytest-cov, httpx, testcontainers[postgres], black, isort, flake8, mypy, pre-commit. mypy is `strict = true` for `src`, with tests overridden to `disallow_untyped_defs = false`. `[tool.isort] profile = "black"`. `.flake8`: `max-line-length = 88`, `extend-ignore = E203,W503,E704`.
- **Dockerfile** (multistage):
  - `builder`: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, `UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0`. A cached `uv sync --locked --no-dev --no-install-project` runs with `uv.lock`/`pyproject.toml` bind-mounted, then `COPY . .`, then `uv sync --locked --no-dev --no-editable`.
  - `runtime`: `python:3.12-slim-bookworm` with system user `app`. It copies `/app/.venv`, `alembic.ini`, and `docker/entrypoint.sh` with `--chown=app:app`, sets `PATH=/app/.venv/bin:$PATH`, runs as `USER app`, and exposes `8000`.
  - `HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"` (slim images have no curl). `ENTRYPOINT ["/app/docker/entrypoint.sh"]`.
- `.dockerignore` excludes `.venv`, `.git`, `tests`, caches, and `openspec`. `.gitattributes` sets `* text=auto eol=lf` and `*.sh text eol=lf`. LF matters here: a CRLF shebang in `entrypoint.sh` breaks the container on Linux when the repo is committed from Windows.
- **docker-compose.yml**:
  - `db` uses `postgres:16-alpine` with a named volume and a `pg_isready` healthcheck.
  - `api` builds `.`, takes its env from `.env.example`-style variables (`DATABASE_URL=postgresql+asyncpg://...@db:5432/...`, a dev-only `JWT_SECRET_KEY`), waits on `depends_on: db: condition: service_healthy`, and maps `8000:8000`.
- `/health` is liveness only (`{"status": "ok"}`, no DB call). Compose ordering and migrations-on-start cover DB readiness.
- **CI** `.github/workflows/ci.yml` runs on PRs and pushes to `develop`/`main`. All jobs use `astral-sh/setup-uv` and `uv sync --locked`. Jobs:
  - `lint`: black --check, isort --check-only, flake8, mypy.
  - `test`: `uv run pytest` on ubuntu-latest, which ships Docker for Testcontainers. Uploads `coverage.xml`.
  - `docker`: `docker build .`, then a compose smoke test (`up -d --wait`, curl `/health`, `down -v`).
- Slice 6b adds `security.yml`.

## Data Flow

```
HTTP ─→ Router (infrastructure/api) ── builds Command from Pydantic schema
          │  Depends: CurrentUserId, get_uow, get_clock, get_password_hasher, get_token_service, get_notifier
          ▼
        UseCase.execute(cmd)                      (application)
          │  async with uow:  ── AccessPolicy (owner/assignee/stranger → 404)
          │      entity methods enforce invariants (domain)
          │      repositories (Protocol) ──→ SqlAlchemy*Repository ──→ AsyncSession ──→ PostgreSQL
          │      await uow.commit()   (IntegrityError → ConflictError)
          │  after commit: notifier.send_task_invitation() ──→ BackgroundTasks ──→ ConsoleEmailNotifier (log)
          ▼
        domain entity / result DTO ──→ response schema (from_attributes) ──→ JSON
Errors: AppError / RequestValidationError / HTTPException / Exception ──→ api/errors.py ──→ {code, message[, details]}
```

Status change (assignee path): `PATCH /lists/{l}/tasks/{t}/status` → `ChangeTaskStatus` → `AccessPolicy.status_changeable_task` (owner OR assignee, else `task_not_found`) → `task.change_status` (409 on illegal transition) → commit.

## File Changes

All files are new. Grouped by delivery slice (see the slice map below for line forecasts).

| File(s) | Slice | Description |
|---|---|---|
| `pyproject.toml`, `uv.lock`, `pytest.ini`, `.flake8`, `.pre-commit-config.yaml`, `.gitattributes`, `.dockerignore`, `.env.example` | 0 | Project + tool config |
| `src/app/__init__.py`, `src/app/main.py`, `src/app/infrastructure/config.py`, `src/app/infrastructure/api/routers/health.py` | 0 | App factory, settings, `/health` |
| `Dockerfile`, `docker/entrypoint.sh`, `docker-compose.yml`, `.github/workflows/ci.yml`, `README.md` (stub), `DECISION_LOG.md` (stub) | 0 | Delivery |
| `tests/unit/test_health.py`, `tests/unit/test_architecture.py` | 0 | First tests |
| `src/app/domain/exceptions.py`, `src/app/domain/user.py`, `src/app/domain/value_objects.py` (email/password rules), `src/app/domain/repositories.py` (UserRepository) | 1a | Domain base |
| `src/app/application/ports.py` (UnitOfWork, Clock), `src/app/application/exceptions.py` | 1a | Ports |
| `src/app/infrastructure/clock.py`, `db/base.py`, `db/models.py` (UserModel), `db/session.py`, `db/mappers.py`, `db/repositories.py`, `db/unit_of_work.py`, `alembic.ini`, `db/alembic/env.py`, `script.py.mako`, `versions/0001_users.py` | 1a | Persistence foundation |
| `src/app/infrastructure/api/errors.py`, `api/schemas/common.py`, `api/dependencies.py` (uow, clock) | 1a | Error contract + DI |
| `tests/unit/fakes.py`, `tests/unit/test_errors.py`, `tests/integration/conftest.py`, `tests/integration/test_user_repository.py`, `tests/integration/test_migrations.py` | 1a | Test harness |
| `src/app/application/auth/{dto,use_cases}.py`, `infrastructure/security/{password,jwt}.py`, `api/schemas/{auth,users}.py`, `api/routers/{auth,users}.py`, `api/dependencies.py` (+hasher, tokens, CurrentUserId), `ports.py` (+PasswordHasher, TokenService) | 1b | Auth |
| `tests/unit/test_auth_use_cases.py`, `tests/unit/test_jwt.py`, `tests/unit/test_password.py`, `tests/unit/test_auth_api.py`, `tests/integration/test_auth_flow.py` | 1b | Auth tests |
| `domain/task_list.py`, `value_objects.py` (+text rules), `repositories.py` (+TaskListRepository), `application/common.py`, `application/authorization.py` (owned_list), `application/task_lists/{dto,use_cases}.py`, fakes extension | 2a | Lists core |
| `db/models.py` (+TaskListModel), `versions/0002_task_lists.py`, repo + mapper + UoW constraint map, `api/schemas/task_lists.py`, `api/routers/task_lists.py` | 2b | Lists API |
| `domain/task.py`, `value_objects.py` (+TaskStatus, Priority, due date), `repositories.py` (+TaskRepository basic), `authorization.py` (+owned_task), `application/tasks/{dto,use_cases}.py` (CRUD + ChangeTaskStatus owner path) | 3a | Tasks core |
| `db/models.py` (+TaskModel incl. `assignee_id`), `versions/0003_tasks.py`, repo/mapper, `api/schemas/tasks.py`, `api/routers/tasks.py` | 3b | Tasks API |
| `repositories.py` (+TaskFilter, TaskCounts, search), `value_objects.py` (+completion_percentage), `tasks/use_cases.py` (+ListTasks), SQL search, list endpoint + query params | 4 | Filters + completion |
| `application/assignment/{dto,use_cases}.py`, `authorization.py` (+status_changeable_task), `ports.py` (+NotificationService), `notifications/console.py`, assignee + `/users/me/tasks` routes, `list_by_assignee` | 5 | Assignment + invitation |
| `api/middleware.py`, slowapi limiter on `/auth`, CORS config | 6a | Code hardening |
| `.github/workflows/security.yml`, `.github/dependabot.yml` | 6b | CI scanners |
| Sentry init in `main.py` gated on `SENTRY_DSN` | 6c | Optional Sentry |

## Interfaces / Contracts

```python
# domain/task.py
@dataclass(slots=True, kw_only=True)
class Task:
    id: UUID
    list_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    due_date: date | None
    assignee_id: UUID | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, list_id: UUID, title: str, description: str | None,
               priority: Priority, due_date: date | None, today: date, now: datetime) -> "Task": ...
    def change_status(self, new: TaskStatus, now: datetime) -> None: ...   # InvalidStatusTransitionError
    def rename(self, title: str, now: datetime) -> None: ...
    def describe(self, description: str | None, now: datetime) -> None: ...
    def set_priority(self, priority: Priority, now: datetime) -> None: ...
    def reschedule(self, due_date: date | None, today: date, now: datetime) -> None: ...  # DueDateInPastError
    def assign(self, user_id: UUID | None, now: datetime) -> None: ...

# application/tasks/use_cases.py
class ChangeTaskStatus:
    def __init__(self, uow: UnitOfWork, clock: Clock) -> None: ...
    async def execute(self, cmd: ChangeTaskStatusCommand) -> Task: ...
```

The domain never imports the application's `Unset`. The `UpdateTask` use case calls only the setters for fields that are not `UNSET`, which keeps the domain API explicit.

HTTP error body:

```json
{ "code": "invalid_status_transition", "message": "Cannot change status from pending to done" }
{ "code": "validation_error", "message": "Request validation failed",
  "details": [ { "field": "body.title", "message": "String should have at most 200 characters", "type": "string_too_long" } ] }
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit: domain | transitions (all 9 pairs), field normalization/limits, password policy, due-date rule, completion rounding (0, 1/3, 2/3, 100) | pure pytest, parametrized |
| Unit: application | each use case; authorization matrix owner/assignee/stranger → 404; uniqueness incl. self-rename; notify only after successful commit; due_date validated only when patched | in-memory fakes, `FixedClock` |
| Unit: adapters | JWT claims/type/expiry/signature; Argon2 hash/verify | real adapters, no I/O |
| Unit: API | routing, schemas, status codes, error shapes, 401 paths, validation `details` without `input` | `ASGITransport` + `dependency_overrides` with fakes |
| Unit: architecture | domain/application import rule | AST scan |
| Integration | repositories (unique index, cascade, SET NULL, search counts), IntegrityError translation, full API flow, migration round-trip | Testcontainers Postgres 16, savepoint rollback per test |
| E2E (manual/CI smoke) | `docker compose up --wait`, `/health`, smoke flow from the proposal | CI `docker` job + README curl script |

## Threat Matrix

N/A: there is no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary in the sense of `references/threat-matrix.md`. Application security (JWT type enforcement, no-enumeration 404s, timing-equalized login, validation output that never echoes input, error sanitizing) is designed in ADR-06, ADR-11, ADR-13 and slice 6a, and covered by the tests above.

## Migration / Rollout

The database is greenfield. Three forward migrations (`0001_users`, `0002_task_lists`, `0003_tasks`) each ship with a working `downgrade()`. A CI-backed round-trip test proves `downgrade base` → `upgrade head`. Migrations run at container start through `docker/entrypoint.sh`. Rolling back a slice means `alembic downgrade -1` plus a `git revert` of its merge commit. Locally, `docker compose down -v` resets everything.

## Slice Map and 400-line Budget

| Slice | Branch | Forecast | Over budget? | Plan |
|---|---|---|---|---|
| 0 | `feature/bootstrap-project` | 350–450 | borderline | Keep. Config files are mostly declarative. If it runs over, move CI to the head of 1a |
| 1a | `feature/auth-foundation` | 300–380 | no | Error contract, persistence foundation, test harness |
| 1b | `feature/auth-jwt` | 350–450 | borderline | Keep. If it runs over, move the API tests for auth into a follow-up commit within the same PR and justify |
| 2 | `feature/task-lists` | 400–550 | **yes** | Split into **2a** `feature/task-lists-core` (domain + use cases + fakes + unit tests, ~250) and **2b** `feature/task-lists-api` (model, 0002, repo, schemas, router, integration tests, ~250) |
| 3 | `feature/tasks-status` | 450–600 | **yes** | Split into **3a** `feature/tasks-core` (Task, TaskStatus table, Priority, due-date rule, CRUD + status use cases, unit tests, ~300) and **3b** `feature/tasks-api` (model incl. `assignee_id`, 0003, repo, schemas, routers, integration tests, ~280) |
| 4 | `feature/task-filters-completion` | 200–300 | no | Search query, counts, `completion_percentage`, list endpoint |
| 5 | `feature/notifications` | 250–350 | no | Assignment, invitation, `/users/me/tasks`, assignee status path |
| 6 | `feature/security-hardening` | 150–300+ | **yes (risk)** | Split into **6a** code hardening, **6b** CI scanners, **6c** Sentry. The cut order follows the proposal (6c first) |

Core-layer splits (a = domain/application with fakes, b = infrastructure/API) follow the dependency rule. Each "a" PR is independently green because unit tests run against fakes, and each "b" PR adds adapters and integration tests on top. The result is 11 PRs into `develop`.

## Context7 Verification Items (at apply)

1. pytest-asyncio: exact option names `asyncio_default_fixture_loop_scope` / `asyncio_default_test_loop_scope`, and session-loop behaviour with sync session fixtures.
2. testcontainers-python: `PostgresContainer(..., driver="asyncpg")` signature and `get_connection_url()`.
3. SQLAlchemy 2.0: `join_transaction_mode="create_savepoint"` with `AsyncSession`; reading the asyncpg constraint name from `IntegrityError.orig` (`__cause__.constraint_name`); `sa.Enum(native_enum=False, create_constraint=True, values_callable=...)`; functional `Index(..., func.lower(...), unique=True)` autogenerate support.
4. Alembic: async `env.py` template; package-resource `script_location = app.infrastructure.db:alembic` with a non-editable install.
5. uv: `uv_build` backend with the src layout; official multistage Dockerfile flags (`--no-editable`, `--no-install-project`, cache mounts).
6. FastAPI: `HTTPBearer(auto_error=False)` behaviour; current docs recommending PyJWT + pwdlib; `RequestValidationError.errors()` keys.
7. pwdlib: `PasswordHash((Argon2Hasher(),))` API. PyJWT: `options={"require": [...]}`.

## Open Questions

None block the design. Decisions the user should consciously confirm are listed in the phase result.
