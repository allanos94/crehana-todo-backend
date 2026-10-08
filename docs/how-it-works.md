# How it works

A functional walkthrough of the Todo Lists API for anyone evaluating or
joining the project — what it does, end to end, without reading the source.
Ten minutes, start to finish. For setup commands see the [README](../README.md);
for API-shape reference see Swagger at `/docs`.

## 1. What the app is

A REST API for managing personal todo lists with optional task assignment.
Everything is scoped to the authenticated caller — you only ever see your
own lists, plus the tasks assigned to you by others.

| Concept | Meaning |
|---|---|
| **User** | A registered account (email + password). Identifies the caller on every request via a JWT. |
| **Task list** | An owner-scoped collection of tasks. Only its owner can see or manage it. |
| **Task** | A unit of work that belongs to exactly one list. Has a status, priority, optional due date, and optional assignee. |
| **Assignee** | A user (not necessarily the owner) a task is handed to. Can progress that one task without owning its list. |
| **Status** | `pending`, `in_progress`, or `done`, moved through a strict state machine. |
| **Priority** | `low`, `medium`, or `high`; defaults to `medium`. |
| **due_date** | An optional calendar date; must not be in the past when set. |
| **completion_percentage** | `done / total` tasks in a list, as a percentage — list-wide, not affected by filters. |

## 2. A typical user journey

| Step | What happens | Endpoint |
|---|---|---|
| 1. Register | Create an owner account and (optionally) an assignee account | `POST /api/v1/auth/register` |
| 2. Log in | Exchange email/password for an access + refresh token pair | `POST /api/v1/auth/login` |
| 3. Create a list | e.g. "Groceries" | `POST /api/v1/lists` |
| 4. Add tasks | Each task starts as `pending` | `POST /api/v1/lists/{list_id}/tasks` |
| 5. Move tasks through statuses | `pending → in_progress → done` | `PATCH /api/v1/lists/{list_id}/tasks/{task_id}/status` |
| 6. Filter and check completion | Filter by status/priority, see `completion_percentage` | `GET /api/v1/lists/{list_id}/tasks` |
| 7. Assign a task | Hand a task to a registered user; triggers a fake invitation | `PATCH /api/v1/lists/{list_id}/tasks/{task_id}/assignee` |
| 8. Assignee works on it | The assignee changes status on their assigned task, without owning the list | `PATCH /api/v1/lists/{list_id}/tasks/{task_id}/status` |
| (anytime) See my assignments | Across every list, regardless of owner | `GET /api/v1/users/me/tasks` |

