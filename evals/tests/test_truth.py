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
    return NOT_A_PATTERN


def stats_tool_value(stats, conn, expect):
    """The same number from the stats layer, through the tool a correct answer would call."""
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
            t = totals(conn, expect.player, expect.filters, expect.opponent)
            if expect.stat in COUNTS or expect.stat in truth.TOTALS_STATS:
                ours = getattr(t, expect.stat) if expect.stat in COUNTS else t.stat(expect.stat)
            else:
                ours = truth.pattern_value(conn, expect.stat, expect.player, expect.filters)[0]
            theirs = stats_tool_value(stats, api_conn, expect)
            assert ours is not None, (case.id, expect)
            if theirs is None or abs(ours - theirs) > 5e-5:  # the stats layer rounds rates to 4 places
                differences.append((case.id, expect.stat, ours, theirs))
    api_conn.close()
    assert differences == []


def test_cases_are_well_formed():
    ids = [case.id for case in CASES]
    assert len(ids) == len(set(ids)) == 51  # the spec's 40, 3 from bugs found by hand, 8 for D-029 and D-030
    counts = {}
    for case in CASES:
        counts[case.category] = counts.get(case.category, 0) + 1
        assert case.expects or case.refusal, case.id
    assert counts == {"single_stat": 10, "filtered_stat": 10, "head_to_head": 11, "comparison": 6, "refuse_or_caveat": 7,
                      "scouting_pattern": 7}  # fmt: skip


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
            "charts", "chart_keys", "tour", "fits", "g", "chosen", "d", "linked", "mine"}  # fmt: skip
    sql = truth.PLAYER_MATCHES_SQL + truth.TOTALS_SQL + truth.SET_PATTERNS_SQL + truth.TOUR_TOTALS_SQL + truth.CHARTS_SQL
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
