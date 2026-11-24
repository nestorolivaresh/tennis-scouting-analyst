"""Integration test: the loaded database must satisfy every invariant in the quality report.

It reads the database only. It's skipped when DATABASE_URL isn't set; run it with:
    uv run --env-file .env pytest
Work that depends on the data (the stats layer, the evals) should not start while it fails.
"""

import os

import pytest

from ingest.quality import INVARIANT_CHECKS

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set; run with uv run --env-file .env pytest")


@pytest.mark.parametrize(("label", "query"), INVARIANT_CHECKS, ids=[label for label, _ in INVARIANT_CHECKS])
def test_invariant_holds(label, query):
    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        (count,) = conn.execute(query).fetchone()
    assert count == 0, f"{label}: {count} rows"


def test_fingerprints_sort_in_byte_order_whatever_the_database_collation():
    """The same rows must give the same MD5 on the local Postgres (en_US.utf8) and on Neon (C).
    Under en_US.utf8, "a" sorts before "B" and "é" before "z"; in byte order, both the other way."""
    import hashlib

    import psycopg

    from ingest.quality import fingerprint

    values = ["a", "B", "é", "z"]
    in_byte_order = sorted(f"({v})" for v in values)  # Python compares code points, the same order as UTF-8 bytes
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute("CREATE TEMP TABLE fingerprint_rows (v TEXT) ON COMMIT DROP")
        conn.cursor().executemany("INSERT INTO fingerprint_rows VALUES (%s)", [(v,) for v in values])
        assert fingerprint(conn, "pg_temp.fingerprint_rows") == (4, hashlib.md5("\n".join(in_byte_order).encode()).hexdigest())
