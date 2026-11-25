"""Ground truth for the evals, computed from the raw source tables only (spec, Evals; D-012).

Independence rule: this module never imports the stats layer (`api`) or the loader
(`ingest`), and reads only the `raw` schema. The rules about which matches count are written
again here, in SQL, from the decision log rather than from the loader's code:
- D-006: exhibitions (from raw.special_events) are left out unless asked for;
- D-007: only completed, retired and defaulted matches count; the result type comes from the
  score text;
- D-008: a match's stats are used only if both players' stats pass the sanity rules;
- D-010: one level code per event, and a year means the file's season.

Shared assumptions (D-012): player identity comes from the reviewed merge file, and the
Sackmann seasons 2015-2025 are the scope, so answers don't change when TML refreshes 2026.
Hands other than R or L count as unknown, and a filter on opponent hand leaves those
matches out, as a filter on surface leaves out matches with no surface.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg.rows import dict_row

def connect() -> psycopg.Connection:
    """A read-only connection of the evals' own (not the API's), from DATABASE_URL."""
    options = "-c default_transaction_read_only=on -c statement_timeout=60000"
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True, options=options)


# One row per player per match, with everything the questions filter on, written as SQL so the
# rules are visible in one place. %(player)s limits it to one player's matches early, so the
# score parsing runs only on those (NULL: every player). Parameters are bound by psycopg.
PLAYER_MATCHES_SQL = r"""
WITH src AS (
  SELECT r.season, r.row_num, r.tourney_id, trim(r.score) AS score, r.tourney_name, trim(r.round) AS round,
         CASE WHEN trim(r.best_of) ~ '^\d+$' THEN trim(r.best_of)::int END AS best_of,
         trim(r.winner_name) AS winner_name, trim(r.loser_name) AS loser_name,
         CASE WHEN trim(r.winner_rank) ~ '^\d+$' THEN trim(r.winner_rank)::int END AS winner_rank,
         CASE WHEN trim(r.loser_rank) ~ '^\d+$' THEN trim(r.loser_rank)::int END AS loser_rank,
         to_date(r.tourney_date, 'YYYYMMDD') AS tourney_date,
         CASE WHEN r.surface IN ('Hard', 'Clay', 'Grass', 'Carpet') THEN r.surface END AS surface,
         CASE WHEN r.tourney_level = 'D' THEN 'D' ELSE coalesce(se.level, r.tourney_level) END AS level,
         coalesce(r.tourney_level <> 'D' AND se.is_exhibition = 'true', false) AS exhibition,
         coalesce(mw.canonical_id, r.winner_id)::int AS winner,
         coalesce(ml.canonical_id, r.loser_id)::int AS loser,
         r.w_ace, r.w_df, r.w_svpt, r."w_1stIn", r."w_1stWon", r."w_2ndWon", r."w_SvGms", r."w_bpSaved", r."w_bpFaced",
         r.l_ace, r.l_df, r.l_svpt, r."l_1stIn", r."l_1stWon", r."l_2ndWon", r."l_SvGms", r."l_bpSaved", r."l_bpFaced"
  FROM raw.matches r
  LEFT JOIN raw.special_events se ON se.tourney_name = trim(r.tourney_name)
  LEFT JOIN raw.player_merges mw ON mw.duplicate_id = r.winner_id
  LEFT JOIN raw.player_merges ml ON ml.duplicate_id = r.loser_id
  WHERE r.source = 'sackmann' AND r.season BETWEEN 2015 AND 2025
    AND (%(player)s::int IS NULL
         OR %(player)s IN (coalesce(mw.canonical_id, r.winner_id)::int, coalesce(ml.canonical_id, r.loser_id)::int))
),
-- Each whitespace-separated token of the score, with its two numbers when it's a set score
-- ("6-4", "7-6(5)") or a match tiebreak ("[10-8]").
tokens AS (
  SELECT s.season, s.row_num, t.token,
         t.token ~ '^\d{1,2}-\d{1,2}(\(\d+\))?$' AS is_set,
         t.token ~ '^\[\d{1,2}-\d{1,2}\]$' AS is_match_tiebreak,
         (regexp_match(t.token, '^\[?(\d{1,2})-(\d{1,2})'))[1]::int AS a,
         (regexp_match(t.token, '^\[?(\d{1,2})-(\d{1,2})'))[2]::int AS b
  FROM src s, regexp_split_to_table(s.score, '\s+') AS t(token)
  WHERE s.score <> ''
),
sets AS (
  SELECT season, row_num,
         bool_and(is_set OR is_match_tiebreak) AS all_set_scores,
         count(*) FILTER (WHERE (is_set OR is_match_tiebreak) AND a > b) AS winner_sets,
         count(*) FILTER (WHERE (is_set OR is_match_tiebreak) AND b > a) AS loser_sets,
         count(*) FILTER (WHERE is_set AND least(a, b) = 6 AND greatest(a, b) = 7) AS tiebreak_sets
  FROM tokens
  GROUP BY season, row_num
),
typed AS (
  SELECT s.*, coalesce(x.tiebreak_sets, 0) AS tiebreak_sets,
         CASE
           WHEN strpos(upper(s.score), 'W/O') > 0 OR strpos(upper(s.score), 'WALKOVER') > 0 THEN 'walkover'
           WHEN strpos(upper(s.score), 'RET') > 0 THEN 'retired'
           WHEN strpos(upper(s.score), 'DEF') > 0 THEN 'defaulted'
           WHEN x.all_set_scores AND x.winner_sets > x.loser_sets THEN 'completed'
           ELSE 'unknown'
         END AS result_type
  FROM src s LEFT JOIN sets x USING (season, row_num)
),
-- Both sides' stats as numbers (NULL unless a whole number), one row per side.
sides AS (
  SELECT t.season, t.row_num, t.result_type, t.tiebreak_sets, side.*
  FROM typed t,
  LATERAL (VALUES
    ('w', t.winner, t.w_ace, t.w_df, t.w_svpt, t."w_1stIn", t."w_1stWon", t."w_2ndWon", t."w_SvGms", t."w_bpSaved", t."w_bpFaced"),
    ('l', t.loser,  t.l_ace, t.l_df, t.l_svpt, t."l_1stIn", t."l_1stWon", t."l_2ndWon", t."l_SvGms", t."l_bpSaved", t."l_bpFaced")
  ) AS raw_side(side, player, ace, df, svpt, first_in, first_won, second_won, games, bp_saved, bp_faced),
  LATERAL (SELECT raw_side.side, raw_side.player,
    CASE WHEN trim(raw_side.ace) ~ '^-?\d+$' THEN trim(raw_side.ace)::int END AS ace,
    CASE WHEN trim(raw_side.df) ~ '^-?\d+$' THEN trim(raw_side.df)::int END AS df,
    CASE WHEN trim(raw_side.svpt) ~ '^-?\d+$' THEN trim(raw_side.svpt)::int END AS svpt,
    CASE WHEN trim(raw_side.first_in) ~ '^-?\d+$' THEN trim(raw_side.first_in)::int END AS first_in,
    CASE WHEN trim(raw_side.first_won) ~ '^-?\d+$' THEN trim(raw_side.first_won)::int END AS first_won,
    CASE WHEN trim(raw_side.second_won) ~ '^-?\d+$' THEN trim(raw_side.second_won)::int END AS second_won,
    CASE WHEN trim(raw_side.games) ~ '^-?\d+$' THEN trim(raw_side.games)::int END AS games,
    CASE WHEN trim(raw_side.bp_saved) ~ '^-?\d+$' THEN trim(raw_side.bp_saved)::int END AS bp_saved,
    CASE WHEN trim(raw_side.bp_faced) ~ '^-?\d+$' THEN trim(raw_side.bp_faced)::int END AS bp_faced,
    concat(raw_side.ace, raw_side.df, raw_side.svpt, raw_side.first_in, raw_side.first_won,
           raw_side.second_won, raw_side.games, raw_side.bp_saved, raw_side.bp_faced) ~ '\S' AS any_value
  ) AS side
),
-- D-008: is one side's stat line believable on its own?
side_ok AS (
  SELECT season, row_num, side, player, ace, svpt, first_in, first_won, second_won, bp_saved, bp_faced, any_value,
         ace IS NOT NULL AND df IS NOT NULL AND svpt IS NOT NULL AND first_in IS NOT NULL
           AND first_won IS NOT NULL AND second_won IS NOT NULL AND games IS NOT NULL
           AND bp_saved IS NOT NULL AND bp_faced IS NOT NULL
           AND least(ace, df, svpt, first_in, first_won, second_won, games, bp_saved, bp_faced) >= 0
           AND (svpt > 0 OR result_type IN ('retired', 'defaulted'))
           AND (svpt = 0 OR games > 0)
           AND svpt >= greatest(games, 4 * games - 3 * tiebreak_sets
                                - CASE WHEN result_type IN ('retired', 'defaulted') THEN 3 ELSE 0 END)
           AND first_in <= svpt AND first_won <= first_in AND second_won + df <= svpt - first_in
           AND bp_saved <= bp_faced AND ace <= first_won + second_won AS valid
  FROM sides
),
match_stats AS (
  SELECT season, row_num,
         bool_or(any_value) AS any_value,
         bool_and(valid) AND max(svpt) > 0 AS sides_valid
  FROM side_ok GROUP BY season, row_num
)
SELECT t.season, t.row_num, t.tourney_id, t.tourney_name, t.tourney_date, t.surface, t.level, t.exhibition,
       t.result_type, t.score, t.round, t.best_of,
       CASE WHEN me.side = 'w' THEN t.winner_name ELSE t.loser_name END AS player_name,
       CASE WHEN me.side = 'w' THEN t.loser_name ELSE t.winner_name END AS opponent_name,
       CASE WHEN me.side = 'w' THEN t.loser_rank ELSE t.winner_rank END AS opponent_rank,
       coalesce(ms.any_value AND ms.sides_valid AND t.result_type <> 'walkover', false) AS has_stats,
       me.player, opp.player AS opponent, me.side = 'w' AS won,
       CASE WHEN p.hand IN ('R', 'L') THEN p.hand END AS opponent_hand,
       me.ace, me.svpt, me.first_in, me.first_won, me.second_won, me.bp_saved, me.bp_faced,
       opp.svpt AS opp_svpt, opp.first_in AS opp_first_in, opp.first_won AS opp_first_won, opp.second_won AS opp_second_won,
       opp.bp_saved AS opp_bp_saved, opp.bp_faced AS opp_bp_faced
