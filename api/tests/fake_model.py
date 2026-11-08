"""A scripted stand-in for the Anthropic client, for testing the agent loop without the API.

It implements only what api/agent.py uses: client.with_options(...).messages.stream(**kwargs)
as a context manager that yields text events and returns a final message. Each script item
is a message, a function of the request (to answer from the tool results it was sent), or
an exception to raise.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def tool_use(call_id: str, name: str, args: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=args)


def message(*content: SimpleNamespace, stop_reason: str | None = None, tokens: tuple[int, int] = (100, 20)):
    if stop_reason is None:
        stop_reason = "tool_use" if any(block.type == "tool_use" for block in content) else "end_turn"
    usage = SimpleNamespace(
        input_tokens=tokens[0], output_tokens=tokens[1], cache_creation_input_tokens=0, cache_read_input_tokens=0
    )
    return SimpleNamespace(content=list(content), stop_reason=stop_reason, usage=usage)


def tool_results(request: dict[str, Any]) -> dict[str, Any]:
    """Every tool result sent so far in a request's conversation, by tool call ID."""
    results = {}
    for msg in request["messages"]:
        if msg["role"] == "user" and isinstance(msg["content"], list):
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    results[block["tool_use_id"]] = json.loads(block["content"])
    return results


class FakeStream:
    def __init__(self, final, on_event=None):
        self.final, self.on_event = final, on_event

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.final.content:
            if self.on_event:
                self.on_event()
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)

    def get_final_message(self):
        return self.final


class FakeClient:
    def __init__(self, script, on_event=None, on_request=None):
        self.script, self.on_event, self.on_request = list(script), on_event, on_request
        self.requests: list[dict[str, Any]] = []
        self.options: list[dict[str, Any]] = []
        self.messages = self

    def with_options(self, **options):
        self.options.append(options)
        return self

    def stream(self, **request):
        request = {**request, "messages": list(request["messages"])}  # a snapshot: the loop keeps appending
        self.requests.append(request)
        if self.on_request:
            self.on_request()
        if not self.script:
            raise AssertionError("the agent called the model more often than the script expects")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeStream(item(request) if callable(item) else item, self.on_event)
