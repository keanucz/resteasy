![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
![domain:eldercare](https://img.shields.io/badge/eldercare-night%20safety-1E294A)

# Pillow family agent

One agent per family member of an older parent who lives alone, for her bedside pillow. The pillow
notices when she gets up in the night and doesn't come back, checks on her by voice, and alerts the
family. This agent is **your** side of it, in ASI:One: it remembers what you tell it and answers the
pillow's coordinator for you.

| Agent | Handle | Address |
|---|---|---|
| Sarah's Pillow Agent | `@pillow-sarah` | `agent1qfazxg7rlwfwj9z5u2vvan8uk6mcgeecyd7wh49taktaarwjxw5kvatzd7h` |
| Szymon's Pillow Agent | `@pillow-szymon` | `agent1qtjfwjlsagy8jmxp20dx523avn2mmpygrf58hczmd5xsr235cvusjhwhe8d` |

## Try it

| Say | It does |
|---|---|
| "How was Mum's night?" | her night from the pillow (in bed, asleep, trips out of bed, check-ins, alerts, anything unusual) as a card |
| "Send Mum a goodnight" | a form; the pillow plays your words when she next lies down |
| "I'm in Denver Thu to Sun, make sure Mum's covered" | a **plan** (your away nights, a goodnight from you, maybe a reminder), shown as one Confirm / Cancel card |
| "Remind her to call me at 7 every Sunday" | a plan; the pillow asks her to agree before it ever plays |
| "Who's on call tonight?" | the family, in alert order |
| "What exactly did the pillow do last night?" | every step its agents took, with the safety Guardian's allowed / blocked verdicts |

**Goals become plans, and nothing changes until you confirm.** Claude works out every step a goal
needs but only queues them. You confirm on a review card (or say yes), then plain code carries each
step out through the pillow's API, where a Guardian checks it: no medical or dosing advice, settings
kept in safe bounds.

**Agents asking agents.** At 9pm the
[Pillow Night Coordinator](https://agentverse.ai/agents/details/agent1qgharmfw5pyftk46gfmfyzqsdn6cqjh3fllnha7al76pyum4zd34zy93xrj/profile)
asks every family agent at once whether its person can be called first tonight. This agent answers
from your away dates, and the coordinator sets the order. Everyone is still alerted in the end, so
this changes who is asked first and never removes anyone.

Protocols: Agent Chat Protocol (with ASI:One interactive cards), `pillow-watch-roster` 0.1.0. Built
with uAgents and Claude, used through ASI:One, part of the Cal Hacks 13.0 agentic pillow.
