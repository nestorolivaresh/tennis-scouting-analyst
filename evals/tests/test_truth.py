"""Ground truth (evals/truth.py) and the eval cases.

1. The ground-truth SQL reproduces values from named sources (Tennis Abstract and
   api/tests/hand_checks.sh, listed in docs/stat-checks.md).
2. It agrees with the loader on every Sackmann match (result type, level, exhibition, stats
   kept, surface), although the two implement the rules separately.
3. For every case, the stats tools give the same numbers as the ground truth. A difference
   means one of the two is wrong, which is what the evals exist to catch.
4. It stays independent: no imports from api/ or ingest/, and only raw tables in its SQL.
"""

import ast
import os
import re
from pathlib import Path

import pytest

from evals import truth
from evals.cases import CASES, COUNTS, FEDERER, NADAL
from evals.truth import Filters as F, totals

needs_db = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")
SINNER, DJOKOVIC, ALCARAZ, GASQUET, ZVEREV, HASSAN = 206173, 104925, 207989, 104755, 100644, 133975  # hand 9
FILS, MUSETTI, FRITZ = 209950, 207518, 126203  # hand 9


@pytest.fixture(scope="module")
def conn():
    connection = truth.connect()
    yield connection
    connection.close()


# ---------- 1. named sources ----------


@needs_db
def test_records_match_named_sources(conn):
    def record(player, **filters):
        t = totals(conn, player, F(**filters))
        return t.wins, t.losses

    assert record(SINNER, season=2024) == (73, 6)  # TA
    assert [record(SINNER, season=2024, surface=s) for s in ("Hard", "Clay", "Grass")] == [(53, 3), (11, 2), (9, 1)]  # hand 1
    assert record(SINNER, season=2024, opponent_hand="L") == (6, 0)  # hand 10
    assert record(SINNER, season=2024, opponent_hand="R") == (67, 6)  # hand 10
    assert record(DJOKOVIC, season=2024, opponent_hand="R") == (32, 8)  # hand 20
    assert record(DJOKOVIC, season=2024, opponent_hand="L") == (4, 1)  # hand 20
    levels = [("G",), ("D",), ("G", "M"), ("A", "F")]
    assert [record(SINNER, season=2024, levels=lv) for lv in levels] == [(23, 2), (3, 0), (51, 5), (19, 1)]  # hand 12
    assert record(SINNER, date_from="2024-01-15", date_to="2024-01-15") == (7, 0)  # hand 11, inclusive bounds
    assert totals(conn, GASQUET, F(season=2018)).matches == 57  # hand 14 (one unknown result left out)
    assert totals(conn, ZVEREV, F(season=2024)).matches == 88  # hand 8
    assert totals(conn, ZVEREV, F(season=2024, include_exhibitions=True)).matches == 90  # hand 8


@needs_db
def test_serve_and_pressure_stats_match_named_sources(conn):
    sinner = totals(conn, SINNER, F(season=2024))
    ta = {"first_serve_in": 61.6, "first_serve_points_won": 79.3, "second_serve_points_won": 57.8,
          "service_points_won": 71.1, "return_points_won": 40.9}  # TA, rounded to 0.1  # fmt: skip
    for stat, percent in ta.items():
        assert 100 * sinner.stat(stat) == pytest.approx(percent, abs=0.05), stat
    assert (sinner.sums["aces"], sinner.sums["serve_points"], sinner.sums["first_in"]) == (594, 5996, 3693)  # TA
    clay = totals(conn, ALCARAZ, F(season=2023, surface="Clay"))
    assert (clay.sums["first_in"], clay.sums["serve_points"], clay.sums["aces"], clay.matches_with_stats) == (1346, 1999, 95, 28)  # hand 4
    year = totals(conn, ALCARAZ, F(season=2022))
    assert (year.matches, year.matches_with_stats, year.sums["aces"]) == (70, 68, 259)  # hand 13
    pressure = totals(conn, SINNER, F(season=2024, surface="Clay"))
    s = pressure.sums
    assert (s["bp_saved"], s["bp_faced"], s["opp_bp_faced"] - s["opp_bp_saved"], s["opp_bp_faced"]) == (47, 68, 57, 120)  # hand 3


