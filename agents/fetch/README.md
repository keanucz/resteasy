![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Pillow family agent

**Agent name:** `pillow-family-agent`
**Agent address:** _printed on start-up (`family agent address: agent1q...`); paste it here after the first run_

The adult child of an older person who lives alone talks to their parent's bedside pillow here, in
ASI:One. No app needed for the whole workflow:

| Say | The agent does |
|---|---|
| "How was Mum's night?" | reads last night (trips, how long, whether she answered the pillow, who was alerted) and the Morning Brief |
| "Is she in bed right now?" | live pillow state |
| "Send Mum a goodnight message: sleep well, love you" | queues it; the pillow plays it in a calm voice when she next lies down |
| "Set quiet hours to 23:00 to 07:00" / "Give her 25 minutes before you check in" | changes the setting, within the Guardian's bounds |
| "What exactly did the pillow do last night?" | the agent log, step by step, with the Guardian's allowed / blocked verdicts |

Behind the chat: Claude (`claude-opus-5-5`) reads the message and calls one of five tools. The
tools only call the pillow's backend API (`coord/CONTRACT.md`, `backend/README.md`), which runs a
plain-code Guardian on every change, so the agent cannot do anything the pillow itself wouldn't
allow: no diagnoses, no out-of-range settings, no messages it can't vouch for.

## Run it

```bash
export AGENT_SEED='a long private phrase'      # the agent's identity; keep it the same between runs
export ANTHROPIC_API_KEY=sk-ant-...
export CHECKIN_TOKEN=...                        # same value as backend/.env (settings changes)
export PILLOW_SERVER=https://pillow.keanuc.net  # default
uv run agents/fetch/family_agent.py
```

First run: open the **Local Agent Inspector** link from the log, click **Connect**, choose
**Mailbox**, **Finish**. The agent then appears under your Agentverse local agents, publishes the
Agent Chat Protocol manifest and this README, and can be found and chatted with in ASI:One (search
for "pillow family agent"). It has to stay running to answer.

## Protocol

Agent Chat Protocol (`uagents_core.contrib.protocols.chat`, `AgentChatProtocol 0.3.0`). Every
incoming `ChatMessage` is acknowledged, answered once with a `TextContent` and closed with
`EndSessionContent`. Short per-sender history (6 turns) is kept in agent storage.
