"""Aggregates every feature router into a single `api_router`."""

from fastapi import APIRouter

from app.routers import commands, connection, contacts, health, items, pillows

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(items.router)
api_router.include_router(connection.router)
api_router.include_router(pillows.router)
api_router.include_router(commands.router)
api_router.include_router(contacts.router)
