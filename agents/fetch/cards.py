"""ASI:One interactive cards (docs.agentverse.ai, "Agent-driven interactive cards").

A card is one MetadataContent block next to the narration. If ASI:One can't show it (bad payload, a
client without cards), the person still gets the narration as a plain reply, so every card here is
optional polish on top of text that stands on its own.

A click comes back as a follow-up TextContent: the CTA's `selection` (plus form fields) as JSON when
the person @mentions the agent directly, or as prose when ASI:One's planner relays it.
`parse_selection` handles the first; prose goes to Claude like any other message.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from uagents_core.contrib.protocols.chat import ChatMessage, EndSessionContent, MetadataContent, TextContent

# Actions our cards put in their selections; anything else is treated as text
CONFIRM_PLAN, CANCEL_PLAN = "confirm_plan", "cancel_plan"
SEND_GOODNIGHT, GOODNIGHT_FORM, SHOW_LOG = "send_goodnight", "goodnight_form", "show_log"
ACTIONS = {CONFIRM_PLAN, CANCEL_PLAN, SEND_GOODNIGHT, GOODNIGHT_FORM, SHOW_LOG}


def reply(text: str, card: tuple[str, dict[str, Any]] | None = None) -> ChatMessage:
    """One answer: the narration and an optional (card_kind, payload) card. A plain answer ends the
    session; a card leaves it open, or ASI:One shows it as already "Submitted", without its buttons."""
    content: list[Any] = [TextContent(type="text", text=text)]
    if card is not None:
        kind, payload = card
        content.append(MetadataContent(metadata={
            "card_protocol_version": "1",
            "requires_card_interaction": "true",
            "card_kind": kind,
            "card_payload": json.dumps(payload),
        }))
    if card is None:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(UTC), msg_id=uuid4(), content=content)


def parse_selection(text: str) -> dict[str, Any] | None:
    """A card click as a dict with a known `action`, or None for ordinary text."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("action") in ACTIONS else None


def plan_review(title: str, rows: list[tuple[str, str]], plan_id: str) -> tuple[str, dict[str, Any]]:
    """The approval step: what the agent wants to change, Confirm or Cancel. Nothing runs before."""
    return "review", {
        "title": title,
        "summary_rows": [{"label": label, "value": value} for label, value in rows],
        "approve_cta": {"label": "Confirm", "primary": True,
                        "selection": {"action": CONFIRM_PLAN, "plan_id": plan_id}},
        "reject_cta": {"label": "Cancel", "selection": {"action": CANCEL_PLAN, "plan_id": plan_id}},
    }


def night_detail(resident: str, summary: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Last night at a glance, from GET /night's plain-code summary."""
    trips = summary.get("trips") or []
    rows = [
        ("In bed", summary.get("lay_down") or "not seen"),
        ("Asleep", summary.get("asleep") or "not seen"),
        ("Up in the night", f"{len(trips)} time{'s' if len(trips) != 1 else ''}"
         + (f", longest {summary.get('longest_trip_min')} min" if trips else "")),
        ("Voice check-ins", str(summary.get("checkins", 0))),
        ("Family alerts", str(summary.get("escalations", 0))),
    ]
    if summary.get("acknowledged_by"):
        rows.append(("Answered by", ", ".join(summary["acknowledged_by"])))
    rows += [("Worth knowing", line) for line in summary.get("unusual") or []]
    return "detail", {
        "title": f"{resident}'s night",
        "summary_rows": [{"label": label, "value": value} for label, value in rows],
        "ctas": [
            {"label": "Send a goodnight", "primary": True, "selection": {"action": GOODNIGHT_FORM}},
            {"label": "What did the pillow do?", "selection": {"action": SHOW_LOG}},
        ],
    }


def goodnight_form(resident: str) -> tuple[str, dict[str, Any]]:
    """A goodnight in the sender's own words; the pillow plays it when she next lies down.

    Only the documented form keys: an unknown key makes ASI:One reject the whole card."""
    return "form", {
        "title": f"Goodnight message for {resident}",
        "fields": [
            {"name": "message", "kind": "text", "label": "Your message", "required": True},
            {"name": "from_name", "kind": "text", "label": "From (as she should hear it)", "required": True},
        ],
        "submit_cta": {"label": "Send", "selection": {"action": SEND_GOODNIGHT}},
    }
