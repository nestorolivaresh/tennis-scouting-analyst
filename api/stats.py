"""Stats tools: plain functions over Postgres that return JSON-ready dicts.

Each tool takes an open connection (api.db.connect) and validated arguments, and knows
nothing about the LLM. Every stats response carries its sample: the filters applied, how
many matches were counted and how many had stats, what was left out and why, and the dates
covered, so the agent can warn about small or missing samples.

Dates: `tourney_date` is a tournament's start date, in both sources. `match_date` is the day
a match was played; only TML (season 2026) has it, so it is None for 2015-2025 (D-014).

Which matches count is decided in one place, SCOPE_SQL below (docs/decisions.md D-014).
All SQL is fixed text with bound parameters; no value is ever pasted into a query.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re
from collections.abc import Mapping
from typing import Any

import psycopg

from ingest.players import name_tokens

SURFACES = ("Hard", "Clay", "Grass", "Carpet")
LEVELS = ("G", "M", "A", "F", "D", "O")
HANDS = ("R", "L")
MAX_RECENT_MATCHES = 50
MAX_NAME_LENGTH = 100  # longer names are refused before any query; trigram cost grows with length
MAX_CANDIDATES = 10
MAX_PLAYER_ID = 2_147_483_647  # Postgres INTEGER
SEASON_RANGE = (1900, 2100)  # a valid season outside the data gives an empty sample, not an error


class ToolInputError(ValueError):
    """The caller passed bad arguments. The message is safe to show to the caller."""


class PlayerNotFound(LookupError):
    """No player with that ID exists in the loaded data."""


def _whole_number(value: Any, low: int, high: int, message: str) -> int:
    """An int, or a string of ASCII digits, from low to high. Anything else raises ToolInputError."""
    text = "" if isinstance(value, bool) else str(value).strip()
    if not re.fullmatch(r"[0-9]{1,10}", text) or not low <= int(text) <= high:
        raise ToolInputError(message)
    return int(text)


def parse_player_id(value: Any, name: str = "player_id") -> int:
    return _whole_number(value, 1, MAX_PLAYER_ID, f"{name} must be a whole number; use resolve_player to find it")


# ---------- filters ----------


@dataclasses.dataclass(frozen=True)
class Filters:
    """The shared filters (spec, Tools), plus `season` (D-010) and `include_exhibitions` (D-006)."""

    surface: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    season: int | None = None
    tourney_level: tuple[str, ...] | None = None
    opponent_hand: str | None = None
    include_exhibitions: bool = False

    @classmethod
    def parse(cls, raw: Mapping[str, Any] | None) -> Filters:
        """Validate filters from an untrusted caller. Raises ToolInputError with a clear message."""
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ToolInputError("filters must be an object of filter names and values")
        unknown = sorted(str(key) for key in set(raw) - {field.name for field in dataclasses.fields(cls)})
        if unknown:
            raise ToolInputError(f"unknown filter(s): {', '.join(unknown)}")

        surface = raw.get("surface")
        if surface is not None:
            found = [s for s in SURFACES if s.lower() == str(surface).strip().lower()]
            if not found:
                raise ToolInputError(f"surface must be one of {', '.join(SURFACES)}")
            surface = found[0]

        date_from = _parse_date(raw.get("date_from"), "date_from")
        date_to = _parse_date(raw.get("date_to"), "date_to")
        if date_from and date_to and date_from > date_to:
            raise ToolInputError("date_from is after date_to")

        season = raw.get("season")
        if season is not None:
            season = _whole_number(season, *SEASON_RANGE, "season must be a year, such as 2024")

        levels = raw.get("tourney_level")
        if levels is not None:
            levels = [levels] if isinstance(levels, str) else levels
            if (
                not isinstance(levels, (list, tuple))
                or not levels
                or not all(isinstance(level, str) and level.strip().upper() in LEVELS for level in levels)
            ):
                raise ToolInputError(f"tourney_level must be one or more of {', '.join(LEVELS)}")
            levels = tuple(sorted({level.strip().upper() for level in levels}))

        hand = raw.get("opponent_hand")
        if hand is not None:
            hand = str(hand).strip().upper()
            if hand not in HANDS:
                raise ToolInputError("opponent_hand must be R or L")

        include_exhibitions = raw.get("include_exhibitions", False)
        if not isinstance(include_exhibitions, bool):
            raise ToolInputError("include_exhibitions must be true or false")

        return cls(surface, date_from, date_to, season, levels, hand, include_exhibitions)

    def params(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "season": self.season,
            "levels": list(self.tourney_level) if self.tourney_level else None,
            "opponent_hand": self.opponent_hand,
            "include_exhibitions": self.include_exhibitions,
        }

    def describe(self) -> dict[str, Any]:
        """The filters as applied, including defaults, for the response."""
        return {
            "surface": self.surface,
            "date_from": _iso(self.date_from),
            "date_to": _iso(self.date_to),
            "season": self.season,
            "tourney_level": list(self.tourney_level) if self.tourney_level else None,
            "opponent_hand": self.opponent_hand,
            "include_exhibitions": self.include_exhibitions,
        }


def _filters(filters: Filters | Mapping[str, Any] | None) -> Filters:
    return filters if isinstance(filters, Filters) else Filters.parse(filters)


def _parse_date(value: Any, name: str) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value).strip())
    except ValueError:
        raise ToolInputError(f"{name} must be a date like 2024-01-31") from None


def _iso(value: dt.date | None) -> str | None:
    return value.isoformat() if value else None


def rate(numerator: int | None, denominator: int | None, unit: str = "fraction") -> dict[str, Any]:
    """A value with the counts behind it. A zero denominator gives None, never zero (spec).

    unit "fraction": a share from 0 to 1 (0.616 means 61.6%).
    unit "per_match": an average count per match (aces per match).
    """
    numerator, denominator = int(numerator or 0), int(denominator or 0)
    return {
        "value": round(numerator / denominator, 4) if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
        "unit": unit,
    }


# ---------- SQL ----------

# One row per match of the player within the filters, with the opponent's serve stats for
# return numbers, and `excluded_as` naming why a match doesn't count (NULL = it counts):
# exhibitions unless asked for (D-006), walkovers (spec), unknown results (D-007), and, only
# when filtering by surface or opponent hand, matches where that value is unknown.
SCOPE_SQL = """
WITH scope AS (
  SELECT m.match_id, m.tourney_name, m.tourney_level, m.tourney_date, m.match_date, m.surface,
         m.round, m.round_order, m.match_num, m.score, m.result_type, m.has_stats, m.season,
         pm.won, pm.rank, pm.opponent_id, o.full_name AS opponent_name, opp.rank AS opponent_rank,
         pm.aces, pm.serve_points, pm.first_in, pm.first_won, pm.second_won, pm.bp_saved, pm.bp_faced,
         opp.serve_points AS opp_serve_points, opp.first_won AS opp_first_won,
         opp.second_won AS opp_second_won, opp.bp_saved AS opp_bp_saved, opp.bp_faced AS opp_bp_faced,
         CASE
           WHEN m.is_exhibition AND NOT %(include_exhibitions)s THEN 'exhibitions'
           WHEN m.result_type = 'walkover' THEN 'walkovers'
           WHEN m.result_type = 'unknown' THEN 'unknown_results'
           WHEN %(surface)s::text IS NOT NULL AND m.surface IS NULL THEN 'unknown_surface'
           WHEN %(opponent_hand)s::text IS NOT NULL AND o.hand IS NULL THEN 'unknown_opponent_hand'
         END AS excluded_as
  FROM player_matches pm
  JOIN matches m ON m.match_id = pm.match_id
  JOIN player_matches opp ON opp.match_id = pm.match_id AND opp.player_id = pm.opponent_id
  JOIN players o ON o.player_id = pm.opponent_id
  WHERE pm.player_id = %(player_id)s
    AND (%(opponent_id)s::int IS NULL OR pm.opponent_id = %(opponent_id)s)
    AND (%(surface)s::text IS NULL OR m.surface IS NULL OR m.surface = %(surface)s)
    AND (%(date_from)s::date IS NULL OR m.tourney_date >= %(date_from)s)
    AND (%(date_to)s::date IS NULL OR m.tourney_date <= %(date_to)s)
    AND (%(season)s::int IS NULL OR m.season = %(season)s)
    AND (%(levels)s::text[] IS NULL OR m.tourney_level = ANY(%(levels)s))
    AND (%(opponent_hand)s::text IS NULL OR o.hand IS NULL OR o.hand = %(opponent_hand)s)
)
"""

# In a retirement or default, the player who quit is always the loser.
SAMPLE_SQL = SCOPE_SQL + """
SELECT count(*) FILTER (WHERE excluded_as IS NULL) AS matches_counted,
       count(*) FILTER (WHERE excluded_as IS NULL AND has_stats) AS matches_with_stats,
       count(*) FILTER (WHERE excluded_as IS NULL AND won AND result_type IN ('retired', 'defaulted'))
         AS opponent_retired_or_defaulted,
       count(*) FILTER (WHERE excluded_as IS NULL AND NOT won AND result_type IN ('retired', 'defaulted'))
         AS player_retired_or_defaulted,
       min(tourney_date) FILTER (WHERE excluded_as IS NULL) AS first_tourney_date,
       max(tourney_date) FILTER (WHERE excluded_as IS NULL) AS last_tourney_date,
       count(*) FILTER (WHERE excluded_as = 'walkovers') AS walkovers,
       count(*) FILTER (WHERE excluded_as = 'exhibitions') AS exhibitions,
       count(*) FILTER (WHERE excluded_as = 'unknown_results') AS unknown_results,
       count(*) FILTER (WHERE excluded_as = 'unknown_surface') AS unknown_surface,
       count(*) FILTER (WHERE excluded_as = 'unknown_opponent_hand') AS unknown_opponent_hand,
       (SELECT min(tourney_date) FROM matches) AS data_first_tourney_date,
       (SELECT max(tourney_date) FROM matches) AS data_last_tourney_date,
       (SELECT max(match_date) FROM matches) AS data_last_match_date
