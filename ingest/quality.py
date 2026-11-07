"""Milestone 1 quality report, computed from the loaded database.

Called by ingest/load.py after every load. Each check queries the tables that were just
written, so the report describes what the stats layer will actually read.
"""

from __future__ import annotations

import collections
import datetime as dt
from dataclasses import dataclass

import psycopg
from psycopg import sql

from ingest.audit import pct, table
from ingest.transform import games_in_score

LARGE_CHANGE = 0.25  # flag a season whose match count moves more than 25% from the previous one
FINGERPRINT_TABLES = [
    "raw.matches", "raw.sackmann_players", "raw.tml_players", "raw.player_merges",
    "raw.player_crosswalk", "raw.special_events", "players", "matches", "player_matches",
]  # fmt: skip
# Number of sets decided by a tiebreak, counted in SQL independently of transform.py.
TIEBREAKS_SQL = "(SELECT count(*) FROM regexp_matches(m.score, '(^| )(7-6|6-7)', 'g'))"

# Each check counts rows that break an invariant; every one should be 0.
INVARIANT_CHECKS = [
    (
        "Matches without exactly two player_matches rows",
        """SELECT count(*) FROM matches m
           LEFT JOIN (SELECT match_id, count(*) AS n FROM player_matches GROUP BY match_id) p USING (match_id)
           WHERE coalesce(p.n, 0) <> 2""",
    ),
    (
        "player_matches rows that don't mirror their match's winner and loser",
        """SELECT count(*) FROM player_matches pm JOIN matches m USING (match_id)
           WHERE NOT ((pm.won AND pm.player_id = m.winner_id AND pm.opponent_id = m.loser_id)
                   OR (NOT pm.won AND pm.player_id = m.loser_id AND pm.opponent_id = m.winner_id))""",
    ),
    (
        "player_matches stats that differ from the raw CSV row they came from",
        """SELECT count(*) FROM player_matches pm
           JOIN matches m USING (match_id)
           JOIN raw.matches r ON (r.source, r.season, r.row_num) = (m.source, m.season, m.source_row)
           WHERE m.has_stats AND (
             (pm.won AND ROW(pm.aces, pm.double_faults, pm.serve_points, pm.first_in, pm.first_won,
                             pm.second_won, pm.service_games, pm.bp_saved, pm.bp_faced)
               IS DISTINCT FROM ROW(r.w_ace::int, r.w_df::int, r.w_svpt::int, r."w_1stIn"::int, r."w_1stWon"::int,
                                    r."w_2ndWon"::int, r."w_SvGms"::int, r."w_bpSaved"::int, r."w_bpFaced"::int))
             OR (NOT pm.won AND ROW(pm.aces, pm.double_faults, pm.serve_points, pm.first_in, pm.first_won,
                                    pm.second_won, pm.service_games, pm.bp_saved, pm.bp_faced)
               IS DISTINCT FROM ROW(r.l_ace::int, r.l_df::int, r.l_svpt::int, r."l_1stIn"::int, r."l_1stWon"::int,
                                    r."l_2ndWon"::int, r."l_SvGms"::int, r."l_bpSaved"::int, r."l_bpFaced"::int)))""",
    ),
    (
        "player_matches rows whose stats disagree with matches.has_stats",
        """SELECT count(*) FROM player_matches pm JOIN matches m USING (match_id)
           WHERE m.has_stats <> (pm.serve_points IS NOT NULL)""",
    ),
    ("Duplicate match IDs", "SELECT count(*) - count(DISTINCT match_id) FROM matches"),
    (
        "Player IDs in matches that are missing from players",
        """SELECT count(*) FROM (SELECT winner_id AS id FROM matches UNION SELECT loser_id FROM matches) ids
           LEFT JOIN players p ON p.player_id = ids.id WHERE p.player_id IS NULL""",
    ),
    ("Stat rows with first_in > serve_points", "SELECT count(*) FROM player_matches WHERE first_in > serve_points"),
    ("Stat rows with bp_saved > bp_faced", "SELECT count(*) FROM player_matches WHERE bp_saved > bp_faced"),
    (
        "Stat rows with second_won + double_faults > second-serve points",
        "SELECT count(*) FROM player_matches WHERE second_won + double_faults > serve_points - first_in",
    ),
    (
        "Stat rows with no serve points in a match that wasn't cut short",
        """SELECT count(*) FROM player_matches pm JOIN matches m USING (match_id)
           WHERE m.has_stats AND m.result_type NOT IN ('retired', 'defaulted') AND pm.serve_points = 0""",
    ),
    (
        "Stat rows with serve points but no service games",
        "SELECT count(*) FROM player_matches WHERE serve_points > 0 AND service_games = 0",
    ),
    (
        "Stat rows with fewer serve points than their service games need",
        f"""SELECT count(*) FROM player_matches pm JOIN matches m USING (match_id)
            WHERE m.has_stats AND pm.serve_points < greatest(
              pm.service_games,
              4 * pm.service_games - 3 * {TIEBREAKS_SQL}
                - CASE WHEN m.result_type IN ('retired', 'defaulted') THEN 3 ELSE 0 END)""",
    ),
]

