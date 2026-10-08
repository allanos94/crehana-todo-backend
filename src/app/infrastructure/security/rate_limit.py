"""Rate limiting on authentication endpoints (security-hardening spec: rate
limiting), built on `slowapi`.

The module-level `limiter` is intentionally a singleton: `slowapi`'s
`@limiter.limit(...)` decorator is applied once, at import time, to the
route functions it protects. Enablement and the limit string stay
configurable at runtime through `Settings` (`rate_limit_enabled`,
`auth_rate_limit`) rather than baked in at import time, so tests can toggle
`limiter.enabled` directly and call `limiter.reset()` to clear counters
between runs without re-importing the module.
"""

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.infrastructure.config import get_settings

limiter = Limiter(
    key_func=get_remote_address, enabled=get_settings().rate_limit_enabled
)


def auth_rate_limit() -> str:
    """Read the configured auth rate limit lazily, on every check, so
    tests that monkeypatch `Settings`/env can change it without having to
    reconstruct the `Limiter` instance."""
    return get_settings().auth_rate_limit


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return our uniform error contract instead of slowapi's default body.

    `exc` is typed as the broad `Exception` to match
    `Starlette.add_exception_handler`'s signature; it is always a
    `RateLimitExceeded` at runtime because it is only ever registered for
    that exact exception type.
    """
    headers: dict[str, str] | None = None
    if isinstance(exc, RateLimitExceeded) and exc.limit is not None:
        headers = {"Retry-After": str(exc.limit.limit.get_expiry())}
    return JSONResponse(
        status_code=429,
        content={
            "code": "rate_limited",
            "message": "Too many requests. Please try again later.",
        },
        headers=headers,
    )
