# User Authentication Specification

## Purpose

Self-service registration and login for `User` accounts, issuance and validation of JWT access and refresh tokens, and the authenticated-identity dependency that every protected endpoint in other capabilities relies on.

## Requirements

### Requirement: User Registration

The system MUST allow a new user to self-register with an email and a password, MUST enforce a password policy of 8–128 characters containing at least one letter and at least one digit, MUST store only a hashed password (never the plaintext), and MUST reject registration with an email that already belongs to an existing user with 409 Conflict.

#### Scenario: Successful registration

- GIVEN no user exists with the email `new@example.com`
- WHEN a client sends `POST /auth/register` with a valid email and a password meeting the policy (e.g. `Passw0rd1`)
- THEN the response status is 201 (or 200, per the chosen convention) and a user resource is created
- AND the stored password is a hash, never the plaintext value submitted

#### Scenario: Duplicate email is rejected

- GIVEN a user already exists with the email `taken@example.com`
- WHEN a client sends `POST /auth/register` with email `taken@example.com` (any case) and a valid password
- THEN the response status is 409
- AND the error body follows the standard `{code, message}` contract

#### Scenario: Password too short is rejected

- WHEN a client sends `POST /auth/register` with a password shorter than 8 characters
- THEN the response status is 422

#### Scenario: Password too long is rejected

- WHEN a client sends `POST /auth/register` with a password longer than 128 characters
- THEN the response status is 422

#### Scenario: Password missing a digit is rejected

- WHEN a client sends `POST /auth/register` with a password containing only letters (e.g. `OnlyLetters`)
- THEN the response status is 422

#### Scenario: Password missing a letter is rejected

- WHEN a client sends `POST /auth/register` with a password containing only digits (e.g. `12345678`)
- THEN the response status is 422

### Requirement: Login Without Account Enumeration

The system MUST authenticate a user by email and password and, on success, MUST return a new access token and a new refresh token. On failure (unknown email OR wrong password), the system MUST return 401 with a single generic error message that does not reveal whether the email exists.

#### Scenario: Successful login

- GIVEN a registered user with email `user@example.com` and a known password
- WHEN a client sends `POST /auth/login` with that email and the correct password
- THEN the response status is 200
- AND the response includes a valid access token and a valid refresh token

#### Scenario: Wrong password does not reveal account existence

- GIVEN a registered user with email `user@example.com`
- WHEN a client sends `POST /auth/login` with that email and an incorrect password
- THEN the response status is 401
- AND the error message is identical in wording to the unknown-email case

#### Scenario: Unknown email does not reveal account non-existence

- GIVEN no user exists with the email `ghost@example.com`
- WHEN a client sends `POST /auth/login` with that email and any password
- THEN the response status is 401
- AND the error message is identical in wording to the wrong-password case

### Requirement: JWT Access and Refresh Tokens with Type Enforcement

The system MUST issue access tokens with a 15-minute expiry and refresh tokens with a 7-day expiry, each carrying a `type` claim (`access` or `refresh`) identifying its kind. The system MUST reject a refresh token presented where an access token is required, MUST reject an access token presented where a refresh token is required, and MUST reject an expired token, in all cases with 401.

#### Scenario: Access token expiry

- GIVEN an access token was issued at time T
- WHEN the token's `exp` claim is inspected
- THEN it corresponds to T + 15 minutes

#### Scenario: Refresh token expiry

- GIVEN a refresh token was issued at time T
- WHEN the token's `exp` claim is inspected
- THEN it corresponds to T + 7 days

#### Scenario: Refresh token rejected as an access token

- GIVEN a valid, unexpired refresh token
- WHEN a client presents it as the bearer token on a protected endpoint that requires an access token
- THEN the response status is 401

#### Scenario: Access token rejected as a refresh token

- GIVEN a valid, unexpired access token
- WHEN a client presents it to `POST /auth/refresh`, which requires a refresh token
- THEN the response status is 401

#### Scenario: Expired access token is rejected

- GIVEN an access token whose `exp` claim is in the past
- WHEN a client presents it on a protected endpoint
- THEN the response status is 401

#### Scenario: Expired refresh token is rejected

- GIVEN a refresh token whose `exp` claim is in the past
- WHEN a client presents it to `POST /auth/refresh`
- THEN the response status is 401

### Requirement: Token Refresh

The system MUST allow a client holding a valid, unexpired refresh token to obtain a new access token via `POST /auth/refresh`.

#### Scenario: Successful refresh

- GIVEN a valid, unexpired refresh token for an existing user
- WHEN a client sends `POST /auth/refresh` with that refresh token
- THEN the response status is 200
- AND the response includes a new valid access token with a `type` claim of `access`

### Requirement: Authenticated Identity Lookup

The system MUST expose `GET /users/me` returning the identity of the user associated with a valid access token, and MUST return 401 when no valid access token is presented.

#### Scenario: Authenticated user retrieves their own identity

- GIVEN a valid, unexpired access token for user `user@example.com`
- WHEN a client sends `GET /users/me` with that token
- THEN the response status is 200
- AND the response body identifies `user@example.com` as the authenticated user

#### Scenario: Unauthenticated request is rejected

- WHEN a client sends `GET /users/me` without an `Authorization` header
- THEN the response status is 401

#### Scenario: Invalid token is rejected

- WHEN a client sends `GET /users/me` with a malformed or tampered token
- THEN the response status is 401
