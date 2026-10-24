"""Aggregates every feature router into a single `api_router`."""

from fastapi import APIRouter

from app.routers import (
    account,
    commands,
    connection,
    contacts,
    family,
    health,
    items,
    pillows,
    reminders,
    residents,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(items.router)
api_router.include_router(connection.router)
api_router.include_router(pillows.router)
api_router.include_router(commands.router)
api_router.include_router(contacts.router)
api_router.include_router(family.router)
api_router.include_router(reminders.router)
api_router.include_router(account.router)
api_router.include_router(residents.router)