FROM scope
"""

SERVE_RETURN_SQL = SCOPE_SQL + """
SELECT sum(aces) AS aces, sum(serve_points) AS serve_points, sum(first_in) AS first_in,
       sum(first_won) AS first_won, sum(second_won) AS second_won,
       sum(opp_serve_points) AS opp_serve_points,
       sum(opp_first_won + opp_second_won) AS opp_serve_points_won
FROM scope
WHERE excluded_as IS NULL AND has_stats
"""

PRESSURE_SQL = SCOPE_SQL + """
SELECT sum(bp_saved) AS bp_saved, sum(bp_faced) AS bp_faced,
       sum(opp_bp_faced - opp_bp_saved) AS bp_converted, sum(opp_bp_faced) AS bp_chances
FROM scope
WHERE excluded_as IS NULL AND has_stats
"""

SURFACE_SPLITS_SQL = SCOPE_SQL + """
SELECT coalesce(surface, 'Unknown') AS surface, count(*) AS matches,
       count(*) FILTER (WHERE won) AS wins, count(*) FILTER (WHERE NOT won) AS losses,
       count(*) FILTER (WHERE won AND result_type IN ('retired', 'defaulted')) AS opponent_retired_or_defaulted,
       count(*) FILTER (WHERE NOT won AND result_type IN ('retired', 'defaulted')) AS player_retired_or_defaulted
