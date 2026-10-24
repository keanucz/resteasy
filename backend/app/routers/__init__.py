"""Aggregates every feature router into a single `api_router`."""

from fastapi import APIRouter

from app.routers import connection, health, items

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(items.router)
api_router.include_router(connection.router)
