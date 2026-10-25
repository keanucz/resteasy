"""Connect a mailbox agent to Agentverse without a browser (the VPS has none).

The Agent Inspector's "Connect -> Mailbox" button only POSTs the user's Agentverse token to the
agent's own /connect endpoint (uagents' AgentverseConnectRequest). With AGENTVERSE_API_KEY set, the
agent does the same to itself at start-up. Without it, nothing happens and the Inspector link in
the log works as usual.
"""

import asyncio
import os

import httpx
from uagents import Context

_tasks: set[asyncio.Task] = set()


def start_connect(ctx: Context, port: int) -> None:
    """Run connect_mailbox in the background (the startup handler must not wait for the server)."""
    task = asyncio.create_task(connect_mailbox(ctx, port))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def connect_mailbox(ctx: Context, port: int) -> None:
    key = os.environ.get("AGENTVERSE_API_KEY", "").strip()
    if not key or os.environ.get("AGENT_ENDPOINT"):
        return
    body = {"user_token": key, "agent_type": "mailbox"}
    for _ in range(30):  # the agent's REST server comes up just after the startup handlers
        await asyncio.sleep(2)
        try:
            async with httpx.AsyncClient(timeout=30) as http:
                r = await http.post(f"http://127.0.0.1:{port}/connect", json=body)
        except httpx.TransportError:
            continue
        result = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if result.get("success"):
            ctx.logger.info("mailbox connected to Agentverse")
        else:
            detail = result.get("detail") or r.text[:200]
            ctx.logger.error(f"mailbox connect failed: {r.status_code} {detail}")
        return
    ctx.logger.error("mailbox connect failed: the agent's REST server never came up")
