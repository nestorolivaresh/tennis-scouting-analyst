"""Linking charted matches to tour matches, and reading their stats (ingest/charting.py, D-030).
The rows are made up; they need no database."""

import datetime as dt

import pytest

from ingest import charting

PLAYERS = [(1, "Jannik Sinner"), (2, "Carlos Alcaraz"), (3, "Felix Auger-Aliassime"), (4, "Alex Smith"), (5, "Alex Smith")]


def tour(match_id, a, b, round_, day, level="M"):
    return {"match_id": match_id, "winner_id": a, "loser_id": b, "round": round_, "tourney_level": level,
            "tourney_date": dt.date.fromisoformat(day)}  # fmt: skip


def chart(match_id, p1, p2, day, round_):
    return {"match_id": match_id, "Player 1": p1, "Player 2": p2, "Date": day, "Tournament": "X", "Round": round_,
            "Surface": "Hard", "Best of": "3"}  # fmt: skip


MATCHES = [
    tour("canada-qf", 1, 2, "QF", "2024-08-05"),
    tour("cincy-qf", 2, 1, "QF", "2024-08-12"),
    tour("ao-sf", 1, 3, "SF", "2024-01-15", level="G"),
    tour("dc", 1, 2, "RR", "2024-11-21", level="D"),
    tour("early", 1, 2, "F", "2015-01-04"),
]


def links(*rows):
    return {link["chart_id"]: link for link in charting.link_charts(list(rows), PLAYERS, MATCHES)}


def test_a_chart_links_to_the_one_tour_match_with_the_same_players_round_and_dates():
    found = links(chart("a", "Jannik Sinner", "Felix Auger Aliassime", "20240125", "SF"))["a"]
    assert (found["link"], found["match_id"]) == ("linked", "ao-sf")  # hyphen or not, same player


def test_the_date_window_runs_from_14_days_after_the_start_to_3_days_before_it():
    days = {"in": "20240129", "late": "20240130", "early": "20240112", "too-early": "20240111"}  # +14, +15, -3, -4
    # One at a time: two charts of the same tour match would both be dropped as charted twice.
    found = {k: links(chart(k, "Jannik Sinner", "Felix Auger-Aliassime", day, "SF"))[k] for k, day in days.items()}
    assert {k: v["link"] for k, v in found.items()} == {
        "in": "linked", "late": "no_tour_match", "early": "linked", "too-early": "no_tour_match",
    }  # fmt: skip


def test_back_to_back_events_link_to_the_one_that_had_started():
    found = links(
        chart("canada", "Andrey Rublev", "Jannik Sinner", "20240810", "QF"),
        chart("ca", "Carlos Alcaraz", "Jannik Sinner", "20240810", "QF"),  # Canada started, Cincinnati not yet
        chart("cincy", "Jannik Sinner", "Carlos Alcaraz", "20240817", "QF"),  # both started: the later one
    )
    assert found["canada"]["link"] == "name_not_resolved"  # Rublev isn't in PLAYERS
    assert (found["ca"]["link"], found["ca"]["match_id"]) == ("linked", "canada-qf")
    assert (found["cincy"]["link"], found["cincy"]["match_id"]) == ("linked", "cincy-qf")


def test_a_different_round_does_not_link_except_for_a_davis_cup_tie():
    found = links(
        chart("r16", "Jannik Sinner", "Felix Auger-Aliassime", "20240125", "R16"),
        chart("dc", "Jannik Sinner", "Carlos Alcaraz", "20241122", "QF"),
    )
    assert found["r16"]["link"] == "no_tour_match"
    assert (found["dc"]["link"], found["dc"]["match_id"]) == ("linked", "dc")


def test_names_that_match_no_player_or_several_dont_link():
    found = links(
        chart("unknown", "Jannik Sinner", "Nobody Here", "20240125", "SF"),
        chart("two", "Jannik Sinner", "Alex Smith", "20240125", "SF"),
    )
    assert found["unknown"]["link"] == found["two"]["link"] == "name_not_resolved"


def test_charts_before_the_data_and_unreadable_rows_are_kept_with_a_reason():
    found = links(
        chart("old", "Jannik Sinner", "Carlos Alcaraz", "20141231", "F"),
        chart("nodate", "Jannik Sinner", "Carlos Alcaraz", "2024", "F"),
        chart("dup", "Jannik Sinner", "Carlos Alcaraz", "20240810", "QF"),
        {**chart("dup", "Jannik Sinner", "Carlos Alcaraz", "20240810", "QF"), "Surface": "Clay"},
    )
    assert {k: v["link"] for k, v in found.items()} == {"old": "before_data", "nodate": "unreadable_row", "dup": "unreadable_row"}


def test_a_tour_match_charted_twice_keeps_neither_chart():
    found = links(
        chart("one", "Jannik Sinner", "Felix Auger-Aliassime", "20240125", "SF"),
        chart("two", "Felix Auger-Aliassime", "Jannik Sinner", "20240125", "SF"),
    )
    assert {v["link"] for v in found.values()} == {"charted_twice"} and all(v["match_id"] is None for v in found.values())


