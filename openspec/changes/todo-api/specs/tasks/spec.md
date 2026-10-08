# Tasks Specification

## Purpose

CRUD of `Task` resources within an owned `TaskList`, field validation including `due_date`, the task status state machine, and filtered/paginated listing with a completion percentage computed over all tasks of the list.

## Requirements

### Requirement: Create Task

The system MUST allow the owner of a `TaskList` to create a `Task` within it via `POST /lists/{list_id}/tasks`. `title` is REQUIRED, MUST be non-empty after trimming whitespace, and MUST NOT exceed 200 characters. `description` is OPTIONAL and MUST NOT exceed 2000 characters when provided. `priority` MUST be one of `low`, `medium`, `high`. `due_date` is OPTIONAL; when provided it is a calendar date (no time component) and MUST NOT be earlier than today. A new task's initial status MUST be `pending`.

#### Scenario: Successful creation with all fields

- GIVEN the authenticated user owns list `L1`
- WHEN they send `POST /lists/L1/tasks` with `title = "Buy milk"`, `priority = "low"`, and `due_date` equal to today
- THEN the response status is 201
- AND the created task has `status = "pending"`

#### Scenario: Successful creation with due_date omitted

- GIVEN the authenticated user owns list `L1`
- WHEN they send `POST /lists/L1/tasks` with `title = "Buy milk"`, `priority = "low"`, and no `due_date`
- THEN the response status is 201
- AND the created task's `due_date` is `null`

#### Scenario: Empty title after trim is rejected

- GIVEN the authenticated user owns list `L1`
- WHEN they send `POST /lists/L1/tasks` with `title = "   "`
- THEN the response status is 422

#### Scenario: Title exceeding max length is rejected

- GIVEN the authenticated user owns list `L1`
- WHEN they send `POST /lists/L1/tasks` with a `title` of 201 characters
- THEN the response status is 422

#### Scenario: Description exceeding max length is rejected

- GIVEN the authenticated user owns list `L1`
- WHEN they send `POST /lists/L1/tasks` with a valid `title` and a `description` of 2001 characters
- THEN the response status is 422

#### Scenario: Invalid priority value is rejected

- GIVEN the authenticated user owns list `L1`
- WHEN they send `POST /lists/L1/tasks` with `priority = "urgent"`
- THEN the response status is 422

#### Scenario: Creating a task in another user's list returns 404

- GIVEN list `L1` is owned by user A
- WHEN user B sends `POST /lists/L1/tasks` with a valid body
- THEN the response status is 404

#### Scenario: Unauthenticated creation is rejected

- WHEN an unauthenticated client sends `POST /lists/{list_id}/tasks`
- THEN the response status is 401

### Requirement: due_date Must Not Be Earlier Than Today

The system MUST treat `due_date` as a calendar date with no time component, MUST compare it against the current date in UTC obtained through an injected clock (not the system wall clock directly), and MUST reject a `due_date` earlier than today with 422 on both create and update. A `due_date` equal to today MUST be accepted. A `null` or omitted `due_date` MUST be accepted.

#### Scenario: due_date in the past is rejected on create

- GIVEN the injected clock reports today as `2026-10-07` (UTC)
- WHEN a client sends `POST /lists/{list_id}/tasks` with `due_date = "2026-10-06"`
- THEN the response status is 422

#### Scenario: due_date equal to today is accepted on create

- GIVEN the injected clock reports today as `2026-10-07` (UTC)
- WHEN a client sends `POST /lists/{list_id}/tasks` with `due_date = "2026-10-07"`
- THEN the response status is 201

#### Scenario: due_date in the future is accepted on create

- GIVEN the injected clock reports today as `2026-10-07` (UTC)
- WHEN a client sends `POST /lists/{list_id}/tasks` with `due_date = "2026-10-08"`
- THEN the response status is 201

#### Scenario: null due_date is accepted on create

- WHEN a client sends `POST /lists/{list_id}/tasks` with `due_date = null` (or omitted)
- THEN the response status is 201
- AND the created task's `due_date` is `null`

