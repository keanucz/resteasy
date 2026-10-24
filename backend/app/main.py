"""FastAPI application entry point. Run with `uv run uvicorn app.main:app --reload`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import acreate_client

from app.agents.watch_service import WatchService
from app.core.app_constants import API_PREFIX, CORS_ALLOW_HEADERS, CORS_ALLOW_METHODS
from app.core.config import get_settings
from app.routers import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open one Supabase client for the whole process; None when credentials are missing."""
    settings = get_settings()
    app.state.supabase = (
        await acreate_client(settings.supabase_url, settings.supabase_secret_key)
        if settings.supabase_configured
        else None
    )
    app.state.night_watch = WatchService()
    yield


def create_app() -> FastAPI:
    """Build the FastAPI app with middleware and every router mounted."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
