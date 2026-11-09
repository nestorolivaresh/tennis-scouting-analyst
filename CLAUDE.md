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
  (D-017 to D-022). Tests use the scripted fake model in `api/tests/fake_model.py`; calls to
  the real model need `ANTHROPIC_API_KEY` in `.env`, which Nestor adds (D-020). Live calls
  cost money: run them only when a change needs one.
- Evals live in `evals/` (D-023). `evals/truth.py` must never import `api` or `ingest` and
  reads only `raw` tables; a test enforces both. Expected numbers are never typed into
  `evals/cases.py`; the truth SQL computes them. A full live run costs about $0.80: rerun only
  the failing questions with `--only`, and use `--rescore` (free) after changing the scorer.
- The frontend is `web/` (D-024): Next.js, React, Recharts and TypeScript only, pinned exactly;
  ask before adding any other package. Anything shown on screen must come from the run's
  evidence (`web/lib/evidence.ts`), never from the model's text, and a missing value is shown as
  missing, not 0. Check with `npm --prefix web test` and `npm --prefix web run build`.
- Deployment is Vercel plus Neon (D-025, `docs/deploy.md`). Never connect to the Neon database,
  run a deploy, or change Vercel settings without Nestor's explicit go-ahead for that action.
  With no `DAILY_SPEND_CAP_USD` the API refuses model calls; run it locally with
  `ALLOW_NO_SPEND_CAP=1`, and never set that in a deployment. Keep `.vercelignore` in step with
  what `api/` imports.
