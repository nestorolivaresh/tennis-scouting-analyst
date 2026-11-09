"""The HTTP API (spec, API; docs/decisions.md D-019). Run it with:

    uv run --env-file .env uvicorn api.app:app --port 8000

Endpoints are plain `def`, so FastAPI runs them in its thread pool: the stats layer and the
Anthropic client are synchronous, and that keeps the code easy to follow.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import anthropic
import psycopg
from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api import chat, report, spend, stats
from api.agent import Settings
from api.db import connect, connect_usage
from api.logs import configure, log_event
from api.streaming import closing as close_on_disconnect

configure()
app = FastAPI(title="Tennis Scouting Analyst", version="0.6.0")
SETTINGS = Settings.from_env()


class StripApiPrefix:
    """On Vercel the API is served under /api and receives the full path (/api/chat), so the
    prefix comes off here and the same routes work locally and deployed (D-025)."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            path = scope["path"][len("/api") :]
            scope = {**scope, "path": path, "raw_path": path.encode()}
        await self.inner(scope, receive, send)


app.add_middleware(StripApiPrefix)


# ---------- dependencies (tests replace these) ----------


def get_settings() -> Settings:
    return SETTINGS


def get_client(settings: Settings = Depends(get_settings)) -> anthropic.Anthropic:
    if not settings.llm_configured:
        raise LLMNotConfigured()
    return settings.client()


def get_connect():
    return connect


def get_usage_connect():
    return connect_usage


def get_conn(connect_db=Depends(get_connect)) -> Iterator[psycopg.Connection]:
    conn = connect_db()
    try:
        yield conn
    finally:
        conn.close()


# ---------- errors ----------


class LLMNotConfigured(Exception):
    pass


def error(status: int, kind: str, message: str, request: Request) -> JSONResponse:
    body = {"error": {"kind": kind, "message": message}, "request_id": request.state.request_id}
    return JSONResponse(body, status_code=status)


@app.exception_handler(stats.ToolInputError)
def bad_input(request: Request, e: stats.ToolInputError) -> JSONResponse:
    return error(422, "invalid_input", str(e), request)


@app.exception_handler(stats.PlayerNotFound)
def player_not_found(request: Request, e: stats.PlayerNotFound) -> JSONResponse:
    return error(404, "player_not_found", str(e), request)


@app.exception_handler(spend.DailyLimitReached)
def daily_limit_reached(request: Request, e: spend.DailyLimitReached) -> JSONResponse:
    return error(429, "daily_limit_reached", "Today's budget for this demo has been used. Try again tomorrow (UTC).", request)


@app.exception_handler(spend.SpendTrackingUnavailable)
def spend_tracking_unavailable(request: Request, e: spend.SpendTrackingUnavailable) -> JSONResponse:
    return error(503, "spend_tracking_unavailable", "The service can't check today's budget right now. Try again soon.", request)


@app.exception_handler(spend.SpendCapNotConfigured)
def spend_cap_not_configured(request: Request, e: spend.SpendCapNotConfigured) -> JSONResponse:
    return error(503, "spend_cap_not_configured", "The model isn't available: no daily budget is set on this server.", request)


@app.exception_handler(LLMNotConfigured)
def llm_not_configured(request: Request, e: LLMNotConfigured) -> JSONResponse:
    return error(503, "llm_not_configured", "The model isn't configured on this server.", request)


@app.exception_handler(psycopg.OperationalError)
def database_unavailable(request: Request, e: psycopg.OperationalError) -> JSONResponse:
    log_event("database_unavailable", logging.ERROR, request_id=request.state.request_id, error_type=type(e).__name__)
    return error(503, "database_unavailable", "The database is unavailable.", request)


API_ERROR_STATUS = {
    "model_rate_limited": 503,
    "model_unavailable": 503,
    "model_unreachable": 502,
    "model_misconfigured": 500,
    "model_error": 502,
}


@app.exception_handler(anthropic.APIError)
def model_api_error(request: Request, e: anthropic.APIError) -> JSONResponse:
    kind, message = chat.api_error(e)
    log_event("model_api_error", logging.ERROR, request_id=request.state.request_id, kind=kind, error_type=type(e).__name__)
    return error(API_ERROR_STATUS[kind], kind, message, request)


@app.middleware("http")
async def request_log(request: Request, call_next):
    """A request ID for every request, returned in X-Request-ID and on every log line."""
    request.state.request_id = uuid.uuid4().hex
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    log_event(
        "http_request", request_id=request.state.request_id, method=request.method, path=request.url.path,
        status=response.status_code, latency_ms=round((time.monotonic() - started) * 1000, 1),
    )  # fmt: skip
    return response


