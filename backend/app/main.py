"""FastAPI application entry point. Run with `uv run uvicorn app.main:app --reload`."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import acreate_client

from app.agents.liaison import Liaison
from app.agents.watch_service import WatchService
from app.core.app_constants import API_PREFIX, CORS_ALLOW_HEADERS, CORS_ALLOW_METHODS, NIGHT_WATCH_TICK_S
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
    app.state.night_watch = WatchService(Liaison.from_api_key(settings.anthropic_api_key))
    ticker = asyncio.create_task(_tick_night_watch(app)) if app.state.supabase is not None else None
    yield
    if ticker is not None:
        ticker.cancel()


async def _tick_night_watch(app: FastAPI) -> None:
    """Run Night Watch's timers even when no pillow reports (unplugged board, silent check-in)."""
    while True:
        await asyncio.sleep(NIGHT_WATCH_TICK_S)
        await app.state.night_watch.tick_all(app.state.supabase)


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
