"""App-wide constants that are not environment specific."""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"

DEFAULT_APP_NAME = "Pillow API"
DEFAULT_ENVIRONMENT = "development"
DEFAULT_CORS_ORIGINS = ["*"]

# HTTP methods the CORS middleware allows; tighten to e.g. ["GET", "POST"] for production
CORS_ALLOW_METHODS = ["*"]
# Request headers the CORS middleware allows; tighten for production
CORS_ALLOW_HEADERS = ["*"]

# Message returned by the root endpoint to confirm the API was reached
HELLO_MESSAGE = "Hello World"

API_PREFIX = "/api"

# Message returned by GET /api/test so the app can show it reached the backend
CONNECTION_TEST_MESSAGE = "Frontend reached the backend"

# Detail returned with a 503 when SUPABASE_URL / SUPABASE_SECRET_KEY are not set
SUPABASE_NOT_CONFIGURED = "Supabase is not configured on this server"

# Seconds between Night Watch timer runs when no pillow reports
NIGHT_WATCH_TICK_S = 5

# Seconds between runs of the reminder schedule (the Routine agent)
REMINDERS_TICK_S = 15

# Detail returned with a 503 when CHECKIN_TOKEN is not set (POST /checkin fails closed)
CHECKIN_TOKEN_NOT_CONFIGURED = "CHECKIN_TOKEN is not configured on this server"
