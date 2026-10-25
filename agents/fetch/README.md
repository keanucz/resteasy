![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

# Agentic pillow: the family's agents

A bedside pillow watches over an older person who lives alone and gets up in the night. The pillow
itself runs on plain, predictable code: if she isn't back in bed in time, it checks on her by voice,
then alerts her family one after another until someone answers. **These agents are the family's
side.** Each family member has their own agent, and the pillow has a coordinator that talks to all of
them.

| Agent | Name | Address |
|---|---|---|
| Pillow coordinator | `pillow-coordinator-mum` | `agent1qgharmfw5pyftk46gfmfyzqsdn6cqjh3fllnha7al76pyum4zd34zy93xrj` |
| Sarah's agent | `pillow-family-sarah` | `agent1qfazxg7rlwfwj9z5u2vvan8uk6mcgeecyd7wh49taktaarwjxw5kvatzd7h` |
| Second family member's agent | `pillow-family-<name>` | `agent1qtjfwjlsagy8jmxp20dx523avn2mmpygrf58hczmd5xsr235cvusjhwhe8d` |

All three are uAgents on Agentverse (Agent Chat Protocol, mailbox), reachable from ASI:One. They use
Claude (`claude-opus-5-5`) for language, and plain code for every decision that matters.

## What you can say to your agent (in ASI:One)

| Say | What happens |
|---|---|
| "How was Mum's night?" | last night from the pillow (in bed, asleep, trips, check-ins, alerts, anything unusual), as a card |
| "Send Mum a goodnight" | a form card; the pillow plays your words when she next lies down |
| "I'm in Denver Thu to Sun, make sure Mum's covered" | a **plan**: your away nights, a goodnight for each night, maybe a setting, shown as one Confirm / Cancel card |
| "Give her 25 minutes before it checks on her" | the same: a plan you confirm. The pillow's Guardian keeps it between 10 and 30 minutes |
| "Who's on call tonight?" | the family roster, in alert order |
| "What exactly did the pillow do last night?" | the agent log, step by step, with the Guardian's allowed or blocked verdicts |

**Goals become plans, and nothing changes until you confirm.** Claude works out every step a goal
needs, but every change is only queued. You see the whole plan on a review card (or reply yes or no),
and only then does plain code carry it out through the pillow's API, which runs the Guardian on each
step.

## The evening roster: agents asking agents

At 21:00 in her timezone (or when you ask the coordinator "plan tonight"), the coordinator asks every
family member's agent **at the same time**: "can your person be called first tonight?" Each agent
answers from what its person told it (the away dates in its memory). The coordinator then puts the
available people on call and the away ones off call, and reports who is first tonight.

    coordinator --AvailabilityRequest--> Sarah's agent, Tom's agent   (in parallel, 30 s to answer)
    each agent  --AvailabilityReply-->   coordinator                  ("away: in Denver")
    coordinator --PUT /roster/{contact}-> pillow API + Guardian       (on/off call, logged)

**Why it's safe:** the pillow only uses `on_call` to decide who it tries *first*. It still alerts
every family member in the end, so a wrong, late or missing roster changes the order of help but
never withholds it. The Guardian never lets the last on-call person go off call. If an agent doesn't
answer, its person is left as they were. If every agent is down, the pillow keeps last night's roster
and works exactly as before.

Protocol `pillow-watch-roster` 0.1.0 (`models.py`): `JoinRoster` (family agent → coordinator, says who
it speaks for; the coordinator accepts it only for people who really look after this pillow),
`AvailabilityRequest`, `AvailabilityReply`.

## Run it

Locally, each agent in its own terminal:

```bash
export CHECKIN_TOKEN=...            # backend/.env: the agents' token for the pillow API
export PILLOW_ID=mum                # default
AGENT_SEED='coordinator private phrase' uv run agents/fetch/coordinator_agent.py
# prints: coordinator for mum: agent1q...

export ANTHROPIC_API_KEY=sk-ant-...
AGENT_SEED='sarah private phrase' CONTACT_ID=<contacts.id> CONTACT_NAME=Sarah \
  COORDINATOR_ADDRESS=agent1q... uv run agents/fetch/family_agent.py
```

Then open each agent's **Inspector** link from its log, click **Connect**, choose **Mailbox**. Or set
`AGENTVERSE_API_KEY` and the agent connects its own mailbox at start-up (`agentverse.py`); this is how
the agents connect on the VPS, which has no browser.

On the VPS they run in Docker next to the backend (`deploy/compose.yml`, profile `fetch`), switched
on by `COMPOSE_PROFILES=fetch` in `deploy/.env`. Each reads its env file from `/opt/pillow`:
`fetch-coordinator.env`, `fetch-family-1.env`, `fetch-family-2.env`.

| Variable | Agent | What |
|---|---|---|
| `AGENT_SEED` | all | private phrase = the agent's identity; never change it, never commit it |
| `CHECKIN_TOKEN` | all | the pillow API's agent token (same as `backend.env`) |
| `AGENTVERSE_API_KEY` | all | connects the mailbox without the Inspector |
| `PILLOW_ID` | all | default `mum` |
| `ROSTER_AT` | coordinator | default `21:00`, her time |
| `CONTACT_ID`, `CONTACT_NAME` | family | who this agent speaks for (`contacts.id`) |
| `COORDINATOR_ADDRESS` | family | the coordinator's `agent1q...` |
| `ANTHROPIC_API_KEY` | family | Claude |
| `RESIDENT_NAME` | family | how she's named in replies, default `Mum` |

For a local test without Agentverse, set `AGENT_ENDPOINT=http://127.0.0.1:<port>/submit` and a
different `AGENT_PORT` per agent.

## Switching it off

The agents are clients of the pillow's API and nothing more. The backend never calls them or waits
for them. Stop them (or remove the `fetch` profile) and the pillow, Night Watch, the check-in voice,
the alerts and the family app carry on unchanged.
