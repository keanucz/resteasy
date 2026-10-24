"""Dumb HTTP router: hello world and liveness checks with no dependencies."""

from fastapi import APIRouter

from app.core.app_constants import HELLO_MESSAGE
from app.core.config import get_settings
from app.schemas.health import HealthResponse, MessageResponse

router = APIRouter(tags=["health"])


@router.get("/")
async def hello() -> MessageResponse:
    """Say hello so clients can confirm they reached the API."""
    return MessageResponse(message=HELLO_MESSAGE)


@router.get("/health")
async def health() -> HealthResponse:
    """Report that the server is up."""
    return HealthResponse(status="ok", environment=get_settings().environment)
