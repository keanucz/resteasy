"""The watch-roster protocol between the pillow's coordinator and each family member's agent.

Frozen on purpose: changing any model changes the protocol digest that Agentverse indexes, so the
agents already registered would stop matching. Add a new model rather than editing one.

    family agent  --JoinRoster-->            coordinator   (on start-up, then every 10 min)
    coordinator   --AvailabilityRequest-->   family agent  (each evening, to every member at once)
    family agent  --AvailabilityReply-->     coordinator
"""

from uagents import Model, Protocol

ROSTER_PROTOCOL = "pillow-watch-roster"
ROSTER_VERSION = "0.1.0"


class JoinRoster(Model):
    """A family member's agent tells the pillow's coordinator who it speaks for."""

    pillow_id: str
    contact_id: str
    name: str


class AvailabilityRequest(Model):
    """Can your person be called first tonight? `night` is the evening's date, YYYY-MM-DD."""

    pillow_id: str
    night: str


class AvailabilityReply(Model):
    """The family agent's answer, from what its person told it (away dates) in their chat."""

    contact_id: str
    available: bool
    reason: str


def roster_protocol() -> Protocol:
    return Protocol(name=ROSTER_PROTOCOL, version=ROSTER_VERSION)
