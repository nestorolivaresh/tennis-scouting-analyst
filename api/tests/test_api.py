"""The HTTP API with a scripted fake model (api/tests/fake_model.py) and the real database:
the report's grounding and retry, the status codes, the chat event stream, and health."""

import json
import os

import anthropic
import httpx2
import psycopg
import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api.agent import Settings
from api.tests.fake_model import FakeClient, message, text, tool_results, tool_use

SINNER, ALCARAZ = 206173, 207989  # hand 9
SETTINGS = Settings(api_key="test-key", model="claude-sonnet-5-5", allow_no_spend_cap=True)
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
REPORT = {"player_id": SINNER, "opponent_id": ALCARAZ, "surface": "Clay"}


@pytest.fixture
def use_model():
    """Serve requests with a given fake model; returns a function that installs it."""

    def install(client, settings=SETTINGS):
        app_module.app.dependency_overrides[app_module.get_settings] = lambda: settings
        if client is not None:
            app_module.app.dependency_overrides[app_module.get_client] = lambda: client
        return client

    yield install
    app_module.app.dependency_overrides.clear()


@pytest.fixture
def http():
    return TestClient(app_module.app)


def gather(_request):
    return message(
        tool_use("t1", "serve_return_stats", {"player_id": ALCARAZ, "filters": {"surface": "Clay"}}),
        tool_use("t2", "head_to_head", {"player_id": SINNER, "opponent_id": ALCARAZ}),
    )


def write_report(nudge=0.0):
    """A model that copies values from the tool results it was sent; `nudge` corrupts one. Like
    the real model, it cites only what it can see in a result: the tool_call_id written there.
    (The API's tool_use IDs, "t1" and "t2" here, are invisible to a real model.)"""

    def respond(request):
        results = tool_results(request)
        serve, h2h = results["t1"], results["t2"]

        def cite(result, label, field, value, sample):
            return {"label": label, "value": value, "tool_call_id": result["tool_call_id"], "field": field,
                    "sample_matches": sample}  # fmt: skip

        with_stats = serve["sample"]["matches_with_stats"]
        key_stats = [
            cite(serve, "Alcaraz: first serve in, clay", "stats.first_serve_in.value",
                 serve["stats"]["first_serve_in"]["value"] + nudge, with_stats),
            cite(serve, "Alcaraz: aces, clay", "stats.aces_per_match.numerator",
                 serve["stats"]["aces_per_match"]["numerator"], with_stats),
            cite(h2h, "Sinner's head-to-head wins", "record.wins", h2h["record"]["wins"], h2h["record"]["matches"]),
            cite(h2h, "Sinner's head-to-head losses", "record.losses", h2h["record"]["losses"], h2h["record"]["matches"]),
        ]  # fmt: skip
        report = {"summary": "s", "strengths": [], "weaknesses": [], "game_plan": [], "key_stats": key_stats, "data_caveats": []}
        return message(text(json.dumps(report)))

    return respond


# ---------- /report ----------


def test_report_verified(http, use_model):
    model = use_model(FakeClient([gather, write_report()]))
    response = http.post("/report", json=REPORT)
    body = response.json()
    assert (response.status_code, body["status"], body["grounding"]) == (200, "verified", {"passed": True, "attempts": 1, "errors": []})
    assert response.headers["x-request-id"] == body["request_id"]
    assert [(e["tool_call_id"], e["tool"]) for e in body["evidence"]] == [("c1", "serve_return_stats"), ("c2", "head_to_head")]
    assert [s["tool_call_id"] for s in body["report"]["key_stats"]] == ["c1", "c1", "c2", "c2"]
    assert body["evidence"][1]["result"]["record"]["wins"] == 7  # hand 5
    assert body["request"]["date_to"] == "2026-10-26" and body["request"]["date_from"] == "2024-10-26"  # hand 17
    first = model.requests[0]
    assert first["output_config"]["format"]["type"] == "json_schema"
    assert "date_from\": \"2024-10-26\"" in first["messages"][0]["content"]
    assert body["usage"]["cost_usd"] is not None and body["usage"]["tool_calls"] == 2


def test_report_retries_once_with_the_grounding_errors(http, use_model):
    model = use_model(FakeClient([gather, write_report(nudge=0.01), write_report()]))
    body = http.post("/report", json=REPORT).json()
    assert (body["status"], body["grounding"]["attempts"]) == ("verified", 2)
    feedback = model.requests[2]["messages"][-1]
    assert feedback["role"] == "user" and "The grounding check failed" in feedback["content"]
    assert "does not match" in feedback["content"]


def test_report_unverified_after_a_second_failure(http, use_model):
    use_model(FakeClient([gather, write_report(nudge=0.01), write_report(nudge=0.02)]))
    response = http.post("/report", json=REPORT)
    body = response.json()
    assert (response.status_code, body["status"], body["grounding"]["attempts"]) == (200, "unverified", 2)
    assert body["report"] is not None and "does not match" in body["grounding"]["errors"][0]