@needs_db
def test_rules_the_cases_never_exercise(conn):
    """Every case's sample has stats for all its matches and a surface for all of them, so
    these three rules need samples of their own (found in review, D-023)."""
    alcaraz = totals(conn, ALCARAZ, F(season=2022))  # hand 13: 70 matches, 68 with stats, 259 aces
    assert alcaraz.stat("aces_per_match") == 259 / 68  # divided by matches with stats, not all 70
    assert alcaraz.stat("win_rate") == alcaraz.wins / 70  # divided by all matches, not the 68
    hard = totals(conn, HASSAN, F(season=2023, surface="Hard"))
    assert hard.left_out_by["no_surface"] == 2  # hand 15: Davis Cup UKR v LBN has no surface


# ---------- 2. agreement with the loader, match by match ----------


@needs_db
def test_rules_agree_with_the_loader_on_every_match(conn):
    """Two implementations of D-006 to D-010 (the loader's Python, this SQL) must classify all
    30,616 Sackmann matches the same way and give them the same players (merges, D-009)."""
    ours = conn.execute(
        "WITH pm AS (" + truth.PLAYER_MATCHES_SQL + ") SELECT season, row_num, result_type, level, exhibition, "
        "has_stats, surface, player AS winner, opponent AS loser FROM pm WHERE won",
        {"player": None},
    ).fetchall()
    loaded = conn.execute(
        "SELECT season, source_row AS row_num, result_type, tourney_level AS level, is_exhibition AS exhibition, "
        "has_stats, surface, winner_id AS winner, loser_id AS loser FROM matches WHERE source = 'sackmann'"
    ).fetchall()
    assert len(ours) == len(loaded) == 30_616  # before keying, so a duplicated row can't hide
    key = lambda row: (row["season"], row["row_num"])  # noqa: E731
    ours, loaded = {key(r): r for r in ours}, {key(r): r for r in loaded}
    assert len(ours) == len(loaded) == 30_616
    differences = [(k, ours[k], loaded[k]) for k in ours if ours[k] != loaded[k]]
    assert differences == []


# ---------- 3. the cases ----------


NOT_A_PATTERN = object()


def pattern_tool_value(stats, conn, expect, filters):
    """The Milestone 8 and 9 numbers (D-029, D-030), from the tool a correct answer would call."""
    stat = expect.stat
    if stat in ("tiebreaks_won_count", "tiebreaks_played"):
        rate = stats.set_patterns(conn, expect.player, filters)["stats"]["tiebreaks_won"]
        return rate["numerator"] if stat == "tiebreaks_won_count" else rate["denominator"]
    if stat in ("tiebreaks_won", "deciding_sets_won", "won_after_winning_first_set", "won_after_losing_first_set"):
        return stats.set_patterns(conn, expect.player, filters)["stats"][stat]["value"]
    if stat.startswith(("tour_rank:", "tour_players:")):
        kind, measure = stat.split(":")
        line = stats.tour_comparison(conn, expect.player, filters)["stats"][measure]
        return line["rank"] if kind == "tour_rank" else line["players_ranked"]
    if stat == "charted_matches":
        return stats.shot_patterns(conn, expect.player, filters)["charting"]["charted_matches"]
    if stat.startswith(("dir_first_", "dir_second_")):
        block = "first_serves_in" if stat.startswith("dir_first_") else "second_serves"
        court, side = stat.removeprefix("dir_first_").removeprefix("dir_second_").split("_")
        return stats.shot_patterns(conn, expect.player, filters)["serve_direction"][block][court][side]["value"]
    if stat.startswith("rally_"):
        band = stat.removeprefix("rally_").removesuffix("_won")
        return stats.shot_patterns(conn, expect.player, filters)["rally_length"]["points_won"][band]["value"]
    if stat in ("path_events", "path_titles"):
        return stats.season_path(conn, expect.player, filters)["summary"][stat.removeprefix("path_")]
    if stat == "shot_dir_matches":
        return stats.shot_patterns(conn, expect.player, filters)["shot_direction"]["matches"]
    if stat.startswith("shot:"):
        _, side, direction, measure = stat.split(":")
        cell = stats.shot_patterns(conn, expect.player, filters)["shot_direction"]["sides"][side]["directions"][direction]
        return cell[measure]["value"]
    return NOT_A_PATTERN


