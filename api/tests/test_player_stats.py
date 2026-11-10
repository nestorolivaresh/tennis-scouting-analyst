"""GET /players/{id}/stats against the real database. Expected values are the direct tool calls
in api/stats.py, whose own numbers are sourced in docs/stat-checks.md (D-015), so no stat is
typed here."""

import json
import os
import re
from pathlib import Path

import anthropic
import psycopg
import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api import spend, stats
from api.agent import Settings
from api.db import connect
from ingest.download import SACKMANN_SEASONS, TML_SEASON

SINNER, ALCARAZ = 206173, 207989  # hand 9
CLAY_2025 = {"surface": "Clay", "season": 2025}
ALL_SEASONS = sorted({*SACKMANN_SEASONS, TML_SEASON}, reverse=True)
ROOT = Path(__file__).parents[2]
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


def get(http, player_id=ALCARAZ, **params):
    return http.get(f"/players/{player_id}/stats", params=params)


def counted_seasons(conn, player_id):
    """The seasons with a counted match, asked of every season loaded, so this doesn't share the
    endpoint's use of the first and last tournament years."""
    return [s for s in ALL_SEASONS if stats.surface_splits(conn, player_id, {"season": s})["overall"]["matches"]]


def keys_in(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from keys_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from keys_in(item)


# ---------- the composition is honest ----------


def expected_blocks(conn, player_id, filters, opponent_id):
    season_only = {"season": filters["season"]} if "season" in filters else {}
    profile = stats.player_profile(conn, player_id)
    del profile["birth_date"]
    return {
        "profile": profile,
        "data_window": stats.data_window(conn),
        "by_surface": stats.surface_splits(conn, player_id, season_only),
        "record": stats.surface_splits(conn, player_id, filters),
        "serve_return": stats.serve_return_stats(conn, player_id, filters),
        "pressure": stats.pressure_stats(conn, player_id, filters),
        "recent_form": stats.recent_form(conn, player_id, 10, filters),
        "career": {"serve_return": stats.serve_return_stats(conn, player_id), "pressure": stats.pressure_stats(conn, player_id)},
        "head_to_head": stats.head_to_head(conn, player_id, opponent_id, filters) if opponent_id else None,
    }


@pytest.mark.parametrize(
    ("filters", "opponent_id"),
    [({}, None), (CLAY_2025, None), (CLAY_2025, SINNER), ({"season": 2024}, SINNER), ({"surface": "Grass"}, None)],
)
def test_each_block_equals_the_direct_tool_call(http, conn, filters, opponent_id):
    params = {**filters, **({"opponent_id": opponent_id} if opponent_id else {})}
    response = get(http, **params)
    assert response.status_code == 200
    body = response.json()
    expected = expected_blocks(conn, ALCARAZ, filters, opponent_id)
    for block, value in expected.items():
        assert body[block] == value, block
    assert set(body) == {*expected, "filters", "seasons"}
    assert body["filters"] == {"surface": filters.get("surface"), "season": filters.get("season")}


def test_the_filters_are_the_parsed_ones(http):
    assert get(http, surface=" clay ", season="2025").json()["filters"] == CLAY_2025


def test_the_whole_response_reads_one_snapshot(http, monkeypatch):
    seen = []
    real = stats.surface_splits

    def spy(conn, *args, **kwargs):
        seen.append(conn.info.transaction_status)
        return real(conn, *args, **kwargs)

    monkeypatch.setattr(stats, "surface_splits", spy)
    assert get(http, **CLAY_2025).status_code == 200
    # Each tool opens its own transaction only inside the call, so an open one here is the outer.
    assert seen and set(seen) == {psycopg.pq.TransactionStatus.INTRANS}


# ---------- birth date ----------


def test_the_birth_date_appears_nowhere(http, conn):
    response = get(http, surface="Clay", opponent_id=SINNER)
    assert "birth_date" not in set(keys_in(response.json()))
    for player_id in (ALCARAZ, SINNER):
        born = stats.player_profile(conn, player_id)["birth_date"]
        assert born is not None and born not in response.text  # or this wouldn't exercise the rule


# ---------- seasons ----------


def test_seasons_are_newest_first_and_stable_under_a_surface_filter(http, conn):
    unfiltered = get(http).json()["seasons"]
    assert [row["season"] for row in unfiltered] == counted_seasons(conn, ALCARAZ)
    for row in unfiltered:
        assert row["overall"] == stats.surface_splits(conn, ALCARAZ, {"season": row["season"]})["overall"]
    for surface in ("Hard", "Clay", "Grass"):
        filtered = get(http, surface=surface).json()["seasons"]
        assert [row["season"] for row in filtered] == [row["season"] for row in unfiltered]
        for row in filtered:
            assert row["overall"] == stats.surface_splits(conn, ALCARAZ, {"surface": surface, "season": row["season"]})["overall"]


def test_seasons_ignore_the_season_filter(http):
    assert get(http, season=2024).json()["seasons"] == get(http).json()["seasons"]


def test_a_season_without_the_surface_has_zero_matches_and_no_rate(http, conn):
    def played_grass(season):
        return any(row["surface"] == "Grass" for row in stats.surface_splits(conn, ALCARAZ, {"season": season})["surfaces"])

    no_grass = [season for season in counted_seasons(conn, ALCARAZ) if not played_grass(season)]
    assert no_grass  # or this wouldn't exercise the rule
    rows = {row["season"]: row["overall"] for row in get(http, surface="Grass").json()["seasons"]}
    for season in no_grass:
        assert (rows[season]["matches"], rows[season]["wins"], rows[season]["losses"]) == (0, 0, 0)
        assert rows[season]["win_rate"]["value"] is None and rows[season]["win_rate"]["denominator"] == 0


def test_a_last_tournament_that_started_the_december_before_keeps_its_season(http, conn):
    """Alejandro Moro Canas' last event started in December 2024 and is in the 2025 season (D-010)."""
    moro_canas = 208279
    assert stats.player_profile(conn, moro_canas)["last_match"]["tourney_date"][:4] == "2024"
    assert 2025 in counted_seasons(conn, moro_canas)  # or this wouldn't exercise the rule
    assert [row["season"] for row in get(http, moro_canas).json()["seasons"]] == counted_seasons(conn, moro_canas)


def test_a_player_whose_only_match_did_not_count_has_no_seasons(http, conn):
    only_uncounted = 212721  # one match loaded, none counted
    assert stats.player_profile(conn, only_uncounted)["matches_loaded"] >= 1
    body = get(http, only_uncounted).json()
    assert body["seasons"] == [] and body["record"]["overall"]["win_rate"]["value"] is None


def test_a_player_with_no_matches_has_no_seasons(http, conn, monkeypatch):
    """Every loaded player has a match today, so the profile of one who doesn't is simulated."""
    empty = {"matches_loaded": 0, "first_tourney_date": None, "last_match": None, "latest_rank": None}
    real = stats.player_profile(conn, ALCARAZ)
    monkeypatch.setattr(stats, "player_profile", lambda *_: {**real, **empty})
    assert get(http).json()["seasons"] == []


# ---------- head to head ----------


def test_head_to_head_is_null_without_an_opponent(http):
    assert get(http).json()["head_to_head"] is None


def test_head_to_head_is_present_with_an_opponent(http):
    block = get(http, opponent_id=SINNER).json()["head_to_head"]
    assert block["tool"] == "head_to_head" and block["opponent"]["player_id"] == SINNER


# ---------- errors ----------


@pytest.mark.parametrize(
    ("player_id", "params", "status", "kind"),
    [
        (ALCARAZ, {"opponent_id": ALCARAZ}, 422, "invalid_input"),
        (ALCARAZ, {"surface": "Ice"}, 422, "invalid_input"),
        (ALCARAZ, {"surface": ""}, 422, "invalid_input"),
        (ALCARAZ, {"season": "abc"}, 422, "invalid_input"),
        (ALCARAZ, {"season": "1800"}, 422, "invalid_input"),
        (ALCARAZ, {"season": ""}, 422, "invalid_input"),
        (ALCARAZ, {"opponent_id": "abc"}, 422, "invalid_input"),
        ("abc", {}, 422, "invalid_input"),
        (0, {}, 422, "invalid_input"),
        (999999999, {}, 404, "player_not_found"),
        (ALCARAZ, {"opponent_id": 999999999}, 404, "player_not_found"),
    ],
)
def test_bad_input_gets_the_apps_errors_and_is_not_cached(http, player_id, params, status, kind):
    response = get(http, player_id, **params)
    assert (response.status_code, response.json()["error"]["kind"]) == (status, kind)
    assert "cache-control" not in response.headers
    if params.get("opponent_id") == 999999999:
        assert "opponent_id" in response.json()["error"]["message"]


def test_a_database_outage_is_a_503(http):
    def down():
        raise psycopg.OperationalError("connection refused")

    app_module.app.dependency_overrides[app_module.get_connect] = lambda: down
    response = get(http)
    assert (response.status_code, response.json()["error"]["kind"]) == (503, "database_unavailable")
    assert "cache-control" not in response.headers


# ---------- caching, cost and routing ----------


def test_the_cache_header_is_sent(http):
    assert get(http).headers["cache-control"] == "public, max-age=300, s-maxage=3600"


def test_nothing_in_the_response_varies_by_caller(http):
    first = get(http, **CLAY_2025)
    caller = {"Authorization": "Bearer x", "Cookie": "a=b", "X-Forwarded-For": "203.0.113.9"}
    second = http.get(f"/players/{ALCARAZ}/stats", params=CLAY_2025, headers=caller)
    assert first.content == second.content
    assert not {"set-cookie", "vary"} & set(second.headers)
    assert "request_id" not in set(keys_in(second.json()))


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
    response = http.get(f"/players/{ALCARAZ}/stats", params=CLAY_2025)
    assert (response.status_code, calls) == (200, [])


def test_the_route_works_under_the_api_prefix(http):
    local, deployed = get(http, **CLAY_2025), http.get(f"/api/players/{ALCARAZ}/stats", params=CLAY_2025)
    assert deployed.status_code == 200 and deployed.content == local.content
    assert deployed.headers["cache-control"] == local.headers["cache-control"]


def test_the_two_route_lists_hold_the_route_and_nothing_else():
    """Each list decides what the public can reach, so an addition here has to be deliberate."""
    rewrites = json.loads((ROOT / "vercel.json").read_text())["rewrites"]
    assert rewrites[-1] == {"source": "/(.*)", "destination": {"service": "web"}}
    assert all(rule["destination"] == {"service": "backend"} for rule in rewrites[:-1])
    assert {rule["source"] for rule in rewrites[:-1]} == {
        "/api/health",
        "/api/players/search",
        "/api/players/:id/stats",
        "/api/report/stream",
        "/api/chat",
    }

    config = (ROOT / "web" / "next.config.ts").read_text()
    routes = re.fullmatch(r".*const ROUTES = \[(.*?)\];.*", config, re.DOTALL)
    assert routes is not None
    assert set(re.findall(r'"([^"]+)"', routes[1])) == {"players/search", "players/:id/stats", "report/stream", "chat"}
