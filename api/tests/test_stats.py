"""Integration tests for the stats tools against the loaded database.

Every expected number comes from a named source, recorded in docs/stat-checks.md:
- "TA": Tennis Abstract, Jannik Sinner's 2024 totals, retrieved 2026-11-07. Tennis Abstract
  rounds to 0.1%, so those checks allow 0.05 percentage points.
- "hand N": check N in api/tests/hand_checks.sh, computed with awk from the raw CSV files.
Skipped when DATABASE_URL isn't set; run with: uv run --env-file .env pytest
"""

import os

import psycopg
import pytest

from api import stats

SINNER, ALCARAZ, A_ZVEREV, M_ZVEREV = 206173, 207989, 100644, 104999  # hand 9
GASQUET, HASSAN, CATARINA = 104755, 133975, 200031  # hand 9
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture(scope="module")
def conn():
    from api.db import connect

    connection = connect()
    yield connection
    connection.close()


def surfaces(result):
    return {s["surface"]: (s["wins"], s["losses"]) for s in result["surfaces"]}


def record(result):
    return (result["overall"]["wins"], result["overall"]["losses"])


# ---------- connection ----------


def test_connection_is_read_only_outside_tool_transactions(conn):
    assert conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
    assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "5s"
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        conn.execute("CREATE TEMP TABLE read_only_check (a int)")


# ---------- resolve_player ----------


@pytest.mark.parametrize(
    ("query", "player_id"),
    [
        ("Sinner", SINNER),
        ("Félix Auger-Aliassime", 200000),  # accent and hyphen
        ("Yunchaokete Bu", 207352),  # Sackmann stores the words in the other order
        ("alcaraz", ALCARAZ),
    ],
)
def test_resolve_player_finds_one_player(conn, query, player_id):
    result = stats.resolve_player(conn, query)
    assert result["status"] == "resolved"
    assert result["player"]["player_id"] == player_id


def test_resolve_player_asks_when_ambiguous_or_unknown(conn):
    zverev = stats.resolve_player(conn, "zverev")
    assert zverev["status"] == "ambiguous"
    assert {c["player_id"] for c in zverev["candidates"]} == {A_ZVEREV, M_ZVEREV}
    unknown = stats.resolve_player(conn, "zzzz")
    assert (unknown["status"], unknown["candidates"]) == ("not_found", [])


@pytest.mark.parametrize(
    ("query", "expected_candidate"),
    [
        ("Sascha Zverev", A_ZVEREV),  # nickname: Mischa Zverev is spelled closer, and must not win
        ("alcarez", ALCARAZ),  # typos
        ("Djokovich", 104925),
        ("Medvedv", 106421),
        ("Demon", None),  # de Minaur's nickname; closest spelling is Marcelo Demoliner
    ],
)
def test_resolve_player_never_accepts_a_close_spelling(conn, query, expected_candidate):
    result = stats.resolve_player(conn, query)
    assert result["status"] == "close_spellings"
    if expected_candidate:
        assert expected_candidate in [c["player_id"] for c in result["candidates"]]


def test_resolve_player_flags_more_candidates(conn):
    result = stats.resolve_player(conn, "alex")
    assert result["status"] == "ambiguous"
    assert (len(result["candidates"]), result["more_candidates"]) == (stats.MAX_CANDIDATES, True)
    assert stats.resolve_player(conn, "zverev")["more_candidates"] is False


# ---------- player_profile ----------


def test_player_profile(conn):
    profile = stats.player_profile(conn, SINNER)
    assert (profile["hand"], profile["country"], profile["height_cm"]) == ("R", "ITA", 191)  # hand 16
    # hand 6: his last match is the Wimbledon 2026 final on 2026-07-12, ranked 1.
    assert profile["latest_rank"]["rank"] == 1
    assert profile["latest_rank"]["tournament"] == "Wimbledon"
    last = profile["last_match"]
    assert (last["tournament"], last["round"], last["result"], last["match_date"]) == ("Wimbledon", "F", "W", "2026-07-12")


def test_latest_rank_skips_matches_without_a_rank(conn):
    profile = stats.player_profile(conn, CATARINA)
    # hand 19: his newest match (Davis Cup, September 2026) has no rank; the newest one with a
    # rank is from September 2023.
    assert (profile["last_match"]["tournament"], profile["last_match"]["match_date"]) == (
        "Davis Cup WG1 R1: FIN vs MON",
        "2026-09-18",
    )
    assert (profile["latest_rank"]["rank"], profile["latest_rank"]["tournament"]) == (452, "Davis Cup WG2 R1: MON vs ECU")


