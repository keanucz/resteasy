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
| `POST` | `/api/pillows/{pillow_id}/checkin` | base laptop (`voice/checkin_client.py`): the voice check-in's result; bearer `CHECKIN_TOKEN` |
| `POST` | `/api/pillows/{pillow_id}/ack` | app: "I'm on it" (`{"contact_id": uuid}`) |
| `GET` | `/api/pillows/{pillow_id}/night` | Morning Brief droid / family agent: last night's summary, events, agent log |
| `GET` `POST` | `/api/pillows/{pillow_id}/brief` | family agent reads the latest Morning Brief; the droid posts it (bearer); diff goes through the Guardian |
| `PATCH` | `/api/pillows/{pillow_id}/settings` | family agent: quiet hours / timeout, Guardian-bounded (bearer) |
| `GET` `POST` | `/api/pillows/{pillow_id}/goodnight` | family agent queues a goodnight message; the base laptop reads it and posts `/goodnight/played` (bearer) |

Unknown pillows get 404; a server without Supabase credentials answers 503 on these routes.

## Agents (`app/agents/`)

Every `POST /state` runs the pillow's agents in order; all settings come from `residents` and `contacts`.

| Module | Does | Settings |
|---|---|---|
| `night_watch.py` | state machine: lay_down, bed_exit, bed_return, no_return, path light, check-in, alert ladder | `residents.*`, `resident_contacts.priority` |
| `sleep_events.py` | restless / settled / asleep, key_talk / key_family (CONTRACT.md section 2) | fixed thresholds |
| `liaison.py` | Family Liaison: Claude (tools) words each alert for its channel and one line for her | `ANTHROPIC_API_KEY` in `.env` (empty = fixed text) |
| `guardian.py` | checks every command / line / alert: contract ranges, brightness <= 40 % at night, no medical claims, alert caps, SMS consent, config whitelist | `contacts.sms_consent`, `residents.step_wait_min` |
| `watch_service.py` | glues them to Supabase: events, commands, incidents, notifications, `agent_log` (with the Guardian's verdict) | |

`.env` keys: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `CHECKIN_TOKEN`, `ANTHROPIC_API_KEY`.

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
