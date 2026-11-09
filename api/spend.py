"""The daily spend cap and the request log (spec: a daily spend cap protects the API key; D-025).

Each model endpoint reserves its estimated cost before calling the model, and the row is
updated with the real cost when the request ends. Serverless copies of the app share no
memory, so the running total lives in the database (`api_requests`, infra/neon_setup.sql).

Why it can't be talked past:
- The check and the reservation happen in one transaction under an advisory lock, so requests
  arriving together can't all see room under the cap.
- A request that dies without settling keeps its estimate, so unknown spend counts.
- If the total can't be read, the model isn't called (fail closed).

A single request can still cost more than its estimate, so the cap can be passed by that
difference. The Anthropic Console's monthly limit is the hard stop behind this one.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import psycopg

from api.logs import log_event

# Above the most any request has cost so far (a report with a retry, $0.111; a chat answer,
# $0.017; D-022), so the reservation errs on the high side.
ESTIMATE_USD = {"/report": 0.15, "/report/stream": 0.15, "/chat": 0.05}

ADVISORY_LOCK = 725_001  # any fixed number; only this module takes it

SPENT_TODAY_SQL = """
SELECT coalesce(sum(cost_usd), 0)::float AS spent
FROM api_requests
WHERE started_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
"""

INSERT_SQL = """
INSERT INTO api_requests (request_id, endpoint, cost_usd) VALUES (%(request_id)s, %(endpoint)s, %(estimate)s)
"""

# A complete cost replaces the estimate. An incomplete or unknown one can only raise it.
SETTLE_SQL = """
UPDATE api_requests
SET status = %(status)s, settled = true, settled_at = now(), model = %(model)s, tokens = %(tokens)s,
    tool_calls = %(tool_calls)s, latency_ms = %(latency_ms)s,
    cost_usd = CASE WHEN %(complete)s AND %(cost)s::numeric IS NOT NULL THEN %(cost)s::numeric
                    ELSE greatest(cost_usd, coalesce(%(cost)s::numeric, 0)) END
WHERE request_id = %(request_id)s
"""


class DailyLimitReached(Exception):
    pass


class SpendTrackingUnavailable(Exception):
    pass


class SpendCapNotConfigured(Exception):
    pass


def reserve(connect: Callable[[], psycopg.Connection], request_id: str, endpoint: str, cap_usd: float) -> None:
    """Reserve this request's estimated cost, or refuse it. Raises DailyLimitReached when the
    estimate doesn't fit under the cap, and SpendTrackingUnavailable when the total can't be read."""
    estimate = ESTIMATE_USD[endpoint]
    try:
        conn = connect()
    except psycopg.Error as e:
        log_event("spend_tracking_unavailable", logging.ERROR, request_id=request_id, error_type=type(e).__name__)
        raise SpendTrackingUnavailable from e
    try:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADVISORY_LOCK,))
            spent = conn.execute(SPENT_TODAY_SQL).fetchone()["spent"]
            if spent + estimate > cap_usd:
                log_event("daily_limit_reached", logging.WARNING, request_id=request_id, spent_usd=spent, cap_usd=cap_usd)
                raise DailyLimitReached
            conn.execute(INSERT_SQL, {"request_id": request_id, "endpoint": endpoint, "estimate": estimate})
    except psycopg.Error as e:
        log_event("spend_tracking_unavailable", logging.ERROR, request_id=request_id, error_type=type(e).__name__)
        raise SpendTrackingUnavailable from e
    finally:
        conn.close()


def settle(connect: Callable[[], psycopg.Connection], request_id: str, status: str, summary: dict[str, Any]) -> None:
    """Record how a request ended. Never raises: the response is already on its way, and a
    failed update leaves the estimate in place, which errs on the safe side."""
    tokens = summary.get("tokens")
    params = {
        "request_id": request_id,
        "status": status,
        "model": summary.get("model"),
        "tokens": sum(tokens.values()) if isinstance(tokens, dict) else None,
        "tool_calls": summary.get("tool_calls"),
        "latency_ms": summary.get("latency_ms"),
        "cost": summary.get("cost_usd"),
        "complete": bool(summary.get("usage_complete")),
    }
    try:
        conn = connect()
        try:
            conn.execute(SETTLE_SQL, params)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001 - logged by type; the reservation stands
        log_event("spend_settle_failed", logging.ERROR, request_id=request_id, error_type=type(e).__name__)
