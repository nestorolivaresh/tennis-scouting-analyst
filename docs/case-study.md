# Case study: a scouting analyst that can't make up numbers

A personal project, built for fun and to explore new tools. Live at [tennis-scouting-analyst.vercel.app](https://tennis-scouting-analyst.vercel.app). Every
claim below links to the decision that records it in [decisions.md](decisions.md) (D-001 to
D-027), and every eval number comes from a committed results file in
[`evals/results/`](../evals/results).

## The problem

A coach preparing a player for a match wants to know how the opponent serves, how they handle
break points, how the two have played each other, and what to do about it. A language model
writes that kind of report fluently. It will also state statistics it was never given, round
or misremember them, and add up records from a list of matches. In a scouting report a
confident wrong number is worse than no number.

So the goal was narrower than "an AI analyst":

- every number a coach sees comes from tested code over public match data;
- every key number can be traced to the exact query result it came from, and is checked
  against it before it is shown;
- the claim that the answers are right is measured by evals whose ground truth doesn't use
  the code under test.

## What it does

- **Match setup.** Pick your player, the opponent and a surface. The report takes 15 to 40
  seconds, and the screen shows each lookup as it really happens. Nothing is timed or estimated.
- **The report.** A scoreboard, a game plan, scouting notes on the opponent, a side-by-side
  comparison of serve, return and break points, the full list of their meetings, and the key
  numbers. Each key number opens to show the tool call behind it: its filters, sample, what
  was left out, and the exact field.
- **Follow-up chat.** It uses the same tools. The app says plainly that chat numbers aren't
  checked the way a report's key numbers are.
- **Player stats.** Any player's record by surface and season, serve and return figures,
  recent matches and head-to-head, with no model involved.
- **Three languages.** English, Spanish and French, defaulting to the browser's language
  (D-027).

## How it's built

```text
public CSVs ── download, hash-pinned ──▶ data/ ── load, one transaction ──▶ Postgres
                                                                              │
                                    raw tables ◀──────────────────────────────┤
                                        │                                     ▼
                              evals/truth.py                       api/stats.py: 7 tools,
                              (separate SQL)                       the only path to the data
                                        │                                     ▼
                                        │                          api/agent.py: tool loop
                                        │                                     ▼
                                        │                          api/grounding.py: each key
                                        │                          number vs its tool result
                                        ▼                                     ▼
                              evals: 43 questions                  FastAPI ── stream ──▶ Next.js
                              scored with no model                 (numbers drawn from tool
                                                                    results, never model text)
```

| Layer | What it does | Decisions |
| --- | --- | --- |
| Data | Jeff Sackmann's ATP files for 2015-2025 (his final commit), TennisMyLife for 2026. Every file is pinned by hash. Player identity across the two sources comes from reviewed ID files, never from automatic merging. | D-001, D-002, D-009 |
| Load | Rebuilds every table in one transaction, writes rejected rows with a reason, and checks invariants (each match has exactly two player rows, stats that can't be true are removed). | D-007, D-008, D-011 |
| Stats | Seven plain functions over Postgres. One SQL definition of which matches count. Every answer carries its sample: matches counted, matches with stats, what was excluded and why, and the dates covered. | D-014 |
| Agent | A tool-use loop written by hand with the Anthropic SDK, with no framework. It runs Claude Sonnet 5.5 at low effort, limited to 8 tool steps, 60 seconds and 120,000 tokens per request. | D-017, D-022 |
| Checks | The report is structured output. Each key number names its tool call and field, and is compared exactly with that result before the report is sent. | D-018 |
| Web | Next.js and React with no other runtime dependency. Every figure on screen is drawn from the tool results, and a missing value is shown as missing, never as 0. | D-024, D-026 |
| Hosting | Vercel and Neon, both on free plans. A daily spend cap is kept in the database, and the API's database role can only read the stats tables and write its own request log. | D-025 |

## How correctness is enforced

Four layers, each meant to catch what the others can't.

1. **The stats layer is tested against outside sources.** Expected values come from Tennis
   Abstract or from `awk` over the raw CSV files, sharing no code with the stats layer. Each
   counting rule was then broken on purpose, to confirm a test fails
   ([stat-checks.md](stat-checks.md), D-015).
2. **Every key number in a report is checked before it's shown.** The model must cite the
   tool call and field each number came from. `api/grounding.py` compares them exactly. A
   mismatch goes back to the model once, and if it still fails, the report is shown marked as
   unverified, with the errors listed (D-018).
3. **The screen can't show a number the model made up.** Values, samples and descriptions
   come from the tool results. A large figure appears beside a game-plan point only when that
   exact value is among the report's checked numbers. The rest of the text is shown as prose
   (D-024, D-026).
4. **Evals with independent ground truth.** `evals/truth.py` recomputes every expected answer
   in SQL over the raw tables, and a test enforces that it never imports the stats layer or
   the loader. It agrees with the loader on all 30,616 Sackmann matches, which means two
   separate implementations of the same rules agree. Scoring is deterministic and uses no
   model (D-023).

## Eval results

Forty-three questions: the spec's 40 in five categories, plus 3 added from bugs found by hand.
Each answer is scored on several checks:
- its numbers, with rates within 0.5 percentage points and counts exact;
- the tool it chose, and the filters it used;
- whether it invented a number absent from its tool results;
- records and counts, checked as pairs;
- for head-to-heads and comparisons, whether it named the wrong leader;
- whether it refused where it should.

| Run | Questions | Scored with | Passed | Cost | Mean time |
| --- | --- | --- | --- | --- | --- |
| `baseline` | 40 | the first scorer | 39/40 | $0.690 | 4.1 s |
| `baseline-rescored` | 40 | the final scorer | 37/40 | (same answers) | |
| `rerun-failures` | 6 | the first scorer plus pairs | 6/6 | $0.127 | 4.6 s |
| `final` | 43 | the first scorer plus pairs | 43/43 | $0.765 | 4.0 s |
| `final-rescored` | 43 | the final scorer | 42/43 | (same answers) | |
| `final-v2` | 43 | the final scorer | 42/43 | $0.779 | 3.9 s |

`final-v2` by category: single stat 10/10, filtered stat 10/10, head-to-head 10/11,
comparison 6/6, refuse or caveat 6/6. On the spec's original 40 questions, scored the same way,
the baseline passed 37 and `final-v2` passed 39.

**What failed, by cause.**
1. A number from general knowledge: "a second-serve win rate under 50% is common".
2. Tallies made up from a list of matches: "Medvedev won 10 of 14" was really 10 of 13, and
   "their last six finals split 3-3" was really 4-2.
3. The first scorer let both through, because each number appeared somewhere in the tool
   results. It reported 39/40 when 37/40 was true. That is the most important finding of this
   milestone: an eval that is too easy to pass is worse than none.

**What changed.** The system prompt names these mistakes as things not to do. The scorer
checks records and counts as pairs and checks who leads. The three hand-found bugs became
questions.

**What is still wrong.** One question (H04, the full Sinner-Alcaraz head-to-head) gave a
different answer in each of three runs. The latest restated a Roland Garros final score from the
other player's side and got two sets wrong. One run per question can't show how often an answer
varies.

## What went wrong along the way

- **A report passed the check with no sources.** The first version asked the model to cite
  API tool-use IDs it can't see. It cited tool names instead, failed, and on the retry
  returned no key numbers at all, which passed because an empty list has nothing to fail.
  The fake model in the tests had hidden it. Now every tool result opens with a short ID the
  model can see, a report needs at least four key numbers, and the fake model only cites what
  appears in a result (D-018).
- **The spend cap could have switched itself off.** A first version recognised production by
  a platform variable that can be disabled in project settings. Now the app refuses model
  calls whenever no cap is set, unless local development opts out explicitly (D-025).
- **A database role with too much access.** The first deploy guide created the API's role in
  Neon's console. Neon adds such roles to a group that can write every table, and keeps their
  passwords in its query history. A script now creates the role and stops if it has any extra
  access (D-025).
- **Birth dates reaching the model.** The player profile tool returned real birth dates, so
  the model could repeat them in chat, and some players are minors. The tool no longer
  returns them, and a test covers every tool (D-026).

## Cost and speed

- **Model.** Claude Sonnet 5.5 at low effort, chosen over Opus 5.5 to halve the price; the
  evals measured whether quality held (D-022).
- **A report.** Nine tool calls, about 18 to 20 seconds of model time and about $0.07
  (D-024, D-027).
- **Evals.** A full run of 43 questions costs about $0.78 and averages about 4 seconds per
  question. The evals milestone spent about $2.43 on model calls (D-023).
- **Hosting.** $0 on Vercel Hobby and Neon's free plan. A paused service is the failure mode,
  not a bill (D-025).

## Limits

- **Data.** ATP men's singles at tour level, from 2015 to a 2026 snapshot taken on
  7 November 2026 (matches through 1 November). There is no point-by-point data, so questions
  about rally length are declined.
- **Checking.** Only a report's key numbers are checked against the data. Its prose and the
  chat answers are not.
- **Evals.** English only, one run per question, and scoring with regular expressions over
  prose. The invented-number check is lenient for whole numbers, which often match some
  number in the results by chance (D-023).
- **The 2026 data can't be redistributed.** TennisMyLife updates its files, so a fresh
  download is a newer snapshot than the one the tests were written against (see the README).
- **Limits on use.** The daily spend cap covers reports and chat. The Player stats routes use
  no model and aren't metered, so varied queries reach the database uncached (D-025, D-026).
- **Not checked.** The French hasn't been read by a native speaker, no real chat answer has
  been run in Spanish or French (D-027), and browsers other than Chromium haven't been
  tested (D-026).

## What's next

From the spec's list for after the first version:
- retrieval over coaching notes or match reports;
- the Match Charting Project's point-by-point data;
- evals in CI;
- WTA data.

And one from the results above: run each eval question several times, to measure how often an
answer varies instead of guessing from one run.
