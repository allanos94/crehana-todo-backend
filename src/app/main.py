"""Application composition root: the `create_app()` factory and its lifespan."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from starlette.middleware.cors import CORSMiddleware

from app.infrastructure.api.errors import register_exception_handlers
from app.infrastructure.api.middleware import security_headers_middleware
from app.infrastructure.api.routers.auth import router as auth_router
from app.infrastructure.api.routers.health import router as health_router
from app.infrastructure.api.routers.task_lists import router as task_lists_router
from app.infrastructure.api.routers.tasks import router as tasks_router
from app.infrastructure.api.routers.users import router as users_router
from app.infrastructure.config import get_settings
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.security.rate_limit import limiter, rate_limit_exceeded_handler

# Python's root logger defaults to WARNING with no handler attached, which
# would silently drop `app.notifications`' INFO invitation lines (and
# `logger.exception` calls elsewhere) in a real running process -- unlike
# tests, where `caplog` attaches its own handler regardless. `basicConfig`
# is idempotent (a no-op once a handler already exists) and runs at import
# time, before uvicorn's own `dictConfig` (which only configures its own
# `uvicorn.*` loggers, not root, and explicitly sets
# `disable_existing_loggers=False`).
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage resources that live for the whole application process.

    Slice 6c adds optional Sentry initialization here.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        await engine.dispose()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    settings = get_settings()
    app = FastAPI(title="Todo Lists API", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(security_headers_middleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(task_lists_router)
    app.include_router(tasks_router)
    return app


app = create_app()
