-- One-time setup of the production database (docs/deploy.md, D-025). Run it in the Neon SQL
-- editor as the database owner, after loading the data and creating the role `tennis_app` in
-- Neon's console (Neon generates its password). Safe to run again.
--
-- The API connects as tennis_app, which can read the stats tables and record its own requests,
-- and nothing else: it can't change the data, and it can't read the raw source tables.

CREATE TABLE IF NOT EXISTS api_requests (
  request_id  TEXT PRIMARY KEY,
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  settled_at  TIMESTAMPTZ,
  endpoint    TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'started',
  cost_usd    NUMERIC(10, 6) NOT NULL,  -- the reserved estimate until the request settles
  settled     BOOLEAN NOT NULL DEFAULT false,
  model       TEXT,
  tokens      INTEGER,
  tool_calls  INTEGER,
  latency_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS api_requests_started_at ON api_requests (started_at);

GRANT USAGE ON SCHEMA public TO tennis_app;
GRANT SELECT ON players, matches, player_matches TO tennis_app;
GRANT SELECT, INSERT, UPDATE ON api_requests TO tennis_app;

-- A data load recreates the stats tables, which would lose the grant above. This applies it
-- to tables the owner creates from now on, so a reload needs no extra step.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO tennis_app;
