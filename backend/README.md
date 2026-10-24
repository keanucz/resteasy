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
uv run pytest        # tests (the Supabase ones skip unless SUPABASE_URL / SUPABASE_SECRET_KEY are set)
uv run ruff check .  # lint
```

## Endpoints

| Method | Path | Who calls it |
|---|---|---|
| `POST` | `/api/pillows/{pillow_id}/state` | device, about 2/s (`coord/CONTRACT.md` section 1) |
| `GET` | `/api/pillows/{pillow_id}/commands?after=N` | device, every 500 ms (section 3) |
| `POST` | `/api/pillows/{pillow_id}/commands` | app / agents: queue `set_light`, `vibrate`, ... |
| `GET` | `/api/pillows/{pillow_id}` and `/state` | app: the pillow and its live status card |
| `GET` | `/api/contacts/{contact_id}/pillows` | app: pillows of every resident a carer looks after |

Unknown pillows get 404; a server without Supabase credentials answers 503 on these routes.

## Supabase

- `supabase/migrations/` - the schema (tables, `night_trips` view, RLS, Realtime publication).
- `supabase/seed.sql` - demo household (Margaret, pillow `mum`, carer Sarah) and the test household
  ("Test User" owns the hypothetical pillow `test-pillow`). Re-runnable. The live tests only ever touch
  `test-pillow`, never the real device.
- Apply both with the Supabase MCP (`apply_migration`, then `execute_sql` with the seed) or paste them
  into Dashboard > SQL Editor, migration first.
- Check the schema offline on a throwaway Postgres (Python 3.12):
  `uvx --python 3.12 --with pgserver python supabase/check_schema.py`

## Layout

```
app/
├── main.py            create_app(): middleware + mounts api_router under /api
├── core/              config (Settings from .env), app_constants, shared dependencies
│                      (the Supabase client and the "pillow exists or 404" check)
├── routers/           one file per resource; __init__.py aggregates them into api_router
│   ├── health.py      dumb router: GET /api/ and GET /api/health
│   └── items.py       example CRUD resource - copy this for new resources
├── schemas/           Pydantic request/response models, one file per resource
├── crud/              data access; base.py is a generic in-memory store, the rest query Supabase
└── utils/             wrappers for third-party services + their constants
tests/                 pytest; seed_constants.py holds the seeded test ids
supabase/              migrations, seed.sql, offline schema check
```

## Adding a resource

1. `schemas/<thing>.py` - `ThingCreate`, `ThingUpdate`, `Thing`.
2. `crud/<thing>.py` - `thing_crud = InMemoryCRUD[Thing, ThingCreate, ThingUpdate](Thing)`.
3. `routers/<thing>.py` - copy `items.py`.
4. Register it in `routers/__init__.py`.

Swap `InMemoryCRUD` for a database-backed class with the same methods when you need persistence.