FROM typed t
JOIN match_stats ms USING (season, row_num)
JOIN side_ok me ON me.season = t.season AND me.row_num = t.row_num
JOIN side_ok opp ON opp.season = t.season AND opp.row_num = t.row_num AND opp.side <> me.side
LEFT JOIN raw.sackmann_players p ON p.player_id = opp.player::text
"""

# The matches one question is about: a player, optionally one opponent, and the filters.
# Excluded matches are kept with the reason, so refusals and caveats can be checked.
SCOPE_SQL = (
    "WITH pm AS (" + PLAYER_MATCHES_SQL + r"""),
scoped AS (
  SELECT pm.*,
         CASE
           WHEN exhibition AND NOT %(include_exhibitions)s THEN 'exhibition'
           WHEN result_type NOT IN ('completed', 'retired', 'defaulted') THEN result_type
           WHEN %(surface)s::text IS NOT NULL AND surface IS NULL THEN 'no surface'
           WHEN %(opponent_hand)s::text IS NOT NULL AND opponent_hand IS NULL THEN 'unknown hand'
           WHEN %(opponent_rank_max)s::int IS NOT NULL AND opponent_rank IS NULL THEN 'unknown rank'
         END AS left_out
  FROM pm
  WHERE player = %(player)s
    AND (%(opponent)s::int IS NULL OR opponent = %(opponent)s)
    AND (%(season)s::int IS NULL OR season = %(season)s)
    AND (%(date_from)s::date IS NULL OR tourney_date >= %(date_from)s)
    AND (%(date_to)s::date IS NULL OR tourney_date <= %(date_to)s)
    AND (%(surface)s::text IS NULL OR surface IS NULL OR surface = %(surface)s)
    AND (%(levels)s::text[] IS NULL OR level = ANY(%(levels)s))
    AND (%(opponent_hand)s::text IS NULL OR opponent_hand IS NULL OR opponent_hand = %(opponent_hand)s)
    AND (%(opponent_rank_max)s::int IS NULL OR opponent_rank IS NULL OR opponent_rank <= %(opponent_rank_max)s)
)
"""
)

TOTALS_SQL = (
    SCOPE_SQL
    + """
