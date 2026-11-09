"""POST /chat: follow-up questions, streamed as server-sent events (spec, API).

The API is stateless, so the client sends the conversation each time. Only plain text turns
are accepted: tool calls and results from earlier turns are never taken from the client, so a
client can't feed the model made-up "tool results". The model calls the tools again for each
question, which also keeps the rule that every number comes from a tool result in this run.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from typing import Any

import anthropic
import psycopg

from api import stats
from api.agent import OUTCOME_MESSAGES, Limits, Run, Settings, run_loop, system_prompt
from api.logs import log_event

MAX_MESSAGES = 21  # ten exchanges plus the new question
MAX_MESSAGE_CHARS = 4_000
MAX_TOTAL_CHARS = 30_000

CHAT_RULES = """

You are answering follow-up questions in a chat. Answer briefly, in plain sentences. When the
user names a player, call resolve_player first; if it doesn't return status "resolved", ask
which player they mean and stop. Recompute every number you use with a tool in this turn, even
one that appeared earlier in the conversation. If the user asks about part of a period, such
as one year of a head-to-head, call the tool again with those dates and quote its record."""


def chat_system_prompt(conn: psycopg.Connection) -> str:
    """The system prompt for chat, shared with the eval runner so the evals test this path."""
    return system_prompt(stats.data_window(conn)) + CHAT_RULES


def validate_history(messages: Any) -> list[dict[str, str]]:
    """The conversation as alternating user and assistant text, ending with the user's question."""
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise stats.ToolInputError(f"messages must be a list of 1 to {MAX_MESSAGES} messages")
    history, total = [], 0
    for i, message in enumerate(messages):
        expected = "user" if i % 2 == 0 else "assistant"
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise stats.ToolInputError(f"messages[{i}] must have exactly 'role' and 'content'")
        if message["role"] != expected:
            raise stats.ToolInputError(f"messages[{i}] must have role {expected!r}; roles alternate from 'user'")
        content = message["content"]
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_MESSAGE_CHARS:
            raise stats.ToolInputError(f"messages[{i}].content must be text of 1 to {MAX_MESSAGE_CHARS} characters")
        total += len(content)
        history.append({"role": expected, "content": content})
    if history[-1]["role"] != "user":
        raise stats.ToolInputError("the last message must be the user's question")
    if total > MAX_TOTAL_CHARS:
        raise stats.ToolInputError(f"the conversation must be at most {MAX_TOTAL_CHARS} characters")
    return history


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def chat_events(
    client: anthropic.Anthropic,
    connect: Callable[[], psycopg.Connection],
    settings: Settings,
    history: list[dict[str, str]],
    request_id: str | None = None,
    limits: Limits = Limits(),
    clock: Callable[[], float] = time.monotonic,
) -> Iterator[str]:
    """Server-sent events: start, then text / tool_call / tool_result as they happen, then
    done (outcome, usage and cost) or error. The connection opens and closes inside the
    stream, because the response outlives the request handler."""
    run = Run(model=settings.model, messages=list(history), started=clock())
    if request_id:
        run.request_id = request_id
    log_event("chat_start", request_id=run.request_id, messages=len(history), chars=sum(len(m["content"]) for m in history))
    yield sse("start", {"request_id": run.request_id})
    try:
        conn = connect()
    except psycopg.OperationalError:
        log_event("request_end", logging.ERROR, request_id=run.request_id, endpoint="/chat", status="database_unavailable")
        yield sse("error", {"kind": "database_unavailable", "message": "The database is unavailable."})
        return
    try:
        for event, data in run_loop(client, conn, settings, run, chat_system_prompt(conn), limits, clock=clock):
            yield sse(event, data)
    except anthropic.APIError as e:
        kind, message = api_error(e)
        log_event("request_end", logging.ERROR, request_id=run.request_id, endpoint="/chat", status=kind, **run.summary())
        yield sse("error", {"kind": kind, "message": message})
        return
    finally:
        conn.close()
    log_event(
        "request_end", logging.INFO if run.outcome == "completed" else logging.WARNING,
        request_id=run.request_id, endpoint="/chat", status=run.outcome, **run.summary(),
    )  # fmt: skip
    yield sse("done", {"outcome": run.outcome, "message": OUTCOME_MESSAGES.get(run.outcome), "usage": run.summary()})


def api_error(error: anthropic.APIError) -> tuple[str, str]:
    """A kind and a message safe to show, for an error from the Anthropic API."""
    if isinstance(error, anthropic.RateLimitError):
        return "model_rate_limited", "The model is rate limited. Try again in a minute."
    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "model_misconfigured", "The server's model credentials were rejected."
    if isinstance(error, anthropic.APIConnectionError):
        return "model_unreachable", "The model API could not be reached."
    if isinstance(error, anthropic.APIStatusError) and error.status_code >= 500:
        return "model_unavailable", "The model API is temporarily unavailable."
    return "model_error", "The model API rejected the request."
