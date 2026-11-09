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
  SELECT r.season, r.row_num, trim(r.score) AS score, r.tourney_name,
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
SELECT t.season, t.row_num, t.tourney_name, t.tourney_date, t.surface, t.level, t.exhibition,
       t.result_type, t.score,
       coalesce(ms.any_value AND ms.sides_valid AND t.result_type <> 'walkover', false) AS has_stats,
       me.player, opp.player AS opponent, me.side = 'w' AS won,
       CASE WHEN p.hand IN ('R', 'L') THEN p.hand END AS opponent_hand,
       me.ace, me.svpt, me.first_in, me.first_won, me.second_won, me.bp_saved, me.bp_faced,
       opp.svpt AS opp_svpt, opp.first_won AS opp_first_won, opp.second_won AS opp_second_won,
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

    def params(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "date_from": dt.date.fromisoformat(self.date_from) if self.date_from else None,
            "date_to": dt.date.fromisoformat(self.date_to) if self.date_to else None,
            "surface": self.surface,
            "levels": list(self.levels) if self.levels else None,
            "opponent_hand": self.opponent_hand,
            "include_exhibitions": self.include_exhibitions,
        }


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