# ---------- endpoints ----------

# Server-sent events must reach the browser as they happen. A proxy that compresses or buffers
# the response holds every event until the end: the Next.js dev proxy gzipped the stream and
# sent it all at once (found in Milestone 5). `no-transform` tells proxies not to compress or
# change it; `X-Accel-Buffering: no` turns off nginx-style buffering.
STREAM_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


@app.get("/health")
def health(request: Request, settings: Settings = Depends(get_settings), connect_db=Depends(get_connect)) -> JSONResponse:
    """The app is up; the database answers. Doesn't call the model."""
    try:
        conn = connect_db()
        try:
            window = stats.data_window(conn)
        finally:
            conn.close()
    except psycopg.Error as e:
        log_event("health_database_error", logging.ERROR, request_id=request.state.request_id, error_type=type(e).__name__)
        return JSONResponse({"status": "degraded", "database": "unavailable", "llm_configured": settings.llm_configured}, 503)
    return JSONResponse({
        "status": "ok", "database": "ok", "llm_configured": settings.llm_configured,
        "spend_cap_active": settings.daily_spend_cap_usd is not None, "data_window": window,
    })  # fmt: skip


@app.get("/players/search")
def players_search(q: str = Query(...), conn=Depends(get_conn)) -> dict[str, Any]:
    """Autocomplete, with no model call."""
    return stats.search_players(conn, q)


def reserve_budget(endpoint: str, request: Request, settings: Settings, connect_log) -> Callable[[str, dict[str, Any]], None]:
    """Reserve this request's estimated cost before any model call, and return the function
    that records how it ended. No cap means no model calls, unless local development has
    explicitly opted out with ALLOW_NO_SPEND_CAP (D-025)."""
    if settings.daily_spend_cap_usd is None:
        if not settings.allow_no_spend_cap:
            raise spend.SpendCapNotConfigured
        return lambda status, summary: None
    request_id = request.state.request_id
    spend.reserve(connect_log, request_id, endpoint, settings.daily_spend_cap_usd)
    return lambda status, summary: spend.settle(connect_log, request_id, status, summary)


class ReportRequest(BaseModel):
    player_id: int
    opponent_id: int
    surface: str


@app.post("/report")
def post_report(
    body: ReportRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    client: anthropic.Anthropic = Depends(get_client),
    conn=Depends(get_conn),
    connect_log=Depends(get_usage_connect),
) -> JSONResponse:
    req = report.prepare_report(conn, body.player_id, body.opponent_id, body.surface)  # bad input costs nothing
    on_end = reserve_budget("/report", request, settings, connect_log)
    result = report.run_report(client, conn, settings, req, request_id=request.state.request_id, on_end=on_end)
    # A report that didn't finish within the limits is the model's failure to deliver, not the
    # caller's: 502 with the reason and whatever evidence was gathered.
    return JSONResponse(result, status_code=200 if result["status"] != "incomplete" else 502)


@app.post("/report/stream")
def post_report_stream(
    body: ReportRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    client: anthropic.Anthropic = Depends(get_client),
    connect_db=Depends(get_connect),
    connect_log=Depends(get_usage_connect),
) -> StreamingResponse:
    """The same report, with progress as server-sent events (D-019). Bad input and a spent
    budget get their status before the stream opens."""
    conn = connect_db()
    try:
        req = report.prepare_report(conn, body.player_id, body.opponent_id, body.surface)
    finally:
        conn.close()
    on_end = reserve_budget("/report/stream", request, settings, connect_log)
    events = report.report_stream(client, connect_db, settings, req, request_id=request.state.request_id, on_end=on_end)
    return StreamingResponse(close_on_disconnect(events), media_type="text/event-stream", headers=STREAM_HEADERS)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@app.post("/chat")
def post_chat(
    body: ChatRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    client: anthropic.Anthropic = Depends(get_client),
    connect_db=Depends(get_connect),
    connect_log=Depends(get_usage_connect),
) -> StreamingResponse:
    history = chat.validate_history([m.model_dump() for m in body.messages])  # before the stream opens
    on_end = reserve_budget("/chat", request, settings, connect_log)
    events = chat.chat_events(client, connect_db, settings, history, request_id=request.state.request_id, on_end=on_end)
    return StreamingResponse(close_on_disconnect(events), media_type="text/event-stream", headers=STREAM_HEADERS)