#### Scenario: due_date in the past is rejected on update

- GIVEN the injected clock reports today as `2026-10-07` (UTC)
- AND an existing task with `due_date = null`
- WHEN a client sends `PATCH /lists/{list_id}/tasks/{task_id}` with `due_date = "2026-10-01"`
- THEN the response status is 422

#### Scenario: due_date equal to today is accepted on update

- GIVEN the injected clock reports today as `2026-10-07` (UTC)
- WHEN a client sends `PATCH /lists/{list_id}/tasks/{task_id}` with `due_date = "2026-10-07"`
- THEN the response status is 200

#### Scenario: Clearing due_date to null on update is accepted

- GIVEN an existing task with a future `due_date`
- WHEN a client sends `PATCH /lists/{list_id}/tasks/{task_id}` with `due_date = null`
- THEN the response status is 200
- AND the task's `due_date` is now `null`

### Requirement: Retrieve, Update, and Delete Task

The system MUST allow the owner of a task's list to retrieve (`GET`), update (`PATCH`), and delete (`DELETE`) the task via `/lists/{list_id}/tasks/{task_id}`, applying the same field validation as creation on update, and MUST return 404 (never 403) when the list or task does not exist or does not belong to the requesting user.

#### Scenario: Owner retrieves a task

- GIVEN the authenticated user owns list `L1` containing task `T1`
- WHEN they send `GET /lists/L1/tasks/T1`
- THEN the response status is 200

#### Scenario: Owner updates a task

- GIVEN the authenticated user owns list `L1` containing task `T1`
- WHEN they send `PATCH /lists/L1/tasks/T1` with `title = "Updated title"`
- THEN the response status is 200
- AND the task's title is now `"Updated title"`

#### Scenario: Owner deletes a task

- GIVEN the authenticated user owns list `L1` containing task `T1`
- WHEN they send `DELETE /lists/L1/tasks/T1`
- THEN the response status is 204 (or 200, per the chosen convention)
- AND a subsequent `GET /lists/L1/tasks/T1` returns 404

#### Scenario: Non-owner access to a task returns 404

- GIVEN list `L1` and task `T1` are owned by user A
- WHEN user B sends `GET`, `PATCH`, or `DELETE` on `/lists/L1/tasks/T1`
- THEN the response status is 404 in every case

#### Scenario: Unauthenticated access is rejected

- WHEN an unauthenticated client sends any request to `/lists/{list_id}/tasks/{task_id}`
- THEN the response status is 401

### Requirement: Task Status State Machine

The system MUST expose `PATCH /lists/{list_id}/tasks/{task_id}/status` to change a task's status among `pending`, `in_progress`, and `done`. The system MUST allow the transitions `pending → in_progress`, `in_progress → pending`, `in_progress → done`, and `done → in_progress`. The system MUST reject `pending → done` with 409 (`InvalidStatusTransitionError`).

**Decision (confirmed by the user):** a same-status transition (e.g. `pending → pending`) is treated as an invalid transition and rejected with 409, consistent with the rule that only the four transitions listed above are valid edges in the state machine.

#### Scenario: pending to in_progress is allowed

- GIVEN a task with `status = "pending"`
- WHEN the owner sends `PATCH .../status` with `status = "in_progress"`
- THEN the response status is 200
- AND the task's status is now `"in_progress"`

#### Scenario: in_progress to pending is allowed

- GIVEN a task with `status = "in_progress"`
- WHEN the owner sends `PATCH .../status` with `status = "pending"`
- THEN the response status is 200
- AND the task's status is now `"pending"`

#### Scenario: in_progress to done is allowed

- GIVEN a task with `status = "in_progress"`
- WHEN the owner sends `PATCH .../status` with `status = "done"`
- THEN the response status is 200
- AND the task's status is now `"done"`

#### Scenario: done to in_progress is allowed

- GIVEN a task with `status = "done"`
- WHEN the owner sends `PATCH .../status` with `status = "in_progress"`
- THEN the response status is 200
- AND the task's status is now `"in_progress"`

