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


def write_report(nudge=0.0, summary=lambda serve, h2h: "s"):
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
        report = {"summary": summary(serve, h2h), "strengths": [], "weaknesses": [], "game_plan": [], "key_stats": key_stats,
                  "data_caveats": []}  # fmt: skip
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


def test_report_text_numbers_are_checked_against_its_tool_results(http, use_model):
    """D-031: a number in the written text that no result states is marked, by field and position."""

    def summary(serve, h2h):
        return f"Sinner leads {h2h['record']['wins']}-{h2h['record']['losses']}; Alcaraz serves 123.4% on clay."

    use_model(FakeClient([gather, write_report(summary=summary)]))
    body = http.post("/report", json=REPORT).json()
    text = body["report"]["summary"]
    assert body["status"] == "verified"  # the key numbers decide the status, not the text
    assert body["numbers"] == {
        "checked": 3,
        "not_found": [{"field": "summary", "text": "123.4%", "start": text.index("123.4%"), "end": text.index("123.4%") + 6}],
    }


def test_a_failing_number_check_never_costs_the_report_or_the_answer(http, use_model, monkeypatch, caplog):
    def broken(*args):
        raise RuntimeError("a bug in the check")

    monkeypatch.setattr("api.report.check_report_text", broken)
    monkeypatch.setattr("api.chat.check_answer", broken)
    use_model(FakeClient([gather, write_report()]))
    body = http.post("/report", json=REPORT).json()
    assert (body["status"], body["numbers"]) == ("verified", None)
    use_model(FakeClient(answer_with(lambda serve: "So.")))
    done = events(http.post("/chat", json={"messages": [{"role": "user", "content": "Serve?"}]}))[-1]
    assert done[0] == "done" and done[1]["outcome"] == "completed" and done[1]["numbers"] is None
    assert caplog.text.count("number_check_failed") == 2


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


def answer_with(numbers_text):
    """A chat model that looks up Alcaraz's serve on clay, then answers with `numbers_text(result)`,
    after a first bit of text, so positions run across the whole streamed answer."""

    def respond(request):
        serve = tool_results(request)["t1"]
        return message(text("So: "), text(numbers_text(serve)))

    return [message(text("Checking. "), tool_use("t1", "serve_return_stats", {"player_id": ALCARAZ, "filters": {"surface": "Clay"}})), respond]


def test_chat_done_carries_the_check_on_the_answers_numbers(http, use_model):
    """D-031: numbers come from this turn's tool results or the user's own words; positions are
    in the text as the browser puts it together from the text events."""

    def say(serve):
        rate = serve["stats"]["first_serve_in"]
        return f"{100 * rate['value']:.1f}% ({rate['numerator']} of {rate['denominator']}), not 4321, and 77.7% in tiebreaks."

    use_model(FakeClient(answer_with(say)))
    question = "Did Alcaraz hit 4321 aces on clay?"
    sequence = events(http.post("/chat", json={"messages": [{"role": "user", "content": question}]}))
    answer = "".join(data["delta"] for name, data in sequence if name == "text")
    done = sequence[-1][1]
    assert answer.startswith("Checking. So: ")
    assert done["numbers"]["checked"] == 5
    assert done["numbers"]["not_found"] == [{"text": "77.7%", "start": answer.index("77.7%"), "end": answer.index("77.7%") + 5}]


def percent(rate):
    """One decimal, halves up, from the counts: how the page writes a rate (D-032)."""
    from decimal import ROUND_HALF_UP, Decimal

    return f"{(Decimal(100 * rate['numerator']) / Decimal(rate['denominator'])).quantize(Decimal('0.1'), ROUND_HALF_UP)}%"


def test_chat_writes_cited_numbers_and_says_where_they_are(http, use_model):
    """D-032: a citation split across two pieces of the stream reaches the browser as a number;
    `done` says where each cited number is and carries the evidence it came from."""
    use_model(FakeClient([
        message(tool_use("t1", "serve_return_stats", {"player_id": ALCARAZ, "filters": {"surface": "Clay"}})),
        message(text("He puts [[c1:stats.first_ser"), text("ve_in.value]] in, over [[c1:sample.matches_with_stats]] matches; [[c1:nope]].")),
    ]))  # fmt: skip
    sequence = events(http.post("/chat", json={"messages": [{"role": "user", "content": "How does Alcaraz serve on clay?"}]}))
    deltas = [data["delta"] for name, data in sequence if name == "text"]
    answer, done = "".join(deltas), sequence[-1][1]
    serve = done["evidence"][0]["result"]
    figure, matches = percent(serve["stats"]["first_serve_in"]), str(serve["sample"]["matches_with_stats"])
    assert not any("[[" in d or "]]" in d for d in deltas)
    assert answer == f"He puts {figure} in, over {matches} matches; [?]."
    assert [(answer[c["start"] : c["end"]], c["tool_call_id"], c["field"]) for c in done["citations"]] == [
        (figure, "c1", "stats.first_serve_in.value"), (matches, "c1", "sample.matches_with_stats"),
    ]
    assert [e["tool_call_id"] for e in done["evidence"]] == ["c1"]
    assert done["numbers"]["not_found"] == [{"text": "[?]", "start": answer.index("[?]"), "end": answer.index("[?]") + 3}]


