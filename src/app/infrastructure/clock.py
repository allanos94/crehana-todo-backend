"""`SystemClock`: the real wall-clock `Clock` adapter, always UTC."""

from datetime import UTC, date, datetime


class SystemClock:
    """Reads real time. Keeps all app-level `now()`/`today()` calls in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return self.now().date()