def event_tool_value(stats, conn, expect):
    """A final's winner, runner-up or score, from the calendar tool (D-036)."""
    calendar = stats.tournament_calendar(conn, expect.filters.season)["tournaments"]
    (event,) = [t for t in calendar if t["tournament"] == expect.event]
    final = event["final"]
    if expect.stat == "final_score":
        return final["score"]
    return truth.last_name(final["winner" if expect.stat == "final_winner" else "runner_up"]["name"])


def stats_tool_value(stats, conn, expect):
    """The same number from the stats layer, through the tool a correct answer would call."""
    if expect.event:
        return event_tool_value(stats, conn, expect)
    f = expect.filters
    filters = {key: value for key, value in {
        "season": f.season, "date_from": f.date_from, "date_to": f.date_to, "surface": f.surface,
        "tourney_level": list(f.levels) if f.levels else None, "opponent_hand": f.opponent_hand,
        "opponent_rank_max": f.opponent_rank_max,
    }.items() if value is not None}  # fmt: skip
    pattern = pattern_tool_value(stats, conn, expect, filters)
    if pattern is not NOT_A_PATTERN:
        return pattern
    if expect.opponent:
        record = stats.head_to_head(conn, expect.player, expect.opponent, filters)["record"]
        return record[expect.stat] if expect.stat in COUNTS else record[expect.stat]["value"]
    if expect.stat in COUNTS or expect.stat == "win_rate":
        overall = stats.surface_splits(conn, expect.player, filters)["overall"]
        return overall[expect.stat] if expect.stat in COUNTS else overall["win_rate"]["value"]
    tool = stats.pressure_stats if expect.stat.startswith("break_points") else stats.serve_return_stats
    return tool(conn, expect.player, filters)["stats"][expect.stat]["value"]


@needs_db
def test_every_case_matches_the_stats_layer(conn):
    from api import stats  # the stats layer, used here only to compare
    from api.db import connect

    api_conn = connect()
    differences = []
    for case in CASES:
        for expect in case.expects:
            if expect.event:
                ours = truth.event_value(conn, expect.stat, expect.filters, expect.event)[0]
            elif expect.stat in COUNTS or expect.stat in truth.TOTALS_STATS:
                t = totals(conn, expect.player, expect.filters, expect.opponent)
                ours = getattr(t, expect.stat) if expect.stat in COUNTS else t.stat(expect.stat)
            else:
                ours = truth.pattern_value(conn, expect.stat, expect.player, expect.filters)[0]
            theirs = stats_tool_value(stats, api_conn, expect)
            assert ours is not None, (case.id, expect)
            if isinstance(ours, str):
                if ours != theirs:
                    differences.append((case.id, expect.stat, ours, theirs))
            elif theirs is None or abs(ours - theirs) > 5e-5:  # the stats layer rounds rates to 4 places
                differences.append((case.id, expect.stat, ours, theirs))
    api_conn.close()
    assert differences == []


def test_cases_are_well_formed():
    ids = [case.id for case in CASES]
    # The spec's 40, 3 from bugs found by hand, 8 for D-029 and D-030, 8 for D-033 to D-038.
    assert len(ids) == len(set(ids)) == 59
    counts = {}
    for case in CASES:
        counts[case.category] = counts.get(case.category, 0) + 1
        assert case.expects or case.refusal, case.id
        for expect in case.expects:
            assert (expect.event is None) == (expect.player is not None), (case.id, expect)
            assert expect.event is None or expect.filters.season, (case.id, expect)  # a final is one season's
    assert counts == {"single_stat": 10, "filtered_stat": 10, "head_to_head": 11, "comparison": 6, "refuse_or_caveat": 8,
                      "scouting_pattern": 10, "tournaments": 4}  # fmt: skip


@needs_db
def test_refusal_preconditions(conn):
    """The data behind the refuse-or-caveat questions is what they assume."""
    federer_2022 = totals(conn, FEDERER, F(season=2022, include_exhibitions=True))
    assert (federer_2022.matches, federer_2022.left_out) == (0, 0)  # no singles match in 2022 at all
    assert totals(conn, NADAL, F(season=2013, surface="Clay")).matches == 0  # before the data starts
    swiatek = conn.execute("SELECT count(*) AS n FROM raw.sackmann_players WHERE name_last = 'Swiatek'").fetchone()
    assert swiatek["n"] == 0  # WTA players aren't in the data
    zverevs = conn.execute(
        "SELECT count(*) AS n FROM raw.sackmann_players WHERE name_last = 'Zverev' AND player_id IN "
        "(SELECT winner_id FROM raw.matches WHERE season = 2019 UNION SELECT loser_id FROM raw.matches WHERE season = 2019)"
    ).fetchone()
    assert zverevs["n"] == 2  # Alexander and Mischa both played in 2019, so "Zverev" is ambiguous


