"""The agent loop against a scripted fake model (api/tests/fake_model.py) and the real
database: tool results go back to the model, errors become tool results, limits stop the
loop with a clear outcome, and every tool call is logged. No API key or network needed."""

import json
import os

import anthropic
import httpx2
import pytest

from api import agent
from api.agent import Limits, Run, Settings, run_loop
from api.tests.fake_model import FakeClient, message, text, tool_use

SINNER = 206173  # hand 9
SETTINGS = Settings(api_key="test-key", model="claude-sonnet-5-5")
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture(scope="module")
def conn():
    from api.db import connect

    connection = connect()
    yield connection
    connection.close()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def drive(client, conn, settings=SETTINGS, limits=Limits(), clock=None, question="Sinner in 2024?"):
    clock = clock or Clock()
    run = Run(model=settings.model, messages=[{"role": "user", "content": question}], started=clock())
    events = list(run_loop(client, conn, settings, run, "system prompt", limits, clock=clock))
    return run, events


def test_tool_results_go_back_to_the_model(conn):
    client = FakeClient(
        [
            message(tool_use("t1", "surface_splits", {"player_id": SINNER, "filters": {"season": 2024}})),
            message(text("Sinner went 73-6.")),
        ]
    )
    run, events = drive(client, conn)
    assert (run.outcome, run.final_text, run.steps, run.model_calls) == ("completed", "Sinner went 73-6.", 1, 2)
    sent = client.requests[1]["messages"][-1]
    assert sent["role"] == "user" and sent["content"][0]["tool_use_id"] == "t1"
    seen = json.loads(sent["content"][0]["content"])
    assert list(seen)[0] == "tool_call_id" and seen["tool_call_id"] == "c1"  # the ID a report can cite
    assert (seen["overall"]["wins"], seen["overall"]["losses"]) == (73, 6)  # TA, via the real tool
    assert [name for name, _ in events] == ["tool_call", "tool_result", "text"]
    request = client.requests[0]
    assert request["model"] == "claude-sonnet-5-5" and request["output_config"] == {"effort": "low"}
    assert request["cache_control"] == {"type": "ephemeral"} and len(request["tools"]) == 7


def test_tool_errors_go_back_to_the_model_as_error_results(conn):
    client = FakeClient(
        [
            message(
                tool_use("t1", "surface_splits", {"player_id": SINNER, "filters": {"surface": "ice"}}),
                tool_use("t2", "player_profile", {"player_id": 999999999}),
                tool_use("t3", "drop_table", {}),
                tool_use("t4", "head_to_head", {"player_id": SINNER}),
            ),
            message(text("I couldn't find that.")),
        ]
    )
    run, _ = drive(client, conn)
    results = {r["tool_use_id"]: r for r in client.requests[1]["messages"][-1]["content"]}
    assert all(r["is_error"] for r in results.values())
    assert "surface must be one of" in results["t1"]["content"]
    assert "no player with player_id 999999999" in results["t2"]["content"]
    assert "unknown tool 'drop_table'" in results["t3"]["content"]
    assert "missing arguments ['opponent_id']" in results["t4"]["content"]
    assert run.outcome == "completed"


def test_step_limit_stops_the_loop(conn):
    asks_forever = [message(tool_use(f"t{i}", "player_profile", {"player_id": SINNER})) for i in range(9)]
    run, _ = drive(FakeClient(asks_forever), conn)
    assert (run.outcome, run.steps, run.model_calls, len(run.tool_calls)) == ("step_limit", 9, 9, 8)


def test_tool_call_cap_per_request(conn):
    client = FakeClient(
        [
            message(*[tool_use(f"t{i}", "player_profile", {"player_id": SINNER}) for i in range(3)]),
            message(text("done")),
        ]
    )
    run, _ = drive(client, conn, limits=Limits(max_tool_calls=2))
    assert [c.error for c in run.tool_calls.values()] == [None, None, "tool call limit of 2 per request reached"]


def test_token_budget_stops_the_loop(conn):
    settings = Settings(api_key="k", model="claude-sonnet-5-5", token_budget=200)
    script = [message(tool_use(f"t{i}", "player_profile", {"player_id": SINNER}), tokens=(100, 20)) for i in range(3)]
    run, _ = drive(FakeClient(script), conn, settings=settings)
    assert (run.outcome, run.model_calls, run.total_tokens) == ("token_limit", 2, 240)


