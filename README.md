# Tennis Scouting Analyst

Scouting reports on ATP players where every number comes from tested code, not from a language
model's memory. A coach picks a player, an opponent and a surface. An agent built on Claude looks
up what it needs through seven tested stats tools, then writes a report and a game plan. Every key
number is checked against the tool result it came from before the report is shown. Evals with
independent ground truth measure whether the answers are right.

It's a personal project, built for fun and to try out new tools: Claude's tool use and structured
outputs, evals with their own ground truth, Next.js 16, Vercel Services and Neon.

- **Live:** [tennis-scouting-analyst.vercel.app](https://tennis-scouting-analyst.vercel.app), in
  English, Spanish and French
- **Case study:** [docs/case-study.md](docs/case-study.md): the problem, the design, the eval
  results and what went wrong
- **Demo script:** [docs/demo.md](docs/demo.md), about three minutes
- **Every decision, with its reasons and checks:** [docs/decisions.md](docs/decisions.md)

## What's in the repository

| Folder | What it holds |
| --- | --- |
| `ingest/` | Download (hash-pinned), validation and loading into Postgres, plus the reviewed player ID files |
| `api/` | The stats tools, the agent loop, the grounding check and the FastAPI app, with tests |
| `evals/` | 43 questions, independent ground truth in SQL, the scorer, the runner and committed results |
| `web/` | The Next.js app: match setup, report, evidence, chat, Player stats |
| `infra/` | The production database role and its setup script |
| `docs/` | Decisions, case study, demo script, data audit, quality report, stat sources, deploy guide |

## Run it locally

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 if needed), Docker, and
Node.js 23.6 or newer (the web tests run TypeScript directly). An Anthropic API key is only needed
for reports and chat; everything else works without one.

```bash
git clone https://github.com/nestorolivaresh/tennis-scouting-analyst.git
cd tennis-scouting-analyst
cp .env.example .env    # works as is for local use; add ANTHROPIC_API_KEY for reports and chat
uv sync                 # Python dependencies
docker compose up -d    # Postgres 16 on 127.0.0.1:5433
```

**Get the data.** The raw files aren't in the repository (their licenses don't allow it), so the
download script fetches them and checks each one against `ingest/data.lock.json`:

```bash
uv run python -m ingest.download
```

Seasons 2015-2025 come from the final commit of Jeff Sackmann's repository and always match.
The 2026 files come from TennisMyLife, which updates them, so a download made after
7 November 2026 won't match the pinned snapshot and the script says so. Accept the newer
snapshot, then add any new players to the reviewed ID files:

```bash
uv run python -m ingest.download --relock    # pins today's TennisMyLife files instead
uv run python -m ingest.players              # appends new players; review them before loading
```

**Load and test.**

```bash
uv run --env-file .env python -m ingest.load   # a few seconds; also writes docs/quality-report.md
uv run --env-file .env pytest                  # unit tests, plus checks on the loaded data
```

These steps were followed from a fresh clone on 10 November 2026, with a newer 2026 snapshot:
298 tests passed and 5 failed. The five pin 2026 dates or counts from the original snapshot:
`test_health`, `test_data_window`, `test_surface_splits_2026_comes_from_tml`,
`test_report_verified` and `test_report_stream_shows_progress_then_the_checked_report`. Seasons
2015-2025 and the evals are unaffected. [D-002](docs/decisions.md) explains the trade-off.

**Run the app.** Start the API in one terminal and the web app in another:

```bash
uv run --env-file .env uvicorn api.app:app --port 8000
npm --prefix web install
npm --prefix web run dev      # then open http://localhost:3000
```

`.env.example` sets `ALLOW_NO_SPEND_CAP=1` so the API will call the model locally without a daily
spend cap. Never set it in a deployment: there, the API refuses model calls unless
`DAILY_SPEND_CAP_USD` is set ([D-025](docs/decisions.md)).

## How it works

### Stats tools

`api/stats.py` holds the seven tools the agent calls: `resolve_player`, `player_profile`,
`surface_splits`, `serve_return_stats`, `pressure_stats`, `head_to_head` and `recent_form`.
Each is a plain function over Postgres that returns JSON, with the sample it was computed from:
matches counted, matches with stats, what was excluded and why, and the dates covered. Their
results match Tennis Abstract and hand calculations from the raw CSV files
([docs/stat-checks.md](docs/stat-checks.md)). Each test was shown to fail when the rule it covers
was broken. `resolve_player` never guesses: it returns one player only when the name identifies
exactly one, and otherwise returns candidates for the agent to ask about.

```python
from api.db import connect
from api import stats

conn = connect()  # needs DATABASE_URL, e.g. uv run --env-file .env python
stats.serve_return_stats(conn, 206173, {"season": 2024, "surface": "Clay"})
```

### Agent and API

