"""Fixed values for the notifications sender."""

TWILIO_API = "https://api.twilio.com/2010-04-01"
TWILIO_VOICE = "Polly.Joanna"  # a clear US voice for the alert call
HTTP_TIMEOUT_S = 15

# Channels this sender delivers; "app" rows are the family app's to show
SENT_CHANNELS = ("sms", "call")

# A queued row older than this is never sent: a 3 a.m. alert must not arrive at noon because the
# sender was down or unconfigured. It stays "queued" in the table, untouched.
MAX_AGE_S = 15 * 60

AGENT = "notifier"  # its name in agent_log, which the family app shows live
FALLBACK_TEXT = "Your family pillow needs you to check in. Please open the app."