The [README's Quick start](../README.md#quick-start-docker) runs this exact
journey with `curl`.

## 3. Architecture at a glance

![Architecture diagram](diagrams/01-arquitectura.png)

The code is organized in three layers, each only allowed to depend on the
one below it:

- **Domain** (`src/app/domain/`) — entities (`User`, `TaskList`, `Task`),
  value objects, the status state machine, and the exception hierarchy.
  Imports nothing but the standard library: no FastAPI, no SQLAlchemy, no
  Pydantic.
- **Application** (`src/app/application/`) — one use case per action
  (`execute(command) -> result`), the `AccessPolicy` authorization rules,
  and the `Protocol`-based ports (`UnitOfWork`, repositories,
  `PasswordHasher`, `TokenService`, `NotificationService`, `Clock`) that
  infrastructure implements.
- **Infrastructure** (`src/app/infrastructure/`) — FastAPI routers and
  schemas, SQLAlchemy/Alembic, JWT, Argon2, the console notifier, and
  everything else that talks to the outside world.

**The dependency rule, in plain words**: inner layers never know the outer
layers exist. Domain code has no idea it's running inside a web API backed
by Postgres — it could be swapped for any framework or database without
touching a single domain or application file. This isn't just a convention
here: `tests/unit/test_architecture.py` walks every module's AST and fails
the build if `domain`/`application` ever import a framework.

## 4. Life of a request

![Request flow diagram](diagrams/02-flujo-request.png)

Walking through `PATCH /api/v1/lists/{list_id}/tasks/{task_id}/status`
(change a task's status) end to end:

1. **Middleware** — rate limiting (if enabled) and security headers run
   first.
2. **Router** — FastAPI matches the route and validates the request body
   against `ChangeTaskStatusRequest`.
3. **Authentication** — `get_current_user_id` decodes the bearer token.
   - No `Authorization` header → **401** `not_authenticated`.
   - Invalid, expired, or wrong-typed token → **401** `invalid_token`.
4. **Use case** — `ChangeTaskStatus.execute(...)` runs inside the
   application layer.
5. **Authorization** — `AccessPolicy.status_changeable_task` checks that
   the caller is the list's owner *or* the task's assignee.
   - Missing list, missing task, or a stranger → **404** `task_not_found`
     (identical response either way — see [section 6](#6-who-can-do-what)).
6. **Domain rule** — `Task.change_status()` checks the state machine.
   - Any transition outside the four valid edges, including the same
     status repeated → **409** `invalid_status_transition`.
7. **Commit** — `UnitOfWork.commit()` persists the change to PostgreSQL.
8. **Response** — **200** with the updated task.

Every other endpoint follows the same shape (auth → authorization → domain
rule → commit), with [section 9](#9-errors) covering the error contract
that any of these failures produce.

## 5. Business rules

![State machine diagram](diagrams/03-maquina-estados.png)

**Status state machine** — only four transitions are valid; everything
else, including re-sending the current status, is a conflict:

| From | To | Allowed? |
|---|---|---|
| `pending` | `in_progress` | Yes |
| `in_progress` | `pending` | Yes |
| `in_progress` | `done` | Yes |
| `done` | `in_progress` | Yes |
| `pending` | `done` (or reverse) | No → 409 |
| any status | itself | No → 409 |

**due_date** — a calendar date (no time component), must not be earlier
than today in UTC. Re-validated only when a request actually sends
`due_date` — leaving it out of a `PATCH` never re-checks the existing
value.

**Field limits**

| Field | Rule |
|---|---|
| `name` (list) | Non-blank after trimming, ≤ 120 chars; unique per owner, case-insensitive → 409 |
| `title` (task) | Non-blank after trimming, ≤ 200 chars |
| `description` (list/task) | Optional, ≤ 2000 chars; blank normalizes to `null` |
| `priority` | `low` / `medium` / `high`; defaults to `medium` if omitted |
| `password` | 8–128 characters, at least one letter and one digit |

**Uniqueness** — a list name is unique per owner only (two different
owners can both have a list named "Groceries"), compared
case-insensitively, enforced both in the use case and by a DB-level
constraint for race safety.

**Cascade delete** — deleting a list deletes its tasks at the database
level.

**completion_percentage** — `done / total` over **every** task in the
list, rounded to 2 decimals, regardless of any `status`/`priority` filter
applied to `items`. An empty list reports `0.0`. Filters only narrow
`items`/`total`; they never change `completion_percentage`.

**Pagination** — `limit` (1–100, default 20) and `offset` (≥ 0, default 0)
on every listing endpoint.

## 6. Who can do what

![Permissions matrix diagram](diagrams/04-permisos.png)

Three roles exist per task:

| Role | View list | CRUD tasks | Change status | Assign | `GET /users/me/tasks` |
|---|---|---|---|---|---|
| **Owner** (created the list) | Yes | Yes | Yes | Yes | Yes (their own) |
| **Assignee** (not the owner) | No — 404 | No — 404 | Yes, on their one task | No — 404 | Yes (their own) |
| **Stranger** (neither) | No — 404 | No — 404 | No — 404 | No — 404 | Yes (their own) |

`GET /api/v1/users/me/tasks` is never scoped to a list — any authenticated
user can call it; it simply returns whatever tasks are currently assigned
to them, possibly an empty list.

**Why 404 instead of 403**: a resource owned by someone else and a
resource that doesn't exist return the exact same response. This means an
attacker can never tell "this exists but isn't mine" apart from "this
doesn't exist" by comparing status codes — there is nothing to enumerate.

## 7. Authentication

Login and refresh return a token pair:

| Token | Lifetime | Carries |
|---|---|---|
| Access | 15 minutes | `sub` (user id), `type=access`, `iat`, `exp`, `jti` |
| Refresh | 7 days | `sub` (user id), `type=refresh`, `iat`, `exp`, `jti` |

Every endpoint that needs identity reads the access token's `type` claim
and rejects a refresh token used in its place (and vice versa at
`/auth/refresh`) with `invalid_token`.

- **Password policy**: 8–128 characters, at least one letter and one
  digit, hashed with Argon2.
- **Non-enumerating login**: a wrong password and an unknown email both
  return the identical `401 invalid_credentials`. An unknown email still
  pays the full Argon2 verification cost against a fixed dummy hash, so
  the response time doesn't leak which case happened either.
- **Rate limiting**: `register`/`login`/`refresh` are limited per client
  IP (`AUTH_RATE_LIMIT`, default `10/minute`), off by default so local
  dev/tests are never throttled, and turned on by the Docker Compose
  stack. Exceeding it returns `429 rate_limited` with a `Retry-After`
  header.

## 8. Notifications

Assigning a task to someone fires one fake "email" invitation — no real
email is ever sent.

- **When it fires**: only when `assignee_id` changes to a *new, non-null*
  user, and only *after* the assignment transaction has committed.
  Unassigning (`assignee_id: null`) never notifies; reassigning notifies
  only the new assignee, never the previous one.
- **What it logs**: one structured `INFO` line — who invited whom, to
  which task, in which list.
- **How to see it**: the notification is scheduled on FastAPI's background
  tasks (so the HTTP response doesn't wait for it), and logged by the
  `app.notifications` logger:

  ```bash
  docker compose logs api | grep notifications
  # -> INFO:app.notifications:Task invitation: owner@example.com invited
  #    assignee@example.com to 'Buy milk' (list 'Groceries')
  ```

## 9. Errors

Every error response — including an unhandled exception — has the same
shape:

```json
{"code": "task_list_not_found", "message": "Task list not found"}
```

A `422` from request validation additionally includes `details` (one entry
per invalid field):

```json
{"code": "validation_error", "message": "Request validation failed",
 "details": [{"field": "body.name", "message": "...", "type": "..."}]}
```

| Status | Meaning | Example `code` |
|---|---|---|
| 401 | Not authenticated, or an invalid/expired/wrong-typed token | `not_authenticated`, `invalid_token`, `invalid_credentials` |
| 404 | Not found, or not owned by the caller (never 403) | `task_list_not_found`, `task_not_found`, `user_not_found` |
| 409 | Conflict — uniqueness or an invalid status transition | `task_list_name_conflict`, `invalid_status_transition` |
| 422 | Business-rule or schema validation failure | `weak_password`, `due_date_in_past`, `assignee_not_found`, `invalid_field`, `validation_error` |
| 429 | Rate limit exceeded | `rate_limited` |
| 500 | Unhandled error — no internal detail is ever leaked | `internal_error` |

## 10. Where to go next

- [README](../README.md) — setup, the full API reference table, and
  security hardening.
- [README § Architecture](../README.md#architecture) and
  [§ API reference](../README.md#api-reference) for the quick-lookup
  version of sections 3 and 9 above.
- [`docs/postman/`](postman/) — a ready-to-import Postman collection that
  exercises every endpoint, including the error paths.
- `http://localhost:8000/docs` — interactive Swagger UI once the app is
  running.
- [DECISION_LOG.md](../DECISION_LOG.md) — the full rationale (ADRs) behind
  every rule described above.