SELECT count(*) FILTER (WHERE left_out IS NULL) AS matches,
       count(*) FILTER (WHERE left_out IS NULL AND won) AS wins,
       count(*) FILTER (WHERE left_out IS NULL AND NOT won) AS losses,
       count(*) FILTER (WHERE left_out IS NULL AND has_stats) AS matches_with_stats,
       count(*) FILTER (WHERE left_out IS NOT NULL) AS left_out,
       count(*) FILTER (WHERE left_out = 'no surface') AS no_surface,
       count(*) FILTER (WHERE left_out = 'unknown hand') AS unknown_hand,
       sum(ace) FILTER (WHERE left_out IS NULL AND has_stats) AS aces,
       sum(svpt) FILTER (WHERE left_out IS NULL AND has_stats) AS serve_points,
       sum(first_in) FILTER (WHERE left_out IS NULL AND has_stats) AS first_in,
       sum(first_won) FILTER (WHERE left_out IS NULL AND has_stats) AS first_won,
       sum(second_won) FILTER (WHERE left_out IS NULL AND has_stats) AS second_won,
       sum(bp_saved) FILTER (WHERE left_out IS NULL AND has_stats) AS bp_saved,
       sum(bp_faced) FILTER (WHERE left_out IS NULL AND has_stats) AS bp_faced,
       sum(opp_svpt) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_serve_points,
       sum(opp_first_won + opp_second_won) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_serve_won,
       sum(opp_first_in) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_first_in,
       sum(opp_first_won) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_first_won,
       sum(opp_second_won) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_second_won,
       sum(opp_bp_saved) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_bp_saved,
       sum(opp_bp_faced) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_bp_faced
