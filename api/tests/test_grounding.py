"""The grounding check (api/grounding.py). Tool results come from the real stats layer, and
every expected value is read from those results, never typed in."""

import os

import pytest

from api import stats
from api.agent import ToolCall
from api.grounding import MIN_KEY_STATS, check_report, resolve_path

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


def padded(calls, stat_under_test):
    """A report with the stat under test first, plus enough grounded stats to reach the minimum."""
    good = [stat(calls, "t2", "overall.wins", "overall.matches")] * (MIN_KEY_STATS - 1)
    return report(stat_under_test, *good)


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
    errors = check_report(padded(calls, bad), calls)
    assert len(errors) == 1 and error in errors[0], errors


@needs_db
def test_a_rounded_value_is_not_grounded(calls):
    good = stat(calls, "t1", "stats.first_serve_in.value", "sample.matches_with_stats")
    rounded = {**good, "value": round(good["value"], 2)}
    assert rounded["value"] != good["value"]
    assert "does not match" in check_report(padded(calls, rounded), calls)[0]


@needs_db
def test_too_few_key_stats_fail(calls):
    """Found live: the model couldn't cite its tool calls, returned no key stats, and an empty
    list passed. A report needs at least MIN_KEY_STATS grounded numbers."""
    good = stat(calls, "t1", "stats.first_serve_in.value", "sample.matches_with_stats")
    assert check_report(report(), calls) == ["the report has 0 key stats; it needs at least 4"]
    assert check_report(report(*[good] * (MIN_KEY_STATS - 1)), calls) == ["the report has 3 key stats; it needs at least 4"]
    assert check_report(report(*[good] * MIN_KEY_STATS), calls) == []


def test_a_report_without_key_stats_fails():
    assert check_report({"summary": "x"}, {}) == ["the report has no key_stats list"]
    assert check_report(["not", "a", "report"], {}) == ["the report has no key_stats list"]
    assert "is not an object" in check_report(report("0.6"), {})[0]


@needs_db
def test_new_tools_samples_can_be_cited():
    """Set patterns cite the completed matches they were read from; shot patterns the charted
    matches of their block; tour ranks the matches with stats (D-029, D-030). A live report
    cited 122 completed matches for a set pattern and failed before the count was citable."""
    from api.db import connect

    conn = connect()
    calls = {
        "s": ToolCall("s", "set_patterns", {}, 1, result=stats.set_patterns(conn, ALCARAZ, {"season": 2024})),
        "c": ToolCall("c", "shot_patterns", {}, 1, result=stats.shot_patterns(conn, ALCARAZ, {"season": 2024})),
        "r": ToolCall("r", "tour_comparison", {}, 1, result=stats.tour_comparison(conn, ALCARAZ, {"season": 2024})),
    }
    conn.close()
    completed = calls["s"].result["scores_read"]["completed_matches"]
    assert completed != calls["s"].result["sample"]["matches_counted"]  # the sample exercises the rule
    good = report(
        {**stat(calls, "s", "stats.won_after_losing_first_set.value", "sample.matches_counted"), "sample_matches": completed},
        stat(calls, "c", "rally_length.points_won.10_plus.value", "rally_length.matches"),
        stat(calls, "c", "serve_direction.first_serves_in.ad.t.value", "serve_direction.matches"),
        stat(calls, "r", "stats.return_points_won.rank", "sample.matches_with_stats"),
    )
    assert check_report(good, calls) == []


@needs_db
def test_a_figure_cites_the_count_it_rests_on_not_the_whole_window():
    """D-037: the deepest object on the path with a `matches` decides the sample, or else the
    result's sample, its matches with stats for a rate read from match stats. Found on
    2026-11-24: a charted figure from 75 charted matches would have passed citing the window's 126."""
    from api.db import connect

    conn = connect()
    calls = {
        "c": ToolCall("c", "shot_patterns", {}, 1, result=stats.shot_patterns(conn, ALCARAZ, {"season": 2024})),
        "s": ToolCall("s", "set_patterns", {}, 1, result=stats.set_patterns(conn, ALCARAZ, {"season": 2024})),
        "w": ToolCall("w", "surface_splits", {}, 1, result=stats.surface_splits(conn, ALCARAZ, {"season": 2024})),
        "r": ToolCall("r", "serve_return_stats", {}, 1, result=stats.serve_return_stats(conn, ALCARAZ, {"season": 2022})),
    }
    conn.close()
    charted = calls["c"].result
    grass = next(i for i, row in enumerate(calls["w"].result["surfaces"]) if row["surface"] == "Grass")
    serve_sample = calls["r"].result["sample"]
    # Each case exercises the rule: the wrong count really differs from the right one.
    assert charted["serve_direction"]["matches"] < charted["sample"]["matches_counted"]
    assert calls["s"].result["stats"]["won_after_losing_first_set"]["matches"] < calls["s"].result["sample"]["matches_counted"]
    assert calls["w"].result["surfaces"][grass]["matches"] < calls["w"].result["sample"]["matches_counted"]
    assert serve_sample["matches_with_stats"] < serve_sample["matches_counted"]  # 68 of 70 (hand 13)
    cases = [
        ("c", "serve_direction.first_serves_in.deuce.wide.value", "serve_direction.matches"),
        ("c", "net_points.net_points_won.value", "net_points.matches"),
        ("s", "stats.won_after_losing_first_set.value", "stats.won_after_losing_first_set.matches"),
        ("w", f"surfaces.{grass}.win_rate.value", f"surfaces.{grass}.matches"),
        ("r", "stats.first_serve_in.value", "sample.matches_with_stats"),
    ]
    for call_id, field, right in cases:
        good = stat(calls, call_id, field, right)
        assert check_report(report(*[good] * MIN_KEY_STATS), calls) == [], field
        wrong = {**good, "sample_matches": calls[call_id].result["sample"]["matches_counted"]}
        errors = check_report(report(wrong, *[good] * (MIN_KEY_STATS - 1)), calls)
        assert len(errors) == 1 and "is not a match count from that result" in errors[0], (field, errors)
