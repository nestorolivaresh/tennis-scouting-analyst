# Project instructions

- `SPEC.md` is the source of truth. `docs/decisions.md` records approved changes to it; read
  both before starting a milestone.
- Exception to Nestor's global credential rules, approved by Nestor on 2026-11-07: this repo
  may use a gitignored `.env` file and a committed `.env.example`. Never print, log or commit
  values from `.env`.
- Raw data lives in `data/` (gitignored) and is fetched only with
  `uv run python -m ingest.download`, which verifies the hashes in `ingest/data.lock.json`.
  Never commit raw data. Re-locking TML data changes eval ground truth; do it only when asked.
- Seasons 2015-2025 come from Sackmann's final commit and 2026 from TennisMyLife. Never mix
  sources within a season (D-001).
- `ingest/player_merges.csv`, `ingest/player_crosswalk.csv`, `ingest/player_review.csv` and
  `ingest/special_events.csv` are reviewed files with manual rows and decisions. Never delete
  and regenerate them; `ingest.players` only appends (D-009, D-010).
- Load with `uv run --env-file .env python -m ingest.load`, then run
  `uv run --env-file .env pytest`. Every invariant must pass before work that depends on the
  data. Anything built on the core tables (views, indexes) belongs in `ingest/schema.sql`;
  the load refuses to drop objects it doesn't know about (D-011).
- Questions that name a year use the `season` filter, not dates (D-010).
- Which matches count is defined once, in `SCOPE_SQL` in `api/stats.py` (D-014). Change it
  there, never per tool. Test values need a named source: Tennis Abstract or
  `api/tests/hand_checks.sh`, recorded in `docs/stat-checks.md` (D-015). A new rule's test
  must be shown to fail when the rule is broken, on a sample that exercises it.
- The agent and API are in `api/agent.py`, `api/report.py`, `api/chat.py` and `api/app.py`
  (D-017 to D-021). Tests use the scripted fake model in `api/tests/fake_model.py`; calls to
  the real model need `ANTHROPIC_API_KEY` in `.env`, which Nestor adds (D-020). Live calls
  cost money: run them only when a change needs one.