FROM scope
WHERE excluded_as IS NULL
GROUP BY 1
"""

# Newest first: tournament date, then match date where the source has it (TML, 2026), then
# round, then match number. Within a round robin or a Davis Cup tie, Sackmann's match
# numbers aren't guaranteed to follow match order (D-014).
NEWEST_FIRST = "tourney_date DESC, match_date DESC NULLS LAST, round_order DESC, match_num DESC"

MATCH_LIST_SQL = SCOPE_SQL + f"""
SELECT match_id, tourney_date, match_date, tourney_name, tourney_level, surface, round, score,
       result_type, won, rank, opponent_id, opponent_name, opponent_rank, has_stats
FROM scope
WHERE excluded_as IS NULL
ORDER BY {NEWEST_FIRST}
LIMIT %(limit)s
"""

PLAYER_SQL = """
SELECT p.player_id, p.full_name, p.hand, p.country, p.height_cm,
       count(pm.match_id) AS matches_loaded, min(m.tourney_date) AS first_tourney_date
FROM players p
LEFT JOIN player_matches pm ON pm.player_id = p.player_id
LEFT JOIN matches m ON m.match_id = pm.match_id
WHERE p.player_id = %(player_id)s
GROUP BY p.player_id
"""

# The newest match loaded for a player (any result type), and the newest one with a rank.
LAST_MATCH_SQL = f"""
SELECT m.tourney_name, m.round, m.tourney_date, m.match_date, m.result_type, pm.won
FROM player_matches pm JOIN matches m ON m.match_id = pm.match_id
WHERE pm.player_id = %(player_id)s
ORDER BY {NEWEST_FIRST}
LIMIT 1
"""

LATEST_RANK_SQL = f"""
SELECT pm.rank, m.tourney_name, m.tourney_date, m.match_date
FROM player_matches pm JOIN matches m ON m.match_id = pm.match_id
WHERE pm.player_id = %(player_id)s AND pm.rank IS NOT NULL
ORDER BY {NEWEST_FIRST}
LIMIT 1
"""

# Candidates for a name: the exact name, names where every typed word starts a word of the
# name ("zverev", "carlos alc"), or close spellings by trigram similarity ("alcarez").
RESOLVE_SQL = """
WITH candidates AS (
  SELECT p.player_id, p.full_name, p.country, p.hand,
         p.search_name = %(query)s AS exact,
         NOT EXISTS (
           SELECT 1 FROM unnest(%(words)s::text[]) AS typed(word)
           WHERE NOT EXISTS (
             SELECT 1 FROM unnest(string_to_array(p.search_name, ' ')) AS name(word)
             WHERE starts_with(name.word, typed.word))) AS word_match,
         word_similarity(%(query)s, p.search_name) AS similarity
  FROM players p
)
SELECT c.*, count(pm.match_id) AS matches_loaded, max(m.tourney_date) AS last_tourney_date
FROM candidates c
LEFT JOIN player_matches pm ON pm.player_id = c.player_id
LEFT JOIN matches m ON m.match_id = pm.match_id
WHERE c.exact OR c.word_match OR c.similarity >= %(min_similarity)s
GROUP BY c.player_id, c.full_name, c.country, c.hand, c.exact, c.word_match, c.similarity
ORDER BY c.exact DESC, c.word_match DESC, c.similarity DESC, matches_loaded DESC, c.player_id
LIMIT %(limit)s
"""

MIN_SIMILARITY = 0.45  # how close a spelling must be to be offered as a candidate

DATA_WINDOW_SQL = """
SELECT min(tourney_date) AS first_tourney_date, max(tourney_date) AS last_tourney_date,
       max(match_date) AS last_match_date
