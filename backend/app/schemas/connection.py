"""Schemas for the connection-test router."""

from pydantic import BaseModel


class ConnectionTestResponse(BaseModel):
    """Proof that a client reached the backend, echoing what the server saw."""

    message: str
    host: str
    server_time: str