FROM scoped
"""
)


@dataclass(frozen=True)
class Filters:
    """The filters a question states. A year is a season (D-010); dates are inclusive."""

    season: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    surface: str | None = None
    levels: tuple[str, ...] | None = None
    opponent_hand: str | None = None
    include_exhibitions: bool = False
    opponent_rank_max: int | None = None  # the opponent's ranking at the time (D-029)

    def params(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "date_from": dt.date.fromisoformat(self.date_from) if self.date_from else None,
            "date_to": dt.date.fromisoformat(self.date_to) if self.date_to else None,
            "surface": self.surface,
            "levels": list(self.levels) if self.levels else None,
            "opponent_hand": self.opponent_hand,
            "include_exhibitions": self.include_exhibitions,
            "opponent_rank_max": self.opponent_rank_max,
        }


# The stats Totals.stat computes (the spec's definitions).
TOTALS_STATS = ("win_rate", "aces_per_match", "first_serve_in", "first_serve_points_won", "second_serve_points_won",
                "service_points_won", "return_points_won", "first_serve_return_points_won",
                "second_serve_return_points_won", "break_points_saved", "break_points_converted")  # fmt: skip


@dataclass(frozen=True)
class Totals:
    """Counts and summed stat columns for one player's matches under some filters."""

    matches: int
    wins: int
    losses: int
    matches_with_stats: int
    left_out: int
    sums: dict[str, int] = field(default_factory=dict)
    left_out_by: dict[str, int] = field(default_factory=dict)  # no_surface, unknown_hand

    def rate(self, numerator: int | None, denominator: int | None) -> float | None:
        if numerator is None or not denominator:
            return None  # a zero denominator has no rate (spec, edge cases)
        return numerator / denominator

    # The spec's stat definitions, written out again here.
    def stat(self, name: str) -> float | None:
        s = self.sums
        if name == "win_rate":
            return self.rate(self.wins, self.matches)
        if name == "aces_per_match":
            return self.rate(s["aces"], self.matches_with_stats)
        if name == "first_serve_in":
            return self.rate(s["first_in"], s["serve_points"])
        if name == "first_serve_points_won":
            return self.rate(s["first_won"], s["first_in"])
        if name == "second_serve_points_won":
            second_serves = None if s["serve_points"] is None else s["serve_points"] - s["first_in"]
            return self.rate(s["second_won"], second_serves)
        if name == "service_points_won":
            won = None if s["first_won"] is None else s["first_won"] + s["second_won"]
            return self.rate(won, s["serve_points"])
        if name == "return_points_won":
            if not s["opp_serve_points"]:
                return None
            return 1 - s["opp_serve_won"] / s["opp_serve_points"]
        # D-033: return points against the opponent's first serves in, and against their second
        # serves (every serve point that wasn't a first serve in).
        if name == "first_serve_return_points_won":
            won = None if s["opp_first_in"] is None else s["opp_first_in"] - s["opp_first_won"]
            return self.rate(won, s["opp_first_in"])
        if name == "second_serve_return_points_won":
            if s["opp_serve_points"] is None:
                return None
            second_serves = s["opp_serve_points"] - s["opp_first_in"]
            return self.rate(second_serves - s["opp_second_won"], second_serves)
        if name == "break_points_saved":
            return self.rate(s["bp_saved"], s["bp_faced"])
        if name == "break_points_converted":
            converted = None if s["opp_bp_faced"] is None else s["opp_bp_faced"] - s["opp_bp_saved"]
            return self.rate(converted, s["opp_bp_faced"])
        raise ValueError(f"unknown stat {name!r}")


def totals(conn: psycopg.Connection, player: int, filters: Filters = Filters(), opponent: int | None = None) -> Totals:
    row = conn.execute(TOTALS_SQL, {"player": player, "opponent": opponent, **filters.params()}).fetchone()
    counts = ("matches", "wins", "losses", "matches_with_stats", "left_out")
    reasons = ("no_surface", "unknown_hand")
    sums = {key: (None if value is None else int(value)) for key, value in row.items() if key not in counts + reasons}
    return Totals(*(int(row[key]) for key in counts), sums=sums, left_out_by={key: int(row[key]) for key in reasons})


# ---------- Milestones 8 and 9 (D-029, D-030), written again from the decision log ----------

# Set patterns: the completed matches in scope, one row per set token, from the player's side.
# A tiebreak is a set with a tiebreak score in parentheses, or a 7-6 set; a match that used all
# its sets was decided in the last one; retirements and defaults are left out.
SET_PATTERNS_SQL = (
    SCOPE_SQL
    + r""",
set_tokens AS (
  SELECT sc.season, sc.row_num, sc.won, sc.best_of, t.ord, t.token,
         (regexp_match(t.token, '^\[?(\d+)-(\d+)'))[1]::int AS a,
         (regexp_match(t.token, '^\[?(\d+)-(\d+)'))[2]::int AS b
  FROM scoped sc, regexp_split_to_table(sc.score, '\s+') WITH ORDINALITY AS t(token, ord)
  WHERE sc.left_out IS NULL AND sc.result_type = 'completed'
),
per_match AS (
  SELECT season, row_num, won, best_of, count(*) AS sets,
         count(*) FILTER (WHERE token LIKE '%%(%%' OR token IN ('7-6', '6-7')) AS tb_played,
         count(*) FILTER (WHERE (token LIKE '%%(%%' OR token IN ('7-6', '6-7'))
                            AND CASE WHEN won THEN a > b ELSE b > a END) AS tb_won,
         bool_or(ord = 1 AND CASE WHEN won THEN a > b ELSE b > a END) AS won_first_set
  FROM set_tokens GROUP BY season, row_num, won, best_of
)
SELECT coalesce(sum(tb_won), 0) AS tiebreaks_won_count, coalesce(sum(tb_played), 0) AS tiebreaks_played,
       count(*) FILTER (WHERE sets = best_of AND won) AS deciding_won, count(*) FILTER (WHERE sets = best_of) AS deciding_played,
       count(*) FILTER (WHERE won_first_set AND won) AS after_win_won, count(*) FILTER (WHERE won_first_set) AS after_win_played,
       count(*) FILTER (WHERE NOT won_first_set AND won) AS after_loss_won, count(*) FILTER (WHERE NOT won_first_set) AS after_loss_played,
       count(*) AS completed
FROM per_match
"""
)

