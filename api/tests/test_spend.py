"""The daily spend cap, the request log and the production role (api/spend.py, D-025). Uses
the local database, in a throwaway schema; the fake model never costs anything."""

import json
import os
import threading
from pathlib import Path

import httpx2
import anthropic
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api import app as app_module
from api import spend
from api.agent import Settings
from api.tests.fake_model import FakeClient, message, text, tool_results, tool_use
from infra import neon_setup

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")

SETUP_SQL = (Path(__file__).parents[2] / "infra" / "neon_setup.sql").read_text()
TABLE_SQL = SETUP_SQL[SETUP_SQL.index("CREATE TABLE") : SETUP_SQL.index("GRANT USAGE")]  # the request log, without the grants
SINNER, ALCARAZ = 206173, 207989  # hand 9
REPORT = {"player_id": SINNER, "opponent_id": ALCARAZ, "surface": "Clay"}
CHAT = {"messages": [{"role": "user", "content": "hi"}]}
ESTIMATE = spend.ESTIMATE_USD["/report/stream"]


def capped(cap=1.0, **kwargs):
    return Settings(api_key="test-key", model="claude-sonnet-5-5", daily_spend_cap_usd=cap, **kwargs)


@pytest.fixture
def log_connect():
    """A connection factory whose api_requests is a throwaway table."""
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute("DROP SCHEMA IF EXISTS test_spend CASCADE")
        admin.execute("CREATE SCHEMA test_spend")

    def connect():
        return psycopg.connect(url, row_factory=dict_row, autocommit=True, options="-c search_path=test_spend,public")

    with connect() as conn:
        conn.execute(TABLE_SQL)
    yield connect
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute("DROP SCHEMA test_spend CASCADE")


def rows(connect):
    with connect() as conn:
        return conn.execute("SELECT * FROM api_requests ORDER BY started_at").fetchall()


# ---------- reserve and settle ----------


def test_reserving_counts_toward_the_cap_and_is_refused_past_it(log_connect):
    spend.reserve(log_connect, "r1", "/report/stream", cap_usd=ESTIMATE * 1.5)
    with pytest.raises(spend.DailyLimitReached):
        spend.reserve(log_connect, "r2", "/report/stream", cap_usd=ESTIMATE * 1.5)
    assert [(r["request_id"], float(r["cost_usd"]), r["settled"]) for r in rows(log_connect)] == [("r1", ESTIMATE, False)]


def test_yesterdays_spending_does_not_count(log_connect):
    with log_connect() as conn:
        conn.execute("INSERT INTO api_requests (request_id, endpoint, cost_usd, started_at) VALUES ('old', '/chat', 100, now() - interval '2 days')")
    spend.reserve(log_connect, "r1", "/chat", cap_usd=1.0)  # doesn't raise


def test_requests_arriving_together_cannot_pass_the_cap(log_connect):
    outcomes = []

    def attempt(i):
        try:
            spend.reserve(log_connect, f"r{i}", "/report/stream", cap_usd=ESTIMATE * 3.1)
            outcomes.append("ok")
        except spend.DailyLimitReached:
            outcomes.append("refused")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["ok"] * 3 + ["refused"] * 5


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"cost_usd": 0.02, "usage_complete": True}, 0.02),  # the real cost replaces the estimate
        ({"cost_usd": 0.02, "usage_complete": False}, ESTIMATE),  # unknown tokens: never lowered
        ({"cost_usd": 0.5, "usage_complete": False}, 0.5),  # but can be raised
        ({"cost_usd": None, "usage_complete": False}, ESTIMATE),
    ],
)
def test_settling(log_connect, summary, expected):
    spend.reserve(log_connect, "r1", "/report/stream", cap_usd=10)
    spend.settle(log_connect, "r1", "verified", {"tokens": {"input_tokens": 5, "output_tokens": 7}, "tool_calls": 2, **summary})
    row = rows(log_connect)[0]
    assert (float(row["cost_usd"]), row["status"], row["settled"], row["tokens"], row["tool_calls"]) == (expected, "verified", True, 12, 2)


def test_settling_never_raises():
    def down():
        raise psycopg.OperationalError("connection refused")

    spend.settle(down, "r1", "verified", {})  # logged; the reservation stands


def test_a_database_that_cannot_answer_refuses_the_request():
    def down():
        raise psycopg.OperationalError("connection refused")

    with pytest.raises(spend.SpendTrackingUnavailable):
        spend.reserve(down, "r1", "/chat", cap_usd=1)


