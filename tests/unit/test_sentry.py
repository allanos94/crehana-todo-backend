"""Optional Sentry integration (security-hardening spec: optional
error-tracking integration, both scenarios). Verified via a monkeypatched
`sentry_sdk.init` call-spy -- never a real network call.
"""

from collections.abc import Iterator

import pytest
import sentry_sdk

from app.infrastructure.config import get_settings
from app.infrastructure.observability.sentry import init_sentry


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sentry_init_is_skipped_when_dsn_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    get_settings.cache_clear()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda *a, **kw: calls.append(kw) or None)

    init_sentry()

    assert calls == []


def test_sentry_init_called_with_send_default_pii_false_when_dsn_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://examplekey@o0.ingest.sentry.io/0")
    get_settings.cache_clear()
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda *a, **kw: calls.append(kw) or None)

    init_sentry()

    assert len(calls) == 1
    assert calls[0]["send_default_pii"] is False
    assert calls[0]["dsn"] == "https://examplekey@o0.ingest.sentry.io/0"
