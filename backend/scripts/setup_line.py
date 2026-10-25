"""Set up the live alert calls on Cartesia Line (docs.cartesia.ai/agents): our Twilio number,
the agent's tools and the agent itself. Safe to run again: it finds what exists by name and
updates it, so this file is the agent's source of truth (prompt, model, voice, tools).

    docker compose -f deploy/compose.yml exec -T backend /app/.venv/bin/python - \
        < backend/scripts/setup_line.py

Needs CARTESIA_API_KEY and the TWILIO_* values in the environment (the backend container has them).
The first run makes a Twilio API key and hands it straight to Cartesia; it is never printed or
stored here. It prints the two ids the backend needs: CARTESIA_LINE_AGENT_ID and
CARTESIA_LINE_NUMBER_ID go into the backend's env, and the backend makes a copy of this agent for
each other voice a pillow speaks in (app/notify/line.py).

Self-contained (httpx only) so it runs in the deployed container before the code that uses it is.
"""

import os
from typing import Any

import httpx

CARTESIA_API = "https://api.cartesia.ai"
CARTESIA_VERSION = "2026-08-14"
TWILIO_API = "https://api.twilio.com/2010-04-01"
PILLOW_API = "https://pillow.keanuc.net/api"  # the tools call the public backend

AGENT_NAME = "Pillow alert calls"
TWILIO_KEY_NAME = "cartesia-line"
NUMBER_LABEL = "Pillow alerts"
MODEL = "claude-haiku-5.5"  # Cartesia's fastest Claude; the person on the line is waiting
VOICE_ID = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"  # Skylar, the pillow's default voice
SPEED = 0.95  # the alert calls' pace (notify_constants.CALL_AUDIO_SPEED)
TOOL_TIMEOUT_S = 10

# Values the backend passes with each call: {{contact_name}} (first name of who is called),
# {{alert}} (the Liaison's call script), {{summary}} (the incident), {{pillow_id}}, {{contact_id}}
INSTRUCTIONS = """\
# Who you are
You are the voice of a bedside pillow that looks after an older woman who lives alone. It is \
night, and you are phoning {{contact_name}}, one of her family contacts, because the pillow is \
worried about her. Speak warmly, calmly and plainly, in short sentences: they may have just woken \
up. Keep every reply under 40 words, and ask one question at a time.

# Start of the call
As soon as they answer, say "Hi {{contact_name}}, it's the pillow." and then this alert, word for \
word: "{{alert}}" Then ask if they can check on her, and say they can ask you about tonight.

# What you know
The alert above, and the pillow's note on what happened: "{{summary}}". For how she is right now, \
call `check_pillow`: head_on true means her head is on the pillow, so she is back in bed; \
night_state "escalating" means the pillow is alerting family, "ok" means it has settled; \
state_since is when that started and last_seen_at is the pillow's last report (UTC). Say times as \
"about 5 minutes ago", never as clock times. If you don't know something, say so.

# Rules
Facts only. Never guess a cause, never name or hint at a medical condition, never give medical \
advice. Never say that you, the pillow or anyone has called emergency services. If they think she \
is hurt or in danger, tell them to call 911.

# Actions
- When they say they will check on her, go round or call her, call `on_my_way` once, then tell \
them the pillow will let her know they are coming and nobody else will be alerted.
- If they can't help, thank them and say the pillow will try her next contact.
- If a voicemail greeting, an answering machine or a beep answers instead of a person, call \
`left_voicemail`, then say the alert once, ask them to call her back, and end the call.
- When they are done, say a short goodbye and end the call."""

# The pillow id and contact id come from the call's dynamic variables via the descriptions, which
# Cartesia fills in; the endpoints are the same public ones the family app uses.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "webhook",
        "name": "check_pillow",
        "description": "The pillow's live readings: whether her head is on it now, what the pillow "
                       "is doing and since when. Use it whenever they ask how she is now.",
        "pre_tool_speech": "auto",
        "execution_mode": "immediate",
        "response_timeout_secs": TOOL_TIMEOUT_S,
        "api_schema": {
            "url": f"{PILLOW_API}/pillows/{{pillow_id}}/state",
            "method": "GET",
            "path_params_schema": {
                "pillow_id": {"type": "string", "description": "Always exactly: {{pillow_id}}"},
            },
        },
    },
    {
        "type": "webhook",
        "name": "on_my_way",
        "description": "Tells the pillow this person is handling it: the pillow tells her they are "
                       "coming and stops alerting the other contacts. Use it once they say so.",
        "pre_tool_speech": "auto",
        "execution_mode": "immediate",
        "response_timeout_secs": TOOL_TIMEOUT_S,
        "api_schema": {
            "url": f"{PILLOW_API}/pillows/{{pillow_id}}/ack",
            "method": "POST",
            "path_params_schema": {
                "pillow_id": {"type": "string", "description": "Always exactly: {{pillow_id}}"},
            },
            "request_body_schema": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "string", "description": "Always exactly: {{contact_id}}"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        # Only a marker: the backend reads it from the call's transcript and texts the alert too
        "type": "webhook",
        "name": "left_voicemail",
        "description": "Call this when a voicemail greeting, answering machine or beep answered "
                       "instead of a person, before leaving the message.",
        "pre_tool_speech": "auto",
        "execution_mode": "async",
        "response_timeout_secs": TOOL_TIMEOUT_S,
        "api_schema": {"url": f"{PILLOW_API}/health", "method": "GET"},
    },
]