# Every player's totals under the same rules, for tour ranks: the scope with its one-player
# condition removed (PLAYER_MATCHES_SQL already reads every player when %(player)s is NULL).
_ONE_PLAYER = "  WHERE player = %(player)s\n"
assert SCOPE_SQL.count(_ONE_PLAYER) == 1
TOUR_TOTALS_SQL = (
    SCOPE_SQL.replace(_ONE_PLAYER, "  WHERE TRUE\n")
    + """
SELECT player, count(*) FILTER (WHERE left_out IS NULL) AS matches,
       count(*) FILTER (WHERE left_out IS NULL AND has_stats) AS matches_with_stats,
       sum(ace) FILTER (WHERE left_out IS NULL AND has_stats) AS aces,
       sum(svpt) FILTER (WHERE left_out IS NULL AND has_stats) AS serve_points,
       sum(first_in) FILTER (WHERE left_out IS NULL AND has_stats) AS first_in,
       sum(first_won) FILTER (WHERE left_out IS NULL AND has_stats) AS first_won,
       sum(second_won) FILTER (WHERE left_out IS NULL AND has_stats) AS second_won,
       sum(bp_saved) FILTER (WHERE left_out IS NULL AND has_stats) AS bp_saved,
       sum(bp_faced) FILTER (WHERE left_out IS NULL AND has_stats) AS bp_faced,
       sum(opp_svpt) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_serve_points,
       sum(opp_first_won + opp_second_won) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_serve_won,
       sum(opp_bp_saved) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_bp_saved,
       sum(opp_bp_faced) FILTER (WHERE left_out IS NULL AND has_stats) AS opp_bp_faced
FROM scoped
GROUP BY player
"""
)

# Charted matches: a chart counts for a tour match in scope when both names match the raw match
# file's names (letters only, case ignored), the round is the same (any round for a Davis Cup
# tie, written "RR"), and the tournament starts 14 days before to 3 days after the chart date.
# If several tour matches fit a chart, the one that started most recently on or before the
# chart date wins; a chart with no single winner, a tour match chosen by two charts, and a
# chart ID listed twice with different details don't count. Names are compared over every
# Sackmann match, not just the player's, so a chart is linked the same way for both players.
CHARTS_SQL = (
    SCOPE_SQL
    + r""",
charts AS (
  SELECT match_id AS chart_id, min(player1) AS player1, min(player2) AS player2,
         to_date(min(date), 'YYYYMMDD') AS chart_date, min(round) AS round
  FROM raw.charting_matches
  WHERE match_id <> ''
  GROUP BY match_id
  HAVING count(DISTINCT (player1, player2, date, tournament, round, surface, best_of)) = 1
     AND min(date) ~ '^\d{8}$'
),
chart_keys AS MATERIALIZED (
  SELECT c.*, least(a.k, b.k) || '|' || greatest(a.k, b.k) AS pair
  FROM charts c,
       LATERAL (SELECT regexp_replace(lower(c.player1), '[^a-z]', '', 'g') AS k) a,
       LATERAL (SELECT regexp_replace(lower(c.player2), '[^a-z]', '', 'g') AS k) b
),
tour AS MATERIALIZED (
  SELECT r.season, r.row_num, trim(r.round) AS round, r.tourney_level AS level,
         to_date(r.tourney_date, 'YYYYMMDD') AS tourney_date,
         least(w.k, l.k) || '|' || greatest(w.k, l.k) AS pair
  FROM raw.matches r,
       LATERAL (SELECT regexp_replace(lower(r.winner_name), '[^a-z]', '', 'g') AS k) w,
       LATERAL (SELECT regexp_replace(lower(r.loser_name), '[^a-z]', '', 'g') AS k) l
  WHERE r.source = 'sackmann' AND r.season BETWEEN 2015 AND 2025
),
fits AS MATERIALIZED (
  SELECT c.chart_id, c.chart_date, c.player1, t.season, t.row_num, t.tourney_date
  FROM chart_keys c JOIN tour t ON t.pair = c.pair
   AND (t.round = c.round OR (t.level = 'D' AND t.round = 'RR'))
   AND t.tourney_date BETWEEN c.chart_date - 14 AND c.chart_date + 3
),
chosen AS MATERIALIZED (
  SELECT f.* FROM fits f
  WHERE (SELECT count(*) FROM fits g WHERE g.chart_id = f.chart_id) = 1
     OR (f.tourney_date <= f.chart_date
         AND NOT EXISTS (SELECT 1 FROM fits g WHERE g.chart_id = f.chart_id AND g.tourney_date <= g.chart_date
                         AND (g.tourney_date > f.tourney_date OR (g.tourney_date = f.tourney_date AND g.row_num <> f.row_num))))
),
linked AS (
  SELECT c.* FROM chosen c
  WHERE (SELECT count(*) FROM chosen d WHERE (d.season, d.row_num) = (c.season, c.row_num)) = 1
),
mine AS (
  SELECT l.chart_id, l.player1, sc.player_name
  FROM scoped sc JOIN linked l ON (l.season, l.row_num) = (sc.season, sc.row_num)
  WHERE sc.left_out IS NULL
)
"""
)


@dataclass(frozen=True)
class Charted:
    """The player's charted matches in scope, and their names in the charting files."""

    chart_ids: list[str]
    names: dict[str, str]  # chart_id -> the player's name as the chart writes it
    first: dict[str, bool]  # chart_id -> whether the player is the chart's Player 1


def _letters(name: str) -> str:
    return "".join(ch for ch in name.lower() if "a" <= ch <= "z")


def charted(conn: psycopg.Connection, player: int, filters: Filters = Filters()) -> Charted:
    mine = {
        row["chart_id"]: row["player_name"]
        for row in conn.execute(CHARTS_SQL + "SELECT chart_id, player_name FROM mine",
                                {"player": player, "opponent": None, **filters.params()}).fetchall()
    }  # fmt: skip
    names, first = {}, {}
    for row in conn.execute("SELECT DISTINCT match_id, player1, player2 FROM raw.charting_matches WHERE match_id = ANY(%(ids)s)",
                            {"ids": list(mine)}).fetchall():  # fmt: skip
        is_first = _letters(row["player1"]) == _letters(mine[row["match_id"]])
        names[row["match_id"]] = row["player1"] if is_first else row["player2"]
        first[row["match_id"]] = is_first
    return Charted(sorted(names), names, first)


