"""Application composition root: the `create_app()` factory and its lifespan."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infrastructure.api.routers.health import router as health_router
from app.infrastructure.config import get_settings
from app.infrastructure.db.session import create_engine, create_session_factory


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
    app = FastAPI(title="Todo Lists API", lifespan=lifespan)
    app.include_router(health_router)
    return app


app = create_app()
