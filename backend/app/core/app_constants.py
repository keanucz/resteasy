"""App-wide constants that are not environment specific."""

from datetime import time, timedelta
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

# Seconds between runs of the notifications sender (app/notify)
NOTIFY_TICK_S = 5

# The one real pillow whose alerts go to real phones (NOTIFY_PILLOW_IDS overrides)
DEFAULT_NOTIFY_PILLOW_IDS = ["mum"]

# Detail returned with a 503 when CHECKIN_TOKEN is not set (POST /checkin fails closed)
CHECKIN_TOKEN_NOT_CONFIGURED = "CHECKIN_TOKEN is not configured on this server"

# Details returned when an app request has no valid Supabase login, or isn't the resident's owner
NOT_SIGNED_IN = "Sign in to the app first"
NOT_OWNER = "Only the owner can change these settings"
NOT_LINKED = "This login does not look after them"

# resident_contacts.role of the one login that may change a resident's settings
OWNER_ROLE = "owner"

# agent_log.agent for changes made from the family app, so the app's live log can say who did it
FAMILY_APP_AGENT = "family_app"
# agent_log.agent for the Fetch.ai family agents, which act with the agent token (CHECKIN_TOKEN)
FAMILY_AGENT = "family_agent"
# Details returned when the agent token changes a reminder without naming a contact of hers
AGENT_CONTACT_MISSING = "Say which contact the agent acts for: the contact_id query parameter"
AGENT_CONTACT_NOT_LINKED = "This contact does not look after them"
# agent_log.tool for a reminder the family agent set up, changed or deleted
REMINDERS_TOOL = "reminders"
# agent_log.intent for a settings change made from the family app
SETTINGS_CHANGE_INTENT = "change settings"

# Profile photos the API accepts, the same limits as the resident-photos bucket
PHOTO_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_WRONG_TYPE = "The photo must be a JPEG, PNG or WebP image"
PHOTO_EMPTY = "The photo file is empty"
PHOTO_TOO_LARGE = "The photo must be 5 MB or smaller"

# Reminders (the Routine agent). What an occurrence is for: say the reminder, or ask her consent
REMIND_PURPOSE = "remind"
CONSENT_PURPOSE = "consent"
# reminders.consent: nothing plays until she agrees, asked by the pillow itself
CONSENT_PENDING = "pending"
CONSENT_AGREED = "agreed"
CONSENT_DECLINED = "declined"
# Changing any of these asks her again: she agrees to what is said and when
CONSENT_RESET_FIELDS = frozenset({"label", "kind", "time_of_day", "days", "on_date"})
# When the pillow asks about a pending reminder, in her timezone: from 09:00 for 12 hours (never at
# night), held like any reminder until she is up for the day, again an hour after no answer
CONSENT_ASK_AT = time(9, 0)
CONSENT_ASK_WINDOW = timedelta(hours=12)
CONSENT_RETRY_AFTER = timedelta(hours=1)
# Who asks, when the family member who set the reminder up is unknown
FAMILY_FALLBACK_NAME = "Your family"
# Longest range GET /reminders/calendar expands, in days (two months)
CALENDAR_MAX_DAYS = 62
# Spoken names, independent of the server's locale (ISO weekday 1 = Monday)
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
