# Backend

FastAPI server for the pillow: device contract (`coord/CONTRACT.md`), calibration, alerts and the
family app API. Managed with [uv](https://docs.astral.sh/uv/).

## Run

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` lets a phone (or a pillow) on the same Wi-Fi reach the API. Docs: http://localhost:8000/docs

```bash
uv run pytest        # tests
uv run ruff check .  # lint
```

## Layout

```
app/
├── main.py            create_app(): middleware + mounts api_router under /api
├── core/              config (Settings from .env), app_constants, shared dependencies
├── routers/           one file per resource; __init__.py aggregates them into api_router
│   ├── health.py      dumb router: GET /api/ and GET /api/health
│   └── items.py       example CRUD resource - copy this for new resources
├── schemas/           Pydantic request/response models, one file per resource
├── crud/              data access; base.py is a generic store, one instance per resource
└── utils/             wrappers for third-party services + their constants
tests/                 pytest
```

## Adding a resource

1. `schemas/<thing>.py` - `ThingCreate`, `ThingUpdate`, `Thing`.
2. `crud/<thing>.py` - `thing_crud = InMemoryCRUD[Thing, ThingCreate, ThingUpdate](Thing)`.
3. `routers/<thing>.py` - copy `items.py`.
4. Register it in `routers/__init__.py`.

Swap `InMemoryCRUD` for a database-backed class with the same methods when you need persistence.
