"""Router the app calls to prove it can reach the backend (directly or through a tunnel)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from app.core.app_constants import CONNECTION_TEST_MESSAGE
from app.schemas.connection import ConnectionTestResponse

router = APIRouter(tags=["connection"])


@router.get("/test")
async def connection_test(request: Request) -> ConnectionTestResponse:
    """Confirm the request arrived, and report the host it was addressed to (e.g. the tunnel)."""
    return ConnectionTestResponse(
        message=CONNECTION_TEST_MESSAGE,
        host=request.headers.get("host", ""),
        server_time=datetime.now(UTC).isoformat(timespec="seconds"),
    )
