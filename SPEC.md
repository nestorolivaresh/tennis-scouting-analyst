# Tennis Scouting Analyst: Claude Code Spec

Nov 6, 2026 · @Nestor Olivares

Build an AI scouting analyst over public ATP match data, where every statistic comes from tested code and evals prove the answers are correct.

## How to use this spec

Export this doc as Markdown, save it as `SPEC.md` in an empty repo, and paste this prompt into Claude Code.

```text
Read SPEC.md fully. Treat it as the source of truth for this project.

First, run the Milestone 0 data check and report what you find. Then give me a short plan for Milestones 1 and 2, and flag anything in the spec that is wrong or ambiguous.

Build Milestones 0, 1 and 2 only, then stop so I can review them. After each milestone, run its acceptance checks, show me the real output, and add any decisions to docs/decisions.md.

Ask me before changing the scope, adding a dependency that the spec doesn't list, or spending money on a cloud service. Never state that a check passed unless you ran it.
```

The build stops after Milestone 2 so you can check the data foundation yourself. Later milestones use the same prompt with new numbers.

## Goal and scope

A coach picks a player, an opponent and a surface, then gets a scouting report and can ask follow-up questions. This is a portfolio project, so correctness, evals and clear trade-offs matter more than feature count.

**User:** a coach preparing a player for an ATP match. Example questions:

- How does this opponent serve under pressure on clay?
- What is the head-to-head, and has it changed recently?
- How has this player performed over the last 10 matches?

| In the MVP | Not in the MVP |
| --- | --- |
| ATP tour-level singles, 2015 onward, as far as the data goes | WTA, Challengers, doubles, pre-2015 data |
| Match-level serve and return stats | Point-by-point data, live scores, predictions |
| Six stats tools plus player lookup | Free-form text-to-SQL |
| Structured report and streaming chat | Accounts, saved reports, RAG |
| 40 evals with independent ground truth | CI on every commit, 100+ evals |
| Public deploy with basic tracing | Multi-tenancy, roles |

**Core rule:** the model never produces a statistic from memory. Every number shown to the user must come from a tool result in that run.

## Architecture and stack

Python owns the data and agent, TypeScript owns the UI, and the eval runner checks answers using its own SQL.

&#91;embedded content: architecture · data, agent, web app and evals\]

The stats layer is the only route from the agent to the data, which is what makes each number traceable.

| Layer | Choice | Why |
| --- | --- | --- |
| Database | Postgres 16 in Docker, then a managed host | Common at customer sites |
| Ingestion | Python 3.12, `uv`, pandas, psycopg | Standard data tools |
| Agent API | FastAPI, Anthropic SDK | Simple, and keeps the tool loop visible |
| Tests and evals | pytest, plus a small runner with CSV results | Reproducible, with no eval platform needed |
| Frontend | Next.js, TypeScript, Recharts | Widely used and typed |
| Deploy | Docker, AWS App Runner, Secrets Manager, Vercel | Managed hosting and secret storage |

The earlier build plan listed DuckDB as a dependency too. This spec uses Postgres only.

## Data and stats layer

