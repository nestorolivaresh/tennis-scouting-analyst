"""POST /report: a structured scouting report, checked against the tool results (D-018)."""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import anthropic
import psycopg

from api import stats
from api.agent import OUTCOME_MESSAGES, Limits, Run, Settings, run_loop, system_prompt
from api.grounding import MIN_KEY_STATS, check_report
from api.logs import log_event

WINDOW_YEARS = 2  # the report's "recent" window, ending at the newest tournament in the data
SMALL_SAMPLE = 10
MAX_ATTEMPTS = 2  # the first report, plus one retry with the grounding errors (spec)

_STRINGS = {"type": "array", "items": {"type": "string"}}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "strengths": _STRINGS,
        "weaknesses": _STRINGS,
        "game_plan": _STRINGS,
        "key_stats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "number"},
                    "tool_call_id": {"type": "string"},
                    "field": {"type": "string"},
                    "sample_matches": {"type": "integer"},
                },
                "required": ["label", "value", "tool_call_id", "field", "sample_matches"],
                "additionalProperties": False,
            },
        },
        "data_caveats": _STRINGS,
    },
    "required": ["summary", "strengths", "weaknesses", "game_plan", "key_stats", "data_caveats"],
    "additionalProperties": False,
}
OUTPUT_FORMAT = {"type": "json_schema", "schema": REPORT_SCHEMA}


def report_prompt(player: dict, opponent: dict, surface: str, date_from: str, date_to: str) -> str:
    p, o = player["player"], opponent["player"]
    return f"""Write a scouting report for the coach of {p["name"]} (player_id {p["player_id"]}), who is
preparing to play {o["name"]} (player_id {o["player_id"]}) on {surface}.

Gather, for both players (call tools for both in parallel where you can):
- surface_splits, serve_return_stats and pressure_stats with filters
  {{"surface": "{surface}", "date_from": "{date_from}", "date_to": "{date_to}"}}. If a player has
  fewer than {SMALL_SAMPLE} matches with stats there, also get serve_return_stats without the
  surface filter (same dates), and say in data_caveats which one you used.
- recent_form with n = 10.
Then call head_to_head once for the pair, with no filters.

Write the report:
- summary: two or three sentences on the matchup.
- strengths and weaknesses: {o["name"]}'s, the opponent being scouted.
- game_plan: three to five concrete points for {p["name"]}, each tied to the facts above.
- key_stats: the {MIN_KEY_STATS} to 8 numbers that matter most, from either player. For each:
  - value: copied exactly from the tool result (fractions as fractions, no rounding),
  - tool_call_id: the tool_call_id written at the top of the tool result that contains it,
    such as "c3",
  - field: the dotted path to it in that result, such as "stats.first_serve_in.value",
    "surfaces.0.win_rate.value" or "record.wins",
  - sample_matches: the matches it is based on (sample.matches_with_stats for serve and
    pressure stats; the record's matches for win-loss records),
  - label: what it is, whose it is, and the filters, e.g. "{o["name"]}: break points saved, {surface}, {date_from[:4]}-{date_to[:4]}".
- data_caveats: small samples, matches without stats, excluded matches, and the data's end date.

In the text, write rates as percentages with one decimal and include only numbers that appear
in tool results."""


def two_years_before(day: dt.date) -> dt.date:
    try:
        return day.replace(year=day.year - WINDOW_YEARS)
    except ValueError:  # 29 February
        return day.replace(year=day.year - WINDOW_YEARS, day=28)


def build_report(
    client: anthropic.Anthropic,
    conn: psycopg.Connection,
    settings: Settings,
    player_id: Any,
    opponent_id: Any,
    surface: Any,
    request_id: str | None = None,
    limits: Limits = Limits(),
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run the agent for a report and check it. Bad input raises ToolInputError, an unknown
    player raises PlayerNotFound, and Anthropic API errors propagate; everything else comes
    back in the result, with status "verified", "unverified" or "incomplete"."""
    pid, oid = stats.parse_player_id(player_id), stats.parse_player_id(opponent_id, "opponent_id")
    if pid == oid:
        raise stats.ToolInputError("player_id and opponent_id must be different players")
    surface = stats.Filters.parse({"surface": surface}).surface
    if surface is None:
        raise stats.ToolInputError("surface is required")
    player = stats.player_profile(conn, pid)
    try:
        opponent = stats.player_profile(conn, oid)
    except stats.PlayerNotFound:
        raise stats.PlayerNotFound(f"no player with opponent_id {oid}") from None
    window = stats.data_window(conn)
    date_to = dt.date.fromisoformat(window["last_tourney_date"])
    date_from = two_years_before(date_to).isoformat()

    prompt = report_prompt(player, opponent, surface, date_from, date_to.isoformat())
    run = Run(model=settings.model, messages=[{"role": "user", "content": prompt}], started=clock())
    if request_id:
        run.request_id = request_id
    log_event(
        "report_start", request_id=run.request_id, player_id=player["player"]["player_id"],
        opponent_id=opponent["player"]["player_id"], surface=surface,
    )  # fmt: skip

    report, errors, attempts = None, [], 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        for _ in run_loop(client, conn, settings, run, system_prompt(window), limits, OUTPUT_FORMAT, clock):
            pass
        if run.outcome != "completed":
            break
        try:
            report = json.loads(run.final_text)
        except json.JSONDecodeError:
            report, errors = None, ["the report is not valid JSON"]
        else:
            errors = check_report(report, run.tool_calls)
        log_event("grounding", request_id=run.request_id, attempt=attempts, passed=not errors, errors=errors)
        if not errors or attempts == MAX_ATTEMPTS:
            break
        run.messages.append(
            {
                "role": "user",
                "content": "The grounding check failed:\n- " + "\n- ".join(errors) + "\n\nFix key_stats so each "
                "value is copied exactly from the named field of that tool call's result, tool_call_id is "
                "the one written at the top of that result, and sample_matches is a match count from it. Call tools again only if you need a value you don't have. "
                "Return the full corrected report.",
            }
        )

    if run.outcome != "completed":
        status = "incomplete"
    else:
        status = "verified" if not errors else "unverified"
    result = {
        "request_id": run.request_id,
        "status": status,
        "message": OUTCOME_MESSAGES.get(run.outcome) if status == "incomplete" else None,
        "report": report if status != "incomplete" else None,
        "grounding": {"passed": status == "verified", "attempts": attempts, "errors": errors},
        "request": {"player": player["player"], "opponent": opponent["player"], "surface": surface,
                    "date_from": date_from, "date_to": date_to.isoformat()},
        "evidence": [call.evidence() for call in run.tool_calls.values()],
        "usage": run.summary(),
    }  # fmt: skip
    log_event(
        "request_end", logging.INFO if status == "verified" else logging.WARNING,
        request_id=run.request_id, endpoint="/report", status=status, **run.summary(),
    )  # fmt: skip
    return result
