"""Security response headers middleware (security-hardening spec: security
response headers).

`X-Frame-Options: DENY` is used instead of a `Content-Security-Policy` frame
directive: a strict CSP would also need to allow inline scripts/styles for
Swagger UI at `/docs` to keep rendering, and `X-Frame-Options` alone already
satisfies the spec's "or an equivalent CSP frame directive" clause without
that extra complexity (documented in `DECISION_LOG.md`).
"""

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

_Call = Callable[[Request], Awaitable[Response]]


def _is_https(request: Request) -> bool:
    """True when the request itself is HTTPS, or a trusted reverse proxy
    says so via `X-Forwarded-Proto` (common behind load balancers/ingress).
    """
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


async def security_headers_middleware(request: Request, call_next: _Call) -> Response:
    """Attach standard security-related headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if _is_https(request):
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
    return response
