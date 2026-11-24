# Case study: a scouting analyst that can't make up numbers

A personal project, built for fun and to explore new tools. Live at [tennis-scouting-analyst.vercel.app](https://tennis-scouting-analyst.vercel.app). Every
claim below links to the decision that records it in [decisions.md](decisions.md) (D-001 to
D-030), and every eval number comes from a committed results file in
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
- **Scouting patterns.** How a player does in tiebreaks and deciding sets, after winning or
  losing the first set, and against top-ranked opponents; how their serve and return rates rank
  against the rest of the tour; and, from matches charted shot by shot, where they serve on each
  court, how they do in short and long rallies, and at the net (D-029, D-030).
- **Player stats.** Any player's record by surface and season, serve and return figures,
  scouting patterns, recent matches and head-to-head, with no model involved. A season path lists
  each tournament of a season and how it ended, with walkovers shown but not counted (D-035).
- **Match prep.** Two players side by side over the report's window: each serve figure against
  the other player's return of the same serve, sets and tiebreaks, charted patterns and every
  meeting, with no model involved (D-033).
- **Three languages.** English, Spanish and French, defaulting to the browser's language
  (D-027).

## How it's built

```text
public CSVs ── download, hash-pinned ──▶ data/ ── load, one transaction ──▶ Postgres
                                                                              │
                                    raw tables ◀──────────────────────────────┤
                                        │                                     ▼
                              evals/truth.py                       api/stats.py: 11 tools,
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
4. **The model cites the numbers in its text, and the app writes them.** In chat answers and a
   report's text the model writes `[[c2:stats.first_serve_in.value]]` instead of a number;
   `api/citations.py` writes the value in, and a tap opens its source, so a figure attached to
   the wrong claim can be seen (D-032). Every other number is looked for in the request's tool
   results, with the rules the evals use for invented numbers, now in `api/numbers.py`, and
   one not found is underlined where it appears, with a line saying which ones. In the last
   eval run's 51 answers (`m10-final`), 4 of 731 numbers were flagged: 3 the model's own, 1 a
   false flag. With numbers changed on purpose, it caught 94% of changed percentages, 89% of
   changed records and scores, and 77% of changed whole numbers (D-031, D-032).
5. **Evals with independent ground truth.** `evals/truth.py` recomputes every expected answer
   in SQL over the raw tables, and a test enforces that it never imports the stats layer or
   the loader. It agrees with the loader on all 30,616 Sackmann matches, which means two
   separate implementations of the same rules agree. Scoring is deterministic and uses no
   model (D-023).

## Eval results

Forty-three questions: the spec's 40 in five categories, plus 3 added from bugs found by hand.
Milestones 8 and 9 added eight more for the scouting patterns, for 51.
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
| `m8-m9` | 51 | the final scorer | 50/51 | $1.268 | 4.1 s |
| `m8-m9-rescored` | 51 | the final scorer, R02's refusal widened | 51/51 | (same answers) | |
| `m10` | 51 | the app's number check, citations in the prompt | 45/51 | $1.347 | 4.5 s |
| `m10-final` | 51 | the same, head-to-head prompt fix | 45/51 | $1.367 | 4.6 s |
| `m10-final-rescored` | 51 | rally ranges, years after "of" and R07's refusal fixed | 47/51 | (same answers) | |

`final-v2` by category: single stat 10/10, filtered stat 10/10, head-to-head 10/11,
comparison 6/6, refuse or caveat 6/6. `m8-m9`, after the scorer fix: every category passed,
including scouting patterns 7/7. On the spec's original 40 questions, scored the same way,
the baseline passed 37 and `final-v2` passed 39. Milestone 10 (D-031, D-032) made the
invented-number check stricter: number words that count something, and records with three or
four digits, are now checked. Of `m10-final-rescored`'s four failures, three are the model's own
numbers ("two of the five" counted from a list, "a bit under 20 matches") and one is the check's
("14 of his 28 matches were charted", two tools' counts put together, which no tool states as
a pair).

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
different answer in each of three runs. One restated a Roland Garros final score from the other
player's side and got two sets wrong. The fix went into the tool rather than the prompt: every
match now carries its score from the asked player's side too, and H04 passed in `m8-m9`,
quoting each final from Sinner's side (D-029). One run per question still can't show how often
an answer varies.

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
  (D-024, D-027). With the scouting-pattern tools, one measured report made 11 calls and cost
  $0.125, including one correction after the check (D-029).
- **Evals.** A full run of 43 questions costs about $0.78 and averages about 4 seconds per
  question. The evals milestone spent about $2.43 on model calls (D-023).
- **Hosting.** $0 on Vercel Hobby and Neon's free plan. A paused service is the failure mode,
  not a bill (D-025).

## Limits

- **Data.** ATP men's singles at tour level, from 2015 to a 2026 snapshot taken on
  24 November 2026 (matches through 14 November). Shot-level figures come only from the matches the
  Match Charting Project's volunteers charted: 4,454 of the tour matches, mostly top players and
  big matches. They don't split serve direction by score, so "where does he serve on break
  points" is declined.
- **Checking.** A report's key numbers are checked exactly, and numbers cited in the text are
  the data's own. A cited number can still be attached to the wrong claim: that's visible on
  its source card, not caught by code. Numbers the model types instead are only looked for in
  the data: a small whole number usually appears somewhere in the results, so a wrong one is
  missed about one time in four (D-031, D-032).
- **Evals.** English only, one run per question, and scoring with regular expressions over
  prose. The invented-number check is lenient for whole numbers, which often match some
  number in the results by chance (D-023).
- **The 2026 data can't be redistributed.** TennisMyLife updates its files, so a fresh
  download is a newer snapshot than the one the tests were written against (see the README).
- **Limits on use.** The daily spend cap covers reports and chat. The Player stats and match
  prep routes use no model and aren't metered, so varied queries reach the database uncached
  (D-025, D-026, D-033).
- **Not checked.** The French hasn't been read by a native speaker, only two real chat answers
  have been run in Spanish and one in French (D-027, D-031, D-032), and browsers other than
  Chromium haven't been tested (D-026).

## What's next

From the spec's list for after the first version:
- retrieval over coaching notes or match reports;
- evals in CI;
- WTA data.

And one from the results above: run each eval question several times, to measure how often an
answer varies instead of guessing from one run.
