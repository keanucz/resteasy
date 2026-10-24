"""FastAPI application entry point. Run with `uv run uvicorn app.main:app --reload`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.app_constants import API_PREFIX, CORS_ALLOW_HEADERS, CORS_ALLOW_METHODS
from app.core.config import get_settings
from app.routers import api_router


def create_app() -> FastAPI:
    """Build the FastAPI app with middleware and every router mounted."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