def _whole(value: str | None) -> int | None:
    text = (value or "").strip()
    return int(text) if text.isdigit() else None


def shot_totals(conn: psycopg.Connection, player: int, filters: Filters = Filters()) -> dict[str, Any]:
    """Sums over the player's charted matches in scope. A match's serve directions need both of
    its rows ('1': first serves in; '2': every second serve); its rally lengths need the Total
    row of Player 1's side, with the length bands adding up to it."""
    c = charted(conn, player, filters)
    out: dict[str, Any] = {"charted_matches": len(c.chart_ids)}
    serve = {(r["match_id"], r["row"]): r for r in conn.execute(
        "SELECT * FROM raw.charting_serve_direction WHERE match_id = ANY(%(ids)s) AND row IN ('1', '2')",
        {"ids": c.chart_ids}).fetchall() if r["player"] == c.names[r["match_id"]]}  # fmt: skip
    columns = ("deuce_wide", "deuce_middle", "deuce_t", "ad_wide", "ad_middle", "ad_t")
    for row_name in ("1", "2"):
        for column in columns:
            out[f"serve{row_name}_{column}"] = 0
    for chart_id in c.chart_ids:
        pair = [serve.get((chart_id, "1")), serve.get((chart_id, "2"))]
        if None in pair or any(_whole(r[col]) is None for r in pair for col in columns):
            continue
        for row_name, r in zip(("1", "2"), pair):
            for column in columns:
                out[f"serve{row_name}_{column}"] += _whole(r[column])
    rally_rows = conn.execute(
        "SELECT r.* FROM raw.charting_rally r JOIN raw.charting_matches m ON m.match_id = r.match_id AND m.player1 = r.server "
        "WHERE r.match_id = ANY(%(ids)s) AND r.row IN ('Total', '1-3', '4-6', '7-9', '10')", {"ids": c.chart_ids}).fetchall()  # fmt: skip
    by_chart: dict[str, dict[str, dict]] = {}
    for r in rally_rows:
        by_chart.setdefault(r["match_id"], {})[r["row"]] = r
    for band in ("1-3", "4-6", "7-9", "10"):
        out[f"rally_{band}_won"] = out[f"rally_{band}_played"] = 0
    for chart_id, rows in by_chart.items():
        total = rows.get("Total")
        bands = {b: rows.get(b) for b in ("1-3", "4-6", "7-9", "10")}
        if total is None or sum(_whole(r["pts"]) or 0 for r in bands.values() if r) != _whole(total["pts"]):
            continue
        side = "pl1_won" if c.first[chart_id] else "pl2_won"
        for band, r in bands.items():
            if r:
                out[f"rally_{band}_played"] += _whole(r["pts"])
                out[f"rally_{band}_won"] += _whole(r[side])
    return out


def rank_in_tour(conn: psycopg.Connection, stat: str, player: int, filters: Filters, min_matches: int = 10) -> dict[str, Any]:
    """The player's rank for one stat among players with at least min_matches matches with
    stats: 1 is the highest, and equal values share the better rank."""
    rows = conn.execute(TOUR_TOTALS_SQL, {"player": None, "opponent": None, **filters.params()}).fetchall()
    sums_keys = ("aces", "serve_points", "first_in", "first_won", "second_won", "bp_saved", "bp_faced",
                 "opp_serve_points", "opp_serve_won", "opp_bp_saved", "opp_bp_faced")  # fmt: skip
    values = {}
    for row in rows:
        if row["matches_with_stats"] < min_matches:
            continue
        t = Totals(int(row["matches"]), 0, 0, int(row["matches_with_stats"]), 0,
                   sums={k: None if row[k] is None else int(row[k]) for k in sums_keys})  # fmt: skip
        value = t.stat(stat)
        if value is not None:
            values[row["player"]] = value
    mine = values.get(player)
    return {"rank": None if mine is None else 1 + sum(1 for v in values.values() if v > mine), "players_ranked": len(values)}


def set_totals(conn: psycopg.Connection, player: int, filters: Filters = Filters()) -> dict[str, int]:
    row = conn.execute(SET_PATTERNS_SQL, {"player": player, "opponent": None, **filters.params()}).fetchone()
    return {key: int(value) for key, value in row.items()}


