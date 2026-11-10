"""The player stats page: one read that composes the tested tools in api/stats.py.

Nothing is counted here. Which matches count and how each stat is defined stay in the tools
(D-014), so every block is exactly what that tool returns. No model is involved.
"""

from __future__ import annotations

from typing import Any

import psycopg

from api import stats

RECENT_MATCHES = 10


def _seasons(conn: psycopg.Connection, player_id: int, profile: dict[str, Any], surface: str | None) -> list[dict[str, Any]]:
    """Each season with a counted match on any surface, newest first. The record respects the
    surface filter, so a season with no match on that surface stays, with 0 matches."""
    if profile["last_match"] is None:
        return []
    first = int(profile["first_tourney_date"][:4])
    # One past the last tournament's year: a tournament that starts in December can belong to
    # the next season (D-010), and it may be the last one a player has.
    last = int(profile["last_match"]["tourney_date"][:4]) + 1

    def overall(filters: stats.Filters) -> dict[str, Any]:
        return stats.surface_splits(conn, player_id, filters)["overall"]

    seasons = []
    for season in range(last, first - 1, -1):
        record = overall(stats.Filters(surface=surface, season=season))
        if record["matches"] or (surface and overall(stats.Filters(season=season))["matches"]):
            seasons.append({"season": season, "overall": record})
    return seasons


def compose(
    conn: psycopg.Connection, player_id: Any, surface: Any = None, season: Any = None, opponent_id: Any = None
) -> dict[str, Any]:
    """Everything the page shows for one player. Raises ToolInputError or PlayerNotFound."""
    pid = stats.parse_player_id(player_id)
    filters = stats.Filters.parse({"surface": surface, "season": season})
    # One snapshot for the whole response, since it is cached: blocks read while a load commits
    # would otherwise mix old and new data.
    with conn.transaction():
        # First, so a bad opponent stops the request before the other queries run.
        h2h = None if opponent_id is None else stats.head_to_head(conn, pid, opponent_id, filters)
        profile = stats.player_profile(conn, pid)
        del profile["birth_date"]
        return {
            "profile": profile,
            "filters": {"surface": filters.surface, "season": filters.season},
            "data_window": stats.data_window(conn),
            "seasons": _seasons(conn, pid, profile, filters.surface),
            "by_surface": stats.surface_splits(conn, pid, stats.Filters(season=filters.season)),
            "record": stats.surface_splits(conn, pid, filters),
            "serve_return": stats.serve_return_stats(conn, pid, filters),
            "pressure": stats.pressure_stats(conn, pid, filters),
            "recent_form": stats.recent_form(conn, pid, RECENT_MATCHES, filters),
            "career": {"serve_return": stats.serve_return_stats(conn, pid), "pressure": stats.pressure_stats(conn, pid)},
            "head_to_head": h2h,
        }
