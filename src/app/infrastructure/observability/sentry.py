"""Optional Sentry error-tracking integration (security-hardening spec:
optional error-tracking integration), gated entirely on `Settings.sentry_dsn`.

The FastAPI integration auto-enables itself inside `sentry_sdk` whenever
`fastapi` is importable, so nothing beyond `sentry_sdk.init(...)` is needed
here. `send_default_pii=False` is mandatory per spec: no personally
identifiable information is sent to the third-party service even when
tracking is enabled.
"""

import sentry_sdk

from app.infrastructure.config import get_settings


def init_sentry() -> None:
    """Initialize Sentry as early as possible in the process, only when a
    DSN is configured. A no-op (no import side effect, no network call,
    nothing sent anywhere) when `SENTRY_DSN` is unset.
    """
    settings = get_settings()
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
    )
