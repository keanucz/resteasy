![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
![domain:eldercare](https://img.shields.io/badge/eldercare-night%20safety-1E294A)

# Pillow Night Coordinator

**Handle:** `@pillow-coordinator`
**Address:** `agent1qgharmfw5pyftk46gfmfyzqsdn6cqjh3fllnha7al76pyum4zd34zy93xrj`

Plans who gets called first tonight for an older parent who lives alone. Her bedside pillow notices
when she gets up in the night and doesn't come back, checks on her by voice, and alerts her family
one after another until someone answers. This agent decides the **order**: every evening at 9pm it
asks each family member's agent, all at the same time, "can your person be called first tonight?",
and puts the available people on call.

## Try it

| Say | It does |
|---|---|
| "plan tonight" | asks every family agent now (in parallel, 30 s to answer) and reports tonight's order |
| "what's happening with Mum's pillow?" | whether she's in bed, the night state, who's on call, the last roster |

Example:

> **You:** plan tonight
> **Coordinator:** Tonight's watch for Margaret: Szymon: off call (Szymon is away: in Denver); Sarah
> Test: on call (Sarah has no plans noted).

## How it works

- **Agents asking agents.** Family agents ([Sarah's](https://agentverse.ai/agents/details/agent1qfazxg7rlwfwj9z5u2vvan8uk6mcgeecyd7wh49taktaarwjxw5kvatzd7h/profile),
  [Szymon's](https://agentverse.ai/agents/details/agent1qtjfwjlsagy8jmxp20dx523avn2mmpygrf58hczmd5xsr235cvusjhwhe8d/profile))
  join with `JoinRoster`. The coordinator only accepts people who really look after her (checked
  against the pillow's API). At 9pm it sends `AvailabilityRequest` to all of them at once, and
  each answers `AvailabilityReply` from what its person told it.
- **Plain code, no LLM.** Available → on call, away → off call, no answer → left as it was.
- **Safe by construction.** The pillow uses the order only to decide who to try *first*; it still
  alerts every family member in the end. Its Guardian never lets the last person go off call. So
  agents can make help come sooner, never later, and if this agent is down the pillow works
  exactly as before.

Protocols: Agent Chat Protocol, `pillow-watch-roster` 0.1.0 (`JoinRoster`, `AvailabilityRequest`,
`AvailabilityReply`). Built with uAgents, used through ASI:One, part of the Cal Hacks 13.0 agentic
pillow.
