"""Database connections for the stats layer and the API."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

STATEMENT_TIMEOUT_MS = 5000  # tool queries take about 10 ms (D-016); anything near this is a bug


def connect() -> psycopg.Connection:
    """Open a read-only connection that returns rows as dicts.

    Read-only applies to the whole session (default_transaction_read_only), not only inside
    the tools' transactions, and statements running longer than STATEMENT_TIMEOUT_MS are
    cancelled. This guards against mistakes, not attacks: the role can still change these
    settings, so Milestone 3 adds a SELECT-only role for the API (docs/decisions.md D-014).

    Autocommit is on, so nothing holds a transaction open between calls (an open transaction
    would block the next data load). Each stats tool wraps its queries in conn.transaction(),
    and REPEATABLE READ gives those queries one consistent snapshot.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; run with: uv run --env-file .env ...")
    options = f"-c default_transaction_read_only=on -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    conn = psycopg.connect(url, row_factory=dict_row, autocommit=True, options=options)
    conn.read_only = True
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    return conn
