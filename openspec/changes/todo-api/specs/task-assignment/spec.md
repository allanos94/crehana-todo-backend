# Task Assignment Specification

## Purpose

Assigning an existing registered user as the responsible party for a task, the resulting fake email invitation, and the bounded visibility and action rights that a non-owner assignee receives, without introducing full shared-list collaboration.

## Requirements

### Requirement: Assign Task to a Registered User

The system MUST expose `PATCH /lists/{list_id}/tasks/{task_id}/assignee` for the list owner to set or change a task's assignee. The target user MUST be an existing registered user.

**Assumption (flagged for confirmation):** assigning to a user ID/email that does not correspond to an existing registered user returns 422 (a business-validation failure on the submitted input), consistent with how other business-rule violations on this endpoint family are reported (e.g. `due_date`). 404 is the documented alternative if the product owner prefers to model it as "referenced resource not found."

#### Scenario: Owner assigns a task to a registered user

- GIVEN the authenticated user owns list `L1` containing task `T1`
- AND a registered user `assignee@example.com` exists
- WHEN the owner sends `PATCH /lists/L1/tasks/T1/assignee` with that user's identifier
- THEN the response status is 200
- AND the task's assignee is now `assignee@example.com`

#### Scenario: Assigning to a nonexistent user is rejected

- GIVEN the authenticated user owns list `L1` containing task `T1`
- AND no registered user matches the identifier `ghost@example.com`
- WHEN the owner sends `PATCH /lists/L1/tasks/T1/assignee` with `ghost@example.com`
- THEN the response status is 422

#### Scenario: Non-owner cannot assign

- GIVEN list `L1` and task `T1` are owned by user A
- WHEN user B (not the owner) sends `PATCH /lists/L1/tasks/T1/assignee`
- THEN the response status is 404

#### Scenario: Unauthenticated assignment is rejected

- WHEN an unauthenticated client sends `PATCH /lists/{list_id}/tasks/{task_id}/assignee`
- THEN the response status is 401

### Requirement: Unassign a Task

The system MUST allow the list owner to clear a task's assignee (set it back to none) via the same endpoint used for assignment.

#### Scenario: Owner unassigns a previously assigned task

- GIVEN task `T1` in list `L1` (owned by the requester) is currently assigned to `assignee@example.com`
- WHEN the owner sends `PATCH /lists/L1/tasks/T1/assignee` with a null/empty assignee
- THEN the response status is 200
- AND the task's assignee is now none

### Requirement: Fake Invitation Notification on Assignment

The system MUST trigger a fake email invitation through a notification port whenever a task is assigned to a user, delivered asynchronously (not blocking the HTTP response), and MUST NOT send a real email.

#### Scenario: Assignment triggers a background notification

- GIVEN the authenticated owner assigns task `T1` to `assignee@example.com`
- WHEN the assignment request completes
- THEN the HTTP response is returned without waiting for the notification to finish
- AND a fake invitation notification for `assignee@example.com` is recorded (e.g. logged) as a result of the assignment

#### Scenario: Unassignment does not trigger an invitation

- GIVEN task `T1` is currently assigned to `assignee@example.com`
- WHEN the owner clears the assignee
- THEN no new invitation notification is triggered

#### Scenario: Reassignment triggers a new notification to the new assignee

- GIVEN task `T1` is currently assigned to `old@example.com`
- WHEN the owner reassigns it to `new@example.com`
- THEN a fake invitation notification for `new@example.com` is recorded

### Requirement: Assignee Visibility Scoped to Their Own Assigned Tasks

The system MUST expose `GET /users/me/tasks` returning only the tasks currently assigned to the authenticated requester, across all lists, regardless of who owns each list. A non-owner who is not the assignee of a given task MUST NOT see that task through this or any other endpoint.

#### Scenario: Assignee retrieves only their assigned tasks

- GIVEN task `T1` (in list `L1`, owned by user A) is assigned to user B
- AND task `T2` (in list `L2`, owned by user A) is not assigned to user B
- WHEN user B sends `GET /users/me/tasks`
- THEN the response includes `T1`
- AND the response does not include `T2`

#### Scenario: Owner is not implicitly an assignee

- GIVEN the authenticated user owns list `L1` containing task `T1`, which is assigned to a different user
- WHEN the owner sends `GET /users/me/tasks`
- THEN `T1` does not appear in the owner's own `GET /users/me/tasks` response (it was not assigned to them)

#### Scenario: User with no assigned tasks gets an empty result

- GIVEN the authenticated user has no tasks assigned to them
- WHEN they send `GET /users/me/tasks`
- THEN the response status is 200
- AND the returned collection is empty

#### Scenario: Unauthenticated access is rejected

- WHEN an unauthenticated client sends `GET /users/me/tasks`
- THEN the response status is 401

### Requirement: Assignee May Change Status of Their Assigned Tasks Only

The system MUST allow a non-owner assignee to change the status of a task assigned to them via `PATCH /lists/{list_id}/tasks/{task_id}/status`, using the same state machine rules as the owner. The system MUST NOT allow that assignee to edit (`PATCH` on the task itself), delete, reassign, or view other fields/tasks of the containing list beyond the assigned task via any other endpoint.

#### Scenario: Assignee changes status of their assigned task

- GIVEN task `T1` (in list `L1`, owned by user A) is assigned to user B and has `status = "pending"`
- WHEN user B sends `PATCH /lists/L1/tasks/T1/status` with `status = "in_progress"`
- THEN the response status is 200
- AND the task's status is now `"in_progress"`

#### Scenario: Assignee cannot edit the assigned task's other fields

- GIVEN task `T1` (in list `L1`, owned by user A) is assigned to user B
- WHEN user B sends `PATCH /lists/L1/tasks/T1` with `title = "Hijacked"`
- THEN the response status is 404

#### Scenario: Assignee cannot delete the assigned task

- GIVEN task `T1` (in list `L1`, owned by user A) is assigned to user B
- WHEN user B sends `DELETE /lists/L1/tasks/T1`
- THEN the response status is 404

#### Scenario: Assignee cannot reassign the task

- GIVEN task `T1` (in list `L1`, owned by user A) is assigned to user B
- WHEN user B sends `PATCH /lists/L1/tasks/T1/assignee`
- THEN the response status is 404

#### Scenario: Assignee cannot see the rest of the owner's list

- GIVEN task `T1` (in list `L1`, owned by user A) is assigned to user B, and `L1` also contains task `T2` not assigned to user B
- WHEN user B sends `GET /lists/L1` or `GET /lists/L1/tasks`
- THEN the response status is 404

#### Scenario: Stranger (neither owner nor assignee) gets 404 everywhere

- GIVEN task `T1` (in list `L1`, owned by user A) is not assigned to user C
- WHEN user C sends `GET`, `PATCH`, or `DELETE` on `/lists/L1`, `/lists/L1/tasks`, or `/lists/L1/tasks/T1` (including the `/status` and `/assignee` sub-resources)
- THEN the response status is 404 in every case
- AND no response reveals whether `L1` or `T1` exists

#### Scenario: Unauthenticated status change by a would-be assignee is rejected

- WHEN an unauthenticated client sends `PATCH /lists/{list_id}/tasks/{task_id}/status`
- THEN the response status is 401
