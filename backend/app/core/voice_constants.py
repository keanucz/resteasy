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

# Where a voice in the app's picker comes from: the list above, a clone made in the app, or a copy
# of either with another accent (Cartesia's localize). The last two are voice_clones rows (`kind`).
STOCK_SOURCE = "stock"
CLONE_SOURCE = "clone"
ACCENT_SOURCE = "accent"

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

# The languages the app's previews can speak in (Settings > Voice), as Cartesia's sonic-3 codes,
# each named in its own language. Only the previews follow it: the pillow and alert calls keep hers.
PREVIEW_LANGUAGE = "en"
PREVIEW_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("pl", "Polski"),
    ("zh", "中文"),
    ("ja", "日本語"),
    ("hi", "हिन्दी"),
)
PREVIEW_LANGUAGE_CODES = frozenset(code for code, _ in PREVIEW_LANGUAGES)
# The English name of each, for the translator's instructions
LANGUAGE_ENGLISH_NAMES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "pl": "Polish",
    "zh": "Mandarin Chinese",
    "ja": "Japanese",
    "hi": "Hindi",
}
# The default preview line in each language, with her preferred name
PREVIEW_TEXTS = {
    "en": PREVIEW_TEXT,
    "es": "Hola {name}, es hora de tomar tus pastillas para el corazón.",
    "fr": "Bonjour {name}, c'est l'heure de prendre tes comprimés pour le cœur.",
    "de": "Hallo {name}, es ist Zeit für deine Herztabletten.",
    "it": "Ciao {name}, è ora di prendere le tue pastiglie per il cuore.",
    "pt": "Olá {name}, está na hora de tomar os seus comprimidos para o coração.",
    "pl": "Cześć {name}, czas wziąć tabletki na serce.",
    "zh": "{name}，你好，该吃心脏药了。",
    "ja": "{name}さん、こんにちは。心臓のお薬を飲む時間ですよ。",
    "hi": "नमस्ते {name}, दिल की दवा लेने का समय हो गया है।",
}
# A typed preview line is translated with Claude before it is spoken in another language; the
# line as typed is spoken if that fails or takes longer than this
TRANSLATE_MODEL = "claude-haiku-5-5"
TRANSLATE_TIMEOUT_S = 8
TRANSLATE_MAX_TOKENS = 400
TRANSLATE_SYSTEM = (
    "Translate the user's text into {language} for a voice to read aloud to an older woman. Keep "
    "names as they are. Reply with the translation only, no quotes and no notes."
)
UNKNOWN_LANGUAGE = "That language is not offered for previews"

# How the pillow speaks to her, set by the owner (residents.voice_speed, voice_volume, voice_emotion).
# Bounds are Cartesia's own for sonic-3 (generation_config); the defaults are how it always spoke.
SPEED_MIN, SPEED_MAX = 0.6, 1.5
VOLUME_MIN, VOLUME_MAX = 0.5, 2.0
DEFAULT_SPEED = PREVIEW_SPEED
DEFAULT_VOLUME = 1.0
DEFAULT_EMOTION = PREVIEW_EMOTION
# The tones offered: gentle ones from Cartesia's emotion list (no angry, scared or sad at her bedside)
EMOTIONS = ("calm", "peaceful", "content", "affectionate", "sympathetic", "neutral", "happy")
# Cartesia's emotions only work in English; other languages are spoken without one
EMOTION_LANGUAGE = "en"

# One short line per voice, spoken once and kept in Supabase Storage, so Play in the app is instant
# and never asks Cartesia again. Casual and the same for everyone, so a stock voice's sample is shared.
SAMPLE_TEXT = "Hi, this is the voice your pillow will use."
# The same line in each preview language
SAMPLE_TEXTS = {
    "en": SAMPLE_TEXT,
    "es": "Hola, esta es la voz que usará tu almohada.",
    "fr": "Bonjour, voici la voix que ton oreiller va utiliser.",
    "de": "Hallo, das ist die Stimme, die dein Kissen benutzen wird.",
    "it": "Ciao, questa è la voce che userà il tuo cuscino.",
    "pt": "Olá, esta é a voz que o seu travesseiro vai usar.",
    "pl": "Cześć, to jest głos, którego będzie używać twoja poduszka.",
    "zh": "你好，这是你的枕头将会使用的声音。",
    "ja": "こんにちは。これがあなたの枕の声です。",
    "hi": "नमस्ते, यह वह आवाज़ है जो आपका तकिया इस्तेमाल करेगा।",
}
SAMPLE_SPEED = 1.0
SAMPLE_EMOTION = "content"
SAMPLES_BUCKET = "voice-samples"
# Stock voices' samples sit in one shared folder; a resident's own voices in a folder of hers
STOCK_SAMPLES_FOLDER = "stock"
SAMPLE_EXTENSION = ".mp3"
# Enough to list every sample in one folder (the stock voices, or a resident's own voices)
SAMPLES_LIST_LIMIT = 1000

# Words the pillow says her way (a Cartesia pronunciation dictionary per resident, synced on change)
PRONUNCIATION_WORD_MAX = 60
SOUNDS_LIKE_MAX = 120
PRONUNCIATIONS_MAX = 100
# The dictionary's name at Cartesia, so it can be told apart in the dashboard
PRONUNCIATION_DICT_NAME = "pillow-{resident_id}"

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
# How an accent copy is named in the picker ("Skylar, British"), cut to CLONE_NAME_MAX
ACCENT_COPY_NAME = "{name}, {accent}"
# Accent names arrive as "British English"; the picker only needs "British"
ACCENT_NAME_SUFFIX = " English"
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
ACCENTS_FAILED = "The voice service could not list accents. Try again in a moment."
ACCENT_FAILED = "The voice service could not make this accent. Try again in a moment."
UNKNOWN_ACCENT = "That accent is not offered for her language"
PRONUNCIATION_FAILED = "The voice service could not save how to say this. Try again in a moment."
PRONUNCIATION_EXISTS = "There is already a pronunciation for that word"
PRONUNCIATIONS_FULL = "That's the most words the pillow can keep. Remove one first."
UNKNOWN_PRONUNCIATION = "That word is not in her list"
NOT_PRONUNCIATION_CREATOR = "Only whoever added this word, or the owner, can remove it"
UNKNOWN_EMOTION = "That tone is not offered"

# Tables and columns the voice features use
PRONUNCIATIONS_TABLE = "pronunciations"
PRONUNCIATION_COLUMNS = "*, creator:contacts(full_name)"
# The resident's column with the language the app's previews speak in
PREVIEW_LANGUAGE_COLUMN = "preview_language"
# The resident's columns that say how the pillow speaks
STYLE_COLUMNS = ("voice_speed", "voice_volume", "voice_emotion")
