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
