"""GET /matchup (D-033) against the real database. Expected values are the direct tool calls in
api/stats.py and the report's own checks, whose numbers are sourced in docs/stat-checks.md
(D-015), so no stat is typed here."""

import json
import os

import anthropic
import psycopg
import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api import report, spend, stats
from api.agent import Settings
from api.db import connect

SINNER, ALCARAZ = 206173, 207989  # hand 9
CLAY = {"player_id": SINNER, "opponent_id": ALCARAZ, "surface": "Clay"}
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


def get(http, **params):
    return http.get("/matchup", params=params)


def as_json(value):
    """The response's JSON form of a tool result (dates become strings)."""
    return json.loads(json.dumps(value, default=str))


def side(conn, player_id, filters):
    return {
        "record": stats.surface_splits(conn, player_id, filters),
        "serve_return": stats.serve_return_stats(conn, player_id, filters),
        "pressure": stats.pressure_stats(conn, player_id, filters),
        "set_patterns": stats.set_patterns(conn, player_id, filters),
        "shots": stats.shot_patterns(conn, player_id, filters),
    }


# ---------- the composition is honest ----------


@pytest.mark.parametrize(("scope", "surface"), [(None, "Clay"), ("surface", "Clay"), ("all", None)])
def test_every_block_is_the_tools_own_result_under_the_reports_window(http, conn, scope, surface):
    params = {**CLAY, **({"scope": scope} if scope else {})}
    body = get(http, **params).json()
    req = report.prepare_report(conn, SINNER, ALCARAZ, "Clay")
    window = {"surface": surface, "date_from": req.date_from, "date_to": req.date_to}
    assert body["window"] == {"date_from": req.date_from, "date_to": req.date_to}
    assert (body["surface"], body["scope"]) == ("Clay", scope or "surface")
    assert body["player"] == as_json(req.player) and body["opponent"] == as_json(req.opponent)
    assert body["data_window"] == as_json(req.window)
    assert body["head_to_head"] == as_json(stats.head_to_head(conn, SINNER, ALCARAZ))
    assert body["sides"] == as_json({"player": side(conn, SINNER, window), "opponent": side(conn, ALCARAZ, window)})


def test_the_window_is_the_reports_two_years(http, conn):
    body = get(http, **CLAY).json()
    newest = stats.data_window(conn)["last_tourney_date"]
    assert body["window"]["date_to"] == newest
    assert body["window"]["date_from"] == report.two_years_before(report.dt.date.fromisoformat(newest)).isoformat()
    filters = body["sides"]["opponent"]["serve_return"]["filters"]
    assert (filters["surface"], filters["date_from"], filters["date_to"]) == ("Clay", body["window"]["date_from"], newest)


def test_the_head_to_head_covers_every_date_and_surface(http):
    h2h = get(http, **CLAY, scope="surface").json()["head_to_head"]
    assert (h2h["filters"]["surface"], h2h["filters"]["date_from"]) == (None, None)
    assert {s["surface"] for s in h2h["by_surface"]} > {"Clay"}


def test_parameters_are_read_like_the_reports(http):
    body = get(http, player_id=str(SINNER), opponent_id=str(ALCARAZ), surface=" clay ", scope=" ALL ").json()
    assert (body["surface"], body["scope"]) == ("Clay", "all")


def test_the_whole_response_reads_one_snapshot(http, monkeypatch):
    seen = []
    real = stats.serve_return_stats

    def spy(conn, *args, **kwargs):
        seen.append(conn.info.transaction_status)
        return real(conn, *args, **kwargs)

    monkeypatch.setattr(stats, "serve_return_stats", spy)
    assert get(http, **CLAY).status_code == 200
    # Each tool opens its own transaction only inside the call, so an open one here is the outer.
    assert len(seen) == 2 and set(seen) == {psycopg.pq.TransactionStatus.INTRANS}


# ---------- errors ----------


@pytest.mark.parametrize(
    ("params", "status", "kind"),
    [
        ({**CLAY, "opponent_id": SINNER}, 422, "invalid_input"),
        ({"player_id": SINNER, "opponent_id": ALCARAZ}, 422, "invalid_input"),
        ({**CLAY, "surface": "Ice"}, 422, "invalid_input"),
        ({**CLAY, "surface": ""}, 422, "invalid_input"),
        ({**CLAY, "scope": "both"}, 422, "invalid_input"),
        ({**CLAY, "scope": ""}, 422, "invalid_input"),
        ({**CLAY, "player_id": "abc"}, 422, "invalid_input"),
        ({"opponent_id": ALCARAZ, "surface": "Clay"}, 422, "invalid_input"),
        ({**CLAY, "opponent_id": 0}, 422, "invalid_input"),
        ({**CLAY, "player_id": 999999999}, 404, "player_not_found"),
        ({**CLAY, "opponent_id": 999999999}, 404, "player_not_found"),
    ],
)
def test_bad_input_gets_the_apps_errors_and_is_not_cached(http, params, status, kind):
    response = get(http, **params)
    assert (response.status_code, response.json()["error"]["kind"]) == (status, kind)
    assert "cache-control" not in response.headers
    if params.get("opponent_id") == 999999999:
        assert "opponent_id" in response.json()["error"]["message"]


class Untouchable:
    """A connection that fails if anything is asked of it."""

    def transaction(self):
        raise AssertionError("the database must not be reached")

    def execute(self, *_args, **_kwargs):
        raise AssertionError("the database must not be reached")

    def close(self):
        pass


def test_a_bad_scope_is_refused_before_any_query(http):
    app_module.app.dependency_overrides[app_module.get_connect] = lambda: Untouchable
    response = get(http, **CLAY, scope="both")
    assert (response.status_code, response.json()["error"]["kind"]) == (422, "invalid_input")


def test_a_database_outage_is_a_503(http):
    def down():
        raise psycopg.OperationalError("connection refused")

    app_module.app.dependency_overrides[app_module.get_connect] = lambda: down
    response = get(http, **CLAY)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "database_unavailable")
    assert "cache-control" not in response.headers


# ---------- caching, cost and routing ----------


def test_the_cache_header_is_sent(http):
    assert get(http, **CLAY).headers["cache-control"] == "public, max-age=300, s-maxage=3600"


def test_nothing_in_the_response_varies_by_caller(http):
    first = get(http, **CLAY)
    caller = {"Authorization": "Bearer x", "Cookie": "a=b", "X-Forwarded-For": "203.0.113.9"}
    second = http.get("/matchup", params=CLAY, headers=caller)
    assert first.content == second.content
    assert not {"set-cookie", "vary"} & set(second.headers)


def test_no_model_client_and_no_spend_reservation(http, monkeypatch):
    calls = []

    def record(name):
        def called(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"{name} must not be used by this route")

        return called

    monkeypatch.setattr(anthropic, "Anthropic", record("anthropic.Anthropic"))
    monkeypatch.setattr(Settings, "client", record("Settings.client"))
    monkeypatch.setattr(spend, "reserve", record("spend.reserve"))
    configured = Settings(api_key="test-key", model="claude-sonnet-5-5", daily_spend_cap_usd=1.0)
    app_module.app.dependency_overrides[app_module.get_settings] = lambda: configured
    assert (get(http, **CLAY).status_code, calls) == (200, [])


def test_the_route_works_under_the_api_prefix(http):
    local, deployed = get(http, **CLAY), http.get("/api/matchup", params=CLAY)
    assert deployed.status_code == 200 and deployed.content == local.content
    assert deployed.headers["cache-control"] == local.headers["cache-control"]


def test_no_birth_date_reaches_the_response(http):
    assert "birth_date" not in get(http, **CLAY).text
