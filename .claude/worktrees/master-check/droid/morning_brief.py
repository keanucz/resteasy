# /// script
# requires-python = ">=3.12"
# dependencies = ["droid-sdk", "httpx>=0.27", "pydantic>=2", "tzdata"]
# ///
"""Morning Brief: a Factory Droid run on a trigger we designed (coord/AGENT_FLOW.md section 6).

At 06:00 in the resident's timezone (or now, with --now) this script:

1. pulls last night from the backend (GET /api/pillows/{id}/night: a plain-code summary, the raw
   events and everything the agents did, with the Guardian's verdicts),
2. writes it into a scratch workspace as files,
3. runs Droid in that workspace with READ-ONLY tools (Read, Grep), low autonomy and a structured
   output: a short family note and a proposed settings diff limited to three whitelisted keys,
4. posts both to POST /api/pillows/{id}/brief. The backend's Guardian clamps the diff
   (checkin_timeout_min 10-30, quiet hours, path_light_pct 0-40) and drops anything else, logs the
   verdict to agent_log, and the family app shows note + diff live.

Droid never touches the database, the device or the family: it reads files and writes an answer.
What it read, planned and produced is printed here and kept in the workspace (brief.md, run.json).

    export FACTORY_API_KEY=...   CHECKIN_TOKEN=<same as backend/.env>
    uv run droid/morning_brief.py --now                              # once, for the demo
    uv run droid/morning_brief.py --now --dry                        # don't post the result
    uv run droid/morning_brief.py                                    # wait for 06:00, then daily
    uv run droid/morning_brief.py --now --no-droid                   # plain-code note, no Droid (fallback)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field

DEFAULT_SERVER = "https://pillow.keanuc.net"
WORKSPACE = Path(__file__).resolve().parent / "workspace"
WHITELIST = {"checkin_timeout_min": "minutes, 10-30", "quiet_start": "HH:MM", "quiet_end": "HH:MM",
             "path_light_pct": "0-40"}
RUN_TIMEOUT_S = 240

SYSTEM_PROMPT = """\
You are the Morning Brief droid for a bedside pillow that watches over an older person who lives \
alone. Every morning you read what happened last night and write to her adult child.
You may ONLY read the files in this workspace. You cannot and must not change settings, send \
messages or run commands. Your output is a structured answer: `note` (the family note) and \
`config_diff` (a proposal; a separate Guardian decides whether it is applied).
Rules for the note: 2-4 short sentences in plain, warm English; lead with how the night went; \
name the facts (times, trip lengths, whether she answered the pillow, who was alerted); never \
guess a cause and never name or hint at a medical condition or diagnosis; never give medical \
advice; say when nothing unusual happened. Rules for the diff: only the keys listed in \
SETTINGS.md, only when the night's evidence supports it, with one sentence of `reasoning`; \
an empty diff is the normal outcome."""


class MorningBrief(BaseModel):
    note: str = Field(max_length=700)
    config_diff: dict[str, int | str] = Field(default_factory=dict)
    reasoning: str = Field(default="", max_length=400)


def fetch_night(http: httpx.Client, base: str) -> dict:
    r = http.get(f"{base}/night")
    r.raise_for_status()
    return r.json()