# ---------- 4. independence ----------


def test_truth_is_independent_of_the_stats_layer_and_loader():
    source = Path(truth.__file__).read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert not imported & {"api", "ingest"}
    ctes = {"src", "tokens", "sets", "typed", "sides", "side_ok", "match_stats", "pm", "scoped", "set_tokens", "per_match",
            "charts", "chart_keys", "tour", "fits", "g", "chosen", "d", "linked", "mine", "shown", "per_event", "pe"}  # fmt: skip
    sql = (truth.PLAYER_MATCHES_SQL + truth.TOTALS_SQL + truth.SET_PATTERNS_SQL + truth.TOUR_TOTALS_SQL + truth.CHARTS_SQL
           + truth.SEASON_EVENTS_SQL + truth.EVENT_FINAL_SQL + truth.SHOT_DIRECTION_SQL)  # fmt: skip
    tables = set(re.findall(r"\b(?:FROM|JOIN)\s+([\w.\"]+)", sql, re.IGNORECASE))
    assert {t for t in tables if t not in ctes and not t.startswith("raw.")} == set()
    # Comma joins too ("FROM src s, public.matches m"): any schema-qualified name is raw.
    assert set(re.findall(r"\b(\w+)\.\w+\b(?=\s+\w+\s*(?:,|ON|WHERE|$|\)))", sql, re.MULTILINE)) <= {"raw"} | ctes
    assert not re.search(r"(?:FROM|JOIN|,)\s+(?:public\.)?(?:matches|player_matches|players)\b", sql, re.IGNORECASE)


# ---------- 5. Milestones 8 and 9 (D-029, D-030) ----------


@needs_db
def test_chart_links_agree_with_the_loader(conn):
    """Two implementations of D-030's link rule: the loader's, by player ID, and this SQL, by the
    names in the raw match files. They must link the same charts to the same matches, except
    where only the reviewed player files know two spellings are one player (D-009, D-012)."""
    ours = {
        (r["chart_id"], r["season"], r["row_num"])
        for r in conn.execute(truth.CHARTS_SQL + "SELECT chart_id, season, row_num FROM linked",
                              {"player": None, "opponent": None, **F().params()}).fetchall()
    }  # fmt: skip
    loaded = {
        (r["chart_id"], r["season"], r["source_row"])
        for r in conn.execute("SELECT c.chart_id, m.season, m.source_row FROM charting_matches c "
                              "JOIN matches m USING (match_id) WHERE m.source = 'sackmann'").fetchall()
    }  # fmt: skip
    assert len(ours) > 4000
    # Coleman Wong is "Chak Lam Coleman Wong" in the 2024 match file; the merge file joins the two.
    assert loaded - ours == {("20240102-M-Hong_Kong-R32-Coleman_Wong-Lorenzo_Musetti", 2024, 81)}
    assert ours - loaded == set()


@needs_db
def test_set_patterns_match_named_sources(conn):
    """Hand checks 21 and 28: the second has the data's only bare 6-7 set, which is a tiebreak."""
    sinner = truth.set_totals(conn, 206173, F(season=2024))
    assert (sinner["tiebreaks_won_count"], sinner["tiebreaks_played"]) == (24, 32)
    assert (sinner["deciding_won"], sinner["deciding_played"]) == (13, 19)
    assert (sinner["after_win_won"], sinner["after_win_played"], sinner["after_loss_won"], sinner["after_loss_played"]) == (62, 66, 10, 12)
    laaksonen = truth.set_totals(conn, 105967, F(season=2015))
    assert (laaksonen["tiebreaks_won_count"], laaksonen["tiebreaks_played"]) == (2, 3)


# ---------- 6. Milestones 11 to 14 (D-033 to D-038) ----------


@needs_db
def test_return_splits_match_named_sources(conn):
    """Hand 29: Sinner 2024 won 1,313 of 4,117 return points against first serves and 1,379 of
    2,469 against second serves."""
    sinner = totals(conn, SINNER, F(season=2024))
    assert sinner.stat("first_serve_return_points_won") == 1313 / 4117
    assert sinner.stat("second_serve_return_points_won") == 1379 / 2469