def test_unknown_player_is_a_distinct_error(conn):
    with pytest.raises(stats.PlayerNotFound):
        stats.player_profile(conn, 999999999)
    with pytest.raises(stats.PlayerNotFound, match="opponent_id"):
        stats.head_to_head(conn, SINNER, 999999999)


def test_data_window(conn):
    window = stats.surface_splits(conn, SINNER, {"season": 2024})["data_window"]
    assert window == {  # hand 17
        "first_tourney_date": "2015-01-04",
        "last_tourney_date": "2026-10-26",
        "last_match_date": "2026-11-01",
    }


# ---------- surface_splits and the shared filters ----------


def test_surface_splits_sinner_2024(conn):
    result = stats.surface_splits(conn, SINNER, {"season": 2024})
    assert surfaces(result) == {"Hard": (53, 3), "Clay": (11, 2), "Grass": (9, 1)}  # hand 1
    assert record(result) == (73, 6)  # TA
    assert result["excluded"]["walkovers"] == 2  # hand 2
    assert result["sample"]["matches_counted"] == 79
    # hand 18: Raonic retired against him at Rotterdam; Sinner never quit a match.
    assert result["sample"]["opponent_retired_or_defaulted"] == 1
    assert result["sample"]["player_retired_or_defaulted"] == 0


def test_surface_splits_2026_comes_from_tml(conn):
    result = stats.surface_splits(conn, ALCARAZ, {"season": 2026})
    assert record(result) == (37, 5)  # hand 7


def test_exhibitions_are_excluded_unless_asked_for(conn):
    default = stats.surface_splits(conn, A_ZVEREV, {"season": 2024})
    included = stats.surface_splits(conn, A_ZVEREV, {"season": 2024, "include_exhibitions": True})
    assert (default["sample"]["matches_counted"], default["excluded"]["exhibitions"]) == (88, 2)  # hand 8
    assert (included["sample"]["matches_counted"], included["excluded"]["exhibitions"]) == (90, 0)


def test_opponent_hand_filter(conn):
    lefties = stats.surface_splits(conn, SINNER, {"season": 2024, "opponent_hand": "L"})
    righties = stats.surface_splits(conn, SINNER, {"season": 2024, "opponent_hand": "R"})
    assert record(lefties) == (6, 0)  # hand 10
    assert record(righties) == (67, 6)  # hand 10 and TA: 73-6 overall, no unknown hands
    assert lefties["excluded"]["unknown_opponent_hand"] == 0


def test_unknown_opponent_hand_is_excluded_and_counted(conn):
    djokovic = 104925  # hand 9
    righties = stats.surface_splits(conn, djokovic, {"season": 2024, "opponent_hand": "R"})
    lefties = stats.surface_splits(conn, djokovic, {"season": 2024, "opponent_hand": "L"})
    # hand 20: 32-8 against R, 4-1 against L, and one win over an opponent of unknown hand.
    assert (record(righties), righties["excluded"]["unknown_opponent_hand"]) == ((32, 8), 1)
    assert (record(lefties), lefties["excluded"]["unknown_opponent_hand"]) == ((4, 1), 1)


def test_date_bounds_are_inclusive(conn):
    result = stats.surface_splits(conn, SINNER, {"date_from": "2024-01-15", "date_to": "2024-01-15"})
    assert record(result) == (7, 0)  # hand 11: the 2024 Australian Open
    assert result["sample"]["first_tourney_date"] == result["sample"]["last_tourney_date"] == "2024-01-15"


@pytest.mark.parametrize(
    ("levels", "expected"),
    [(["G"], (23, 2)), (["D"], (3, 0)), (["G", "M"], (51, 5)), (["A", "F"], (19, 1))],  # hand 12
)
def test_tourney_level_filter(conn, levels, expected):
    assert record(stats.surface_splits(conn, SINNER, {"season": 2024, "tourney_level": levels})) == expected


def test_unknown_result_is_excluded_and_counted(conn):
    result = stats.surface_splits(conn, GASQUET, {"season": 2018})
    # hand 14: 58 matches that aren't walkovers, one of them the Davis Cup rubber whose score
    # contradicts its listed winner.
    assert (result["sample"]["matches_counted"], result["excluded"]["unknown_results"]) == (57, 1)


def test_unknown_surface_is_excluded_and_counted_when_filtering_by_surface(conn):
    by_hard = stats.surface_splits(conn, HASSAN, {"season": 2023, "surface": "Hard"})
    assert by_hard["excluded"]["unknown_surface"] == 2  # hand 15
    unfiltered = stats.surface_splits(conn, HASSAN, {"season": 2023})
    assert unfiltered["excluded"]["unknown_surface"] == 0
    assert {s["surface"]: s["matches"] for s in unfiltered["surfaces"]}["Unknown"] == 2