def test_text_held_back_for_a_citation_is_sent_before_an_error(http, use_model):
    """Found by the review: a model error mid-citation lost the held-back text."""
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    calls = {"n": 0}

    def fail_on_second_block():
        calls["n"] += 1
        if calls["n"] == 2:
            raise anthropic.APIConnectionError(request=request)

    use_model(FakeClient([message(text("Partly [[c1:rec"), text("ord.wins]]"))], on_event=fail_on_second_block))
    sequence = events(http.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]}))
    assert "".join(d["delta"] for n, d in sequence if n == "text") == "Partly [[c1:rec"
    assert sequence[-1][0] == "error"


def test_a_cited_score_is_written_in_but_opens_no_card(http, use_model):
    use_model(FakeClient([
        message(tool_use("t1", "head_to_head", {"player_id": SINNER, "opponent_id": ALCARAZ})),
        message(text("Last time: [[c1:matches.0.player_score]], [[c1:record.wins]] wins.")),
    ]))  # fmt: skip
    sequence = events(http.post("/chat", json={"messages": [{"role": "user", "content": "H2H?"}]}))
    done = sequence[-1][1]
    meeting = done["evidence"][0]["result"]["matches"][0]
    answer = "".join(d["delta"] for n, d in sequence if n == "text")
    assert answer.startswith(f"Last time: {meeting['player_score']}, ")
    assert [c["field"] for c in done["citations"]] == ["record.wins"]


def test_positions_are_counted_as_the_browser_counts_them(http, use_model):
    """JavaScript counts an emoji as two units; positions sent to the page count the same way."""
    use_model(FakeClient([
        message(tool_use("t1", "serve_return_stats", {"player_id": ALCARAZ, "filters": {"surface": "Clay"}})),
        message(text("\U0001f3be Serve: [[c1:stats.first_serve_in.value]], and 77.7%.")),
    ]))  # fmt: skip
    sequence = events(http.post("/chat", json={"messages": [{"role": "user", "content": "Serve?"}]}))
    answer, done = "".join(d["delta"] for n, d in sequence if n == "text"), sequence[-1][1]
    utf16 = answer.encode("utf-16-le")
    in_browser = lambda item: utf16[2 * item["start"] : 2 * item["end"]].decode("utf-16-le")  # noqa: E731
    assert [in_browser(c) for c in done["citations"]] == [done["citations"][0]["text"]]
    assert [in_browser(s) for s in done["numbers"]["not_found"]] == ["77.7%"]
    assert done["citations"][0]["start"] == answer.index(done["citations"][0]["text"]) + 1  # one emoji before it


def test_report_text_citations_are_written_in(http, use_model):
    def summary(serve, h2h):
        return "Sinner trails [[c2:record.wins]]-[[c2:record.losses]]; Alcaraz serves [[c1:stats.first_serve_in.value]] in."

    use_model(FakeClient([gather, write_report(summary=summary)]))
    body = http.post("/report", json=REPORT).json()
    serve, h2h = body["evidence"][0]["result"], body["evidence"][1]["result"]
    text = body["report"]["summary"]
    assert text == f"Sinner trails {h2h['record']['wins']}-{h2h['record']['losses']}; Alcaraz serves {percent(serve['stats']['first_serve_in'])} in."
    assert [(c["text_field"], text[c["start"] : c["end"]], c["field"]) for c in body["citations"]] == [
        ("summary", str(h2h["record"]["wins"]), "record.wins"),
        ("summary", str(h2h["record"]["losses"]), "record.losses"),
        ("summary", percent(serve["stats"]["first_serve_in"]), "stats.first_serve_in.value"),
    ]
    assert body["numbers"] == {"checked": 3, "not_found": []}


def test_a_record_made_of_two_records_is_caught(http, use_model):
    """Two real numbers from different records make a record no result states (D-031, D-032)."""

    def summary(serve, h2h):
        return "Sinner trails [[c2:record.wins]]-[[c1:sample.matches_with_stats]]."

    use_model(FakeClient([gather, write_report(summary=summary)]))
    body = http.post("/report", json=REPORT).json()
    assert [s["text"] for s in body["numbers"]["not_found"]] == [body["report"]["summary"][len("Sinner trails ") : -1]]


def test_chat_check_reads_numbers_in_the_pages_language(http, use_model):
    def say(serve):
        return f"{100 * serve['stats']['first_serve_in']['value']:.1f}".replace(".", ",") + " % de primeros saques."

    use_model(FakeClient(answer_with(say)))
    body = {"messages": [{"role": "user", "content": "¿Qué tal saca?"}], "language": "es"}
    assert events(http.post("/chat", json=body))[-1][1]["numbers"] == {"checked": 1, "not_found": []}


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