@needs_db
def test_season_paths_match_named_sources(conn):
    """Hand 30: Sinner's 2025 tournament by tournament, a walkover shown but not counted, an
    Olympic bronze medal match, and a team event whose last match was a win (D-035)."""
    path = [(e["tourney_name"], e["wins"], e["matches"] - e["wins"], e["title"])
            for e in truth.season_events(conn, SINNER, F(season=2025))]  # fmt: skip
    assert path == [
        ("Australian Open", 7, 0, True), ("Rome Masters", 5, 1, False), ("Roland Garros", 6, 1, False),
        ("Halle", 1, 1, False), ("Wimbledon", 7, 0, True), ("Cincinnati Masters", 5, 1, False),
        ("Us Open", 6, 1, False), ("Beijing", 5, 0, True), ("Shanghai Masters", 1, 1, False),
        ("Vienna", 5, 0, True), ("Paris Masters", 5, 0, True), ("Tour Finals", 5, 0, True),
    ]  # fmt: skip
    fils = {e["tourney_name"]: e for e in truth.season_events(conn, FILS, F(season=2025))}["Roland Garros"]
    assert (fils["wins"], fils["matches"], fils["walkovers"], fils["title"]) == (2, 2, 1, False)
    musetti = {e["tourney_name"]: e for e in truth.season_events(conn, MUSETTI, F(season=2024))}["Paris Olympics"]
    assert (musetti["wins"], musetti["matches"], musetti["title"]) == (5, 6, False)  # won the bronze medal match
    fritz = {e["tourney_name"]: e for e in truth.season_events(conn, FRITZ, F(season=2025))}["United Cup"]
    assert (fritz["wins"], fritz["matches"], fritz["title"]) == (4, 5, False)  # won his final match: still no title


@needs_db
def test_finals_match_named_sources(conn):
    """Hand 31: Indian Wells finals 2015-2025 (none in 2020), and the 2025 United Cup, a team event
    with no single winner (D-036)."""
    finals = {year: truth.event_final(conn, year, "Indian Wells Masters") for year in (2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025)}
    assert {year: (f["winner"], f["runner_up"], f["score"]) for year, f in finals.items()} == {
        2015: ("Novak Djokovic", "Roger Federer", "6-3 6-7(5) 6-2"),
        2016: ("Novak Djokovic", "Milos Raonic", "6-2 6-0"),
        2017: ("Roger Federer", "Stan Wawrinka", "6-4 7-5"),
        2018: ("Juan Martin del Potro", "Roger Federer", "6-4 6-7(8) 7-6(2)"),
        2019: ("Dominic Thiem", "Roger Federer", "3-6 6-3 7-5"),
        2021: ("Cameron Norrie", "Nikoloz Basilashvili", "3-6 6-4 6-1"),
        2022: ("Taylor Fritz", "Rafael Nadal", "6-3 7-6(5)"),
        2023: ("Carlos Alcaraz", "Daniil Medvedev", "6-3 6-2"),
        2024: ("Carlos Alcaraz", "Daniil Medvedev", "7-6(5) 6-1"),
        2025: ("Jack Draper", "Holger Rune", "6-2 6-2"),
    }
    with pytest.raises(ValueError):
        truth.event_final(conn, 2020, "Indian Wells Masters")  # not played
    assert truth.event_final(conn, 2025, "United Cup") is None
    assert truth.event_final(conn, 2025, "Brisbane") == {"winner": "Jiri Lehecka", "runner_up": "Reilly Opelka", "score": "4-1 RET"}


@needs_db
def test_shot_direction_matches_named_sources(conn):
    """Hand 32: Sinner's six charted Roland Garros 2024 matches (the matches of hand 26), each side
    and direction hit: shots, winners, unforced errors, points won (D-038)."""
    result = truth.shot_direction_totals(conn, SINNER, F(season=2024, levels=("G",), surface="Clay"))
    cells = {f"{side}-{direction}": (v[0], v[1], v[3], v[4]) for (side, direction), v in result["sums"].items()}
    assert result["matches"] == 6
    assert cells == {
        "B-DTL": (104, 16, 16, 63), "B-DTM": (201, 1, 10, 93), "B-IO": (26, 4, 3, 18), "B-XC": (392, 8, 23, 223),
        "F-DTL": (87, 12, 16, 49), "F-DTM": (187, 1, 7, 94), "F-II": (40, 3, 3, 28), "F-IO": (184, 19, 14, 127),
        "F-XC": (266, 35, 21, 175), "S-DTL": (13, 0, 1, 7), "S-DTM": (7, 0, 1, 2), "S-IO": (2, 0, 0, 1), "S-XC": (17, 1, 1, 5),
    }  # fmt: skip


