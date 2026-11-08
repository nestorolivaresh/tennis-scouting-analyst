"""The grounding check (api/grounding.py). Tool results come from the real stats layer, and
every expected value is read from those results, never typed in."""

import os

import pytest

from api import stats
from api.agent import ToolCall
from api.grounding import check_report, resolve_path

SINNER, ALCARAZ = 206173, 207989  # hand 9


def test_resolve_path_walks_dicts_and_lists():
    data = {"surfaces": [{"surface": "Hard", "win_rate": {"value": 0.5}}]}
    found, value, seen = resolve_path(data, "surfaces.0.win_rate.value")
    assert (found, value, len(seen)) == (True, 0.5, 5)
    assert resolve_path(data, "surfaces.1.win_rate.value")[0] is False
    assert resolve_path(data, "surfaces.x")[0] is False
    assert resolve_path(data, "")[0] is False


needs_db = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture(scope="module")
def calls():
    from api.db import connect

    conn = connect()
    serve = stats.serve_return_stats(conn, SINNER, {"season": 2024})
    splits = stats.surface_splits(conn, SINNER, {"season": 2024})
    h2h = stats.head_to_head(conn, SINNER, ALCARAZ)
    conn.close()
    return {
        "t1": ToolCall("t1", "serve_return_stats", {}, 1, result=serve),
        "t2": ToolCall("t2", "surface_splits", {}, 1, result=splits),
        "t3": ToolCall("t3", "head_to_head", {}, 1, result=h2h),
        "t4": ToolCall("t4", "player_profile", {}, 1, error="no player with player_id 1"),
    }


def stat(calls, call_id, field, sample_path):
    """A correct key stat: the value at `field`, and the match count at `sample_path`."""
    result = calls[call_id].result
    return {
        "label": field,
        "value": resolve_path(result, field)[1],
        "tool_call_id": call_id,
        "field": field,
        "sample_matches": resolve_path(result, sample_path)[1],
    }


def report(*key_stats):
    return {"summary": "", "strengths": [], "weaknesses": [], "game_plan": [], "key_stats": list(key_stats), "data_caveats": []}


@needs_db
def test_grounded_stats_pass(calls):
    grass = next(i for i, s in enumerate(calls["t2"].result["surfaces"]) if s["surface"] == "Grass")
    h2h_clay = next(i for i, s in enumerate(calls["t3"].result["by_surface"]) if s["surface"] == "Clay")
    good = report(
        stat(calls, "t1", "stats.first_serve_in.value", "sample.matches_with_stats"),
        stat(calls, "t1", "stats.aces_per_match.numerator", "sample.matches_with_stats"),
        stat(calls, "t2", f"surfaces.{grass}.win_rate.value", f"surfaces.{grass}.matches"),  # one surface's count
        stat(calls, "t2", "overall.wins", "overall.matches"),
        stat(calls, "t3", f"by_surface.{h2h_clay}.wins", f"by_surface.{h2h_clay}.matches"),
    )
    assert check_report(good, calls) == []


@needs_db
@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"tool_call_id": "t9"}, "is not a tool call from this run"),
        ({"tool_call_id": "t4"}, "failed, so it has no values"),
        ({"field": "stats.rally_length.value"}, "does not exist in the serve_return_stats result"),
        ({"field": "player.name"}, "not a number"),
        ({"field": "stats.first_serve_in"}, "not a number"),
        ({"value": True}, "does not match"),
        ({"value": "0.6159"}, "does not match"),
        ({"sample_matches": 5}, "is not a match count from that result"),
    ],
)
def test_ungrounded_stats_fail(calls, change, error):
    bad = {**stat(calls, "t1", "stats.first_serve_in.value", "sample.matches_with_stats"), **change}
    errors = check_report(report(bad), calls)
    assert len(errors) == 1 and error in errors[0], errors


@needs_db
def test_a_rounded_value_is_not_grounded(calls):
    good = stat(calls, "t1", "stats.first_serve_in.value", "sample.matches_with_stats")
    rounded = {**good, "value": round(good["value"], 2)}
    assert rounded["value"] != good["value"]
    assert "does not match" in check_report(report(rounded), calls)[0]


def test_a_report_without_key_stats_fails():
    assert check_report({"summary": "x"}, {}) == ["the report has no key_stats list"]
    assert check_report(["not", "a", "report"], {}) == ["the report has no key_stats list"]
    assert "is not an object" in check_report(report("0.6"), {})[0]