`api/agent.py` runs the tool-use loop by hand. The model asks for stats tools, the code runs them
and sends the results back, within 8 tool steps, 60 seconds and a token budget per request.
`POST /report` returns a structured report in which each key number names the tool call and field
it came from. `api/grounding.py` checks every one against that run's tool results, retries once
with the errors, and otherwise marks the report unverified. `POST /chat` streams follow-up answers
as server-sent events. Every request logs its tool calls, tokens and estimated cost as JSON lines
([D-017 to D-022](docs/decisions.md)).

```bash
curl -s 'localhost:8000/health'                          # app and database, no model call
curl -s 'localhost:8000/players/search?q=sinner'
curl -s 'localhost:8000/players/207989/stats?surface=Clay&season=2025'
curl -s localhost:8000/report -H 'content-type: application/json' \
  -d '{"player_id": 206173, "opponent_id": 207989, "surface": "Clay"}'
curl -sN localhost:8000/report/stream -H 'content-type: application/json' \
  -d '{"player_id": 206173, "opponent_id": 207989, "surface": "Clay", "language": "es"}'
curl -sN localhost:8000/chat -H 'content-type: application/json' \
  -d '{"messages": [{"role": "user", "content": "How has Alcaraz served on clay in 2025?"}]}'
```

A report costs about $0.07 and a chat answer a few cents.

### Evals

`evals/` asks the agent 43 questions: the spec's 40 in five categories, plus one for each bug
found by hand. Answers are scored against ground truth computed by separate SQL over the raw
source files, never by the stats layer. Scoring needs no model:
- each expected number must appear in the answer (counts exactly, rates within 0.5 percentage
  points);
- the right tool must be called with the question's filters;
- numbers, records ("11-8") and counts ("905 of 1,774") must match the run's tool results;
- head-to-head and comparison answers must not name the wrong leader.

The latest run passed 42 of 43 ([case study](docs/case-study.md#eval-results),
[D-023](docs/decisions.md)). Every answer is in `evals/results/`.

```bash
uv run --env-file .env python -m evals.run --dry-run                 # ground truth only, free
uv run --env-file .env python -m evals.run --label myrun             # all questions, about $0.80
uv run --env-file .env python -m evals.run --label myrun --only S01,H04
uv run --env-file .env python -m evals.run --rescore final-v2        # rescore saved answers, free
```

`--rescore` works only on the data snapshot the saved answers were run on, and refuses any other.

### Web app

`web/` is the coach's screen, built with Next.js and React. You pick your player, the opponent and
a surface, watch each lookup as the report is written, then read the report. Any key number opens
to show the tool call, filters and sample behind it, and a streaming chat takes follow-up
questions. A second page, Player stats, shows any player's record, serve, return and recent form,
with no model involved. Numbers on screen are drawn from the tool results, never from the model's
text. The app talks to the API through its own server, so the Anthropic key never reaches the
browser. It's in English, Spanish and French, chosen from the browser's language and switchable
in the nav ([D-024, D-026, D-027](docs/decisions.md)).

```bash
npm --prefix web test         # logic tests, no server needed
npm --prefix web run build
```

### How the data is loaded

1. `ingest/download.py` fetches the files and checks them against `ingest/data.lock.json`.
2. `ingest/load.py` refuses files that don't match, and refuses a special event missing from
   `ingest/special_events.csv`. It transforms every row (`ingest/transform.py`), maps player IDs
   with the reviewed files `ingest/player_merges.csv` and `ingest/player_crosswalk.csv`, and
   rebuilds all tables in one transaction.
3. The source files and the reviewed files are also stored unchanged in a `raw` schema, which
   the evals use for ground truth, independent of the transform.
4. Rows that can't be loaded, and stats that fail sanity checks, go to `data/rejects/rejects.csv`
   with a reason. [docs/quality-report.md](docs/quality-report.md) summarizes the load.

`uv run python -m ingest.audit` regenerates [docs/data-audit.md](docs/data-audit.md).

## Deploy your own

The live site runs on Vercel and Neon on their free plans. [docs/deploy.md](docs/deploy.md) has
the steps, the daily spend cap, the restricted database role and the go-live checks.

## Data and licenses

This is a non-commercial personal project: no ads, payments or paid features.

- **Seasons 2015-2025:** Jeff Sackmann / [Tennis Abstract](https://www.tennisabstract.com/),
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Sackmann's
  `tennis_atp` repository was removed from GitHub in 2026. This project uses his final commit
  (`712be0c`, 8 June 2026), fetched from forks and verified against that commit's file hashes.
- **Season 2026:** [TennisMyLife](https://stats.tennismylife.org/tennis-match-database), for
  personal, educational and non-commercial research use.

Raw data is never committed. Data derived from Sackmann's files is shared under CC BY-NC-SA 4.0,
and what comes from TennisMyLife stays under its own terms. Committed files contain no player
birth dates. [DATA_LICENSE.md](DATA_LICENSE.md) has the details, the changes made to the data,
and how to ask for a correction or removal. The code's license hasn't been chosen yet.
