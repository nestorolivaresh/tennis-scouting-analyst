"""Create the API's database role on Neon and apply neon_setup.sql, all or nothing (D-025).
Nestor runs this through 1Password, after the data load (docs/deploy.md, step 3).

It's a script, not a page in Neon's console, for two reasons: Neon adds a role made in its
Console to neon_superuser, which can write to every table, and its SQL Editor keeps every
statement, password included, in the project's query history.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

SETUP_SQL = (Path(__file__).parent / "neon_setup.sql").read_text()


def apply(conn: psycopg.Connection, app_password: str) -> None:
    conn.execute(sql.SQL("CREATE ROLE tennis_app WITH LOGIN PASSWORD {}").format(sql.Literal(app_password)))
    conn.execute(SETUP_SQL)


def main() -> None:
    missing = [name for name in ("DATABASE_URL", "APP_PASSWORD") if not os.environ.get(name)]
    if missing:
        sys.exit(f"Not set: {', '.join(missing)}. See docs/deploy.md, step 3.")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:  # commits at the end; any error rolls it all back
        apply(conn, os.environ["APP_PASSWORD"])
    print("Done: tennis_app exists, with only the access in infra/neon_setup.sql.")


if __name__ == "__main__":
    main()