# ---------- serve_return_stats ----------


@pytest.mark.parametrize(
    ("stat", "tennis_abstract"),
    [
        ("first_serve_in", 0.616),
        ("first_serve_points_won", 0.793),
        ("second_serve_points_won", 0.578),
        ("service_points_won", 0.711),
        ("return_points_won", 0.409),
    ],
)
def test_serve_return_stats_match_tennis_abstract(conn, stat, tennis_abstract):
    result = stats.serve_return_stats(conn, SINNER, {"season": 2024})
    assert result["stats"][stat]["value"] == pytest.approx(tennis_abstract, abs=0.0005)  # TA
    assert result["stats"][stat]["unit"] == "fraction"


def test_ace_rate_matches_tennis_abstract(conn):
    s = stats.serve_return_stats(conn, SINNER, {"season": 2024})["stats"]
    aces, serve_points = s["aces_per_match"]["numerator"], s["first_serve_in"]["denominator"]
    assert aces / serve_points == pytest.approx(0.099, abs=0.0005)  # TA: Ace% 9.9


def test_serve_return_stats_alcaraz_2023_clay(conn):
    s = stats.serve_return_stats(conn, ALCARAZ, {"season": 2023, "surface": "Clay"})["stats"]
    assert (s["first_serve_in"]["numerator"], s["first_serve_in"]["denominator"]) == (1346, 1999)  # hand 4
    assert (s["aces_per_match"]["numerator"], s["aces_per_match"]["denominator"]) == (95, 28)  # hand 4


def test_aces_per_match_divides_by_matches_with_stats(conn):
    result = stats.serve_return_stats(conn, ALCARAZ, {"season": 2022})
    assert (result["sample"]["matches_counted"], result["sample"]["matches_with_stats"]) == (70, 68)  # hand 13
    aces = result["stats"]["aces_per_match"]
    assert (aces["numerator"], aces["denominator"], aces["unit"]) == (259, 68, "per_match")  # hand 13


def test_empty_sample_gives_none_not_zero(conn):
    result = stats.serve_return_stats(conn, SINNER, {"surface": "Carpet"})
    assert result["sample"]["matches_counted"] == 0
    assert all(stat["value"] is None for stat in result["stats"].values())


# ---------- pressure_stats ----------


def test_pressure_stats_sinner_2024_clay(conn):
    s = stats.pressure_stats(conn, SINNER, {"season": 2024, "surface": "Clay"})["stats"]
    assert (s["break_points_saved"]["numerator"], s["break_points_saved"]["denominator"]) == (47, 68)  # hand 3
    assert (s["break_points_converted"]["numerator"], s["break_points_converted"]["denominator"]) == (57, 120)  # hand 3
    assert s["break_points_saved"]["value"] == pytest.approx(47 / 68, abs=0.00005)


# ---------- head_to_head ----------


def test_head_to_head_sinner_alcaraz(conn):
    result = stats.head_to_head(conn, SINNER, ALCARAZ)
    assert (result["record"]["wins"], result["record"]["losses"]) == (7, 10)  # hand 5
    by_surface = {s["surface"]: (s["wins"], s["losses"]) for s in result["by_surface"]}
    assert by_surface == {"Hard": (3, 7), "Clay": (2, 3), "Grass": (2, 0)}  # hand 5
    newest = result["matches"][0]
    assert (newest["tournament"], newest["round"], newest["result"]) == ("Monte Carlo", "F", "W")  # hand 5
    assert len(result["matches"]) == 17


def test_head_to_head_is_symmetric(conn):
    reverse = stats.head_to_head(conn, ALCARAZ, SINNER)
    assert (reverse["record"]["wins"], reverse["record"]["losses"]) == (10, 7)


# ---------- recent_form ----------


def test_recent_form_sinner_last_five(conn):
    result = stats.recent_form(conn, SINNER, n=5)
    played = [(m["round"], m["opponent"]["name"], m["result"]) for m in result["matches"]]
    assert played == [  # hand 6, newest first
        ("F", "Alexander Zverev", "W"),
        ("SF", "Novak Djokovic", "W"),
        ("QF", "Jan Lennard Struff", "W"),
        ("R16", "Shintaro Mochizuki", "W"),
        ("R32", "Jenson Brooksby", "W"),
    ]
    assert result["matches"][0]["match_date"] == "2026-07-12"  # hand 6
    assert (result["record"]["wins"], result["record"]["losses"]) == (5, 0)
    assert result["sample"]["matches_counted"] == 5
