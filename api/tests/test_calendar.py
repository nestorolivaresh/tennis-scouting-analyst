"""GET /calendar (D-036) against the real database. Expected values are the direct tool calls in
api/stats.py, whose own numbers are sourced in docs/stat-checks.md (D-015), so no stat is typed
here."""

import json
import os

import anthropic
import psycopg
import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api import spend, stats
from api.agent import Settings
from api.db import connect

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture
def http():
    yield TestClient(app_module.app)
    app_module.app.dependency_overrides.clear()


@pytest.fixture
def conn():
    connection = connect()
    yield connection
    connection.close()


def as_json(value):
    return json.loads(json.dumps(value, default=str))


def test_a_season_is_the_tools_own_result(http, conn):
    body = http.get("/calendar", params={"season": "2025"}).json()
    assert body == {"calendar": as_json(stats.tournament_calendar(conn, 2025)), "history": None}


def test_with_no_season_it_is_the_newest_one_with_tournaments(http, conn):
    newest = max(season for season in range(2015, 2031) if stats.tournament_calendar(conn, season)["count"])
    assert http.get("/calendar").json()["calendar"]["filters"]["season"] == newest


def test_an_event_adds_its_history(http, conn):
    body = http.get("/calendar", params={"season": "2025", "event": "404"}).json()
    assert body["history"] == as_json(stats.tournament_history(conn, 404))
    assert body["calendar"]["filters"]["season"] == 2025


def test_the_whole_response_reads_one_snapshot(http, monkeypatch):
    seen = []
    real = stats.tournament_history

    def spy(conn, *args, **kwargs):
        seen.append(conn.info.transaction_status)
        return real(conn, *args, **kwargs)

    monkeypatch.setattr(stats, "tournament_history", spy)
    assert http.get("/calendar", params={"event": "404"}).status_code == 200
    assert seen == [psycopg.pq.TransactionStatus.INTRANS]


@pytest.mark.parametrize(
    ("params", "status", "kind"),
    [
        ({"season": "abc"}, 422, "invalid_input"),
        ({"season": "1800"}, 422, "invalid_input"),
        ({"season": ""}, 422, "invalid_input"),
        ({"event": "abc"}, 422, "invalid_input"),
        ({"event": "0"}, 422, "invalid_input"),
        ({"event": "99999"}, 404, "tournament_not_found"),
    ],
)
def test_bad_input_gets_the_apps_errors_and_is_not_cached(http, params, status, kind):
    response = http.get("/calendar", params=params)
    assert (response.status_code, response.json()["error"]["kind"]) == (status, kind)
    assert "cache-control" not in response.headers


def test_cached_with_no_model_and_under_the_api_prefix(http, monkeypatch):
    calls = []
    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: calls.append("anthropic"))
    monkeypatch.setattr(spend, "reserve", lambda *a, **k: calls.append("reserve"))
    configured = Settings(api_key="test-key", model="claude-sonnet-5-5", daily_spend_cap_usd=1.0)
    app_module.app.dependency_overrides[app_module.get_settings] = lambda: configured
    local, deployed = http.get("/calendar", params={"season": "2025"}), http.get("/api/calendar", params={"season": "2025"})
    assert (local.status_code, deployed.status_code, calls) == (200, 200, [])
    assert local.content == deployed.content
    assert local.headers["cache-control"] == "public, max-age=300, s-maxage=3600"