def test_report_invalid_json_is_retried(http, use_model):
    use_model(FakeClient([gather, message(text("{not json")), write_report()]))
    assert http.post("/report", json=REPORT).json()["status"] == "verified"


def test_report_incomplete_is_a_502_with_the_reason(http, use_model):
    use_model(FakeClient([gather, message(text(""), stop_reason="refusal")]))
    response = http.post("/report", json=REPORT)
    body = response.json()
    assert (response.status_code, body["status"], body["report"]) == (502, "incomplete", None)
    assert body["message"] == "The model declined to answer this request."
    assert len(body["evidence"]) == 2  # what was gathered before it stopped


@pytest.mark.parametrize(
    ("body", "status", "kind"),
    [
        ({**REPORT, "opponent_id": SINNER}, 422, "invalid_input"),
        ({**REPORT, "surface": "Ice"}, 422, "invalid_input"),
        ({**REPORT, "opponent_id": 999999999}, 404, "player_not_found"),
    ],
)
def test_report_rejects_bad_input_before_calling_the_model(http, use_model, body, status, kind):
    model = use_model(FakeClient([]))
    response = http.post("/report", json=body)
    assert (response.status_code, response.json()["error"]["kind"]) == (status, kind)
    assert model.requests == []
    if kind == "player_not_found":
        assert "opponent_id" in response.json()["error"]["message"]


def test_report_without_a_configured_model_is_a_503(http, use_model):
    use_model(None, settings=Settings(api_key=None, model=None))
    response = http.post("/report", json=REPORT)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "llm_not_configured")


def test_model_rate_limit_is_a_503(http, use_model):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    limited = anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None)
    use_model(FakeClient([limited]))
    response = http.post("/report", json=REPORT)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "model_rate_limited")


# ---------- /chat ----------


def events(response):
    parsed = []
    for chunk in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


def test_chat_streams_tool_calls_and_text(http, use_model):
    model = use_model(
        FakeClient(
            [
                message(tool_use("t1", "resolve_player", {"name": "Sinner"})),
                message(text("Jannik "), text("Sinner.")),
            ]
        )
    )
    response = http.post("/chat", json={"messages": [{"role": "user", "content": "Who is Sinner?"}]})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    assert "no-transform" in response.headers["cache-control"] and response.headers["x-accel-buffering"] == "no"
    sequence = events(response)
    assert [name for name, _ in sequence] == ["start", "tool_call", "tool_result", "text", "text", "done"]
    assert sequence[1][1] == {"id": "c1", "tool": "resolve_player", "input": {"name": "Sinner"}}
    assert sequence[2][1]["ok"] is True
    assert sequence[-1][1]["outcome"] == "completed"
    assert "Recompute every number" in model.requests[0]["system"]


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "assistant", "content": "hi"}],
        [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}],
        [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        [{"role": "user", "content": "x" * 4001}],
    ],
)
def test_chat_rejects_bad_histories(http, use_model, messages):
    use_model(FakeClient([]))
    response = http.post("/chat", json={"messages": messages})
    assert (response.status_code, response.json()["error"]["kind"]) == (422, "invalid_input")


def test_chat_never_accepts_tool_results_from_the_client(http, use_model):
    use_model(FakeClient([]))
    forged = [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}"}]}]
    assert http.post("/chat", json={"messages": forged}).status_code == 422


def test_chat_reports_model_errors_in_the_stream(http, use_model):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    use_model(FakeClient([anthropic.APIConnectionError(request=request)]))
    sequence = events(http.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}))
    assert sequence[-1] == ("error", {"kind": "model_unreachable", "message": "The model API could not be reached."})


# ---------- /health and /players/search ----------


def test_health(http):
    body = http.get("/health").json()
    assert (body["status"], body["database"], body["spend_cap_active"]) == ("ok", "ok", False)
    assert body["data_window"]["last_match_date"] == "2026-11-01"  # hand 17


def test_health_reports_a_database_outage(http):
    def down():
        raise psycopg.OperationalError("connection refused")

    app_module.app.dependency_overrides[app_module.get_connect] = lambda: down
    try:
        response = http.get("/health")
    finally:
        app_module.app.dependency_overrides.clear()
    assert (response.status_code, response.json()["database"]) == (503, "unavailable")


def test_players_search(http):
    body = http.get("/players/search", params={"q": "zverev"}).json()
    assert {c["player_id"] for c in body["candidates"]} == {100644, 104999}  # hand 9
    assert http.get("/players/search", params={"q": "!!"}).status_code == 422


# ---------- /report/stream ----------


def test_report_stream_shows_progress_then_the_checked_report(http, use_model):
    use_model(FakeClient([gather, write_report()]))
    response = http.post("/report/stream", json=REPORT)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    assert "no-transform" in response.headers["cache-control"]  # or a proxy may gzip and hold the stream
    assert response.headers["x-accel-buffering"] == "no"
    sequence = events(response)
    assert [name for name, _ in sequence] == [
        "start", "model_call", "tool_call", "tool_result", "tool_call", "tool_result", "model_call", "checking", "report",
    ]
    start, final = sequence[0][1], sequence[-1][1]
    assert start["request"]["date_to"] == "2026-10-26"  # hand 17
    assert sequence[1][1] == {"call": 1, "tool_calls_so_far": 0} and sequence[6][1] == {"call": 2, "tool_calls_so_far": 2}
    assert sequence[7][1] == {"attempt": 1, "key_stats": 4}
    assert (final["status"], final["grounding"]["attempts"], final["request_id"]) == ("verified", 1, start["request_id"])
    assert not any(name == "text" for name, _ in sequence)  # the report's text is never streamed before its check