def test_time_limit_between_calls(conn):
    clock = Clock()

    def slow():
        clock.now += 61  # the first model call uses up the whole 60 seconds

    client = FakeClient([message(tool_use("t1", "player_profile", {"player_id": SINNER}))], on_request=slow)
    run, _ = drive(client, conn, clock=clock)
    assert (run.outcome, run.model_calls) == ("time_limit", 1)
    assert client.options[0]["timeout"] == 60  # the SDK call itself is bounded by the time left


def test_time_limit_mid_stream(conn):
    clock = Clock()

    def tick():
        clock.now += 40

    client = FakeClient([message(text("a"), text("b"), text("c"))], on_event=tick)
    run, events = drive(client, conn, clock=clock)
    assert (run.outcome, run.usage_complete, run.final_text) == ("time_limit", False, "")
    assert [e for e, _ in events] == ["text", "text"]


def test_sdk_timeout_is_a_time_limit(conn):
    timeout = anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    run, _ = drive(FakeClient([timeout]), conn)
    assert run.outcome == "time_limit"


@pytest.mark.parametrize(
    ("stop_reason", "outcome"),
    [("refusal", "model_declined"), ("max_tokens", "output_truncated"), ("pause_turn", "unexpected_stop")],
)
def test_stop_reasons_are_distinct_outcomes(conn, stop_reason, outcome):
    run, _ = drive(FakeClient([message(text("partial"), stop_reason=stop_reason)]), conn)
    assert run.outcome == outcome


def test_api_errors_propagate(conn):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    overloaded = anthropic.InternalServerError("overloaded", response=httpx2.Response(529, request=request), body=None)
    with pytest.raises(anthropic.InternalServerError):
        drive(FakeClient([overloaded]), conn)


@pytest.fixture
def log_lines():
    """The app's log events as parsed JSON lines."""
    import io
    import logging

    from api.logs import JsonFormatter, logger

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield lambda: [json.loads(line) for line in buffer.getvalue().splitlines()]
    logger.removeHandler(handler)


def test_every_tool_call_is_logged(conn, log_lines):
    client = FakeClient(
        [
            message(
                tool_use("t1", "player_profile", {"player_id": SINNER}),
                tool_use("t2", "surface_splits", {"player_id": SINNER, "filters": {"surface": "ice"}}),
            ),
            message(text("done")),
        ]
    )
    run, _ = drive(client, conn)
    lines = log_lines()
    tool_lines = [line for line in lines if line["event"] == "tool_call"]
    assert [(line["tool_call_id"], line["tool_use_id"], line["ok"], line["request_id"]) for line in tool_lines] == [
        ("c1", "t1", True, run.request_id),
        ("c2", "t2", False, run.request_id),
    ]
    assert tool_lines[1]["input"] == {"player_id": SINNER, "filters": {"surface": "ice"}}
    assert [line["call"] for line in lines if line["event"] == "model_call"] == [1, 2]


def test_cost_estimate():
    # Anthropic's pricing page, checked 2026-11-08 (D-021): per million tokens, input / output /
    # 5-minute cache write / cache read are $4 / $20 / $5 / $0.20 on Opus 5.5 and
    # $2 / $10 / $2.50 / $0.10 on Sonnet 5.5.
    tokens = dict(input_tokens=1_000_000, output_tokens=100_000, cache_creation_input_tokens=1_000_000)
    tokens["cache_read_input_tokens"] = 10_000_000
    expected = {"claude-opus-5-5": 4.00 + 2.00 + 5.00 + 2.00, "claude-sonnet-5-5": 2.00 + 1.00 + 2.50 + 1.00}
    for model, cost in expected.items():
        run = Run(model=model, messages=[])
        run.tokens.update(tokens)
        assert run.cost_usd == pytest.approx(cost), model
    assert Run(model="claude-unknown", messages=[]).cost_usd is None  # unknown, never 0


def test_settings_fail_closed():
    assert not Settings.from_env({}).llm_configured
    defaults = Settings.from_env({"ANTHROPIC_API_KEY": "k", "ANTHROPIC_MODEL": "m"})
    assert (defaults.effort, defaults.token_budget) == ("low", 120_000)  # D-022
    with pytest.raises(ValueError, match="ANTHROPIC_EFFORT"):
        Settings.from_env({"ANTHROPIC_EFFORT": "extreme"})
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        Settings(api_key=None, model="m").client()


def test_tool_schemas_match_the_stats_functions():
    import inspect

    from api import stats

    for tool in agent.TOOLS:
        params = list(inspect.signature(getattr(stats, tool["name"])).parameters)[1:]  # after conn
        assert set(tool["input_schema"]["properties"]) == set(params), tool["name"]
