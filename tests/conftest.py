"""Shared pytest configuration.

Keeps the suite hermetic: settings must come from defaults, environment
variables set by tests, or fixtures, never from a developer's local `.env`.
"""

from app.infrastructure.config import Settings, get_settings

Settings.model_config["env_file"] = None
get_settings.cache_clear()