# ---------- through the API ----------


@pytest.fixture
def use(log_connect):
    def install(client, settings):
        overrides = app_module.app.dependency_overrides
        overrides[app_module.get_settings] = lambda: settings
        overrides[app_module.get_usage_connect] = lambda: log_connect
        if client is not None:
            overrides[app_module.get_client] = lambda: client
        return client

    yield install
    app_module.app.dependency_overrides.clear()


@pytest.fixture
def http():
    return TestClient(app_module.app)


def gather(_request):
    return message(tool_use("t1", "head_to_head", {"player_id": SINNER, "opponent_id": ALCARAZ}))


def write_report(request):
    h2h = tool_results(request)["t1"]
    cite = lambda field, value: {"label": field, "value": value, "tool_call_id": h2h["tool_call_id"], "field": f"record.{field}",  # noqa: E731
                                 "sample_matches": h2h["record"]["matches"]}  # fmt: skip
    stats = [cite("wins", h2h["record"]["wins"]), cite("losses", h2h["record"]["losses"]), cite("matches", h2h["record"]["matches"]),
             cite("wins", h2h["record"]["wins"])]  # fmt: skip
    return message(text(json.dumps({"summary": "s", "strengths": [], "weaknesses": [], "game_plan": [], "key_stats": stats, "data_caveats": []})))


def last_event(response):
    chunk = response.text.strip().split("\n\n")[-1]
    lines = dict(line.split(": ", 1) for line in chunk.splitlines())
    return lines["event"], json.loads(lines["data"])


def test_a_report_settles_with_its_real_cost(http, use, log_connect):
    use(FakeClient([gather, write_report]), capped())
    event, body = last_event(http.post("/report/stream", json=REPORT))
    assert (event, body["status"]) == ("report", "verified")
    row = rows(log_connect)[0]
    assert (row["request_id"], row["endpoint"], row["status"], row["settled"]) == (body["request_id"], "/report/stream", "verified", True)
    assert float(row["cost_usd"]) == pytest.approx(body["usage"]["cost_usd"], abs=1e-6)
    assert float(row["cost_usd"]) < ESTIMATE  # not left at the estimate


@pytest.mark.parametrize(("path", "body"), [("/report/stream", REPORT), ("/report", REPORT), ("/chat", CHAT)])
def test_over_the_cap_is_refused_before_any_model_call(http, use, log_connect, path, body):
    model = use(FakeClient([]), capped(cap=0.01))  # less than any estimate
    response = http.post(path, json=body)
    assert (response.status_code, response.json()["error"]["kind"]) == (429, "daily_limit_reached")
    assert model.requests == [] and rows(log_connect) == []


def test_bad_input_costs_nothing(http, use, log_connect):
    use(FakeClient([]), capped())
    assert http.post("/report/stream", json={**REPORT, "surface": "Ice"}).status_code == 422
    assert http.post("/chat", json={"messages": []}).status_code == 422
    assert rows(log_connect) == []


def test_no_model_call_when_the_budget_cannot_be_checked(http, use):
    model = use(FakeClient([]), capped())

    def down():
        raise psycopg.OperationalError("connection refused")

    app_module.app.dependency_overrides[app_module.get_usage_connect] = lambda: down
    response = http.post("/report/stream", json=REPORT)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "spend_tracking_unavailable")
    assert model.requests == []


def test_no_cap_refuses_the_model_unless_local_development_opted_out(http, use):
    model = use(FakeClient([]), Settings(api_key="k", model="claude-sonnet-5-5"))
    response = http.post("/chat", json=CHAT)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "spend_cap_not_configured")
    assert model.requests == []


def test_local_use_without_a_cap_records_nothing(http, use, log_connect):
    use(FakeClient([message(text("hello"))]), Settings(api_key="k", model="claude-sonnet-5-5", allow_no_spend_cap=True))
    assert last_event(http.post("/chat", json=CHAT))[0] == "done"
    assert rows(log_connect) == []


def test_a_model_error_settles_with_its_kind(http, use, log_connect):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    limited = anthropic.RateLimitError("slow down", response=httpx2.Response(429, request=request), body=None)
    use(FakeClient([limited]), capped())
    assert last_event(http.post("/chat", json=CHAT))[1]["kind"] == "model_rate_limited"
    assert [(r["status"], r["settled"], float(r["cost_usd"])) for r in rows(log_connect)] == [("model_rate_limited", True, 0.0)]