def write_workspace(night: dict) -> Path:
    """Lay last night out as files the droid can read: nothing else is in reach."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for old in WORKSPACE.glob("*"):
        if old.is_file():
            old.unlink()
    s = night["summary"]
    lines = [f"# Last night for {night['resident']}", "",
             f"Window: {night['window_start']} to {night['window_end']}", "",
             f"- lay down: {s['lay_down']}   asleep: {s['asleep']}   up for the day: {s['got_up']}",
             f"- trips out of bed: {s['trip_count']}  (longest {s['longest_trip_min']} min)",
             f"- voice check-ins: {s['checkins']}   family alerted: {s['escalations']} "
             f"(acknowledged by: {', '.join(s['acknowledged_by']) or 'nobody needed to'})",
             f"- restless spells: {s['restless_spells']}", ""]
    if s["trips"]:
        lines += ["## Trips", ""]
        for t in s["trips"]:
            length = "" if t["min"] is None else f", {t['min']} min"
            lines.append(f"- left {t['left']}, back {t['back'] or 'not yet'}{length}")
        lines.append("")
    lines += ["## Unusual", ""] + ([f"- {u}" for u in s["unusual"]] or ["- nothing"]) + [""]
    (WORKSPACE / "SUMMARY.md").write_text("\n".join(lines))
    (WORKSPACE / "events.json").write_text(json.dumps(night["events"], indent=1))
    (WORKSPACE / "agent_log.json").write_text(json.dumps(night["agent_log"], indent=1))
    settings = ["# Settings you may propose to change", "", "Current values:", ""]
    settings += [f"- {k}: {v}" for k, v in night["settings"].items()]
    settings += ["", "Allowed keys and bounds (anything else is dropped by the Guardian):", ""]
    settings += [f"- {k}: {bounds}" for k, bounds in WHITELIST.items()]
    (WORKSPACE / "SETTINGS.md").write_text("\n".join(settings) + "\n")
    return WORKSPACE


def plain_brief(night: dict) -> MorningBrief:
    """No Droid available: a factual note from the summary alone, no diff."""
    s, who = night["summary"], night["resident"]
    if s["trip_count"] == 0:
        note = f"{who} had a quiet night: in bed from {s['lay_down'] or 'the evening'}"
        note += f", up at {s['got_up']}." if s["got_up"] else "."
    else:
        note = (f"{who} got up {s['trip_count']} time{'s' if s['trip_count'] > 1 else ''} in the night, "
                f"the longest trip {s['longest_trip_min']} min.")
        note += f" The pillow checked in {s['checkins']} time{'s' if s['checkins'] != 1 else ''}."
        if s["escalations"]:
            note += f" Family were alerted {s['escalations']} time{'s' if s['escalations'] > 1 else ''}."
    if s["unusual"]:
        note += " Worth knowing: " + "; ".join(s["unusual"]) + "."
    return MorningBrief(note=note, reasoning="plain-code fallback, no Droid run")


async def droid_brief(workspace: Path) -> tuple[MorningBrief, dict]:
    """Run Droid read-only in the workspace and return its structured answer plus run details."""
    from droid_sdk import Autonomy, SessionConfig, run

    config = SessionConfig(autonomy=Autonomy.LOW, restrict_tools=["Read", "Grep"],
                           system_prompt=SYSTEM_PROMPT)
    prompt = ("Read SUMMARY.md, SETTINGS.md and, if you need detail, events.json and agent_log.json. "
              "Then answer with the family note and the settings proposal.")
    result = await run(prompt, cwd=workspace, config=config, output=MorningBrief, timeout=RUN_TIMEOUT_S)
    details = {"success": result.success, "subtype": getattr(result, "subtype", None),
               "session_id": getattr(result, "session_id", None), "text": getattr(result, "text", None),
               "turn_count": getattr(result, "turn_count", None),
               "duration": str(getattr(result, "duration", ""))}
    if not result.success or result.output is None:
        raise RuntimeError(f"Droid run did not succeed: {details}")
    return result.output, details


def post_brief(http: httpx.Client, base: str, token: str, brief: MorningBrief,
               session_id: str | None) -> dict:
    body = {"note": brief.note, "config_diff": brief.config_diff, "droid_session_id": session_id}
    r = http.post(f"{base}/brief", json=body, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def run_once(args: argparse.Namespace) -> None:
    base = f"{args.server.rstrip('/')}/api/pillows/{args.pillow_id}"
    with httpx.Client(timeout=20, headers={"User-Agent": "calhacks-morning-brief/1.0"}) as http:
        night = fetch_night(http, base)
        workspace = write_workspace(night)
        print(f"workspace: {workspace}  ({len(night['events'])} events, {len(night['agent_log'])} log rows)")
        print((workspace / "SUMMARY.md").read_text())
        details: dict = {}
        if args.no_droid:
            brief = plain_brief(night)
        else:
            try:
                brief, details = asyncio.run(droid_brief(workspace))
                print(f"droid run: session {details['session_id']}  turns {details['turn_count']}  "
                      f"{details['duration']}")
                if details.get("text"):
                    print(f"droid said: {details['text']}")
            except Exception as err:  # noqa: BLE001 - the brief must still go out
                print(f"droid unavailable ({type(err).__name__}: {err}); plain-code note instead",
                      file=sys.stderr)
                brief = plain_brief(night)
        print(f"\nNOTE: {brief.note}\nDIFF: {brief.config_diff or '{}'}  ({brief.reasoning})")
        (workspace / "brief.md").write_text(f"{brief.note}\n\nproposed: {json.dumps(brief.config_diff)}\n"
                                            f"reasoning: {brief.reasoning}\n")
        (workspace / "run.json").write_text(json.dumps(details, indent=1, default=str))
        if args.dry:
            print("(dry run: not posted)")
            return
        token = os.environ.get("CHECKIN_TOKEN", "").strip()
        if not token:
            sys.exit("CHECKIN_TOKEN is not set (same value as backend/.env); use --dry to skip posting")
        stored = post_brief(http, base, token, brief, details.get("session_id"))
        print(f"posted: guardian={stored['guardian']} applied={stored['applied']} "
              f"{('reason=' + stored['reason']) if stored.get('reason') else ''}")


def seconds_until(hhmm: str, timezone: str) -> float:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    hh, mm = map(int, hhmm.split(":"))
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default=os.environ.get("PILLOW_SERVER", DEFAULT_SERVER))
    parser.add_argument("--pillow-id", default="mum")
    parser.add_argument("--at", default="06:00", help="daily trigger time in the resident's timezone")
    parser.add_argument("--timezone", default="America/Los_Angeles")
    parser.add_argument("--now", action="store_true", help="run once immediately instead of waiting")
    parser.add_argument("--dry", action="store_true", help="don't post the brief")
    parser.add_argument("--no-droid", action="store_true", help="skip Droid, plain-code note only")
    args = parser.parse_args()
    if args.now:
        run_once(args)
        return
    while True:
        wait = seconds_until(args.at, args.timezone)
        print(f"next Morning Brief at {args.at} {args.timezone} (in {wait / 3600:.1f} h)", flush=True)
        time.sleep(wait)
        try:
            run_once(args)
        except Exception as err:  # noqa: BLE001 - keep the daily trigger alive
            print(f"morning brief failed: {type(err).__name__}: {err}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