def serve_rows(chart_id, name, first, second):
    return [
        {"match_id": chart_id, "player": name, "row": row, **dict(zip(charting.SERVE_COLUMNS, map(str, values)))}
        for row, values in (("1", first), ("2", second))
    ]


def rally_row(chart_id, server, row, pts, won1, won2):
    return {"match_id": chart_id, "server": server, "row": row, "pts": str(pts), "pl1_won": str(won1), "pl2_won": str(won2)}


def test_stats_are_read_for_both_players_from_player_ones_rally_rows():
    link = charting.link_charts([chart("a", "Jannik Sinner", "Felix Auger-Aliassime", "20240125", "SF")], PLAYERS, MATCHES)
    serve = serve_rows("a", "Jannik Sinner", [1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1]) + serve_rows(
        "a", "Felix Auger-Aliassime", [0] * 6, [1] * 6
    )
    rally = [
        rally_row("a", "Jannik Sinner", "Total", 10, 6, 4),
        rally_row("a", "Jannik Sinner", "1-3", 7, 4, 3),
        rally_row("a", "Jannik Sinner", "10", 3, 2, 1),  # no 4-6 or 7-9 row: no points there
    ]
    net = [{"match_id": "a", "player": "Jannik Sinner", "row": "NetPoints", "net_pts": "2", "pts_won": "1"}]
    out = charting.player_stats(link, serve, rally, net)
    rows = {row[2]: dict(zip(charting.STATS_COLUMNS, row)) for row in out.stats}
    sinner, felix = rows[1], rows[3]
    assert [sinner[c] for c in ("first_deuce_wide", "first_ad_t", "second_deuce_wide", "second_ad_t")] == [1, 6, 6, 1]
    assert [sinner[c] for c in ("rally_1_3_played", "rally_1_3_won", "rally_4_6_played", "rally_10_won", "points_played")] == [7, 4, 0, 2, 10]
    assert [felix[c] for c in ("rally_1_3_won", "rally_10_won", "points_played")] == [3, 1, 10]
    assert (sinner["net_points"], sinner["net_points_won"]) == (2, 1)
    assert felix["net_points"] is None and out.empty_categories == {"net_points": 1}


def test_rally_totals_that_dont_add_up_leave_the_category_empty():
    link = charting.link_charts([chart("a", "Jannik Sinner", "Felix Auger-Aliassime", "20240125", "SF")], PLAYERS, MATCHES)
    rally = [rally_row("a", "Jannik Sinner", "Total", 10, 6, 4), rally_row("a", "Jannik Sinner", "1-3", 9, 5, 4)]
    out = charting.player_stats(link, [], rally, [])
    assert all(row[charting.STATS_COLUMNS.index("points_played")] is None for row in out.stats)
    assert out.empty_categories == {"serve_direction": 2, "rally_length": 2, "net_points": 2}


# ---------- shot direction (D-038) ----------


def shot_row(row, shots="10", winners="2", forced="1", unforced="1", won="6", lost="4", match="m1", player="A"):
    return {"match_id": match, "player": player, "row": row, "shots": shots, "pt_ending": "", "winners": winners,
            "induced_forced": forced, "unforced": unforced, "shots_in_pts_won": won, "shots_in_pts_lost": lost}  # fmt: skip


def directions_of(rows):
    grouped = {}
    for r in rows:
        grouped.setdefault((r["match_id"], r["player"]), []).append(r)
    return charting._shot_directions(grouped, "m1", "A")


def test_shot_direction_rows_are_read_by_side_and_direction():
    assert directions_of([shot_row("F-XC"), shot_row("S-DTL", shots="3", winners="0", forced="0", unforced="1", won="1", lost="2")]) == [
        ("F", "XC", 10, 2, 1, 1, 6, 4), ("S", "DTL", 3, 0, 0, 1, 1, 2),
    ]  # fmt: skip
    assert directions_of([shot_row("F-XC"), shot_row("F-XC")]) == [("F", "XC", 10, 2, 1, 1, 6, 4)]  # an exact repeat counts once


@pytest.mark.parametrize(
    "rows",
    [
        [shot_row("F-XC", won="5")],  # shots aren't points won plus lost
        [shot_row("F-XC", winners="6", forced="3", unforced="2")],  # more winners and errors than shots
        [shot_row("F-XC", shots="x")],  # not a whole number
        [shot_row("F-XC", winners="-1")],
        [shot_row("X-XC")],  # an unknown side
        [shot_row("F-ZZ")],  # an unknown direction
        [shot_row("F-XC"), shot_row("F-XC", shots="11", lost="5")],  # the same row twice, with different counts
        [],  # no rows for the player
    ],
)
def test_a_player_whose_rows_dont_hold_up_is_left_out(rows):
    assert directions_of(rows) is None
