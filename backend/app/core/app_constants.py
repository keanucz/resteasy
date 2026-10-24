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
