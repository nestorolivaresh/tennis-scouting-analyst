"""Server-sent events for /chat and /report/stream: the wire format, and a wrapper that closes
the event generator as soon as the client goes away (D-019, D-024).

Starlette runs a plain generator in a worker thread and, when the client disconnects, simply
stops asking it for more. The generator then stays suspended, holding its database connection
and, for chat, the model's HTTP stream, until garbage collection. `closing` asks for each
event itself and always closes the generator in the end: right away if it was waiting at a
`yield`, or as soon as the step it was running (a model call, say) returns. Closing it runs
its `finally` blocks, which close the connection, the model stream, and log the request.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import anyio

HEARTBEAT_S = 10.0  # well inside the 30-second idle timeouts common in proxies
KEEP_ALIVE = ": keep-alive\n\n"  # an SSE comment: clients ignore it, proxies see traffic


def sse(event: str, data: dict[str, Any]) -> str:
    if event == "heartbeat":
        return KEEP_ALIVE
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


_END = object()


async def closing(events: Iterator[str]) -> AsyncIterator[str]:
    try:
        while True:
            # Waits for the thread even if the request is cancelled, so the generator is
            # never closed while it is running (that would raise "already executing").
            chunk = await anyio.to_thread.run_sync(next, events, _END)
            if chunk is _END:
                return
            yield chunk
    finally:
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(events.close)