#### Scenario: pending to done is rejected

- GIVEN a task with `status = "pending"`
- WHEN the owner sends `PATCH .../status` with `status = "done"`
- THEN the response status is 409
- AND the error `code` identifies an invalid status transition

#### Scenario: done to pending is rejected

- GIVEN a task with `status = "done"`
- WHEN the owner sends `PATCH .../status` with `status = "pending"`
- THEN the response status is 409

#### Scenario: Same-status transition is rejected

- GIVEN a task with `status = "pending"`
- WHEN the owner sends `PATCH .../status` with `status = "pending"`
- THEN the response status is 409

#### Scenario: Non-owner cannot change status (unless they are the assignee)

- GIVEN task `T1` in list `L1` is owned by user A and not assigned to user B
- WHEN user B sends `PATCH /lists/L1/tasks/T1/status`
- THEN the response status is 404

#### Scenario: Unauthenticated status change is rejected

- WHEN an unauthenticated client sends `PATCH /lists/{list_id}/tasks/{task_id}/status`
- THEN the response status is 401

### Requirement: Filtered, Paginated Listing with Completion Percentage

The system MUST expose `GET /lists/{list_id}/tasks?status=&priority=&limit=&offset=` returning `{items, total, completion_percentage}`, where `items` and `total` reflect the applied `status`/`priority` filters and `limit`/`offset` pagination, but `completion_percentage` MUST always be computed over ALL tasks belonging to the list, regardless of any filters applied to `items`. `completion_percentage` is `done_count / total_task_count * 100`, rounded to 2 decimal places, and MUST be `0.0` when the list has zero tasks.

#### Scenario: completion_percentage ignores active filters

- GIVEN list `L1` has 4 tasks total: 1 `done`, 3 `pending`
- WHEN a client sends `GET /lists/L1/tasks?status=pending`
- THEN `items` contains only the 3 `pending` tasks
- AND `completion_percentage` is `25.00` (1 of 4 tasks done, computed over all tasks)

#### Scenario: completion_percentage with no tasks is zero

- GIVEN list `L1` has zero tasks
- WHEN a client sends `GET /lists/L1/tasks`
- THEN `items` is an empty array, `total` is `0`
- AND `completion_percentage` is `0.0`

#### Scenario: completion_percentage rounds to 2 decimals

- GIVEN list `L1` has 3 tasks total: 1 `done`, 2 not done
- WHEN a client sends `GET /lists/L1/tasks`
- THEN `completion_percentage` is `33.33`

#### Scenario: Filtering by status

- GIVEN list `L1` has tasks with statuses `pending`, `in_progress`, and `done`
- WHEN a client sends `GET /lists/L1/tasks?status=done`
- THEN `items` contains only tasks with `status = "done"`

#### Scenario: Filtering by priority

- GIVEN list `L1` has tasks with priorities `low`, `medium`, and `high`
- WHEN a client sends `GET /lists/L1/tasks?priority=high`
- THEN `items` contains only tasks with `priority = "high"`

#### Scenario: Combining status and priority filters

- GIVEN list `L1` has a mix of tasks across statuses and priorities
- WHEN a client sends `GET /lists/L1/tasks?status=pending&priority=high`
- THEN `items` contains only tasks matching both `status = "pending"` AND `priority = "high"`

#### Scenario: Pagination with limit and offset

- GIVEN list `L1` has 10 tasks
- WHEN a client sends `GET /lists/L1/tasks?limit=3&offset=3`
- THEN `items` contains at most 3 tasks, starting after the first 3
- AND `total` reflects the full matching count, not the page size

#### Scenario: Non-owner listing returns 404

- GIVEN list `L1` is owned by user A
- WHEN user B (not the owner and not an assignee of any task in `L1`) sends `GET /lists/L1/tasks`
- THEN the response status is 404

#### Scenario: Unauthenticated listing is rejected

- WHEN an unauthenticated client sends `GET /lists/{list_id}/tasks`
- THEN the response status is 401
