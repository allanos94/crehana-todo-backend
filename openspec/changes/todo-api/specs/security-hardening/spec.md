# Security Hardening Specification

## Purpose

Defense-in-depth controls layered on top of the core API: rate limiting on authentication endpoints, security response headers, a strict CORS policy, and automated CI security scanning. Per the proposal's cut order, this capability is the first candidate to cut under time pressure; its requirements are therefore expressed with SHOULD, not MUST, except where noted.

## Requirements

### Requirement: Rate Limiting on Authentication Endpoints

The system SHOULD limit the rate of requests to `/auth/register`, `/auth/login`, and `/auth/refresh` per client (e.g. per IP or per identifier), and SHOULD return 429 Too Many Requests once the limit is exceeded within the configured window.

#### Scenario: Requests within the limit succeed

- GIVEN a client that has not exceeded the configured request rate for `/auth/login`
- WHEN they send a login request
- THEN the request is processed normally (200 on success, 401 on bad credentials)

#### Scenario: Requests exceeding the limit are throttled

- GIVEN a client that has exceeded the configured request rate for `/auth/login` within the configured window
- WHEN they send another login request
- THEN the response status is 429

### Requirement: Security Response Headers

The system SHOULD set standard security-related HTTP response headers (at minimum `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` or an equivalent `Content-Security-Policy` frame directive, and `Strict-Transport-Security` when served over HTTPS) on API responses.

#### Scenario: Security headers are present on a typical response

- GIVEN the security-hardening slice is active
- WHEN a client sends any request to the API
- THEN the response includes the configured security headers

### Requirement: Strict CORS Policy

The system SHOULD restrict cross-origin requests to an explicit allow-list of origins rather than allowing all origins (`*`), and MUST NOT allow credentials-bearing requests from an unlisted origin.

#### Scenario: Allowed origin receives CORS headers

- GIVEN an origin present in the configured allow-list
- WHEN a browser sends a cross-origin request from that origin
- THEN the response includes CORS headers permitting that origin

#### Scenario: Disallowed origin does not receive permissive CORS headers

- GIVEN an origin absent from the configured allow-list
- WHEN a browser sends a cross-origin request from that origin
- THEN the response does not grant that origin access via CORS headers

### Requirement: CI Security Scanning

The system SHOULD run free-tier security scanners (at minimum `bandit`, `pip-audit`, `gitleaks`, and GitHub CodeQL/Dependabot) in CI on every pushed change, and SHOULD surface findings in the CI run output without blocking merges solely on scanner findings unless explicitly configured to do so.

#### Scenario: Scanners run on a pushed change

- GIVEN a pushed commit
- WHEN the CI workflow runs
- THEN the configured security scanners execute and their results are visible in the CI run output

### Requirement: Optional Error-Tracking Integration

The system MAY integrate an error-tracking service (e.g. Sentry), gated entirely on the presence of a `SENTRY_DSN` configuration value, and when enabled MUST configure the integration with `send_default_pii=False` so no personally identifiable information is sent to the third-party service.

#### Scenario: Error tracking is inactive without configuration

- GIVEN `SENTRY_DSN` is not set
- WHEN the application starts and an unhandled error occurs
- THEN no data is sent to the error-tracking service

#### Scenario: Error tracking excludes PII when enabled

- GIVEN `SENTRY_DSN` is set and the integration is enabled
- WHEN an unhandled error occurs during a request that includes user-identifying data
- THEN the error report sent to the service does not include default PII fields
