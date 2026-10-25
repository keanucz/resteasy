"""Fixed values for the notifications sender."""

TWILIO_API = "https://api.twilio.com/2010-04-01"
TWILIO_VOICE = "Polly.Joanna"  # a clear US voice for the alert call
HTTP_TIMEOUT_S = 15

# Alert calls: ring this long before Twilio gives up ("no-answer"), shorter than most voicemail
# pickups. Twilio's answering-machine detection tells voicemail from a person ("machine_*").
CALL_RING_S = 25
# Wait for the voicemail beep before speaking, so a voicemail holds the whole script rather than
# the end of it talked over the greeting; a person who answers still hears it straight away
MACHINE_DETECTION = "DetectMessageEnd"
# After placing a call the sender checks how it went this often, for at most this long; a call
# that was rejected, not answered or went to voicemail is followed by a text with the same alert
CALL_POLL_S = 3
CALL_WATCH_S = 120
CALL_MISSED = {"busy": "rejected the call", "no-answer": "didn't answer",
               "failed": "couldn't be called", "canceled": "couldn't be called"}

# Channels this sender delivers; "app" rows are the family app's to show
SENT_CHANNELS = ("sms", "call")

# A queued row older than this is never sent: a 3 a.m. alert must not arrive at noon because the
# sender was down or unconfigured. It stays "queued" in the table, untouched.
MAX_AGE_S = 15 * 60

AGENT = "notifier"  # its name in agent_log, which the family app shows live
FALLBACK_TEXT = "Your family pillow needs you to check in. Please open the app."
