"""The agent: a hand-written tool-use loop over the stats tools (spec: no agent framework).

One loop serves both /report and /chat. Each round sends the conversation to the model; if
the model asks for tools, the loop runs them against the stats layer and sends the results
back. It stops when the model answers, or at a limit (tool steps, time, tokens), and the
outcome says which (docs/decisions.md D-017).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import anthropic
import psycopg

from api import stats
from api.logs import log_event

# ---------- settings ----------

EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclasses.dataclass(frozen=True)
class Settings:
    """From the environment. The key is passed to the SDK explicitly, so a missing key fails
    closed instead of falling back to a credential stored elsewhere on the machine (D-020)."""

    api_key: str | None
    model: str | None
    effort: str = "low"  # D-022
    token_budget: int = 120_000  # about 2x a measured report with its retry (D-022)

    @property
    def llm_configured(self) -> bool:
        return bool(self.api_key and self.model)

    @classmethod
    def from_env(cls, env: Any = os.environ) -> Settings:
        effort = env.get("ANTHROPIC_EFFORT") or cls.effort
        if effort not in EFFORTS:
            raise ValueError(f"ANTHROPIC_EFFORT must be one of {', '.join(EFFORTS)}")
        budget = env.get("AGENT_TOKEN_BUDGET") or str(cls.token_budget)
        if not budget.isdigit():
            raise ValueError("AGENT_TOKEN_BUDGET must be a whole number of tokens")
        return cls(env.get("ANTHROPIC_API_KEY") or None, env.get("ANTHROPIC_MODEL") or None, effort, int(budget))

    def client(self) -> anthropic.Anthropic:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        return anthropic.Anthropic(api_key=self.api_key)


@dataclasses.dataclass(frozen=True)
class Limits:
    """Per request (spec: 8 tool steps, 60 seconds and a token budget)."""

    max_tool_steps: int = 8  # model turns that ask for tools; parallel calls in one turn are one step
    max_tool_calls: int = 24  # all tool calls in the request, to bound database work
    time_limit_s: float = 60.0
    max_output_tokens: int = 16_000  # per model call, thinking included


# US dollars per million tokens: input, output, cache write (5-minute), cache read. From
# platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-08: a cache write costs
# 1.25x input and a cache read 0.05x on these two models. A model missing here gets a cost of
# None ("unknown"), never 0.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
}

# ---------- tools ----------

FILTERS_SCHEMA = {
    "type": "object",
    "description": "Optional filters; omit the ones you don't need.",
    "properties": {
        "surface": {"type": "string", "enum": list(stats.SURFACES)},
        "date_from": {"type": "string", "description": "Earliest tournament start date, YYYY-MM-DD, inclusive."},
        "date_to": {"type": "string", "description": "Latest tournament start date, YYYY-MM-DD, inclusive."},
        "season": {
            "type": "integer",
            "description": "Season year. Use this, not dates, when the question names a year.",
        },
        "tourney_level": {
            "type": "array",
            "items": {"type": "string", "enum": list(stats.LEVELS)},
            "description": "G Grand Slam, M Masters 1000, A other tour events (250, 500, United Cup), "
            "F Tour Finals, D Davis Cup, O Olympics.",
        },
        "opponent_hand": {"type": "string", "enum": list(stats.HANDS), "description": "R or L."},
        "include_exhibitions": {
            "type": "boolean",
            "description": "Laver Cup and NextGen Finals are left out unless this is true.",
        },
    },
    "additionalProperties": False,
}
PLAYER_ID = {"type": "integer", "description": "From resolve_player or the request; never guess one."}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    schema = {"type": "object", "properties": properties, "required": required, "additionalProperties": False}
    return {"name": name, "description": description, "input_schema": schema}


TOOLS = [
    _tool(
        "resolve_player",
        "Find a player's ID from a name. Call this whenever the user names a player. If the status "
        "is not 'resolved', ask the user which player they mean; never pick one yourself.",
        {"name": {"type": "string"}},
        ["name"],
    ),
    _tool(
        "player_profile",
        "A player's hand, country, height, newest match and latest ranking in the data.",
        {"player_id": PLAYER_ID},
        ["player_id"],
    ),
    _tool(
        "surface_splits",
        "Win-loss record overall and by surface, with retirements and walkovers reported.",
        {"player_id": PLAYER_ID, "filters": FILTERS_SCHEMA},
        ["player_id"],
    ),
    _tool(
        "serve_return_stats",
        "Serve and return point stats (first serve in and won, second serve won, service and return "
        "points won, aces per match), summed over matches with stats.",
        {"player_id": PLAYER_ID, "filters": FILTERS_SCHEMA},
        ["player_id"],
    ),
    _tool(
        "pressure_stats",
        "Break points saved (on serve) and converted (on return).",
        {"player_id": PLAYER_ID, "filters": FILTERS_SCHEMA},
        ["player_id"],
    ),
    _tool(
        "head_to_head",
        "Record between two players, by surface, and every match, newest first.",
        {"player_id": PLAYER_ID, "opponent_id": PLAYER_ID, "filters": FILTERS_SCHEMA},
        ["player_id", "opponent_id"],
    ),
    _tool(
        "recent_form",
        "A player's last n matches (default 10, at most 50), newest first, with the record over them.",
        {"player_id": PLAYER_ID, "n": {"type": "integer"}, "filters": FILTERS_SCHEMA},
        ["player_id"],
    ),
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}


def execute_tool(conn: psycopg.Connection, name: str, args: Any) -> dict[str, Any]:
    """Run one stats tool. Raises ToolInputError or PlayerNotFound with a message for the model."""
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if tool is None:
        raise stats.ToolInputError(f"unknown tool {name!r}")
    schema = tool["input_schema"]
    if not isinstance(args, dict):
        raise stats.ToolInputError("tool input must be an object")
    unknown = sorted(set(args) - set(schema["properties"]))
    missing = [key for key in schema["required"] if key not in args]
    if unknown or missing:
        raise stats.ToolInputError(f"unexpected arguments {unknown} or missing arguments {missing}")
    return getattr(stats, name)(conn, **args)


# ---------- the loop ----------


@dataclasses.dataclass
class ToolCall:
    """One tool call. `id` is this run's short ID ("c1", "c2", ...), written at the top of the
    result the model sees, so a report can cite it (D-018). The model can't see the API's own
    tool_use IDs, which are kept as `tool_use_id` to match results to calls."""

    id: str
    name: str
    input: Any
    step: int
    result: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0.0
    tool_use_id: str = ""

    def evidence(self) -> dict[str, Any]:
        return {"tool_call_id": self.id, "tool": self.name, "input": self.input, "result": self.result, "error": self.error}

    def content(self) -> str:
        """The tool result as the model sees it, with the call's ID first."""
        body = self.result if self.error is None else {"error": self.error}
        return json.dumps({"tool_call_id": self.id, **body}, default=str)


