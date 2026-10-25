"""The Cartesia voices the family app offers for the pillow, and how the backend calls Cartesia.

A short, hand-picked list rather than Cartesia's whole catalogue: calm, clear English voices that
an older adult can follow at night (no whisper or ASMR voices). Skylar is the team's demo voice.
The Cartesia API key stays on the server, so the app never lists voices from Cartesia itself.
Each id was checked against Cartesia's voice list (GET /voices) on 2026-10-25.
"""

DEFAULT_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"  # Skylar

# (id, name, one line on how it sounds)
VOICES: tuple[tuple[str, str, str], ...] = (
    (DEFAULT_VOICE_ID, "Skylar", "Friendly and clear, American"),
    ("ca566b43-944e-4474-b494-7d9f0695f307", "Celine", "Relaxed, with a gentle warmth"),
    ("ea93f57f-7c71-4d79-aeaa-0a39b150f6ca", "Diana", "Mature and warm"),
    ("62ae83ad-4f6a-430b-af41-a9bede9286ca", "Gemma", "Warm and steady, British"),
    ("0ad65e7f-006c-47cf-bd31-52279d487913", "Rupert", "Warm and reassuring, deeper"),
    ("a924b0e6-9253-4711-8fc3-5cb8e0188c94", "Noah", "Slow paced and gentle, deeper"),
)

VOICE_IDS = frozenset(voice_id for voice_id, _, _ in VOICES)

# Where a voice in the app's picker comes from: the list above, or a clone made in the app
STOCK_SOURCE = "stock"
CLONE_SOURCE = "clone"

# Cartesia's REST API, the same version and model the laptop speaks with (voice/voice.py)
CARTESIA_API = "https://api.cartesia.ai"
CARTESIA_VERSION = "2026-08-14"
TTS_MODEL = "sonic-3.6"
CARTESIA_TIMEOUT_S = 30

# A preview is MP3, the format every phone plays; spoken slower and calm, like the pillow speaks
PREVIEW_FORMAT = {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000}
PREVIEW_CONTENT_TYPE = "audio/mpeg"
PREVIEW_SPEED = 0.85
PREVIEW_EMOTION = "calm"
PREVIEW_TEXT_MAX = 200
# What a preview says when the app sends no text, with her preferred name
PREVIEW_TEXT = "Hello {name}, it's time to take your heart tablets."

# A recording to clone: Cartesia takes up to 16 MB; about 10 seconds is enough, up to 60 keeps the
# accent. Cartesia lists flac, mp3, ogg, wav and webm; m4a and aac are passed on as they are.
CLIP_MAX_BYTES = 10 * 1024 * 1024
CLIP_CONTENT_TYPES = frozenset(
    {
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/aac",
        "audio/x-aac",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/ogg",
        "audio/flac",
        "audio/x-flac",
    }
)
CLONE_NAME_MAX = 40
# The consent form field must be exactly this: the person recorded agreed to having their voice cloned
CONSENT_GIVEN = "true"

# agent_log.tool when the voice she hears changes
VOICE_TOOL = "voice"

# Details the app shows when something about a voice goes wrong
VOICE_NOT_CONFIGURED = "Voice service is not set up"
UNKNOWN_VOICE = "That voice is not one of hers"
NOT_CLONE_CREATOR = "Only whoever made this voice, or the owner, can remove it"
CLIP_WRONG_TYPE = "The recording must be an audio file (m4a, aac, wav, mp3, webm, ogg or flac)"
CLIP_EMPTY = "The recording is empty"
CLIP_TOO_LARGE = "The recording must be 10 MB or smaller"
CLONE_NAME_MISSING = "Give the voice a name"
CONSENT_MISSING = "The person recorded must agree to having their voice cloned"
PREVIEW_FAILED = "The voice service could not make this preview. Try again in a moment."
CLONE_FAILED = "The voice service could not clone this recording. Try a clear 10 to 60 second clip."
DELETE_FAILED = "The voice service could not remove this voice. Try again in a moment."