def test_an_unexpected_failure_keeps_the_reservation(http, use, log_connect):
    use(FakeClient([RuntimeError("boom")]), capped())
    assert last_event(http.post("/report/stream", json=REPORT))[1]["kind"] == "internal_error"
    assert [(r["status"], float(r["cost_usd"])) for r in rows(log_connect)] == [("internal_error", ESTIMATE)]


# ---------- deployment details ----------


def test_routes_work_under_the_api_prefix(http):
    assert http.get("/api/health").json()["database"] == "ok"
    assert http.get("/api/players/search", params={"q": "zverev"}).status_code == 200
    assert http.get("/health").status_code == 200  # and without it, locally


def test_the_upload_keeps_what_the_api_imports_and_never_includes_secrets_or_raw_data():
    """Excluding ingest/ once would have crashed production: api/stats.py imports from it."""
    import ast

    root = Path(__file__).parents[2]
    ignored = {line.strip() for line in (root / ".vercelignore").read_text().splitlines() if line.strip() and not line.startswith("#")}
    imported = set()
    for path in (root / "api").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
    assert "ingest" in imported and "evals" not in imported
    assert not {f"{package}/" for package in imported} & ignored
    assert {".env", ".env.*", "data/"} <= ignored


def test_settings_for_the_cap():
    assert Settings.from_env({"DAILY_SPEND_CAP_USD": "0.5"}).daily_spend_cap_usd == 0.5
    assert Settings.from_env({}).daily_spend_cap_usd is None
    assert Settings.from_env({"ALLOW_NO_SPEND_CAP": "1"}).allow_no_spend_cap and not Settings.from_env({}).allow_no_spend_cap
    for not_opted_out in ("0", "false", ""):  # only the documented value opts out
        assert not Settings.from_env({"ALLOW_NO_SPEND_CAP": not_opted_out}).allow_no_spend_cap
    for bad in ("zero", "0", "-1", "inf"):
        with pytest.raises(ValueError, match="DAILY_SPEND_CAP_USD"):
            Settings.from_env({"DAILY_SPEND_CAP_USD": bad})


def test_the_production_role_can_only_read_stats_and_log_requests():
    """infra/neon_setup.sql, applied inside a transaction that is rolled back."""
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    try:
        conn.execute("DROP ROLE IF EXISTS tennis_app")
        neon_setup.apply(conn, "a quote' in the password")
        assert conn.execute("SELECT rolpassword IS NOT NULL AS has_password, rolcanlogin FROM pg_authid WHERE rolname = 'tennis_app'").fetchone() == {"has_password": True, "rolcanlogin": True}
        conn.execute("CREATE TABLE created_after_setup (id int)")  # as a data load would
        conn.execute("SET LOCAL ROLE tennis_app")

        def refused(sql):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    conn.execute(sql)

        assert conn.execute("SELECT count(*) AS n FROM players").fetchone()["n"] > 0
        conn.execute("SELECT * FROM created_after_setup")  # default privileges cover a reload
        with conn.transaction():
            conn.execute("INSERT INTO api_requests (request_id, endpoint, cost_usd) VALUES ('r', '/chat', 0.05)")
            conn.execute("UPDATE api_requests SET status = 'done' WHERE request_id = 'r'")
        refused("UPDATE matches SET score = NULL")
        refused("DELETE FROM player_matches")
        refused("INSERT INTO players (player_id, full_name) VALUES (1, 'x')")
        refused("DELETE FROM api_requests")
        refused("SELECT * FROM raw.matches")
        refused("DROP TABLE players")
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize(
    "extra_access",
    [
        "CREATE ROLE neon_superuser_stand_in NOLOGIN; GRANT neon_superuser_stand_in TO tennis_app",  # a role made in Neon's Console
        "ALTER ROLE tennis_app CREATEROLE",
    ],
)
def test_the_setup_script_refuses_a_role_with_more_access(extra_access):
    """Neon's docs: a role made in its Console joins neon_superuser, which can write every table."""
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    try:
        conn.execute("DROP ROLE IF EXISTS tennis_app")
        conn.execute("CREATE ROLE tennis_app LOGIN")
        conn.execute(extra_access)
        with pytest.raises(psycopg.errors.RaiseException, match="more access"):
            conn.execute(SETUP_SQL)
    finally:
        conn.rollback()
        conn.close()
