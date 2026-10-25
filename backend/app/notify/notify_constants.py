"""Fixed values for the notifications sender."""

TWILIO_API = "https://api.twilio.com/2010-04-01"
TWILIO_VOICE = "Polly.Joanna"  # reads the alert call only when the pillow's own voice can't be made
HTTP_TIMEOUT_S = 15

# Alert calls: ring this long before Twilio gives up ("no-answer"), shorter than most voicemail
# pickups. Twilio's answering-machine detection tells voicemail from a person ("machine_*").
CALL_RING_S = 25
# Wait for the voicemail beep before speaking, so a voicemail holds the whole script rather than
# the end of it talked over the greeting; a person who answers still hears it straight away
MACHINE_DETECTION = "DetectMessageEnd"
# The script starts once detection decides, i.e. after their "Hello?"; someone who picks up and
# says nothing hears it after this much silence (Twilio's default is 5 s)
MACHINE_DETECTION_SILENCE_MS = 3000

# Alert calls speak in the pillow's own Cartesia voice, the one she hears at night: the script as
# an MP3 in the voice-samples bucket at an unguessable name, which Twilio fetches and plays. If it
# isn't made within the budget, Twilio's voice reads the script so the call is never held up.
CALL_AUDIO_BUDGET_S = 8
CALL_AUDIO_FOLDER = "calls"
CALL_AUDIO_LANGUAGE = "en"  # the Liaison writes the family's alerts in English
# A touch quicker than the pillow's bedside pace (0.85): someone woken at 3 a.m. wants it plainly
CALL_AUDIO_SPEED = 0.95
# Then the MP3 is deleted: the script names her and what happened. Long enough for a voicemail,
# which only plays it after the greeting
CALL_AUDIO_KEEP_S = 10 * 60
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

# Live alert calls on Cartesia Line (app/notify/line.py, set up by scripts/setup_line.py): a
# Claude agent speaks the alert in the pillow's voice and answers questions. The Twilio call above
# is the fallback whenever Line isn't configured or refuses the call.
LINE_API_PATH = "/agents/calls"
LINE_AGENTS_PATH = "/v1/agents"
LINE_AGENT_NAME = "Pillow alert calls"  # the base agent; one copy per other voice, named after it
LINE_RING_S = CALL_RING_S
# A conversation outlasts a played alert: watch longer before counting no news as reached
LINE_WATCH_S = 10 * 60
LINE_REF = "line:"  # notifications.provider_ref prefix for these calls
LINE_VOICEMAIL_TOOL = "left_voicemail"  # the agent calls it when voicemail answers
LINE_DONE = ("completed", "failed")
# An agent made or changed moments ago isn't callable yet (Cartesia answers 404): retry this often
LINE_NEW_AGENT_TRIES = 5
LINE_NEW_AGENT_WAIT_S = 2
LINE_MISSED = {"dial_no_answer": "didn't answer", "dial_busy": "rejected the call",
               "dial_failed": "couldn't be called", "error": "couldn't be called"}
