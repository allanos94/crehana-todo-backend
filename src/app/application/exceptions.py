"""Authentication errors (design ADR-03). Not a domain concept — authentication
is an application/infrastructure boundary concern, so this lives outside
`domain/exceptions.py` even though it subclasses `AppError`.
"""

from app.domain.exceptions import AppError


class AuthenticationError(AppError):
    """Base class for authentication failures (401)."""


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"

    def __init__(self) -> None:
        super().__init__("Invalid or expired token")


class NotAuthenticatedError(AuthenticationError):
    code = "not_authenticated"

    def __init__(self) -> None:
        super().__init__("Authentication required")