SEASONS_SQL = """
SELECT r.source, r.season, r.raw_rows, coalesce(m.loaded, 0), coalesce(m.with_stats, 0),
       coalesce(m.walkovers, 0), coalesce(m.retired, 0), coalesce(m.davis_cup, 0)
FROM (SELECT source, season, count(*) AS raw_rows FROM raw.matches GROUP BY 1, 2) r
LEFT JOIN (
  SELECT source, season, count(*) AS loaded,
         count(*) FILTER (WHERE has_stats) AS with_stats,
         count(*) FILTER (WHERE result_type = 'walkover') AS walkovers,
         count(*) FILTER (WHERE result_type IN ('retired', 'defaulted')) AS retired,
         count(*) FILTER (WHERE tourney_level = 'D') AS davis_cup
  FROM matches GROUP BY 1, 2
) m USING (source, season)
ORDER BY r.season
"""


@dataclass
class LoadSummary:
    rejects: list[dict]
    notes: collections.Counter
    merged_rows: int  # Sackmann rows whose player ID was replaced by a canonical ID
    crosswalk_methods: collections.Counter  # how 2026 TML players were mapped
    review_decisions: collections.Counter  # decisions in ingest/player_review.csv, 'pending' if none


def fetch(conn: psycopg.Connection, query: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall()


def ranked(counter: collections.Counter) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def build_report(conn: psycopg.Connection, load: LoadSummary, generated_on: dt.date) -> str:
    out: list[str] = []
    add = out.append
    add("# Data quality report (Milestone 1)")
    add("")
    add(
        f"Generated by `ingest/load.py` on {generated_on.isoformat()} from the loaded database. "
        "Do not edit by hand; rerun `uv run --env-file .env python -m ingest.load`."
    )

    # 1. Invariants
    add("\n## 1. Invariants (each should be 0)\n")
    rows = []
    for label, query in INVARIANT_CHECKS:
        (count,) = fetch(conn, query)[0]
        rows.append([label, f"{count:,}", "ok" if count == 0 else "**FAILED**"])
    add(table(["Check", "Rows", "Result"], rows))

    # 2. Seasons
    rejected_rows = collections.Counter(
        (r["source"], r["season"]) for r in load.rejects if r["action"] == "row_rejected"
    )
    add("\n## 2. Matches per season\n")
    rows, previous, unaccounted = [], None, 0
    for source, season, raw, loaded, with_stats, walkovers, retired, davis in fetch(conn, SEASONS_SQL):
        rejected = rejected_rows[(source, season)]
        unaccounted += raw - loaded - rejected
        change = (loaded - previous) / previous if previous else None
        flag = f"{change:+.0%}" + (" **large change**" if change is not None and abs(change) > LARGE_CHANGE else "") if change is not None else ""
        rows.append([season, source, f"{raw:,}", f"{loaded:,}", f"{rejected:,}", flag,
                     f"{with_stats:,} ({pct(with_stats, loaded)})", f"{walkovers:,}", f"{retired:,}", f"{davis:,}"])  # fmt: skip
        previous = loaded
    add(table(["Season", "Source", "Raw rows", "Loaded", "Rejected", "Change", "With stats", "Walkovers", "Retired or defaulted", "Davis Cup"], rows))
    add(f"\nRaw rows neither loaded nor rejected: {unaccounted} (should be 0).")
    add(
        "\nExpected large changes: 2020 was shortened by COVID-19, so 2020 drops and 2021 recovers. "
        "Season 2026 runs only to the TML snapshot date (see `ingest/data.lock.json`)."
    )

    # 3. Rejects and removed stats
    add("\n## 3. Rejected rows and removed stats\n")
    add("Every item is also in `data/rejects/rejects.csv` (gitignored) with the source row number and match details.\n")
    by_reason = collections.Counter((r["action"], r["reason"]) for r in load.rejects)
    add(table(["Action", "Reason", "Rows"], [[a, r, f"{n:,}"] for (a, r), n in ranked(by_reason)] or [["none", "", "0"]]))

    # Service games against the score: flagged for review only. The sources don't agree on
    # whether a tiebreak counts as a service game, so the expected total is a range.
    flagged = []
    for source, season, name, rnd, score, service_games in fetch(
        conn,
        """SELECT m.source, m.season, m.tourney_name, m.round, m.score, sum(pm.service_games)
           FROM matches m JOIN player_matches pm USING (match_id)
           WHERE m.has_stats AND m.result_type = 'completed' AND NOT m.is_exhibition
           GROUP BY m.match_id, 1, 2, 3, 4, 5 ORDER BY 2, 3, 4, 5""",
    ):
        games, tiebreaks = games_in_score(score)
        if not games - tiebreaks - 2 <= service_games <= games + 2:
            flagged.append(f"{season} {name} {rnd} `{score}`: {service_games} service games")
    add(
        f"\nCompleted matches whose total service games fall outside the range the score allows "
        f"(games minus tiebreaks, minus 2, to games plus 2), kept but flagged for review: {len(flagged)}"
        + (f". For example: {'; '.join(flagged[:5])}." if flagged else ".")
    )

    # 4. Result types
    add("\n## 4. Result types parsed from `score`\n")
    by_type = collections.defaultdict(dict)
    for source, result_type, count in fetch(conn, "SELECT source, result_type, count(*) FROM matches GROUP BY 1, 2"):
        by_type[result_type][source] = count
    types = ["completed", "retired", "defaulted", "walkover", "unknown"]
    add(table(["Result type", "Sackmann", "TML"], [[t, f"{by_type[t].get('sackmann', 0):,}", f"{by_type[t].get('tml', 0):,}"] for t in types]))
    unknown = fetch(
        conn,
        """SELECT coalesce(score, '(empty)'), tourney_level, count(*) FROM matches
           WHERE result_type = 'unknown' GROUP BY 1, 2 ORDER BY 3 DESC, 1""",
    )
    add("\nScores classified as `unknown`, with their level. They are loaded but left out of records and stats "
        "by default, because the score contradicts the listed winner or the match was abandoned: "
        + (", ".join(f"`{score}` ({level})" + (f" x{n}" if n > 1 else "") for score, level, n in unknown) or "none") + ".")  # fmt: skip
    best_of = [(k, v) for k, v in ranked(load.notes) if k.startswith("completed score")]
    if best_of:
        add("\nCompleted scores whose set count doesn't fit `best_of` (loaded as given, not corrected): "
            + "; ".join(f"{k.replace('completed score ', '')}: {v}" for k, v in best_of) + ".")  # fmt: skip

    # 5. Levels, exhibitions, surfaces
    add("\n## 5. Levels, exhibitions and surfaces\n")
    changed = fetch(
        conn,
        """SELECT tourney_name, source_level, tourney_level, count(*), min(season), max(season)
           FROM matches WHERE source_level <> tourney_level AND source_level NOT IN ('250', '500')
           GROUP BY 1, 2, 3 ORDER BY 1, 2""",
    )
    tml_split = fetch(conn, "SELECT count(*) FROM matches WHERE source_level IN ('250', '500')")[0][0]
    add(f"TML's `250` and `500` levels mapped to `A`: {tml_split:,} matches. Other level corrections:\n")
    add(table(["Event", "Level in file", "Loaded as", "Matches", "Seasons"],
              [[n, s, t, f"{c:,}", f"{a}-{b}" if a != b else a] for n, s, t, c, a, b in changed]))  # fmt: skip
    add("\nLoaded levels: " + ", ".join(f"`{level}` {n:,}" for level, n in fetch(conn, "SELECT tourney_level, count(*) FROM matches GROUP BY 1 ORDER BY 2 DESC")) + ".")
    exhibitions = fetch(conn, "SELECT tourney_name, count(*) FROM matches WHERE is_exhibition GROUP BY 1 ORDER BY 1")
    add("\nSpecial events take their level and exhibition flag from `ingest/special_events.csv`; "
        "the load stops if a special-looking event isn't listed there.")  # fmt: skip
    add("\nFlagged as exhibitions (excluded from records and stats by default): "
        + ", ".join(f"{name} {n:,}" for name, n in exhibitions) + ".")  # fmt: skip
    no_surface = fetch(conn, "SELECT tourney_level, count(*) FROM matches WHERE surface IS NULL GROUP BY 1 ORDER BY 2 DESC")
    add("\nMatches without a surface (left out of surface filters): "
        + (", ".join(f"level `{level}` {n:,}" for level, n in no_surface) or "none") + ".")  # fmt: skip

    # 6. Players
    add("\n## 6. Players\n")
    total, no_hand, no_birth, new = fetch(
        conn,
        """SELECT count(*), count(*) FILTER (WHERE hand IS NULL), count(*) FILTER (WHERE birth_date IS NULL),
                  count(*) FILTER (WHERE player_id >= 900001) FROM players""",
    )[0]
    add(f"- {total:,} players appear in loaded matches; {new:,} exist only in TML (IDs from 900001).")
    add(f"- Unknown hand: {no_hand:,} ({pct(no_hand, total)}). Their opponents' matches drop out of `opponent_hand` filters.")
    add(f"- Unknown birth date: {no_birth:,} ({pct(no_birth, total)}).")
    add(f"- Sackmann rows whose player ID was replaced through `ingest/player_merges.csv`: {load.merged_rows:,}.")
    add("- How the 2026 TML players were mapped (`ingest/player_crosswalk.csv`): "
        + ", ".join(f"`{m}` {n}" for m, n in ranked(load.crosswalk_methods)) + ".")  # fmt: skip
    add("- Possible duplicates in `ingest/player_review.csv`, by decision: "
        + ", ".join(f"{d} {n}" for d, n in ranked(load.review_decisions))
        + (". **Some are still pending review.**" if load.review_decisions.get("pending") else "."))  # fmt: skip
    same_name = fetch(conn, "SELECT full_name, array_agg(player_id ORDER BY player_id) FROM players GROUP BY 1 HAVING count(*) > 1 ORDER BY 1")
    add("- Different player IDs with the same full name, for review (may be different people): "
        + ("; ".join(f"{name} ({', '.join(map(str, ids))})" for name, ids in same_name) or "none") + ".")  # fmt: skip

    # 7. Fingerprints
    add("\n## 7. Table fingerprints\n")
    add("MD5 of each table's rows in sorted order. Two loads of the same files must give the same values.\n")
    rows = []
    for name in FINGERPRINT_TABLES:
        query = sql.SQL("SELECT count(*), md5(coalesce(string_agg(t::text, E'\\n' ORDER BY t::text), '')) FROM {} AS t").format(
            sql.Identifier(*name.split("."))
        )
        with conn.cursor() as cur:
            cur.execute(query)
            count, digest = cur.fetchone()
        rows.append([f"`{name}`", f"{count:,}", f"`{digest}`"])
    add(table(["Table", "Rows", "MD5"], rows))
    return "\n".join(out) + "\n"
