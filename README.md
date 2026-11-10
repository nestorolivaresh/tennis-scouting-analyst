# Tennis Scouting Analyst

An AI scouting analyst over public ATP match data. A coach picks a player, an opponent and a
surface, and gets a scouting report where every number comes from tested code, not from the
model's memory. Evals with independent ground truth check that the answers are correct.

**Status:** Milestone 6 (deploy), set up but not yet deployed. Steps: [docs/deploy.md](docs/deploy.md). See [SPEC.md](SPEC.md) for the plan,
[docs/data-audit.md](docs/data-audit.md) for what the raw data contains,
[docs/quality-report.md](docs/quality-report.md) for what was loaded,
[docs/stat-checks.md](docs/stat-checks.md) for where every test number comes from, and
[docs/decisions.md](docs/decisions.md) for the choices made so far.

## Stats tools

`api/stats.py` holds the seven tools the agent calls: `resolve_player`, `player_profile`,
`surface_splits`, `serve_return_stats`, `pressure_stats`, `head_to_head` and `recent_form`.
Each is a plain function over Postgres that returns JSON, with the sample it was computed
from (matches counted, matches with stats, what was excluded and why, dates covered). Their
results match Tennis Abstract and independent hand calculations from the raw CSV files, and
each test was shown to fail when the rule it covers is broken. `resolve_player` never guesses:
it returns one player only when the name identifies exactly one, and otherwise candidates for
the agent to ask about.

```python
from api.db import connect
from api import stats

conn = connect()  # needs DATABASE_URL, e.g. uv run --env-file .env python
stats.serve_return_stats(conn, 206173, {"season": 2024, "surface": "Clay"})
```

## Agent and API

`api/agent.py` runs the tool-use loop by hand: the model asks for stats tools, the code runs
them and sends the results back, within 8 tool steps, 60 seconds and a token budget per
request. `POST /report` returns a structured report whose key stats each name the tool call
and field they came from; `api/grounding.py` checks every one against that run's tool
results, retries once with the errors, and otherwise marks the report unverified.
`POST /chat` streams follow-up answers as server-sent events. Every request logs its tool
calls, tokens and estimated cost as JSON lines. The design is in
[D-017 to D-022](docs/decisions.md).

```bash
ALLOW_NO_SPEND_CAP=1 uv run --env-file .env uvicorn api.app:app --port 8000   # needs ANTHROPIC_API_KEY in .env
curl -s 'localhost:8000/players/search?q=sinner'
curl -s localhost:8000/report -H 'content-type: application/json' \
  -d '{"player_id": 206173, "opponent_id": 207989, "surface": "Clay"}'
curl -sN localhost:8000/report/stream -H 'content-type: application/json' \
  -d '{"player_id": 206173, "opponent_id": 207989, "surface": "Clay"}'    # the same, with progress
curl -sN localhost:8000/chat -H 'content-type: application/json' \
  -d '{"messages": [{"role": "user", "content": "How has Alcaraz served on clay in 2025?"}]}'
```

`GET /health` checks the app and the database without calling the model.

## Evals

`evals/` asks the agent 43 questions (the spec's 40 in five categories, plus one for each bug
found by hand) and scores the answers against ground truth computed by separate SQL over the
raw source files, never by the stats layer. Scoring needs no model: each expected number must
appear in the answer (counts exactly, rates within 0.5 percentage points), the right tool
must be called with the question's filters, numbers, records ("11-8") and counts ("905 of
1,774") must match the run's tool results, and head-to-head and comparison answers must not
name the wrong leader. The checks read prose with regular expressions, so they catch the
errors seen so far but not every possible one; every answer is in `evals/results/` for
reading. The design, results and limits are in [D-023](docs/decisions.md).

```bash
uv run --env-file .env python -m evals.run --dry-run                 # ground truth only, free
uv run --env-file .env python -m evals.run --label myrun             # all questions, about $0.80
uv run --env-file .env python -m evals.run --label myrun --only S01,H04
uv run --env-file .env python -m evals.run --rescore baseline        # rescore old answers, free
```

## Web app

`web/` is the coach's screen (Next.js, TypeScript): pick your player, the opponent
and a surface, watch each lookup as the report is written, read the report, open any key number to see the tool call, filters and sample
behind it, and ask follow-up questions in a streaming chat. It talks to the API through its
own server, so the Anthropic key never reaches the browser. A second page, Player stats, shows any
player's record, serve, return and recent form, with no model involved. The app, its reports and
the chat are in English, Spanish and French, chosen from the browser's language and switchable in
the nav. Design and checks: [D-024, D-026 and D-027](docs/decisions.md).

```bash
ALLOW_NO_SPEND_CAP=1 uv run --env-file .env uvicorn api.app:app --port 8000   # the API, in one terminal
npm --prefix web install
npm --prefix web run dev                                  # then open http://localhost:3000
npm --prefix web test                                     # logic tests, no server needed
```

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/), Docker, and Python 3.12 (uv can install it).

```bash
cp .env.example .env                           # then set POSTGRES_PASSWORD (also in DATABASE_URL) and ANTHROPIC_API_KEY
uv sync                                        # install Python dependencies
docker compose up -d                           # local Postgres on 127.0.0.1:5433
uv run python -m ingest.download               # fetch the pinned data files and verify their hashes
uv run --env-file .env python -m ingest.load   # load Postgres, write docs/quality-report.md
uv run --env-file .env pytest                  # unit tests, plus invariant checks on the loaded data
```

Other commands:

- `uv run python -m ingest.audit` regenerates [docs/data-audit.md](docs/data-audit.md).
- `uv run python -m ingest.players` adds rows to the player ID files for new TML players and
  refreshes the review list. It never changes existing rows or decisions; review the new ones
  before loading.

Seasons 2015-2025 reproduce exactly. TML updates its files daily, so a later download of the
2026 file won't match the pinned hash; `uv run python -m ingest.download --relock` accepts a
new snapshot, which also changes any 2026 numbers ([D-002](docs/decisions.md)).

## How the data is loaded

1. `ingest/download.py` fetches the files and checks them against `ingest/data.lock.json`.
2. `ingest/load.py` refuses to run on files that don't match, or on a special event missing
   from `ingest/special_events.csv`. It then transforms every row (`ingest/transform.py`),
   maps player IDs with the reviewed files `ingest/player_merges.csv` and
   `ingest/player_crosswalk.csv`, and rebuilds all tables in one transaction.
3. The source files and the reviewed files are also stored unchanged in a `raw` schema, which
   the evals will use for ground truth, independent of the transform.
4. Rows that can't be loaded, and stats that fail sanity checks, are written to
   `data/rejects/rejects.csv` with a reason. `docs/quality-report.md` summarizes them.

## Data and licenses

This is a non-commercial learning and portfolio project: no ads, payments or paid features.

- **Seasons 2015-2025:** Jeff Sackmann / [Tennis Abstract](https://www.tennisabstract.com/),
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Sackmann's
  `tennis_atp` repository was removed from GitHub in 2026; this project uses his final commit
  (`712be0c`, 8 June 2026), fetched from forks and verified against that commit's file hashes.
- **Season 2026:** [TennisMyLife](https://stats.tennismylife.org/tennis-match-database), for
  personal, educational and non-commercial research use.

Raw data is never committed: `ingest/download.py` fetches it into `data/` and checks every file
against the hashes in `ingest/data.lock.json`. Data derived from the sources is shared under
CC BY-NC-SA 4.0, and committed files contain no player birth dates.
[DATA_LICENSE.md](DATA_LICENSE.md) has the details, the changes made to the data, and how to
ask for a correction or removal.