FROM matches
"""


# ---------- helpers ----------


def _player(conn: psycopg.Connection, player_id: int, name: str = "player_id") -> dict[str, Any]:
    row = conn.execute(PLAYER_SQL, {"player_id": player_id}).fetchone()
    if row is None:
        raise PlayerNotFound(f"no player with {name} {player_id}")
    return row


def _scope_params(player: dict, filters: Filters, opponent_id: int | None = None) -> dict[str, Any]:
    return {"player_id": player["player_id"], "opponent_id": opponent_id, **filters.params()}


def _retirements(won: int, lost: int) -> dict[str, int]:
    return {"opponent_retired_or_defaulted": won, "player_retired_or_defaulted": lost}


def _sample(conn: psycopg.Connection, params: dict[str, Any]) -> dict[str, Any]:
    row = conn.execute(SAMPLE_SQL, params).fetchone()
    return {
        "sample": {
            "matches_counted": row["matches_counted"],
            "matches_with_stats": row["matches_with_stats"],
            **_retirements(row["opponent_retired_or_defaulted"], row["player_retired_or_defaulted"]),
            "first_tourney_date": _iso(row["first_tourney_date"]),
            "last_tourney_date": _iso(row["last_tourney_date"]),
        },
        "excluded": {
            "walkovers": row["walkovers"],
            "exhibitions": row["exhibitions"],
            "unknown_results": row["unknown_results"],
            "unknown_surface": row["unknown_surface"],
            "unknown_opponent_hand": row["unknown_opponent_hand"],
        },
        "data_window": {
            "first_tourney_date": _iso(row["data_first_tourney_date"]),
            "last_tourney_date": _iso(row["data_last_tourney_date"]),
            "last_match_date": _iso(row["data_last_match_date"]),
        },
    }


def _envelope(tool: str, player: dict, filters: Filters, sample: dict, **payload: Any) -> dict[str, Any]:
    return {
        "tool": tool,
        "player": {"player_id": player["player_id"], "name": player["full_name"]},
        **payload.pop("before", {}),
        "filters": filters.describe(),
        **sample,
        **payload,
    }


def _match_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "tourney_date": _iso(row["tourney_date"]),
        "match_date": _iso(row["match_date"]),
        "tournament": row["tourney_name"],
        "level": row["tourney_level"],
        "surface": row["surface"],
        "round": row["round"],
        "result": "W" if row["won"] else "L",
        "score": row["score"],
        "result_type": row["result_type"],
        "rank": row["rank"],
        "opponent": {"player_id": row["opponent_id"], "name": row["opponent_name"], "rank": row["opponent_rank"]},
        "has_stats": row["has_stats"],
    }


def _record(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for row in rows if row["won"])
    return {"matches": len(rows), "wins": wins, "losses": len(rows) - wins, "win_rate": rate(wins, len(rows))}


# ---------- tools ----------


def _name_candidates(conn: psycopg.Connection, name: Any) -> list[dict[str, Any]]:
    """Candidate rows for a typed name, best first, at most MAX_CANDIDATES + 1."""
    if not isinstance(name, str):
        raise ToolInputError("name must be text")
    if len(name) > MAX_NAME_LENGTH:
        raise ToolInputError(f"name must be at most {MAX_NAME_LENGTH} characters")
    words = name_tokens(name)
    if not words:
        raise ToolInputError("name must contain letters")
    with conn.transaction():
        return conn.execute(
            RESOLVE_SQL,
            {"query": " ".join(words), "words": words, "min_similarity": MIN_SIMILARITY, "limit": MAX_CANDIDATES + 1},
        ).fetchall()


def _describe_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_id": row["player_id"],
        "name": row["full_name"],
        "country": row["country"],
        "hand": row["hand"],
        "matches_loaded": row["matches_loaded"],
        "last_tourney_date": _iso(row["last_tourney_date"]),
    }


def data_window(conn: psycopg.Connection) -> dict[str, Any]:
    """The dates the loaded data covers (the same fields as `data_window` in stats responses)."""
    with conn.transaction():
        row = conn.execute(DATA_WINDOW_SQL).fetchone()
    return {key: _iso(value) for key, value in row.items()}


def search_players(conn: psycopg.Connection, query: Any) -> dict[str, Any]:
    """Autocomplete: every candidate for what was typed, best first. Unlike resolve_player,
    this never picks one; the person typing does."""
    rows = _name_candidates(conn, query)
    return {
        "query": query,
        "candidates": [_describe_candidate(row) for row in rows[:MAX_CANDIDATES]],
        "more_candidates": len(rows) > MAX_CANDIDATES,
    }


def resolve_player(conn: psycopg.Connection, name: str) -> dict[str, Any]:
    """Find a player by name. Never guesses (spec: "ask instead of guessing").

    status "resolved": the typed name identifies exactly one player, either by the exact name
      or as the only name containing every typed word (as the start of a word).
    status "ambiguous": several names match; the agent should ask which one is meant.
    status "close_spellings": no name matches, but some are spelled similarly ("alcarez",
      "Sascha Zverev"); the agent should ask whether one of them is meant.
    status "not_found": nothing matches.
    """
    rows = _name_candidates(conn, name)
    describe = _describe_candidate

    def answer(status, message=None, group=()):
        result = {"tool": "resolve_player", "query": name, "status": status}
        if message:
            result["message"] = message
        result["candidates"] = [describe(row) for row in group[:MAX_CANDIDATES]]
        result["more_candidates"] = len(group) > MAX_CANDIDATES
        return result

    for kind, how in (("exact", "exact name"), ("word_match", "name words")):
        group = [row for row in rows if row[kind]]
        if len(group) == 1:
            return {"tool": "resolve_player", "query": name, "status": "resolved", "match": how, "player": describe(group[0])}
        if len(group) > 1:
            return answer("ambiguous", "Several players match this name; ask which one is meant.", group)
    if rows:  # every remaining row is a close spelling
        message = "No player has this name. These players have similar names; ask whether one of them is meant."
        return answer("close_spellings", message, rows)
    return answer("not_found", "No player in the data matches this name.")


def player_profile(conn: psycopg.Connection, player_id: Any) -> dict[str, Any]:
    """Bio, the newest match loaded, and the latest ranking found in the match data."""
    pid = parse_player_id(player_id)
    with conn.transaction():
        player = _player(conn, pid)
        last = conn.execute(LAST_MATCH_SQL, {"player_id": pid}).fetchone()
        latest = conn.execute(LATEST_RANK_SQL, {"player_id": pid}).fetchone()
    return {
        "tool": "player_profile",
        "player": {"player_id": player["player_id"], "name": player["full_name"]},
        "hand": player["hand"],
        "country": player["country"],
        "height_cm": player["height_cm"],
        "matches_loaded": player["matches_loaded"],
        "first_tourney_date": _iso(player["first_tourney_date"]),
        "last_match": (
            {
                "tournament": last["tourney_name"],
                "round": last["round"],
                "result": "W" if last["won"] else "L",
                "result_type": last["result_type"],
                "tourney_date": _iso(last["tourney_date"]),
                "match_date": _iso(last["match_date"]),
            }
            if last
            else None
        ),
        "latest_rank": (
            {
                "rank": latest["rank"],
                "tournament": latest["tourney_name"],
                "tourney_date": _iso(latest["tourney_date"]),
                "match_date": _iso(latest["match_date"]),
            }
            if latest
            else None
        ),
    }


def surface_splits(conn: psycopg.Connection, player_id: Any, filters: Filters | Mapping | None = None) -> dict[str, Any]:
    """Win-loss by surface."""
    pid, parsed = parse_player_id(player_id), _filters(filters)
    with conn.transaction():
        player = _player(conn, pid)
        params = _scope_params(player, parsed)
        sample = _sample(conn, params)
        rows = {row["surface"]: row for row in conn.execute(SURFACE_SPLITS_SQL, params).fetchall()}
    splits = [
        {
            "surface": surface,
            "matches": row["matches"],
            "wins": row["wins"],
            "losses": row["losses"],
            "win_rate": rate(row["wins"], row["matches"]),
            **_retirements(row["opponent_retired_or_defaulted"], row["player_retired_or_defaulted"]),
        }
        for surface in (*SURFACES, "Unknown")
        if (row := rows.get(surface))
    ]
    wins, matches = sum(s["wins"] for s in splits), sum(s["matches"] for s in splits)
    overall = {"matches": matches, "wins": wins, "losses": matches - wins, "win_rate": rate(wins, matches)}
    return _envelope("surface_splits", player, parsed, sample, overall=overall, surfaces=splits)


def serve_return_stats(
    conn: psycopg.Connection, player_id: Any, filters: Filters | Mapping | None = None
) -> dict[str, Any]:
    """Serve and return point stats, summed over matches with stats (never averaged)."""
    pid, parsed = parse_player_id(player_id), _filters(filters)
    with conn.transaction():
        player = _player(conn, pid)
        params = _scope_params(player, parsed)
        sample = _sample(conn, params)
        s = conn.execute(SERVE_RETURN_SQL, params).fetchone()
    serve_points, first_in = int(s["serve_points"] or 0), int(s["first_in"] or 0)
    opp_points = int(s["opp_serve_points"] or 0)
    stats = {
        "first_serve_in": rate(first_in, serve_points),
        "first_serve_points_won": rate(s["first_won"], first_in),
        "second_serve_points_won": rate(s["second_won"], serve_points - first_in),
        "service_points_won": rate(int(s["first_won"] or 0) + int(s["second_won"] or 0), serve_points),
        "return_points_won": rate(opp_points - int(s["opp_serve_points_won"] or 0), opp_points),
        "aces_per_match": rate(s["aces"], sample["sample"]["matches_with_stats"], unit="per_match"),
    }
    return _envelope("serve_return_stats", player, parsed, sample, stats=stats)


def pressure_stats(conn: psycopg.Connection, player_id: Any, filters: Filters | Mapping | None = None) -> dict[str, Any]:
    """Break points saved (on serve) and converted (on return)."""
    pid, parsed = parse_player_id(player_id), _filters(filters)
    with conn.transaction():
        player = _player(conn, pid)
        params = _scope_params(player, parsed)
        sample = _sample(conn, params)
        s = conn.execute(PRESSURE_SQL, params).fetchone()
    stats = {
        "break_points_saved": rate(s["bp_saved"], s["bp_faced"]),
        "break_points_converted": rate(s["bp_converted"], s["bp_chances"]),
    }
    return _envelope("pressure_stats", player, parsed, sample, stats=stats)


def head_to_head(
    conn: psycopg.Connection, player_id: Any, opponent_id: Any, filters: Filters | Mapping | None = None
) -> dict[str, Any]:
    """Record between two players, by surface, and each match (newest first)."""
    pid, oid, parsed = parse_player_id(player_id), parse_player_id(opponent_id, "opponent_id"), _filters(filters)
    if pid == oid:
        raise ToolInputError("player_id and opponent_id must be different players")
    with conn.transaction():
        player = _player(conn, pid)
        opponent = _player(conn, oid, "opponent_id")
        params = _scope_params(player, parsed, opponent_id=oid)
        sample = _sample(conn, params)
        rows = conn.execute(MATCH_LIST_SQL, {**params, "limit": None}).fetchall()
    by_surface = [
        {"surface": surface, **_record([r for r in rows if (r["surface"] or "Unknown") == surface])}
        for surface in (*SURFACES, "Unknown")
        if any((r["surface"] or "Unknown") == surface for r in rows)
    ]
    return _envelope(
        "head_to_head",
        player,
        parsed,
        sample,
        before={"opponent": {"player_id": opponent["player_id"], "name": opponent["full_name"]}},
        record=_record(rows),
        by_surface=by_surface,
        matches=[_match_entry(row) for row in rows],
    )


def recent_form(
    conn: psycopg.Connection, player_id: Any, n: Any = 10, filters: Filters | Mapping | None = None
) -> dict[str, Any]:
    """The last n counted matches, newest first, with the record over them.

    The sample describes the returned matches; the excluded counts cover the dates they span.
    """
    n = _whole_number(n, 1, MAX_RECENT_MATCHES, f"n must be a whole number from 1 to {MAX_RECENT_MATCHES}")
    pid, parsed = parse_player_id(player_id), _filters(filters)
    with conn.transaction():
        player = _player(conn, pid)
        params = _scope_params(player, parsed)
        rows = conn.execute(MATCH_LIST_SQL, {**params, "limit": n}).fetchall()
        window = dict(params)
        if rows:  # narrow the sample to the dates the returned matches span
            window["date_from"], window["date_to"] = rows[-1]["tourney_date"], rows[0]["tourney_date"]
        sample = _sample(conn, window)
    ended_early = [r for r in rows if r["result_type"] in ("retired", "defaulted")]
    sample["sample"] = {
        "matches_counted": len(rows),
        "matches_with_stats": sum(1 for r in rows if r["has_stats"]),
        **_retirements(sum(1 for r in ended_early if r["won"]), sum(1 for r in ended_early if not r["won"])),
        "first_tourney_date": _iso(rows[-1]["tourney_date"]) if rows else None,
        "last_tourney_date": _iso(rows[0]["tourney_date"]) if rows else None,
    }
    return _envelope(
        "recent_form", player, parsed, sample, n=n, record=_record(rows), matches=[_match_entry(r) for r in rows]
    )
