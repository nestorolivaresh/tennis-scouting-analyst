"""The match prep page (D-033): both players side by side, composed from the tested tools in
api/stats.py, with the report's checks and window.

Nothing is counted here. Which matches count and how each stat is defined stay in the tools
(D-014), so every block is exactly what that tool returns. No model is involved.
"""

from __future__ import annotations

from typing import Any

import psycopg

from api import report, stats

# "surface": the chosen surface only. "all": every surface, for figures too thin on one.
SCOPES = ("surface", "all")


def parse_scope(value: Any) -> str:
    if value is None:
        return "surface"
    if isinstance(value, str) and value.strip().lower() in SCOPES:
        return value.strip().lower()
    raise stats.ToolInputError("scope must be 'surface' or 'all'")


def _side(conn: psycopg.Connection, player_id: int, filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "record": stats.surface_splits(conn, player_id, filters),
        "serve_return": stats.serve_return_stats(conn, player_id, filters),
        "pressure": stats.pressure_stats(conn, player_id, filters),
        "set_patterns": stats.set_patterns(conn, player_id, filters),
        "shots": stats.shot_patterns(conn, player_id, filters),
    }


def compose(conn: psycopg.Connection, player_id: Any, opponent_id: Any, surface: Any, scope: Any = None) -> dict[str, Any]:
    """Everything the page shows for one match-up. Raises ToolInputError or PlayerNotFound."""
    chosen = parse_scope(scope)  # first, so a bad scope stops the request before any query
    # One snapshot for the whole response, since it is cached: blocks read while a load commits
    # would otherwise mix old and new data.
    with conn.transaction():
        # The report's own checks and window, so the page and a report agree number for number.
        req = report.prepare_report(conn, player_id, opponent_id, surface)
        pid, oid = req.player["player"]["player_id"], req.opponent["player"]["player_id"]
        filters = {"surface": req.surface if chosen == "surface" else None, "date_from": req.date_from, "date_to": req.date_to}
        return {
            "player": req.player,
            "opponent": req.opponent,
            "surface": req.surface,
            "scope": chosen,
            "window": {"date_from": req.date_from, "date_to": req.date_to},
            "data_window": req.window,
            # Every meeting, on any date: two years would leave almost none.
            "head_to_head": stats.head_to_head(conn, pid, oid),
            "sides": {"player": _side(conn, pid, filters), "opponent": _side(conn, oid, filters)},
        }
