"""The Cartesia voices the family app offers for the pillow.

A short, hand-picked list rather than Cartesia's whole catalogue: calm, clear English voices that
an older adult can follow at night (no whisper or ASMR voices). Skylar is the team's demo voice.
The Cartesia API key stays on the server, so the app never lists voices from Cartesia itself.
"""

DEFAULT_VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"  # Skylar

# (id, name, one line on how it sounds)
VOICES: tuple[tuple[str, str, str], ...] = (
    (DEFAULT_VOICE_ID, "Skylar", "Friendly and clear, American"),
    ("ca566b43-944e-4474-b494-7d9f0695f307", "Celine", "Relaxed, with a gentle warmth"),
    ("6adbb439-0865-468c-9e68-adbb0eb2e71c", "Sally", "Soft spoken and calm"),
    ("ea93f57f-7c71-4d79-aeaa-0a39b150f6ca", "Diana", "Mature and warm"),
    ("62ae83ad-4f6a-430b-af41-a9bede9286ca", "Gemma", "Warm and steady, British"),
    ("0ad65e7f-006c-47cf-bd31-52279d487913", "Rupert", "Warm and reassuring, deeper"),
    ("a924b0e6-9253-4711-8fc3-5cb8e0188c94", "Noah", "Slow paced and gentle, deeper"),
)

VOICE_IDS = frozenset(voice_id for voice_id, _, _ in VOICES)