def _share(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


# ---------- Milestones 11 to 14 (D-033 to D-038), written again from the decision log ----------

# Season paths (D-035): every counted match, plus walkovers, which a path shows but never counts.
# A walkover is shown only where a counted match would be, so a filter on surface, hand or ranking
# leaves out one whose value is unknown. A final won, by walkover too, is a title, except at a
# Davis Cup tie or a team event (a special event whose note says "Team"), where one player's
# matches can't say how the team did.
SEASON_EVENTS_SQL = (
    SCOPE_SQL
    + r""",
shown AS (
  SELECT * FROM scoped
  WHERE left_out IS NULL
     OR (left_out = 'walkover'
         AND (%(surface)s::text IS NULL OR surface IS NOT NULL)
         AND (%(opponent_hand)s::text IS NULL OR opponent_hand IS NOT NULL)
         AND (%(opponent_rank_max)s::int IS NULL OR opponent_rank IS NOT NULL))
),
per_event AS (
  SELECT tourney_id, min(trim(tourney_name)) AS tourney_name, min(level) AS level, min(tourney_date) AS tourney_date,
         count(*) FILTER (WHERE left_out IS NULL) AS matches,
         count(*) FILTER (WHERE left_out IS NULL AND won) AS wins,
         count(*) FILTER (WHERE left_out = 'walkover') AS walkovers,
         bool_or(round = 'F' AND won) AS won_final
  FROM shown
  GROUP BY tourney_id
)
SELECT pe.tourney_id, pe.tourney_name, pe.level, pe.tourney_date, pe.matches, pe.wins, pe.walkovers,
       pe.won_final AND pe.level <> 'D'
         AND NOT EXISTS (SELECT 1 FROM raw.special_events se
                         WHERE se.tourney_name = pe.tourney_name AND se.note ILIKE 'team%%') AS title
FROM per_event pe
ORDER BY pe.tourney_date, pe.tourney_id
"""
)


def season_events(conn: psycopg.Connection, player: int, filters: Filters) -> list[dict[str, Any]]:
    """One row per tournament of the player's season path, in date order."""
    return conn.execute(SEASON_EVENTS_SQL, {"player": player, "opponent": None, **filters.params()}).fetchall()


# A tournament's final (D-036): the round 'F' row of the raw match file, named the way that file
# names the tournament. A team event's final is a tie between teams, so it has no single winner,
# and neither does a final whose score contradicts the listed winner (D-007).
EVENT_FINAL_SQL = r"""
SELECT r.season, r.row_num, trim(r.winner_name) AS winner_name, trim(r.loser_name) AS loser_name,
       trim(r.score) AS score, coalesce(m.canonical_id, r.winner_id)::int AS winner,
       coalesce(se.note ILIKE 'team%%', false) AS team, coalesce(se.is_exhibition = 'true', false) AS exhibition
FROM raw.matches r
LEFT JOIN raw.player_merges m ON m.duplicate_id = r.winner_id
LEFT JOIN raw.special_events se ON se.tourney_name = trim(r.tourney_name)
WHERE r.source = 'sackmann' AND r.season = %(season)s AND trim(r.tourney_name) = %(event)s
  AND trim(r.round) = 'F' AND r.tourney_level <> 'D'
"""


def event_final(conn: psycopg.Connection, season: int, event: str) -> dict[str, str] | None:
    """The final's winner, runner-up and score (winner's games first), or None when no one player
    won it. Raises when the case names a final the data doesn't have once."""
    rows = conn.execute(EVENT_FINAL_SQL, {"season": season, "event": event}).fetchall()
    if len(rows) != 1:
        raise ValueError(f"{event} {season}: {len(rows)} final rows; fix the case")
    final = rows[0]
    if final["exhibition"]:
        raise ValueError(f"{event} {season} is an exhibition, left out of the calendar unless asked; fix the case")
    if final["team"]:
        return None
    played = conn.execute(
        "WITH pm AS (" + PLAYER_MATCHES_SQL + ") SELECT result_type FROM pm WHERE season = %(season)s AND row_num = %(row)s AND won",
        {"player": final["winner"], "season": final["season"], "row": final["row_num"]},
    ).fetchone()  # fmt: skip
    if played["result_type"] == "unknown":
        return None
    return {"winner": final["winner_name"], "runner_up": final["loser_name"], "score": final["score"]}


def last_name(full_name: str) -> str:
    return full_name.split()[-1]


# Shot direction (D-038): the charting file's counts for each side (forehand, backhand, backhand
# slice) and direction. A player's chart counts only when every one of its rows has a known side
# and direction and whole numbers, each row's shots are its points won plus lost, its winners and
# errors don't outnumber its shots, and no row appears twice with different counts (an exact
# repeat counts once). The file's pt_ending column isn't used.
SHOT_SIDES = {"F": "forehand", "B": "backhand", "S": "backhand_slice"}
SHOT_DIRECTIONS = {"XC": "crosscourt", "DTM": "down_the_middle", "DTL": "down_the_line", "IO": "inside_out", "II": "inside_in"}
SHOT_COLUMNS = ("shots", "winners", "induced_forced", "unforced", "shots_in_pts_won", "shots_in_pts_lost")
SHOT_DIRECTION_SQL = """
SELECT d.match_id, d.player, d.row, d.shots, d.winners, d.induced_forced, d.unforced, d.shots_in_pts_won, d.shots_in_pts_lost
FROM raw.charting_shot_direction d
WHERE d.match_id = ANY(%(ids)s)
"""


def shot_direction_cells(conn: psycopg.Connection, names: dict[str, set[str]]) -> dict[tuple[str, str], dict[tuple[str, str], tuple[int, ...]]]:
    """For each chart and player name asked for, the counts per (side, direction), in
    SHOT_COLUMNS order. A player's chart that breaks a rule is absent."""
    found: dict[tuple[str, str], list[dict]] = {}
    for row in conn.execute(SHOT_DIRECTION_SQL, {"ids": list(names)}).fetchall():
        if row["player"] in names[row["match_id"]]:
            found.setdefault((row["match_id"], row["player"]), []).append(row)
    out = {}
    for key, rows in found.items():
        cells: dict[tuple[str, str], tuple[int, ...]] = {}
        for row in rows:
            side, _, direction = row["row"].partition("-")
            values = tuple(_whole(row[column]) for column in SHOT_COLUMNS)
            if side not in SHOT_SIDES or direction not in SHOT_DIRECTIONS or None in values:
                break
            shots, winners, forced, unforced, won, lost = values
            if won + lost != shots or winners + forced + unforced > shots:
                break
            if cells.setdefault((side, direction), values) != values:
                break
        else:
            out[key] = cells
    return out


def shot_direction_totals(conn: psycopg.Connection, player: int, filters: Filters = Filters()) -> dict[str, Any]:
    """Sums over the player's charted matches in scope: the charts with shot direction, and
    each (side, direction)'s counts."""
    c = charted(conn, player, filters)
    cells = shot_direction_cells(conn, {chart_id: {c.names[chart_id]} for chart_id in c.chart_ids})
    sums: dict[tuple[str, str], list[int]] = {}
    for chart_cells in cells.values():
        for key, values in chart_cells.items():
            sums[key] = [a + b for a, b in zip(sums.get(key, [0] * len(SHOT_COLUMNS)), values)]
    return {"matches": len(cells), "sums": sums}


# Each new stat a question can expect: how to compute it, and whether it's a count (exact).
def pattern_value(conn: psycopg.Connection, stat: str, player: int, filters: Filters) -> tuple[float | int | None, str]:
    if stat in ("tiebreaks_won", "tiebreaks_won_count", "tiebreaks_played", "deciding_sets_won",
                "won_after_winning_first_set", "won_after_losing_first_set"):  # fmt: skip
        s = set_totals(conn, player, filters)
        return {
            "tiebreaks_won": (_share(s["tiebreaks_won_count"], s["tiebreaks_played"]), "rate"),
            "tiebreaks_won_count": (s["tiebreaks_won_count"], "count"),
            "tiebreaks_played": (s["tiebreaks_played"], "count"),
            "deciding_sets_won": (_share(s["deciding_won"], s["deciding_played"]), "rate"),
            "won_after_winning_first_set": (_share(s["after_win_won"], s["after_win_played"]), "rate"),
            "won_after_losing_first_set": (_share(s["after_loss_won"], s["after_loss_played"]), "rate"),
        }[stat]
    if stat.startswith(("tour_rank:", "tour_players:")):
        kind, measure = stat.split(":")
        ranked = rank_in_tour(conn, measure, player, filters)
        return (ranked["rank"] if kind == "tour_rank" else ranked["players_ranked"]), "count"
    if stat == "charted_matches":
        return shot_totals(conn, player, filters)["charted_matches"], "count"
    if stat.startswith(("dir_first_", "dir_second_")):
        s = shot_totals(conn, player, filters)
        row_name = "1" if stat.startswith("dir_first_") else "2"
        court, side = stat.removeprefix("dir_first_").removeprefix("dir_second_").split("_")
        column = {"wide": "wide", "body": "middle", "t": "t"}[side]
        court_total = sum(s[f"serve{row_name}_{court}_{c}"] for c in ("wide", "middle", "t"))
        return _share(s[f"serve{row_name}_{court}_{column}"], court_total), "rate"
    if stat.startswith("rally_") and stat.endswith("_won"):
        band = stat.removeprefix("rally_").removesuffix("_won").replace("_plus", "").replace("_", "-")
        s = shot_totals(conn, player, filters)
        return _share(s[f"rally_{band}_won"], s[f"rally_{band}_played"]), "rate"
    if stat in ("path_events", "path_titles"):
        events = season_events(conn, player, filters)
        return (len(events) if stat == "path_events" else sum(1 for e in events if e["title"])), "count"
    if stat == "shot_dir_matches":
        return shot_direction_totals(conn, player, filters)["matches"], "count"
    if stat.startswith("shot:"):  # shot:<side>:<direction>:<measure>, with names as in SHOT_SIDES
        _, side, direction, measure = stat.split(":")
        side_code = next(code for code, name in SHOT_SIDES.items() if name == side)
        direction_code = next(code for code, name in SHOT_DIRECTIONS.items() if name == direction)
        sums = shot_direction_totals(conn, player, filters)["sums"]
        shots, winners, forced, unforced, won, _ = sums.get((side_code, direction_code), [0] * len(SHOT_COLUMNS))
        if measure == "share":
            return _share(shots, sum(v[0] for (code, _), v in sums.items() if code == side_code)), "rate"
        per_shot = {"winners": winners, "forced_errors_drawn": forced, "unforced_errors": unforced, "points_won": won}
        return _share(per_shot[measure], shots), "rate"
    raise ValueError(f"unknown stat {stat!r}")


# A tournament's final (D-036): who won it and who lost it (by last name, as the answer would
# write them) and its score, winner's games first.
EVENT_STATS = ("final_winner", "final_runner_up", "final_score")


def event_value(conn: psycopg.Connection, stat: str, filters: Filters, event: str) -> tuple[str | None, str]:
    final = event_final(conn, filters.season, event)
    if final is None:
        return None, "name"
    if stat == "final_winner":
        return last_name(final["winner"]), "name"
    if stat == "final_runner_up":
        return last_name(final["runner_up"]), "name"
    if stat == "final_score":
        return final["score"], "score"
    raise ValueError(f"unknown stat {stat!r}")
