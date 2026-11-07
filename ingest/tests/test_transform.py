"""Unit tests for ingest/transform.py.

Score, level and stat examples are real values from the pinned data (docs/data-audit.md,
docs/quality-report.md, and the decision review of 2026-11-07); expected results follow from
the rules in docs/decisions.md, not from running the code.
"""

import datetime as dt

import pytest

from ingest.transform import (
    STAT_FIELDS,
    classify_event,
    games_in_score,
    parse_date,
    player_row,
    result_type,
    sets_won_lost,
    stats_problem,
    transform_file,
)

SPECIAL = {
    "Tour Finals": ("F", False),
    "Laver Cup": ("A", True),
    "Tokyo Olympics": ("O", False),
    "NextGen Finals": ("F", True),
}

# A valid side: 80 serve points, 50 first serves in (35 won), 30 second-serve points
# (15 won, 3 double faults), 4 aces, 12 service games, 2 of 5 break points saved.
GOOD = {"ace": 4, "df": 3, "svpt": 80, "1stIn": 50, "1stWon": 35, "2ndWon": 15, "SvGms": 12, "bpSaved": 2, "bpFaced": 5}
NO_SERVE = {"ace": 0, "df": 0, "svpt": 0, "1stIn": 0, "1stWon": 0, "2ndWon": 0, "SvGms": 0, "bpSaved": 0, "bpFaced": 0}


def side(**overrides):
    values = {**GOOD, **overrides}
    return [values[name] for name in STAT_FIELDS]


def raw_row(**overrides):
    row = {
        "tourney_id": "2025-0339", "tourney_name": "Brisbane", "surface": "Hard",
        "tourney_level": "A", "tourney_date": "20241229", "match_num": "300",
        "winner_id": "1", "loser_id": "2", "score": "6-4 7-6(5)", "best_of": "3",
        "round": "F", "minutes": "95", "winner_rank": "20", "loser_rank": "30",
    }  # fmt: skip
    for prefix, stats in (("w", GOOD), ("l", {**GOOD, "svpt": 70})):
        for name, value in stats.items():
            row[f"{prefix}_{name}"] = str(value)
    row.update(overrides)
    return row


def identity(player_id):
    return int(player_id) if player_id.isdigit() else None


def transform(rows, source="sackmann", season=2025):
    return transform_file(rows, source, season, identity, SPECIAL)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        ("6-4 7-6(5)", "completed"),
        ("7-5 6-1 0-0 RET", "retired"),  # Sackmann 2025 Australian Open format
        ("7-5 6-1 RET", "retired"),  # TML format for the same match
        ("W/O", "walkover"),
        ("6-3 2-1 DEF", "defaulted"),
        ("6-4 3-0 ABD", "unknown"),  # abandoned Davis Cup match
        ("6-2 5-7 [0-1]", "unknown"),  # Davis Cup: the listed winner lost the match tiebreak
        ("", "unknown"),
        ("6-4 3-6 [10-8]", "completed"),  # match tiebreak instead of a third set
    ],
)
def test_result_type(score, expected):
    assert result_type(score) == expected


def test_sets_and_games_in_score():
    assert sets_won_lost("6-7(5) 7-6(2) 6-4") == (2, 1)
    assert sets_won_lost("6-4 xx") is None
    assert games_in_score("6-7(5) 7-6(2) 6-4") == (36, 2)  # 13 + 13 + 10
    assert games_in_score("6-4 3-6 [10-8]") == (19, 0)  # the bracketed match tiebreak isn't a set


@pytest.mark.parametrize(
    ("source_level", "name", "expected"),
    [
        ("A", "Tour Finals", ("F", False)),  # coded A in 2023
        ("F", "Tour Finals", ("F", False)),
        ("A", "Tokyo Olympics", ("O", False)),  # coded A in 2021
        ("A", "Laver Cup", ("A", True)),
        ("250", "Brisbane", ("A", False)),  # TML splits A into 250 and 500
        ("500", "Basel", ("A", False)),
        ("D", "Davis Cup Finals", ("D", False)),  # Davis Cup comes from the level, never the name
        ("M", "Miami Masters", ("M", False)),
        ("A", "Next Gen ATP Finals", None),  # special-looking name not in the table
        ("F", "Some New Finals", None),
        ("C", "Some Challenger", None),
    ],
)
def test_classify_event(source_level, name, expected):
    assert classify_event(source_level, name, SPECIAL) == expected


def test_parse_date_rejects_partial_dates():
    assert parse_date("20250131") == dt.date(2025, 1, 31)
    assert parse_date("19850000") is None
    assert parse_date("20250230") is None
    assert parse_date("") is None


def test_stats_problem_accepts_valid_stats():
    assert stats_problem(side(), side(), "6-4 6-4") is None


def test_only_a_match_cut_short_may_have_a_player_without_serve_points():
    no_serve = [NO_SERVE[name] for name in STAT_FIELDS]
    assert stats_problem(side(), no_serve, "1-0 RET") is None
    # Davis Cup 2017 AUS v USA: Jack Sock has 0 serve points in a completed four-set match.
    assert "no serve points in a match that wasn't cut short" in stats_problem(side(), no_serve, "6-3 3-6 7-6(4) 6-4")