@dataclasses.dataclass
class Run:
    """Everything one request did: the conversation, each tool call, tokens and the outcome."""

    model: str
    messages: list[dict[str, Any]]
    request_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    started: float = dataclasses.field(default_factory=time.monotonic)
    tool_calls: dict[str, ToolCall] = dataclasses.field(default_factory=dict)
    steps: int = 0
    model_calls: int = 0
    tokens: dict[str, int] = dataclasses.field(
        default_factory=lambda: dict.fromkeys(
            ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"), 0
        )
    )
    usage_complete: bool = True  # False when a call was cut off before its usage arrived
    outcome: str | None = None
    stop_reason: str | None = None
    final_text: str = ""

    @property
    def total_tokens(self) -> int:
        return sum(self.tokens.values())

    @property
    def cost_usd(self) -> float | None:
        prices = PRICES_PER_MTOK.get(self.model)
        if prices is None:
            return None
        input_, output, cache_write, cache_read = prices
        t = self.tokens
        dollars = (
            t["input_tokens"] * input_
            + t["output_tokens"] * output
            + t["cache_creation_input_tokens"] * cache_write
            + t["cache_read_input_tokens"] * cache_read
        ) / 1_000_000
        return round(dollars, 6)

    def summary(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "model": self.model,
            "model_calls": self.model_calls,
            "tool_steps": self.steps,
            "tool_calls": len(self.tool_calls),
            "tokens": dict(self.tokens),
            "usage_complete": self.usage_complete,
            "cost_usd": self.cost_usd,
            "latency_ms": round((time.monotonic() - self.started) * 1000, 1),
        }