@needs_db
def test_shot_direction_agrees_with_the_loader(conn):
    """Two implementations of D-038's rules, the loader's and this module's, must keep the same
    rows for every player of every chart both link to a tour match. The rules that leave a chart
    out (a repeated row with other counts, shots that aren't points won plus lost) are exercised
    by the real file: 13 charts repeat rows."""
    linked = [r["chart_id"] for r in conn.execute(truth.CHARTS_SQL + "SELECT chart_id FROM linked",
                                                  {"player": None, "opponent": None, **F().params()}).fetchall()]  # fmt: skip
    names: dict[str, set[str]] = {}
    for row in conn.execute("SELECT DISTINCT match_id, player1, player2 FROM raw.charting_matches WHERE match_id = ANY(%(ids)s)",
                            {"ids": linked}).fetchall():  # fmt: skip
        names.setdefault(row["match_id"], set()).update((row["player1"], row["player2"]))
    ours = {
        (chart_id, name, side, direction, *values)
        for (chart_id, name), cells in truth.shot_direction_cells(conn, names).items()
        for (side, direction), values in cells.items()
    }
    loaded = {
        (r["chart_id"], r["name"], r["side"], r["direction"], r["shots"], r["winners"], r["induced_forced"],
         r["unforced"], r["points_won"], r["points_lost"])
        for r in conn.execute(
            "SELECT d.*, CASE WHEN d.player_id = c.player1_id THEN m.player1 ELSE m.player2 END AS name "
            "FROM charting_shot_direction d JOIN charting_matches c USING (chart_id) "
            "JOIN (SELECT DISTINCT match_id, player1, player2 FROM raw.charting_matches) m ON m.match_id = d.chart_id "
            "WHERE d.chart_id = ANY(%(ids)s)", {"ids": linked}).fetchall()
    }  # fmt: skip
    assert len(loaded) > 90_000  # a floor, so an empty join cannot pass; 2015-2025 charts only
    assert ours == loaded


class _Rows:
    """A stand-in connection that returns the given rows, for rules no real row breaks."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        return self

    def fetchall(self):
        return self.rows


def test_shot_direction_rules_on_made_up_rows():
    """D-038's rules for leaving a player's chart out. Every real row has shots equal to points won
    plus lost, and winners and errors no more than shots, so those two need made-up rows."""

    def row(chart, label, shots="10", winners="2", forced="1", unforced="3", won="6", lost="4", player="A"):
        return {"match_id": chart, "player": player, "row": label, "shots": shots, "winners": winners,
                "induced_forced": forced, "unforced": unforced, "shots_in_pts_won": won, "shots_in_pts_lost": lost}  # fmt: skip

    rows = [
        row("ok", "F-XC"), row("ok", "B-DTL"), row("ok", "F-XC", player="B"),
        row("exact_repeat", "F-IO"), row("exact_repeat", "F-IO"),
        row("other_counts", "F-IO"), row("other_counts", "F-IO", winners="3"),
        row("sum", "F-XC", won="5"),
        row("errors", "F-XC", winners="5", forced="3", unforced="3"),
        row("not_whole", "F-XC", shots="10.0"), row("negative", "F-XC", unforced="-1"),
        row("unknown_side", "X-XC"), row("unknown_direction", "F-ZZ"),
    ]  # fmt: skip
    names = {r["match_id"]: {"A"} for r in rows}
    cells = truth.shot_direction_cells(_Rows(rows), names)
    assert cells == {
        ("ok", "A"): {("F", "XC"): (10, 2, 1, 3, 6, 4), ("B", "DTL"): (10, 2, 1, 3, 6, 4)},  # B's row isn't A's
        ("exact_repeat", "A"): {("F", "IO"): (10, 2, 1, 3, 6, 4)},  # counted once
    }