@pytest.mark.parametrize(
    ("stats", "score", "fragment"),
    [
        # TML Australian Open 2026 retirements: serve points but 0 service games.
        (side(SvGms=0), "6-1 6-1 RET", "serve points but no service games"),
        # Davis Cup 2016 PAR v VEN, 6-1 6-0: 26 serve points can't cover 7 service games (28 needed).
        (side(svpt=26, SvGms=7, **{"1stIn": 16, "1stWon": 12, "2ndWon": 5}, df=1, ace=2), "6-1 6-0", "fewer serve points than its service games need"),
        # Wimbledon 2017, 5-0 RET: 8 serve points over 3 service games, even allowing an unfinished game (9 needed).
        (side(svpt=8, SvGms=3, **{"1stIn": 5, "1stWon": 4, "2ndWon": 1}, df=0, ace=1, bpSaved=0, bpFaced=0), "5-0 RET", "fewer serve points"),
        (side(**{"1stIn": 81}), "6-4 6-4", "first serves in > serve points"),
        (side(**{"1stWon": 51}), "6-4 6-4", "first-serve points won > first serves in"),
        (side(**{"2ndWon": 28}), "6-4 6-4", "second-serve points won + double faults"),  # 28 + 3 > 30
        (side(bpSaved=6), "6-4 6-4", "break points saved > break points faced"),
        (side(ace=51), "6-4 6-4", "aces > serve points won"),
        (side(ace=-1), "6-4 6-4", "negative stat"),
        (side(ace=None), "6-4 6-4", "missing"),
    ],
)
def test_stats_problem_flags_impossible_values(stats, score, fragment):
    assert fragment in stats_problem(stats, side(), score)


def test_tiebreak_counted_as_a_service_game_is_allowed_fewer_points():
    # 12 service games with 2 tiebreaks in the score: 4 * 12 - 3 * 2 = 42 points needed.
    exactly_enough = side(svpt=42, **{"1stIn": 25, "1stWon": 18, "2ndWon": 9}, df=2)
    assert stats_problem(exactly_enough, side(), "7-6(3) 6-7(5) 6-4") is None
    assert stats_problem(exactly_enough, side(), "6-3 6-4 6-4") == "winner: fewer serve points than its service games need"


def test_a_service_game_needs_at_least_one_serve_point_even_when_cut_short():
    # 1 service game and 1 tiebreak in a retired match: 4 - 3 - 3 < 1, so the one-point floor applies.
    no_points_one_game = [{**NO_SERVE, "SvGms": 1}[name] for name in STAT_FIELDS]
    assert stats_problem(side(), no_points_one_game, "7-6(5) 1-0 RET") == "loser: fewer serve points than its service games need"


def test_stats_problem_rejects_zero_serve_points_on_both_sides():
    zero = [NO_SERVE[name] for name in STAT_FIELDS]
    assert stats_problem(zero, zero, "6-4 6-4") == "no serve points recorded for either player"


def test_each_match_becomes_two_mirrored_player_rows():
    result = transform([raw_row()])
    assert len(result.matches) == 1 and not result.rejects
    match = result.matches[0]
    assert match["match_id"] == "2025-0339-300"
    assert match["has_stats"] and match["result_type"] == "completed"
    winner_row, loser_row = result.player_matches
    assert winner_row[:5] == ("2025-0339-300", 1, 2, True, 20)
    assert loser_row[:5] == ("2025-0339-300", 2, 1, False, 30)
    assert winner_row[7] == 80 and loser_row[7] == 70  # serve_points: each side keeps its own


def test_walkover_stats_are_removed_and_logged():
    result = transform([raw_row(score="W/O")])
    assert result.matches[0]["has_stats"] is False
    assert all(value is None for value in result.player_matches[0][5:])
    assert result.rejects[0]["action"] == "stats_removed"


def test_bad_stats_keep_the_match_but_not_the_stats():
    result = transform([raw_row(**{"w_bpSaved": "9"})])
    assert len(result.matches) == 1 and result.matches[0]["has_stats"] is False
    assert result.rejects == [
        {"source": "sackmann", "season": 2025, "row_num": 1, "action": "stats_removed",
         "reason": "winner: break points saved > break points faced"}
    ]  # fmt: skip


def test_unmapped_player_rejects_the_row():
    result = transform([raw_row(loser_id="B0BI")], "tml", 2026)
    assert result.matches == [] and result.player_matches == []
    assert result.rejects[0]["reason"] == "unmapped player id B0BI"


def test_unknown_round_rejects_the_row():
    result = transform([raw_row(round="")], "tml", 2026)
    assert result.rejects[0]["reason"] == "unknown round ''"


def test_tml_dates_become_tournament_start_plus_match_date():
    rows = [raw_row(tourney_date="20260217", match_num="1"), raw_row(tourney_date="20260222", match_num="2")]
    result = transform(rows, "tml", 2026)
    assert [m["tourney_date"] for m in result.matches] == [dt.date(2026, 2, 17)] * 2
    assert [m["match_date"] for m in result.matches] == [dt.date(2026, 2, 17), dt.date(2026, 2, 22)]


def test_player_row_treats_unknown_values_as_missing():
    # Some TML rows are misaligned and put a date in the height column. Dates are made up.
    assert player_row(1, " Jakub  Mensik ", "U", "18000900", "CZE", "18001031") == (1, "Jakub Mensik", None, None, "CZE", None)
    assert player_row(2, "A B", "L", "18000901", "", "193") == (2, "A B", "L", dt.date(1800, 9, 1), None, 193)


def test_exhibitions_come_from_the_special_events_table():
    result = transform([raw_row(tourney_name="Laver Cup", round="RR")])
    assert result.matches[0]["is_exhibition"] is True
    assert result.matches[0]["tourney_level"] == "A"
