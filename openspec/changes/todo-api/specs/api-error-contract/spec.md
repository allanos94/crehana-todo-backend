# API Error Contract Specification

## Purpose

A single, consistent error response shape across the entire API, driven by a domain exception hierarchy mapped to HTTP status codes, so that no endpoint leaks internal details and every client can parse errors uniformly.

## Requirements

### Requirement: Consistent Error Body Shape

The system MUST return every 4xx error response produced by a mapped domain or validation exception as a JSON body containing at minimum `code` (a stable machine-readable string identifying the error kind) and `message` (a human-readable description). The system MAY include an additional `details` field for 422 responses carrying field-level validation information.

#### Scenario: 404 error follows the contract

- GIVEN a request for a resource that does not exist or does not belong to the requester
- WHEN the system returns a 404 response
- THEN the response body contains `code` and `message` fields
- AND the body contains no other top-level fields beyond `code`, `message`, and the optional `details`

#### Scenario: 409 error follows the contract

- GIVEN a request that violates a uniqueness or state constraint (e.g. duplicate list name, invalid status transition)
- WHEN the system returns a 409 response
- THEN the response body contains `code` and `message` fields

#### Scenario: 422 error follows the contract with details

- GIVEN a request with an invalid field value (e.g. a `due_date` in the past, or a name exceeding its length limit)
- WHEN the system returns a 422 response
- THEN the response body contains `code` and `message` fields
- AND the response body MAY include a `details` field describing which field(s) failed and why

#### Scenario: 401 error follows the contract

- GIVEN a request with no, invalid, or expired authentication credentials
- WHEN the system returns a 401 response
- THEN the response body contains `code` and `message` fields

### Requirement: No Internal Detail Leakage

The system MUST NOT include stack traces, internal exception class names, file paths, SQL text, or other implementation details in any error response body, regardless of status code.

#### Scenario: Unhandled server error does not leak internals

- GIVEN an unexpected server-side failure occurs while processing a request
- WHEN the system returns a 5xx response
- THEN the response body contains only the standard `{code, message}` shape
- AND the response body contains no stack trace, exception class name, or file path

#### Scenario: Database constraint violation is translated, not leaked

- GIVEN a request triggers a lower-level database constraint violation that maps to a domain error (e.g. a race on list-name uniqueness)
- WHEN the system returns the corresponding error response
- THEN the response body contains only the standard `{code, message}` shape
- AND the response body contains no raw database error text or SQL

### Requirement: Domain Exception Hierarchy Mapping

The system MUST map each domain exception type to exactly one HTTP status code among 401, 404, 409, and 422, consistently across all endpoints that can raise it.

#### Scenario: The same domain exception maps to the same status everywhere

- GIVEN a domain exception type (e.g. a "resource not found" exception) is raised by two different use cases (e.g. task-list lookup and task lookup)
- WHEN each use case's failure is translated to an HTTP response
- THEN both responses use the same HTTP status code for that exception type
