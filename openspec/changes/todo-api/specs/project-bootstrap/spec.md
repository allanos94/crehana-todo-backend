# Project Bootstrap Specification

## Purpose

Establish the runnable skeleton, configuration, health endpoint, containerized runtime, and automated quality/coverage gates that every other capability in `todo-api` builds on. This spec covers verifiable, testable requirements only; it does not prescribe internal module layout beyond what is externally observable (e.g. command exit codes, HTTP responses).

## Requirements

### Requirement: Health Check Endpoint

The system MUST expose an unauthenticated `GET /health` endpoint that reports the application is running and able to serve requests.

#### Scenario: Health endpoint returns OK when the app is running

- GIVEN the application is started and listening
- WHEN a client sends `GET /health`
- THEN the response status is 200
- AND the response body indicates a healthy status

#### Scenario: Health endpoint requires no authentication

- GIVEN the application is started
- WHEN a client sends `GET /health` without an `Authorization` header
- THEN the response status is 200 (not 401)

### Requirement: Readiness Check Endpoint

The system MUST expose an unauthenticated `GET /health/ready` endpoint that reports
whether the application can currently serve requests that depend on the database,
by executing a trivial query (`SELECT 1`) against it.

#### Scenario: Readiness endpoint returns OK when the database is reachable

- GIVEN the application is started and the database is reachable
- WHEN a client sends `GET /health/ready`
- THEN the response status is 200
- AND the response body indicates a healthy status

#### Scenario: Readiness endpoint fails when the database is unreachable

- GIVEN the application is started and the database is NOT reachable
- WHEN a client sends `GET /health/ready`
- THEN the response status is 503
- AND the response body indicates an unhealthy status

### Requirement: Containerized Runtime

The system MUST provide a multistage Dockerfile that builds a runnable image and a docker-compose definition that starts the API alongside a PostgreSQL 16 database, with database migrations applied automatically on container start.

#### Scenario: Compose stack starts successfully

- GIVEN a host with Docker and docker-compose available
- WHEN the operator runs `docker compose up --build`
- THEN the API container and the PostgreSQL container both reach a running/healthy state
- AND `GET /health` on the API container returns 200

#### Scenario: Database schema is current on container start

- GIVEN the compose stack is starting for the first time (empty database volume)
- WHEN the API container starts
- THEN pending database migrations are applied before the API begins serving traffic
- AND subsequent API requests that depend on the schema succeed without manual migration steps

#### Scenario: Image runs as a non-root user

- GIVEN the built Docker image
- WHEN the container is inspected for its runtime user
- THEN the process MUST NOT run as root

### Requirement: Code Quality Gates

The system MUST provide configuration such that `flake8`, `black --check`, `isort --check`, and `mypy --strict` each run as standalone commands and exit with status 0 against a conformant codebase, and MUST fail (non-zero exit) when the codebase violates the corresponding rule set.

#### Scenario: Quality gates pass on a conformant codebase

- GIVEN the repository is in a state that conforms to its own lint, format, import-order, and type-checking configuration
- WHEN `flake8`, `black --check`, `isort --check`, and `mypy --strict` are each run
- THEN each command exits with status 0

#### Scenario: Quality gate fails on a violation

- GIVEN a source file that violates one of the configured rule sets (e.g. an unused import, a type error, or a formatting difference)
- WHEN the corresponding command (`flake8`, `black --check`, `isort --check`, or `mypy --strict`) is run
- THEN that command exits with a non-zero status
- AND identifies the offending file and rule

### Requirement: Automated Test Execution and Coverage Gate

The system MUST provide a test configuration such that `uv run pytest` executes the full unit and integration test suite and fails the run when combined line coverage is below 75%.

#### Scenario: Test suite passes with sufficient coverage

- GIVEN a codebase where all tests pass and combined coverage is at or above 75%
- WHEN `uv run pytest` is run
- THEN the command exits with status 0
- AND reports the measured coverage percentage

#### Scenario: Coverage gate fails below threshold

- GIVEN a codebase where all tests pass but combined coverage is below 75%
- WHEN `uv run pytest` is run
- THEN the command exits with a non-zero status
- AND the output indicates the coverage threshold was not met

#### Scenario: A failing test fails the run

- GIVEN a codebase containing at least one failing test
- WHEN `uv run pytest` is run
- THEN the command exits with a non-zero status
- AND identifies the failing test(s)

### Requirement: Continuous Integration Quality Gate

The system MUST run the code quality gates, the test suite, and the coverage gate automatically on CI for every pushed change, and MUST report failure when any gate fails.

#### Scenario: CI fails when any gate fails

- GIVEN a pushed commit that fails at least one of lint, format, import-order, type-check, tests, or coverage
- WHEN the CI workflow runs
- THEN the CI run reports a failed status
- AND identifies which gate(s) failed

#### Scenario: CI succeeds when all gates pass

- GIVEN a pushed commit that passes lint, format, import-order, type-check, tests, and coverage
- WHEN the CI workflow runs
- THEN the CI run reports a successful status