The source is [Jeff Sackmann's tennis\_atp repo](https://github.com/JeffSackmann/tennis_atp), licensed CC BY-NC-SA 4.0. Credit it in the README and app footer, keep the project non-commercial, and keep the raw data out of git.

The latest available season and the CSV headers are still unconfirmed, and this schema was written without inspecting the files. Milestone 0 checks it against `matches_data_dictionary.txt` and that file wins.

### Source facts to design around

The first three come from the repo's README; the last two come from how the files are structured.

- Stats are integer totals, so percentages must be calculated.
- Some matches have no stats, because they were unpublished or removed after failing sanity checks.
- Davis Cup matches appear in tour-level files, mostly without stats until recent seasons.
- `tourney_date` is the tournament's date, not the match date. Order matches within a tournament by round.
- Each row has winner and loser columns, so it must be reshaped into one row per player.

### Schema

```sql
CREATE TABLE players (
  player_id   INTEGER PRIMARY KEY,
  full_name   TEXT NOT NULL,
  hand        TEXT,
  birth_date  DATE,
  country     TEXT,
  height_cm   INTEGER
);

CREATE TABLE matches (
  match_id        TEXT PRIMARY KEY, -- tourney_id + '-' + match_num
  tourney_name    TEXT NOT NULL,
  tourney_level   TEXT NOT NULL,
  tourney_date    DATE NOT NULL,
  surface         TEXT,
  round           TEXT NOT NULL,
  round_order     INTEGER NOT NULL,
  best_of         INTEGER NOT NULL,
  score           TEXT,
  minutes         INTEGER,
  winner_id       INTEGER NOT NULL REFERENCES players(player_id),
  loser_id        INTEGER NOT NULL REFERENCES players(player_id),
  result_type     TEXT NOT NULL CHECK (result_type IN ('completed', 'retired', 'walkover', 'defaulted', 'unknown')),
  has_stats       BOOLEAN NOT NULL
);

CREATE TABLE player_matches (
  match_id     TEXT NOT NULL REFERENCES matches(match_id),
  player_id    INTEGER NOT NULL REFERENCES players(player_id),
  opponent_id  INTEGER NOT NULL REFERENCES players(player_id),
  won          BOOLEAN NOT NULL,
  rank         INTEGER,
  aces         INTEGER,
  double_faults INTEGER,
  serve_points INTEGER,
  first_in     INTEGER,
  first_won    INTEGER,
  second_won   INTEGER,
  service_games INTEGER,
  bp_saved     INTEGER,
  bp_faced     INTEGER,
  PRIMARY KEY (match_id, player_id)
);

CREATE INDEX idx_pm_player_opponent ON player_matches (player_id, opponent_id);
CREATE INDEX idx_matches_date ON matches (tourney_date);
```

The primary key already serves lookups by match. `player_matches` also needs a way to filter one player's matches by date and surface, so check `EXPLAIN ANALYZE` on the real tool queries in Milestone 2 and add only the indexes that help.

### Stat definitions

These are the single source of truth for tools and evals. When combining matches, **sum numerators and denominators, and never average per-match percentages**.

| Stat | Formula |
| --- | --- |
| First serve in % | first\_in / serve\_points |
| First serve points won % | first\_won / first\_in |
| Second serve points won % | second\_won / (serve\_points - first\_in) |
| Service points won % | (first\_won + second\_won) / serve\_points |
| Break points saved % | bp\_saved / bp\_faced |
| Return points won % | 1 - (opp first\_won + opp second\_won) / opp serve\_points |
| Break points converted % | (opp bp\_faced - opp bp\_saved) / opp bp\_faced |
| Aces per match | aces / matches with stats |

**Handling edge cases:**

- **Walkovers:** exclude them from win-loss records and stats by default, and report how many were excluded.
- **Retirements:** count them in records, flag them in the output, and keep their partial stats.
- **Zero denominators:** return null, never zero.
- **Missing stats:** include the match in records, but leave it out of stat calculations.

### Tools

Each is a plain, tested Python function that returns JSON, and has no knowledge of the LLM.

| Function | Returns |
| --- | --- |
| `resolve_player(name)` | Best match with player ID, or a list of candidates when ambiguous |
| `player_profile(player_id)` | Bio, plus latest ranking found in the match data |
| `surface_splits(player_id, filters)` | Win-loss by surface |
| `serve_return_stats(player_id, filters)` | The serve and return stats above |
| `pressure_stats(player_id, filters)` | Break points saved and converted |
| `head_to_head(player_id, opponent_id, filters)` | Record, by surface, and each match |
| `recent_form(player_id, n, filters)` | Last n matches, ordered by date and then round |

**Shared filters:** surface, date\_from, date\_to, tourney\_level, opponent\_hand.

**Every stats response includes:** the filters applied, matches counted, matches with stats, walkovers excluded, and the date range actually covered. That lets the agent warn about a small sample or missing data.

## Agent, API and frontend

### Agent

- **Model:** set through `ANTHROPIC_MODEL`, never hardcoded. Check the current Anthropic docs for model names and SDK usage.
- **Loop:** run the tool-use loop directly with the Anthropic SDK, without an agent framework, so the mechanics stay easy to explain.
- **Limits:** a maximum of 8 tool steps, 60 seconds and a token budget per request. Hitting a limit returns a clear partial failure.
- **Tool errors:** return them to the model as tool results, so it can adjust or say what it couldn't find.
- **Ambiguous names:** ask the user which player they mean instead of guessing.
- **Prompt rules:** report only numbers from tool results, state the sample size, separate facts from coaching inferences, and say so when data is missing.

### Grounding check

After the model responds, code checks that each statistic in the report matches a value from a tool result in that run.

The report schema makes this possible, because each key stat carries its value and source:

```json
{
  "summary": "string",
  "strengths": ["string"],
  "weaknesses": ["string"],
  "game_plan": ["string"],
  "key_stats": [
    {
      "label": "Break points saved, clay, 2024",
      "value": 0.64,
      "tool_call_id": "string",
      "field": "bp_saved_pct",
      "sample_matches": 31
    }
  ],
  "data_caveats": ["string"]
}
```

The values above only show the format. On a failed check, retry once with the error; if it fails again, return the report marked as unverified. Narrative text can still contain a wrong number, so the evals check for that as well.

### API

| Endpoint | Purpose |
| --- | --- |
| `GET /players/search?q=` | Autocomplete, with no LLM call |
| `POST /report` | Takes player, opponent and surface, then returns the report |
| `POST /chat` | Streams answers over server-sent events, using a conversation history sent by the client |
| `GET /health` | Checks the app and database |

The API stays stateless. There are no accounts in the MVP, so public deploys need a simple per-IP rate limit and a daily spend cap to protect the API key.

### Logging

For each request, log a request ID, tools called and their inputs, latency per step, tokens, estimated cost and the grounding result. Use structured JSON logs.

### Frontend

Use Next.js, TypeScript and Recharts. Build these screens only:

- **Match setup:** player and opponent autocomplete, plus a surface picker.
- **Report:** summary, strengths, weaknesses, game plan and two charts: surface win rate, and serve stats side by side.
- **Evidence:** expanding a stat shows the tool, filters and sample size behind it.
- **Chat:** a streaming panel for follow-up questions.

The API key stays on the server. Evals must exist before any UI polish.

## Evals

The evals are the project's main proof of quality, so they must be able to catch mistakes in the stats layer as well as in the model.

**Independence rule:** ground truth comes from separate SQL in `evals/`, which never imports the stats layer. Each question uses explicit dates and is pinned to one data snapshot, so answers don't change when new data arrives.

| Category | Questions | Example |
| --- | --- | --- |
| Single stat | 10 | A player's aces per match in 2023 |
| Filtered stat | 10 | Break points saved on clay against left-handers |
| Head-to-head | 8 | Record between two players on hard courts |
| Comparison | 6 | Which of two players won more second-serve points in 2022? |
| Should refuse or caveat | 6 | A stat outside the dataset, such as rally length, or a filter with no matches |

**What the runner scores:**

- **Numeric accuracy:** each expected number is correct within a tolerance of 0.5 percentage points for rates, and exactly for counts.
- **Tool choice:** the expected tool was called with the expected filters.
- **Invented numbers:** the answer contains no statistic absent from its tool results.
- **Refusal:** should-refuse questions don't produce a made-up answer.
- **Cost and latency:** record tokens and time per question.

**Process:**

1. Record the first full run as the baseline.
2. Group failures by cause.
3. Fix the top three causes.
4. Rerun and commit both results to `evals/results/` as CSV.

Add every bug found by hand as a new eval case. Report results split by category, and never claim a score that wasn't produced by a committed run.

## Milestones

Each milestone ends with something that runs.

| # | Build | Done when |
| --- | --- | --- |
| 0 | Repo setup, Docker Postgres, data download script, check of files and columns | `docs/data-audit.md` lists the years available, row counts, and columns checked against the data dictionary |
| 1 | Idempotent ingestion, schema, quality checks | Running it twice gives identical row counts, each match has two `player_matches` rows, and a quality report is written |
| 2 | Stats layer and player lookup | Tests pass, with 3 or 4 numbers per tool checked against [Tennis Abstract](https://www.tennisabstract.com) or by hand from the raw CSV |
| 3 | Agent, `/report`, `/chat`, logging, grounding check | A curl call returns a valid report with sources, and logs show every tool call |
| 4 | 40 evals and runner | Baseline and improved results are committed |
| 5 | Frontend | The full flow works locally, including the evidence view |
| 6 | Docker image and deploy | A public URL works from a phone, with rate and spend limits active |
| 7 | README, case study, demo script | A stranger can run it from the README, and the case study reports real eval results |

**Quality checks for Milestone 1:**

- Row counts per year, with any large change flagged.
- Duplicate match IDs and missing player IDs.
- Share of matches with stats, per year.
- Stat sanity: first\_in no greater than serve\_points, and bp\_saved no greater than bp\_faced.
- Result types from `score`, with unrecognized values reported.

Rejected rows go to `data/rejects/` with a reason, never silently dropped.

### Repo layout

```text
api/        FastAPI app, agent, stats layer, tests
ingest/     Download, validation, loading
evals/      Questions, ground-truth SQL, runner, results
web/        Next.js app
infra/      Dockerfile and deploy config
docs/       decisions.md, data-audit.md, case-study.md
data/       Raw data and rejects, gitignored
```

## Working rules and open decisions

### Rules for Claude Code

1. Build one milestone at a time, and stop at the stopping point in the prompt.
2. Verify before claiming. Show real command output, and label anything not run.
3. Never hardcode or estimate a statistic in app code, tests or docs. Test values must come from a named source.
4. If the data contradicts this spec, stop and report it instead of working around it.
5. Keep it simple: no ORM, agent framework or abstraction unless a current problem needs it.
6. Write SQL by hand with parameterized queries, and never build queries by joining strings.
7. Keep secrets in `.env`, which is gitignored, and commit a `.env.example`.
8. Record each significant choice in `docs/decisions.md`: what was chosen, the alternatives, and why.
9. Commit small changes with clear messages, and only when asked.

The decision log feeds the case study. Keep the code simple enough that I can explain every line.

### Decisions for me to make

- [ ] **Latest data:** if the repo stops before the current season, is that acceptable? The options are to state the cutoff clearly or evaluate another source, checking its license first.
- [ ] **API budget:** set a monthly Anthropic spend limit before Milestone 3.
- [ ] **Hosting:** AWS App Runner is the plan, with Fly.io or Railway as the fallback if AWS blocks progress. Confirm availability and pricing before Milestone 6.
- [ ] **Real user:** find one coach or player to try the report. Their feedback goes into the case study.

### After the MVP

These wait until the case study is published: RAG over coaching notes or match reports, Match Charting Project data, evals in CI, and WTA data.

## Sources

- [Jeff Sackmann, tennis\_atp repository](https://github.com/JeffSackmann/tennis_atp)