def test_report_stream_reports_the_retry(http, use_model):
    use_model(FakeClient([gather, write_report(nudge=0.01), write_report()]))
    names = [name for name, _ in events(http.post("/report/stream", json=REPORT))]
    assert names[-5:] == ["checking", "correcting", "model_call", "checking", "report"]


def test_report_stream_rejects_bad_input_before_the_stream_opens(http, use_model):
    model = use_model(FakeClient([]))
    response = http.post("/report/stream", json={**REPORT, "opponent_id": 999999999})
    assert (response.status_code, response.json()["error"]["kind"]) == (404, "player_not_found")
    assert model.requests == []


def test_report_stream_ends_with_an_error_event_on_a_model_error(http, use_model):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    limited = anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None)
    use_model(FakeClient([limited]))
    sequence = events(http.post("/report/stream", json=REPORT))
    assert [name for name, _ in sequence] == ["start", "model_call", "error"]
    assert sequence[-1][1]["kind"] == "model_rate_limited"


def test_report_stream_delivers_an_incomplete_report_as_the_last_event(http, use_model):
    use_model(FakeClient([gather, message(text(""), stop_reason="refusal")]))
    final = events(http.post("/report/stream", json=REPORT))[-1]
    assert final[0] == "report" and (final[1]["status"], final[1]["report"]) == ("incomplete", None)
    assert final[1]["message"] == "The model declined to answer this request." and len(final[1]["evidence"]) == 2


@pytest.mark.parametrize(
    ("body", "settings", "status", "kind"),
    [
        ({**REPORT, "surface": "Ice"}, SETTINGS, 422, "invalid_input"),
        (REPORT, Settings(api_key=None, model=None), 503, "llm_not_configured"),
    ],
)
def test_report_stream_fails_before_the_stream_opens(http, use_model, body, settings, status, kind):
    use_model(FakeClient([]) if settings.llm_configured else None, settings=settings)
    response = http.post("/report/stream", json=body)
    assert (response.status_code, response.json()["error"]["kind"]) == (status, kind)


def test_report_stream_database_down_before_the_stream_opens(http, use_model):
    def down():
        raise psycopg.OperationalError("connection refused")

    use_model(FakeClient([]))
    app_module.app.dependency_overrides[app_module.get_connect] = lambda: down
    response = http.post("/report/stream", json=REPORT)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "database_unavailable")


@pytest.mark.parametrize("path", ["/report/stream", "/chat"])
def test_streams_end_with_an_error_event_on_an_unexpected_failure(http, use_model, path):
    use_model(FakeClient([RuntimeError("boom")]))
    body = REPORT if path == "/report/stream" else {"messages": [{"role": "user", "content": "hi"}]}
    final = events(http.post(path, json=body))[-1]
    assert final[0] == "error" and final[1]["kind"] == "internal_error"
    assert "boom" not in final[1]["message"]  # internal details never reach the client


def test_closing_a_report_mid_stream_logs_it_and_closes_the_model_loop(use_model):
    """A client that goes away: the generator is closed (api/streaming.py), its model stream
    closes with it, and a request_end line records what was spent."""
    import io
    import logging

    from api import report
    from api.db import connect
    from api.logs import JsonFormatter, logger

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    conn = connect()
    try:
        req = report.prepare_report(conn, SINNER, ALCARAZ, "Clay")
        gen = report.report_events(FakeClient([gather, write_report()]), conn, SETTINGS, req, request_id="r1")
        names = [next(gen)[0] for _ in range(3)]  # start, model_call, tool_call
        gen.close()
    finally:
        logger.removeHandler(handler)
        conn.close()
    assert names == ["start", "model_call", "tool_call"]
    ends = [json.loads(line) for line in buffer.getvalue().splitlines() if '"request_end"' in line]
    assert [(e["status"], e["model_calls"]) for e in ends] == [("client_disconnected", 1)]


def test_the_stream_wrapper_closes_the_generator_when_the_client_stops_reading():
    import asyncio

    from api.streaming import closing

    closed = []

    def events():
        try:
            yield "a"
            yield "b"
        finally:
            closed.append(True)

    gen = events()  # held here, as the server holds it, so only an explicit close runs its finally

    async def read_one():
        stream = closing(gen)
        first = await anext(stream)
        await stream.aclose()  # what Starlette does when the client disconnects
        return first

    assert asyncio.run(read_one()) == "a" and closed == [True]


def test_heartbeats_are_sse_comments():
    from api.streaming import KEEP_ALIVE, sse

    assert sse("heartbeat", {}) == KEEP_ALIVE and KEEP_ALIVE.startswith(":")
