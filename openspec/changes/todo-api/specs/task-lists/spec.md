# Task Lists Specification

## Purpose

Owner-scoped CRUD of `TaskList` resources: field validation, case-insensitive per-owner name uniqueness, cascade deletion of contained tasks, and strict ownership-based access control.

## Requirements

### Requirement: Create Task List

The system MUST allow an authenticated user to create a `TaskList` they own. `name` is REQUIRED, MUST be non-empty after trimming whitespace, and MUST NOT exceed 120 characters. `description` is OPTIONAL and MUST NOT exceed 2000 characters when provided.

#### Scenario: Successful creation

- GIVEN an authenticated user
- WHEN they send `POST /lists` with `name = "Groceries"` and no description
- THEN the response status is 201
- AND the created list is owned by the authenticated user

#### Scenario: Empty name after trim is rejected

- GIVEN an authenticated user
- WHEN they send `POST /lists` with `name = "   "`
- THEN the response status is 422

#### Scenario: Name exceeding max length is rejected

- GIVEN an authenticated user
- WHEN they send `POST /lists` with a `name` of 121 characters
- THEN the response status is 422

#### Scenario: Description exceeding max length is rejected

- GIVEN an authenticated user
- WHEN they send `POST /lists` with a valid `name` and a `description` of 2001 characters
- THEN the response status is 422

#### Scenario: Unauthenticated creation is rejected

- WHEN an unauthenticated client sends `POST /lists`
- THEN the response status is 401

### Requirement: Per-Owner Case-Insensitive Name Uniqueness

The system MUST reject creating or renaming a `TaskList` to a `name` that already exists (case-insensitively) among the same owner's other lists, with 409 Conflict. The same `name` MUST be permitted across different owners.

#### Scenario: Duplicate name for the same owner (exact case) is rejected

- GIVEN the authenticated user already owns a list named `"Groceries"`
- WHEN they send `POST /lists` with `name = "Groceries"`
- THEN the response status is 409

#### Scenario: Duplicate name for the same owner (different case) is rejected

- GIVEN the authenticated user already owns a list named `"Groceries"`
- WHEN they send `POST /lists` with `name = "GROCERIES"`
- THEN the response status is 409

#### Scenario: Same name is allowed across different owners

- GIVEN user A owns a list named `"Groceries"`
- WHEN user B (a different authenticated user) sends `POST /lists` with `name = "Groceries"`
- THEN the response status is 201

#### Scenario: Renaming into a conflicting name is rejected

- GIVEN the authenticated user owns list `"Work"` and list `"Personal"`
- WHEN they send `PATCH /lists/{id of "Personal"}` with `name = "work"`
- THEN the response status is 409

### Requirement: Retrieve and List Owned Task Lists

The system MUST allow an authenticated owner to retrieve their own `TaskList` resources via `GET /lists` (collection) and `GET /lists/{list_id}` (single), and MUST return 404 (never 403) when `{list_id}` does not belong to the requesting user or does not exist.

#### Scenario: Owner retrieves their list

- GIVEN the authenticated user owns a list with id `L1`
- WHEN they send `GET /lists/L1`
- THEN the response status is 200
- AND the response body is that list

#### Scenario: Owner retrieves their collection

- GIVEN the authenticated user owns two lists
- WHEN they send `GET /lists`
- THEN the response status is 200
- AND the response contains exactly their own lists, not other users' lists

#### Scenario: Non-owner access returns 404, not 403

- GIVEN list `L1` is owned by user A
- WHEN user B (a different authenticated user) sends `GET /lists/L1`
- THEN the response status is 404

#### Scenario: Nonexistent list returns 404

- GIVEN no list exists with id `UNKNOWN`
- WHEN an authenticated user sends `GET /lists/UNKNOWN`
- THEN the response status is 404

#### Scenario: Unauthenticated access is rejected

- WHEN an unauthenticated client sends `GET /lists` or `GET /lists/{list_id}`
- THEN the response status is 401

### Requirement: Update Task List

The system MUST allow the owner to update `name` and/or `description` of their own `TaskList` via `PATCH /lists/{list_id}`, applying the same field validation and uniqueness rules as creation, and MUST return 404 for a non-owner or nonexistent list.

#### Scenario: Owner updates name successfully

- GIVEN the authenticated user owns list `L1` named `"Old"`
- WHEN they send `PATCH /lists/L1` with `name = "New"` (not colliding with another of their lists)
- THEN the response status is 200
- AND the list's name is now `"New"`

#### Scenario: Non-owner update returns 404

- GIVEN list `L1` is owned by user A
- WHEN user B sends `PATCH /lists/L1` with any valid field
- THEN the response status is 404

#### Scenario: Invalid field value on update is rejected

- GIVEN the authenticated user owns list `L1`
- WHEN they send `PATCH /lists/L1` with `name = ""`
- THEN the response status is 422

### Requirement: Delete Task List Cascades Tasks

The system MUST allow the owner to delete their own `TaskList` via `DELETE /lists/{list_id}`, and deleting a list MUST delete all tasks that belong to it. The system MUST return 404 for a non-owner or nonexistent list.

#### Scenario: Owner deletes a list and its tasks are gone

- GIVEN the authenticated user owns list `L1` containing two tasks
- WHEN they send `DELETE /lists/L1`
- THEN the response status is 204 (or 200, per the chosen convention)
- AND a subsequent `GET /lists/L1` returns 404
- AND a subsequent `GET /lists/L1/tasks/{any former task id}` returns 404

#### Scenario: Non-owner delete returns 404

- GIVEN list `L1` is owned by user A
- WHEN user B sends `DELETE /lists/L1`
- THEN the response status is 404
- AND list `L1` and its tasks remain unaffected

#### Scenario: Unauthenticated delete is rejected

- WHEN an unauthenticated client sends `DELETE /lists/{list_id}`
- THEN the response status is 401
