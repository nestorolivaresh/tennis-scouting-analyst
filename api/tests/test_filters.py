"""Unit tests for input validation and rate math in api/stats.py. No database needed."""

import datetime as dt

import pytest

from api import stats
from api.stats import Filters, ToolInputError, rate


def test_parse_normalizes_valid_filters():
    parsed = Filters.parse(
        {"surface": "clay", "date_from": "2024-01-01", "season": "2024", "tourney_level": ["g", "M"], "opponent_hand": "l"}
    )
    assert parsed == Filters(
        surface="Clay", date_from=dt.date(2024, 1, 1), season=2024, tourney_level=("G", "M"), opponent_hand="L"
    )
    assert parsed.describe()["date_from"] == "2024-01-01"
    assert parsed.params()["levels"] == ["G", "M"]


def test_parse_accepts_nothing_and_a_single_level():
    assert Filters.parse(None) == Filters()
    assert Filters.parse({"tourney_level": "a"}).tourney_level == ("A",)
    assert Filters.parse({"date_to": dt.datetime(2024, 1, 31, 12)}).date_to == dt.date(2024, 1, 31)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"surface": "ice"}, "surface must be one of"),
        ({"date_from": "31/01/2024"}, "date_from must be a date"),
        ({"date_from": "2024-02-01", "date_to": "2024-01-01"}, "date_from is after date_to"),
        ({"season": "twenty"}, "season must be a year"),
        ({"season": True}, "season must be a year"),
        ({"season": "99999999999"}, "season must be a year"),  # would overflow Postgres INTEGER
        ({"season": "²"}, "season must be a year"),  # a Unicode digit that int() rejects
        ({"season": 2024.5}, "season must be a year"),
        ({"tourney_level": ["G", "Z"]}, "tourney_level must be"),
        ({"tourney_level": []}, "tourney_level must be"),
        ({"tourney_level": 5}, "tourney_level must be"),
        ({"tourney_level": [5]}, "tourney_level must be"),
        ({"opponent_hand": "ambidextrous"}, "opponent_hand must be R or L"),
        ({"include_exhibitions": "yes"}, "include_exhibitions must be true or false"),
        ({"rally_length": 9}, "unknown filter(s): rally_length"),
        (["season", 2024], "filters must be an object"),
        ("season=2024", "filters must be an object"),
    ],
)
def test_parse_rejects_bad_filters(raw, message):
    with pytest.raises(ToolInputError, match=message.replace("(", r"\(").replace(")", r"\)")):
        Filters.parse(raw)


def test_rate_returns_none_for_a_zero_denominator():
    assert rate(0, 0) == {"value": None, "numerator": 0, "denominator": 0, "unit": "fraction"}
    assert rate(None, None)["value"] is None
    assert rate(1, 3) == {"value": 0.3333, "numerator": 1, "denominator": 3, "unit": "fraction"}
    assert rate(259, 68, unit="per_match")["value"] == 3.8088


# These raise before touching the connection, so None stands in for it.
@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: stats.resolve_player(None, "  123 "), "name must contain letters"),
        (lambda: stats.resolve_player(None, None), "name must be text"),
        (lambda: stats.resolve_player(None, "a" * 101), "name must be at most 100 characters"),
        (lambda: stats.recent_form(None, 206173, n=0), "n must be a whole number from 1 to 50"),
        (lambda: stats.recent_form(None, 206173, n=51), "n must be a whole number from 1 to 50"),
        (lambda: stats.recent_form(None, 206173, n="²"), "n must be a whole number"),
        (lambda: stats.player_profile(None, "Sinner"), "player_id must be a whole number"),
        (lambda: stats.player_profile(None, "²"), "player_id must be a whole number"),
        (lambda: stats.player_profile(None, 2**31), "player_id must be a whole number"),
        (lambda: stats.head_to_head(None, 206173, "Alcaraz"), "opponent_id must be a whole number"),
        (lambda: stats.head_to_head(None, 206173, 206173), "must be different players"),
        (lambda: stats.surface_splits(None, 206173, ["x"]), "filters must be an object"),
        (lambda: stats.pressure_stats(None, 206173, {"season": "²"}), "season must be a year"),
    ],
)
def test_argument_checks_happen_before_any_query(call, message):
    with pytest.raises(ToolInputError, match=message):
        call()
