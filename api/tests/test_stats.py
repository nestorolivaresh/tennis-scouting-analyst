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
FILS, MUSETTI, AUGER_ALIASSIME, FRITZ = 209950, 207518, 200000, 126203  # hand 9
GASQUET, HASSAN, CATARINA = 104755, 133975, 200031  # hand 9
pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
# Checks on 2026 stop at the last tournament start in the 2026-11-07 TML snapshot, as the hand
# checks do, so a newer snapshot doesn't move them (D-034). Only test_data_window, and the
# player_profile checks on whoever played last, describe the snapshot itself.
PINNED = {"date_to": "2026-10-26"}


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
    assert window == {  # hand 17, for the snapshot in ingest/data.lock.json
        "first_tourney_date": "2015-01-04",
        "last_tourney_date": "2026-11-08",
        "last_match_date": "2026-11-14",
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
    result = stats.surface_splits(conn, ALCARAZ, {"season": 2026, **PINNED})
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


def counts(rate):
    return (rate["numerator"], rate["denominator"])


@pytest.mark.parametrize(
    ("player_id", "filters", "against_first", "against_second"),
    [
        (SINNER, {"season": 2024}, (1313, 4117), (1379, 2469)),  # hand 29 (Sackmann)
        (ALCARAZ, {"season": 2026, **PINNED}, (777, 2245), (705, 1304)),  # hand 29 (TML)
    ],
)
def test_return_points_won_against_first_and_second_serves(conn, player_id, filters, against_first, against_second):
    s = stats.serve_return_stats(conn, player_id, filters)["stats"]
    assert counts(s["first_serve_return_points_won"]) == against_first
    assert counts(s["second_serve_return_points_won"]) == against_second


def test_return_splits_mirror_the_opponents_serve_over_a_head_to_head(conn):
    # D-033: in the same matches, a point one player won returning is one the other lost serving.
    def serve_return_against(player_id, opponent_id):
        player = stats._player(conn, player_id)
        params = stats._scope_params(player, stats.Filters(), opponent_id=opponent_id)
        row = conn.execute(stats.SERVE_RETURN_SQL, params).fetchone()
        return stats._serve_return_rates(row, 0)

    sinner, alcaraz = serve_return_against(SINNER, ALCARAZ), serve_return_against(ALCARAZ, SINNER)
    for returner, server in ((sinner, alcaraz), (alcaraz, sinner)):
        first, second = returner["first_serve_return_points_won"], returner["second_serve_return_points_won"]
        assert first["denominator"] == server["first_serve_points_won"]["denominator"] > 0
        assert first["numerator"] == server["first_serve_points_won"]["denominator"] - server["first_serve_points_won"]["numerator"]
        assert second["denominator"] == server["second_serve_points_won"]["denominator"] > 0
        assert second["numerator"] == server["second_serve_points_won"]["denominator"] - server["second_serve_points_won"]["numerator"]


# ---------- pressure_stats ----------


def test_pressure_stats_sinner_2024_clay(conn):
    s = stats.pressure_stats(conn, SINNER, {"season": 2024, "surface": "Clay"})["stats"]
    assert (s["break_points_saved"]["numerator"], s["break_points_saved"]["denominator"]) == (47, 68)  # hand 3
    assert (s["break_points_converted"]["numerator"], s["break_points_converted"]["denominator"]) == (57, 120)  # hand 3
    assert s["break_points_saved"]["value"] == pytest.approx(47 / 68, abs=0.00005)


# ---------- head_to_head ----------


def test_head_to_head_sinner_alcaraz(conn):
    result = stats.head_to_head(conn, SINNER, ALCARAZ, PINNED)
    assert (result["record"]["wins"], result["record"]["losses"]) == (7, 10)  # hand 5
    by_surface = {s["surface"]: (s["wins"], s["losses"]) for s in result["by_surface"]}
    assert by_surface == {"Hard": (3, 7), "Clay": (2, 3), "Grass": (2, 0)}  # hand 5
    newest = result["matches"][0]
    assert (newest["tournament"], newest["round"], newest["result"]) == ("Monte Carlo", "F", "W")  # hand 5
    assert len(result["matches"]) == 17


def test_head_to_head_is_symmetric(conn):
    reverse = stats.head_to_head(conn, ALCARAZ, SINNER, PINNED)
    assert (reverse["record"]["wins"], reverse["record"]["losses"]) == (10, 7)


# ---------- recent_form ----------


def test_recent_form_sinner_last_five(conn):
    result = stats.recent_form(conn, SINNER, 5, PINNED)
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


# ---------- season_path (D-035) ----------


def path_rows(result):
    return [(e["tourney_date"], e["tournament"], (e["record"]["wins"], e["record"]["losses"]), e["walkovers"], e["outcome"], e["round"])
            for e in result["events"]]


def test_season_path_sinner_2025(conn):
    result = stats.season_path(conn, SINNER, {"season": 2025})
    assert path_rows(result) == [  # hand 30: start, name, counted win-loss, walkovers, last round and its result
        ("2025-01-13", "Australian Open", (7, 0), 0, "title", "F"),
        ("2025-05-07", "Rome Masters", (5, 1), 0, "lost", "F"),
        ("2025-05-26", "Roland Garros", (6, 1), 0, "lost", "F"),
        ("2025-06-16", "Halle", (1, 1), 0, "lost", "R16"),
        ("2025-06-30", "Wimbledon", (7, 0), 0, "title", "F"),
        ("2025-08-07", "Cincinnati Masters", (5, 1), 0, "lost", "F"),
        ("2025-08-25", "Us Open", (6, 1), 0, "lost", "F"),
        ("2025-09-25", "Beijing", (5, 0), 0, "title", "F"),
        ("2025-10-01", "Shanghai Masters", (1, 1), 0, "lost", "R32"),
        ("2025-10-20", "Vienna", (5, 0), 0, "title", "F"),
        ("2025-10-27", "Paris Masters", (5, 0), 0, "title", "F"),
        ("2025-11-09", "Tour Finals", (5, 0), 0, "title", "F"),
    ]
    assert result["summary"] == {"events": 12, "titles": 6, "record": {"matches": 64, "wins": 58, "losses": 6}, "walkovers_shown": 0}
    cincinnati = result["events"][5]["last_match"]
    assert (cincinnati["opponent"]["player_id"], cincinnati["result_type"], cincinnati["player_score"]) == (ALCARAZ, "retired", "0-5 RET")
    assert [m["round"] for m in result["events"][0]["matches"]] == ["R128", "R64", "R32", "R16", "QF", "SF", "F"]  # play order


def test_season_path_shows_a_walkover_but_never_counts_it(conn):
    result = stats.season_path(conn, FILS, {"season": 2025})
    rg = next(e for e in result["events"] if e["tournament"] == "Roland Garros")
    assert (rg["record"], rg["walkovers"], rg["outcome"], rg["round"]) == ({"matches": 2, "wins": 2, "losses": 0}, 1, "withdrew", "R32")  # hand 30
    assert (rg["last_match"]["result"], rg["last_match"]["score"], rg["last_match"]["counted"]) == ("L", "W/O", False)
    assert [m["counted"] for m in rg["matches"]] == [True, True, False]
    assert result["summary"]["record"]["matches"] == result["sample"]["matches_counted"]
    assert result["summary"]["walkovers_shown"] == result["excluded"]["walkovers"] == 1


@pytest.mark.parametrize(
    ("player_id", "season", "tournament", "expected"),
    [  # hand 30
        (MUSETTI, 2024, "Paris Olympics", ((5, 1), "bronze", "BR")),
        (AUGER_ALIASSIME, 2024, "Paris Olympics", ((4, 2), "fourth", "BR")),
        (MUSETTI, 2024, "Davis Cup Finals QF: ITA vs ARG", ((0, 1), "tie", "RR")),
        (A_ZVEREV, 2025, "Tour Finals", ((1, 2), "round_robin", "RR")),
        (A_ZVEREV, 2025, "United Cup", ((2, 0), "team", "RR")),
        (FRITZ, 2025, "United Cup", ((4, 1), "team", "F")),  # won his final match; the team result isn't his
    ],
)
def test_season_path_endings(conn, player_id, season, tournament, expected):
    event = next(e for e in stats.season_path(conn, player_id, {"season": season})["events"] if e["tournament"] == tournament)
    assert ((event["record"]["wins"], event["record"]["losses"]), event["outcome"], event["round"]) == expected


@pytest.mark.parametrize(
    ("player_id", "filters"),
    [(SINNER, {"season": 2025}), (FILS, {"season": 2025}), (A_ZVEREV, {"season": 2025, "surface": "Clay"}),
     (ALCARAZ, {"season": 2026, **PINNED}), (MUSETTI, {"season": 2024, "opponent_rank_max": 20})],
)
def test_season_path_counts_what_every_tool_counts(conn, player_id, filters):
    path = stats.season_path(conn, player_id, filters)
    record = stats.surface_splits(conn, player_id, filters)["overall"]
    assert path["summary"]["record"] == {k: record[k] for k in ("matches", "wins", "losses")}
    assert sum(e["record"]["matches"] for e in path["events"]) == record["matches"]
    if filters.get("surface"):
        assert {m["surface"] for e in path["events"] for m in e["matches"]} == {filters["surface"]}


def test_season_path_needs_a_season(conn):
    with pytest.raises(stats.ToolInputError, match="season"):
        stats.season_path(conn, SINNER, {"surface": "Clay"})


def test_season_path_with_no_matches_is_empty_not_an_error(conn):
    result = stats.season_path(conn, SINNER, {"season": 2015})
    assert (result["events"], result["summary"]["events"], result["summary"]["record"]["matches"]) == ([], 0, 0)


def row(round_, won, result_type="completed"):
    return {"round": round_, "won": won, "result_type": result_type}


@pytest.mark.parametrize(
    ("level", "name", "last", "outcome"),
    [
        ("D", "Davis Cup Finals QF: ITA vs ARG", row("RR", True), "tie"),
        ("A", "United Cup", row("F", True), "team"),
        ("G", "Roland Garros", row("R32", False, "walkover"), "withdrew"),
        ("G", "Roland Garros", row("R32", True, "walkover"), "no_later_match"),  # the opponent withdrew; nothing after
        ("F", "Tour Finals", row("RR", True), "round_robin"),
        ("F", "Tour Finals", row("F", True), "title"),
        ("M", "Paris Masters", row("F", True, "walkover"), "title"),  # a final won by walkover is still a title
        ("O", "Paris Olympics", row("BR", True), "bronze"),
        ("O", "Paris Olympics", row("BR", False), "fourth"),
        ("M", "Cincinnati Masters", row("F", False, "retired"), "lost"),
        ("A", "Stockholm", row("QF", True), "no_later_match"),  # still being played
    ],
)
def test_event_outcome_rules(level, name, last, outcome):
    assert stats.event_outcome(level, name, last) == outcome


def test_team_events_are_the_special_events_marked_team():
    import csv
    from pathlib import Path

    rows = csv.DictReader((Path(__file__).parents[2] / "ingest" / "special_events.csv").open())
    assert stats.TEAM_EVENTS == {r["tourney_name"] for r in rows if r["note"].startswith("Team")}


# ---------- tournament_calendar and tournament_history (D-036) ----------


def finals(result, key="tournaments"):
    return {t["tournament"]: (t["status"], t["final"] and (t["final"]["winner"]["name"], t["final"]["runner_up"]["name"], t["final"]["score"]))
            for t in result[key]}


def test_tournament_calendar_2025(conn):
    result = stats.tournament_calendar(conn, 2025)
    assert result["count"] == 61  # hand 31: 61 tournaments outside Davis Cup and exhibitions, each with a final
    by_name = finals(result)
    assert sum(1 for status, _ in by_name.values() if status == "final") == 60
    assert by_name["United Cup"] == ("team", None)  # its final was a tie between teams (hand 31 lists its first match)
    assert by_name["Brisbane"] == ("final", ("Jiri Lehecka", "Reilly Opelka", "4-1 RET"))  # hand 31
    assert by_name["Hong Kong"] == ("final", ("Alexandre Muller", "Kei Nishikori", "2-6 6-1 6-3"))  # hand 31
    assert by_name["Adelaide"] == ("final", ("Felix Auger Aliassime", "Sebastian Korda", "6-3 3-6 6-1"))  # hand 31
    assert by_name["Auckland"] == ("final", ("Gael Monfils", "Zizou Bergs", "6-3 6-4"))  # hand 31
    dates = [t["tourney_date"] for t in result["tournaments"]]
    assert dates == sorted(dates) and dates[0] == "2024-12-27"  # the United Cup starts in December of the season before (D-010)
    assert not any(t["tournament"].startswith("Davis Cup") for t in result["tournaments"])


def test_tournament_calendar_filters(conn):
    clay = stats.tournament_calendar(conn, 2025, surface="Clay")
    assert clay["count"] > 0 and {t["surface"] for t in clay["tournaments"]} == {"Clay"}
    slams = stats.tournament_calendar(conn, 2025, tourney_level=["G"])
    assert [t["tournament"] for t in slams["tournaments"]] == ["Australian Open", "Roland Garros", "Wimbledon", "Us Open"]
    default = finals(stats.tournament_calendar(conn, 2025))
    with_exhibitions = finals(stats.tournament_calendar(conn, 2025, include_exhibitions=True))
    assert "Laver Cup" not in default and with_exhibitions["Laver Cup"] == ("team", None)  # D-006
    with pytest.raises(stats.ToolInputError, match="season"):
        stats.tournament_calendar(conn, None)


def test_tournament_history_follows_the_code_across_seasons_and_sources(conn):
    result = stats.tournament_history(conn, 404)
    assert [(e["season"], e["final"]["winner"]["name"], e["final"]["runner_up"]["name"]) for e in result["editions"]] == [  # hand 31
        (2026, "Jannik Sinner", "Daniil Medvedev"),
        (2025, "Jack Draper", "Holger Rune"),
        (2024, "Carlos Alcaraz", "Daniil Medvedev"),
        (2023, "Carlos Alcaraz", "Daniil Medvedev"),
        (2022, "Taylor Fritz", "Rafael Nadal"),
        (2021, "Cameron Norrie", "Nikoloz Basilashvili"),
        (2019, "Dominic Thiem", "Roger Federer"),  # 2016-2019 from ingest/event_codes.csv (M006)
        (2018, "Juan Martin del Potro", "Roger Federer"),
        (2017, "Roger Federer", "Stan Wawrinka"),
        (2016, "Novak Djokovic", "Milos Raonic"),
        (2015, "Novak Djokovic", "Roger Federer"),
    ]
    assert {e["tournament"] for e in result["editions"]} == {"Indian Wells Masters"}


def test_a_code_that_moved_city_gives_each_edition_its_own_name(conn):
    editions = stats.tournament_history(conn, 496)["editions"]
    assert (editions[0]["season"], editions[0]["tournament"]) == (2026, "Lyon")  # as TML codes it
    assert {e["tournament"] for e in editions[1:]} == {"Marseille"}


def test_tournament_history_errors(conn):
    with pytest.raises(stats.TournamentNotFound):
        stats.tournament_history(conn, 99999)
    with pytest.raises(stats.ToolInputError):
        stats.tournament_history(conn, "abc")


@pytest.mark.parametrize(
    ("name", "has_final", "result_type", "status"),
    [
        ("Rome Masters", True, "completed", "final"),
        ("Brisbane", True, "retired", "final"),
        ("Paris Masters", True, "walkover", "final"),  # a title won by walkover is still a final
        ("United Cup", True, "completed", "team"),
        ("Stockholm", False, None, "no_final"),  # still being played
        ("Kitzbuhel", True, "unknown", "unclear"),  # the score contradicts the listed winner (D-007)
    ],
)
def test_final_status_rules(name, has_final, result_type, status):
    assert stats.final_status(name, has_final, result_type) == status


# ---------- Milestone 8: scouting patterns from the match data (D-029) ----------

DJOKOVIC = 104925  # hand 9


def test_opponent_rank_filter_counts_unranked_opponents_as_excluded(conn):
    result = stats.surface_splits(conn, DJOKOVIC, {"season": 2024, "opponent_rank_max": 10})
    assert record(result) == (2, 4)  # hand 22
    assert result["excluded"]["unknown_opponent_rank"] == 1  # hand 22: Matthew Ebden, unranked
    assert result["filters"]["opponent_rank_max"] == 10
    unfiltered = stats.surface_splits(conn, DJOKOVIC, {"season": 2024})
    assert unfiltered["excluded"]["unknown_opponent_rank"] == 0  # only counted when filtering by rank


@pytest.mark.parametrize("bad", [0, 5001, "ten", -3, 2.5, True])
def test_opponent_rank_filter_refuses_bad_values(bad):
    with pytest.raises(stats.ToolInputError, match="opponent_rank_max"):
        stats.Filters.parse({"opponent_rank_max": bad})


def test_scores_read_from_the_asked_players_side(conn):
    matches = stats.head_to_head(conn, SINNER, ALCARAZ)["matches"]
    final = next(m for m in matches if m["tournament"] == "Roland Garros" and m["round"] == "F")
    assert final["result"] == "L"
    assert final["score"] == "4-6 6-7(4) 6-4 7-6(3) 7-6(2)"  # hand 27, as written: Alcaraz first
    assert final["player_score"] == "6-4 7-6(4) 4-6 6-7(3) 6-7(2)"  # hand 27, read from Sinner's side
    won = next(m for m in matches if m["result"] == "W")
    assert won["player_score"] == won["score"]


def test_recent_form_time_on_court(conn):
    result = stats.recent_form(conn, SINNER, 10, {"season": 2026, **PINNED})
    assert result["time_on_court"]["matches_with_minutes"] == 10  # hand 23
    assert result["time_on_court"]["total_minutes"] == 1592  # hand 23
    assert result["time_on_court"]["longest_match_minutes"] == 226  # hand 23
    assert result["time_on_court"]["minutes_per_match"]["value"] == pytest.approx(159.2)


def test_missing_minutes_are_missing_not_zero(conn):
    result = stats.recent_form(conn, SINNER, 10, {"season": 2023, "tourney_level": "D"})
    assert result["sample"]["matches_counted"] == 3  # hand 25
    assert all(m["minutes"] is None for m in result["matches"])  # hand 25: no durations
    time = result["time_on_court"]
    assert time["matches_with_minutes"] == 0 and time["total_minutes"] is None
    assert time["longest_match_minutes"] is None and time["minutes_per_match"]["value"] is None


def test_set_patterns_sinner_2024(conn):
    result = stats.set_patterns(conn, SINNER, {"season": 2024})
    counts = {name: (r["numerator"], r["denominator"]) for name, r in result["stats"].items()}
    assert counts == {  # hand 21
        "tiebreaks_won": (24, 32),
        "deciding_sets_won": (13, 19),
        "won_after_winning_first_set": (62, 66),
        "won_after_losing_first_set": (10, 12),
    }
    assert result["scores_read"] == {"completed_matches": 78, "ended_early": 1, "unreadable_scores": 0}  # hand 21


def test_tour_comparison_grass_2023(conn):
    result = stats.tour_comparison(conn, ALCARAZ, {"season": 2023, "surface": "Grass"})
    assert result["tour"] == {"min_matches": 10, "qualifying_players": 10, "player_qualifies": True}  # hand 24
    spw = result["stats"]["service_points_won"]
    assert (spw["value"]["numerator"], spw["value"]["denominator"]) == (767, 1117)  # hand 24
    assert spw["rank"] == 5 and spw["players_ranked"] == 10  # hand 24
    assert spw["tour_median"] == round((767 / 1117 + 700 / 1035) / 2, 4)  # hand 24: 5th and 6th of 10
    top = stats.tour_comparison(conn, SINNER, {"season": 2023, "surface": "Grass"})
    assert top["stats"]["service_points_won"]["rank"] == 1  # hand 24


def test_tour_comparison_uses_the_tools_own_numbers(conn):
    filters = {"season": 2023, "surface": "Grass"}
    result = stats.tour_comparison(conn, ALCARAZ, filters)
    serve = stats.serve_return_stats(conn, ALCARAZ, filters)["stats"]
    pressure = stats.pressure_stats(conn, ALCARAZ, filters)["stats"]
    assert {name: s["value"] for name, s in result["stats"].items()} == {**serve, **pressure}


def test_tour_comparison_below_the_threshold_has_no_rank(conn):
    result = stats.tour_comparison(conn, ALCARAZ, {"season": 2023, "surface": "Grass"}, min_matches=13)
    assert result["tour"]["player_qualifies"] is False  # 12 matches with stats (hand 24)
    assert result["stats"]["service_points_won"]["rank"] is None
    assert result["stats"]["service_points_won"]["value"]["numerator"] == 767
    assert result["tour"]["qualifying_players"] == 2  # hand 24: Mannarino 16, Thompson 14


def test_rank_among_shares_the_better_rank_on_ties():
    from fractions import Fraction as F

    values = [F(3, 4), F(1, 2), F(1, 2), F(1, 4)]
    assert [stats.rank_among(v, values) for v in values] == [1, 2, 2, 4]


@pytest.mark.parametrize("bad", [0, 201, "x"])
def test_tour_comparison_refuses_bad_thresholds(conn, bad):
    with pytest.raises(stats.ToolInputError, match="min_matches"):
        stats.tour_comparison(conn, SINNER, min_matches=bad)


# ---------- Milestone 9: shot patterns from the Match Charting Project (D-030) ----------


def test_shot_patterns_sinner_roland_garros_2024(conn):
    result = stats.shot_patterns(conn, SINNER, {"season": 2024, "tourney_level": "G", "surface": "Clay"})
    assert result["charting"]["charted_matches"] == 6 and result["charting"]["points_charted"] == 1176  # hand 26

    def counts(court):
        return [court[side]["numerator"] for side in ("wide", "body", "t")], court["wide"]["denominator"]

    first, second = result["serve_direction"]["first_serves_in"], result["serve_direction"]["second_serves"]
    assert counts(first["deuce"]) == ([80, 29, 69], 178) and counts(first["ad"]) == ([96, 21, 51], 168)  # hand 26
    assert counts(second["deuce"]) == ([22, 49, 39], 110) and counts(second["ad"]) == ([42, 45, 11], 98)  # hand 26
    rally = {name: (r["numerator"], r["denominator"]) for name, r in result["rally_length"]["points_won"].items()}
    assert rally == {"1_3": (350, 646), "4_6": (152, 269), "7_9": (80, 138), "10_plus": (67, 123)}  # hand 26
    net = result["net_points"]
    assert (net["net_points_won"]["numerator"], net["net_points_won"]["denominator"]) == (107, 147)  # hand 26
    assert (net["share_of_points_at_net"]["numerator"], net["share_of_points_at_net"]["denominator"]) == (147, 1176)


def test_shot_patterns_report_the_players_charts_that_dont_count(conn):
    result = stats.shot_patterns(conn, SINNER)
    not_linked = result["charting"]["player_charts_not_linked_all_dates"]
    assert set(not_linked) <= {"before_data", "name_not_resolved", "no_tour_match", "several_tour_matches", "charted_twice"}
    rows = conn.execute(
        "SELECT count(*) AS n FROM charting_matches WHERE 206173 IN (player1_id, player2_id) AND link <> 'linked'"
    ).fetchone()
    assert sum(not_linked.values()) == rows["n"] > 0
    assert "volunteers" in result["charting"]["about"]


def test_shot_patterns_with_no_charted_match_are_empty_not_zero(conn):
    result = stats.shot_patterns(conn, SINNER, {"season": 2016})  # before his first tour match
    assert result["charting"]["charted_matches"] == 0
    assert result["rally_length"]["points_won"]["1_3"]["value"] is None
    assert result["serve_direction"]["first_serves_in"]["deuce"]["wide"]["value"] is None


def test_a_bare_seven_six_set_is_a_tiebreak(conn):
    laaksonen = 105967  # his 2015 Davis Cup loss to Bemelmans has a "6-7" set with no tiebreak score
    result = stats.set_patterns(conn, laaksonen, {"season": 2015})
    tiebreaks = result["stats"]["tiebreaks_won"]
    assert (tiebreaks["numerator"], tiebreaks["denominator"]) == (2, 3)  # hand 28
