"""The Calendar page (D-036): every tournament of a season with its final, and one tournament's
history across seasons, from the tested tools in api/stats.py. No model is involved.

The data holds only tournaments already played; the page links to the ATP's own calendar for
upcoming ones.
"""

from __future__ import annotations

from typing import Any

import psycopg

from api import stats

NEWEST_SEASON_SQL = "SELECT max(season) AS season FROM matches WHERE event_code IS NOT NULL"


def compose(conn: psycopg.Connection, season: Any = None, event: Any = None) -> dict[str, Any]:
    """A season's tournaments (the newest season when none is given) and, when `event` names an
    ATP tournament code, that tournament's history. Raises ToolInputError or TournamentNotFound."""
    # One snapshot for the whole response, since it is cached (as in api/player_stats.py).
    with conn.transaction():
        chosen = season if season is not None else conn.execute(NEWEST_SEASON_SQL).fetchone()["season"]
        history = None if event is None else stats.tournament_history(conn, event)
        return {"calendar": stats.tournament_calendar(conn, chosen), "history": history}