def agent_config(tool_ids: list[str]) -> dict[str, Any]:
    return {
        "instructions": INSTRUCTIONS,
        "initial_message": None,  # wait for their "Hello?" so nothing is said over the pickup
        "model": {"id": MODEL},  # its temperature is fixed
        "language": {"primary": "en"},
        "audio": {"output": {"voice_id": VOICE_ID, "speed": SPEED}},
        "tools": [{"id": tool_id} for tool_id in tool_ids],
        "system_tools": {"end_call": {"description": None, "pre_tool_speech": "force"}},
    }


def check(response: httpx.Response) -> Any:
    if response.status_code >= 300:
        raise SystemExit(f"{response.request.method} {response.request.url.path}: "
                         f"{response.status_code} {response.text[:400]}")
    return response.json() if response.content else None


def items(body: Any) -> list[dict[str, Any]]:
    return body if isinstance(body, list) else body.get("data", [])


def provider_id(cartesia: httpx.Client, twilio: httpx.Client, sid: str) -> str:
    """Our Twilio account as a Cartesia phone provider, made with a fresh Twilio API key."""
    for provider in items(check(cartesia.get("/agents/phone-numbers/providers"))):
        if provider.get("account_sid") == sid or provider.get("type") == "twilio":
            return provider["id"]
    key = check(twilio.post(f"/Accounts/{sid}/Keys.json", data={"FriendlyName": TWILIO_KEY_NAME}))
    body = {"type": "twilio", "account_sid": sid, "api_key_sid": key["sid"],
            "api_key_secret": key["secret"], "region": "us1"}
    return check(cartesia.post("/agents/phone-numbers/providers", json=body))["id"]


def number_id(cartesia: httpx.Client, provider: str, number: str) -> str:
    for row in items(check(cartesia.get("/agents/phone-numbers"))):
        if row.get("number") == number:
            return row["id"]
    body = {"label": NUMBER_LABEL, "number": number, "provider": {"id": provider}}
    return check(cartesia.post("/agents/phone-numbers", json=body))["id"]


def tool_ids(cartesia: httpx.Client) -> list[str]:
    existing = {tool["name"]: tool["id"] for tool in items(check(cartesia.get("/v1/agents/tools")))}
    ids = []
    for tool in TOOLS:
        if tool["name"] in existing:
            update = {k: v for k, v in tool.items() if k != "type"}  # a tool's type can't change
            ids.append(check(cartesia.patch(f"/v1/agents/tools/{existing[tool['name']]}", json=update))["id"])
        else:
            ids.append(check(cartesia.post("/v1/agents/tools", json=tool))["id"])
    return ids


def agent_id(cartesia: httpx.Client, config: dict[str, Any]) -> str:
    for agent in items(check(cartesia.get("/v1/agents"))):
        if agent["name"] == AGENT_NAME:
            return check(cartesia.patch(f"/v1/agents/{agent['id']}", json={"config": config}))["id"]
    body = {"name": AGENT_NAME, "description": "Calls family when the pillow is worried about her",
            "config": config}
    return check(cartesia.post("/v1/agents", json=body))["id"]


def main() -> None:
    sid, number = os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_FROM_NUMBER"]
    headers = {"Authorization": f"Bearer {os.environ['CARTESIA_API_KEY']}",
               "Cartesia-Version": CARTESIA_VERSION}
    with (httpx.Client(base_url=CARTESIA_API, headers=headers, timeout=30) as cartesia,
          httpx.Client(base_url=TWILIO_API, auth=(sid, os.environ["TWILIO_AUTH_TOKEN"]),
                       timeout=30) as twilio):
        provider = provider_id(cartesia, twilio, sid)
        number_ref = number_id(cartesia, provider, number)
        agent = agent_id(cartesia, agent_config(tool_ids(cartesia)))
    print(f"CARTESIA_LINE_AGENT_ID={agent}")
    print(f"CARTESIA_LINE_NUMBER_ID={number_ref}")


if __name__ == "__main__":
    main()