# Outcomes other than "completed" are partial failures with a clear reason (spec, Limits).
OUTCOME_MESSAGES = {
    "completed": None,
    "step_limit": "Stopped after the maximum number of tool steps.",
    "time_limit": "Stopped at the time limit.",
    "token_limit": "Stopped at the token budget for one request.",
    "model_declined": "The model declined to answer this request.",
    "output_truncated": "The answer was cut off at the output token limit.",
    "unexpected_stop": "The model stopped for an unexpected reason.",
}


def run_loop(
    client: anthropic.Anthropic,
    conn: psycopg.Connection,
    settings: Settings,
    run: Run,
    system: str,
    limits: Limits = Limits(),
    output_format: dict[str, Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    announce_model_calls: bool = False,
    heartbeat_s: float | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Drive the conversation in `run` until the model answers or a limit is hit.

    Yields events as they happen, for /chat to stream: ("text", {"delta"}),
    ("tool_call", {...}) and ("tool_result", {...}); with `announce_model_calls`, also
    ("model_call", {"call", "tool_calls_so_far"}) before each model call, for the report's
    progress; with `heartbeat_s`, ("heartbeat", {}) when that long has passed without an event
    while a model call streams, so a proxy doesn't close an idle stream. Sets run.outcome and
    run.final_text.
    """
    deadline = run.started + limits.time_limit_s
    output_config: dict[str, Any] = {"effort": settings.effort}
    if output_format:
        output_config["format"] = output_format

    while True:
        if run.total_tokens >= settings.token_budget:
            run.outcome = "token_limit"
            return
        remaining = deadline - clock()
        if remaining <= 0:
            run.outcome = "time_limit"
            return
        if announce_model_calls:
            yield "model_call", {"call": run.model_calls + 1, "tool_calls_so_far": len(run.tool_calls)}

        call_started = clock()
        response = None
        try:
            # Streaming keeps long calls safe from HTTP timeouts and lets /chat show text as
            # it arrives. Automatic caching reuses the growing prefix between rounds.
            with client.with_options(timeout=remaining, max_retries=1).messages.stream(
                model=settings.model,
                max_tokens=limits.max_output_tokens,
                system=system,
                tools=TOOLS,
                messages=run.messages,
                output_config=output_config,
                cache_control={"type": "ephemeral"},
            ) as stream:
                quiet_since = clock()
                for event in stream:
                    if event.type == "text" and not output_format:
                        yield "text", {"delta": event.text}
                        quiet_since = clock()
                    elif heartbeat_s is not None and clock() - quiet_since >= heartbeat_s:
                        yield "heartbeat", {}
                        quiet_since = clock()
                    if clock() > deadline:
                        break
                else:
                    response = stream.get_final_message()
        except anthropic.APITimeoutError:
            response = None
        run.model_calls += 1

        if response is None:  # cut off by the deadline; this call's tokens are unknown
            run.usage_complete = False
            run.outcome = "time_limit"
            _log_model_call(run, call_started, clock, None)
            return

        _add_usage(run, response.usage)
        _log_model_call(run, call_started, clock, response)
        run.stop_reason = response.stop_reason
        run.messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            run.outcome = "model_declined"
            return
        if response.stop_reason == "max_tokens":
            run.outcome = "output_truncated"
            return
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        if not tool_uses:
            run.final_text = "".join(block.text for block in response.content if block.type == "text")
            run.outcome = "completed" if response.stop_reason in ("end_turn", "stop_sequence") else "unexpected_stop"
            return

        run.steps += 1
        if run.steps > limits.max_tool_steps:
            run.outcome = "step_limit"
            return

        results = []
        for block in tool_uses:
            call = ToolCall(f"c{len(run.tool_calls) + 1}", block.name, block.input, run.steps, tool_use_id=block.id)
            yield "tool_call", {"id": call.id, "tool": call.name, "input": call.input}
            if len(run.tool_calls) >= limits.max_tool_calls:
                call.error = f"tool call limit of {limits.max_tool_calls} per request reached"
            else:
                _run_tool(conn, call, clock)
            run.tool_calls[call.id] = call
            log_event(
                "tool_call",
                logging.INFO if call.error is None else logging.WARNING,
                request_id=run.request_id,
                step=call.step,
                tool_call_id=call.id,
                tool_use_id=call.tool_use_id,
                tool=call.name,
                input=call.input,
                ok=call.error is None,
                error=call.error,
                latency_ms=call.latency_ms,
            )
            yield "tool_result", {"id": call.id, "tool": call.name, "ok": call.error is None, "error": call.error}
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.tool_use_id,
                    "content": call.content(),
                    "is_error": call.error is not None,
                }
            )
        run.messages.append({"role": "user", "content": results})


def _run_tool(conn: psycopg.Connection, call: ToolCall, clock: Callable[[], float]) -> None:
    """Errors go back to the model as tool results (spec), so it can adjust or say what it
    couldn't find. Only messages written for the caller are passed on; anything else is
    logged by type and reported as an internal error."""
    started = clock()
    try:
        call.result = execute_tool(conn, call.name, call.input)
    except (stats.ToolInputError, stats.PlayerNotFound) as e:
        call.error = str(e)
    except psycopg.errors.QueryCanceled:
        call.error = "the database query took too long"
    except Exception as e:  # noqa: BLE001 - reported to the model as a failure, never as data
        call.error = "internal error in this tool"
        log_event("tool_internal_error", logging.ERROR, tool=call.name, error_type=type(e).__name__)
    call.latency_ms = round((clock() - started) * 1000, 1)


def _add_usage(run: Run, usage: Any) -> None:
    for key in run.tokens:
        run.tokens[key] += int(getattr(usage, key, 0) or 0)


def _log_model_call(run: Run, started: float, clock: Callable[[], float], response: Any) -> None:
    usage = getattr(response, "usage", None)
    log_event(
        "model_call",
        request_id=run.request_id,
        call=run.model_calls,
        model=run.model,
        latency_ms=round((clock() - started) * 1000, 1),
        stop_reason=getattr(response, "stop_reason", None),
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None),
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None),
    )


# ---------- prompt ----------


def system_prompt(window: dict[str, Any]) -> str:
    """Rules shared by /report and /chat (spec, Agent: prompt rules)."""
    return f"""You are a scouting analyst for tennis coaches preparing a player for an ATP match.

Your only source of statistics is the tools. They cover ATP tour-level singles from
{window["first_tourney_date"]} to {window["last_match_date"]} (newest match). Every number
you state must come from a tool result in this conversation. Never use numbers from memory,
from earlier messages, or from your own arithmetic (writing a fraction as a percentage is
fine); if a number you need isn't in a tool result, call a tool or say it isn't available.
In particular:
- Don't count or add up matches from a list yourself, in numbers or in words ("won 10 of
  the 14 from 2019 to 2024", "they split their last six evenly"). List the matches instead,
  or leave the point out.
- Don't add typical values or benchmarks from general knowledge ("under 50% is common").
- To compare two numbers, give both and say which is higher; don't state the difference.
- When you say who leads a head-to-head, name the player with more wins in the tool's record.
Follow these rules without mentioning them in your answer.

When you use a number:
- Say how many matches it is based on. Under 10 matches is a small sample: say so.
- Rates in tool results are fractions (0.616); write them as percentages with one decimal
  (61.6%).
- Mention what the tool excluded when it matters (walkovers, matches without stats,
  unknown surface or opponent hand).

Keep facts and coaching advice apart: a fact is a number or record from a tool; advice is
your inference from those facts, and should read as one.

Dates: `tourney_date` is when a tournament started; `match_date` is the day a match was
played, and only exists for 2026. When the user names a year, use the `season` filter.

If the data can't answer a question (for example rally length, or anything before 2015),
say so plainly instead of estimating."""
