# Decisions

Each entry records what was chosen, the alternatives, and why. Numbers come from
`docs/data-audit.md` and `docs/quality-report.md` unless another source is linked.

On 2026-11-07 an independent review of D-001 to D-012 found real problems in D-006, D-008,
D-009, D-010, D-011 and D-012, plus several wrong numbers. The entries below include the
fixes, marked "Revised after review".

## D-001 Data sources: Sackmann for 2015-2025, TennisMyLife for 2026

*2026-11-06, Milestone 0. Approved by Nestor.*

**Context.** The spec's source, `JeffSackmann/tennis_atp`, returns 404 on GitHub (checked
2026-11-06). Jeff Sackmann's account now shows only `tennis_MatchChartingProject`, and
GitHub has made `jasonmauss/tennis_atp` the root of the fork network, which happens when
the original repository is deleted. Others reported the same 404 from about 2026-09-20
([MLT-OSS/FirstData#238](https://github.com/MLT-OSS/FirstData/issues/238)). No reason has
been published, and [Tennis Abstract](https://www.tennisabstract.com/) is still updated.
His last commit, `712be0c` ("thru 8 jun 2026"), is identical in at least four forks.

**Chosen.** Seasons 2015-2025 come from Sackmann's commit `712be0c`. Season 2026 comes
from the [TennisMyLife (TML) website](https://stats.tennismylife.org/tennis-match-database)
CSV `2026.csv`. Each season comes from exactly one source; the two are never mixed
within a season.

**Alternatives.**
- Sackmann only, ending 2026-06-08: simplest, but loses Wimbledon through Paris 2026, and
  only 82.2% of its January to June 2026 matches have stats.
- TML for every season: one source and one player ID scheme, updated daily. Rejected
  because its terms are custom (not a CC license), its history integrates Sackmann's data,
  and Tennis Abstract, the planned test oracle, shows Sackmann's numbers.
- Paid APIs (Sportradar, api-tennis and others): cost money and need display licensing.

**Why.** For 2026 up to June 7, the period both cover, TML has stats for 1,393 of 1,404
matches (99.2%) and Sackmann for 1,191 of 1,449 (82.2%); Sackmann's 2026 file is pinned as a
cross-check so the audit reproduces these numbers. TML also reaches 2026-11-01. A season boundary is easy to explain and to evaluate. On the 2025
season, 2,377 of the 2,504 matches that both sources pair and both have stats for are
identical (94.9%); the rest differ, mostly in first and second serve fields, and 8 have
winner and loser stats swapped in one source. We can't yet tell which source is right, so
the sources are not mixed within a season.

**Consequences.**
- Two sets of terms: Sackmann CC BY-NC-SA 4.0; TML personal, educational and non-commercial
  research use, with no redistribution of raw CSVs. Raw data stays out of git, and both are
  credited in the README and the app footer.
- TML identifies players by ATP codes (`B0BI`), so 2026 players must be mapped to
  Sackmann's numeric IDs (Milestone 1; audit section 5).
- TML's `tourney_date` is the match date, while Sackmann's is the tournament start date.
  Ingestion must derive one consistent tournament date (Milestone 1).

## D-002 Pin the data by hash

*2026-11-06, Milestone 0.*

**Chosen.** `ingest/data.lock.json` records each file's SHA-256. Sackmann files also record
the git blob hash from commit `712be0c`, so they can be downloaded from any fork and still
be proven identical to the upstream commit. TML has no versions, so its lock entry records
the download date and SHA-256. `ingest/download.py` fails if a file doesn't match, and
`--relock` is the only way to accept a new TML snapshot.

**Alternatives.** Commit the raw CSVs (not allowed by either source's terms); trust a
mirror without hashes (no proof of provenance).

**Why.** Evals are pinned to one data snapshot (spec, Evals). Hashes make that snapshot
checkable, and TML refreshes become a deliberate change that also updates eval ground truth.

**Limit (found in review).** TML updates its files daily, so someone else downloading later
gets a different `2026.csv` and a hash mismatch. They can run `--relock`, but their 2026 data
and any 2026 eval answers will then differ from ours. Seasons 2015-2025 reproduce exactly. To
keep the "a stranger can run it" goal (Milestone 7) realistic, most evals should use
2015-2025.

## D-003 Use a `.env` file in this repo

*2026-11-07, Milestone 0. Approved by Nestor as an exception to his global credential rules.*

**Chosen.** As the spec says: a gitignored `.env` (created with file mode 600) and a
committed `.env.example` with placeholder values only. `docker compose` reads `.env`
directly. The Python code will read environment variables, loaded with
`uv run --env-file .env`, which needs no extra dependency.

**Rules.** Values from `.env` are never printed, logged or committed. The local Postgres
password is randomly generated. `ANTHROPIC_API_KEY` is filled in by Nestor.

## D-004 Local Postgres in Docker

*2026-11-06, Milestone 0.*

**Chosen.** `postgres:16` (major version pinned; minor versions float to get security
fixes), published only on `127.0.0.1:5433`, data in a named volume, and a fixed compose
project name (`tennis-scouting`) so the volume survives renaming the folder.

**Alternatives.** Port 5432 (often already used by another local Postgres); Homebrew
Postgres (not what the spec or production use).

## D-005 Python project layout

*2026-11-06, Milestone 0.*

**Chosen.** One `uv` project at the repo root with no build backend. Scripts run as
modules from the root (`uv run python -m ingest.download`), and pytest adds the root to
the import path. Dependencies so far: psycopg (Postgres driver) and pandas (used only by the
audit), plus pytest for development. All three are listed in the spec. Season ranges live in
one place (`ingest/download.py`) and every module imports them.

**Why.** It is the simplest setup that lets `api/`, `ingest/` and `evals/` share code
without packaging.

## D-006 Exhibitions are loaded but excluded by default

*2026-11-07, Milestone 1. Approved by Nestor.*

**Chosen.** Laver Cup and NextGen Finals rows get `matches.is_exhibition = true`. They are
loaded, and the stats tools (Milestone 2) leave them out of records and stats unless a filter
asks for them. Every tool response reports how many exhibition matches it left out, as it
does for walkovers.

**Alternatives.** Include them like any match (Tennis Abstract does for Laver Cup); drop them
at ingestion (loses data a coach might still want).

**Why.** They don't use the regular tour format: NextGen plays short sets (first to 4
games), which changes service-game and break-point numbers, and Laver Cup is a team
exhibition decided by a match tiebreak. The quality report lists 187 such matches.

**Revised after review.** The flag came from an exact list of names, and TML calls the
event "Next Gen ATP Finals". A future TML refresh would have loaded it as a normal match
with no warning. The flag now comes from the reviewed table `ingest/special_events.csv`
(see D-010), and the load stops if a special-looking event isn't listed there.

**For Milestone 2.** Many top players have Laver Cup or NextGen matches, so test values taken
from Tennis Abstract must use the include-exhibitions filter, or exclude those matches on the
Tennis Abstract side as well.

## D-007 Result types and which matches count

*2026-11-07, Milestone 1.*

**Chosen.** `result_type` comes from `score`: `walkover` (W/O), `retired` (RET), `defaulted`
(DEF), `completed` (every token is a set score and the listed winner won more sets), and
`unknown` for everything else. By default, records and stats count `completed`, `retired`
and `defaulted`. `walkover` is excluded (spec), and so is `unknown`, which is reported with
its count.

**Why `unknown` is excluded.** All 15 such rows are Davis Cup. One is abandoned (`ABD`),
one is `5-7 1-0`, and 13 end in a match tiebreak that the listed winner lost
(for example `6-2 5-7 [0-1]`). Either the winner or the score is wrong, and if the winner is
wrong the stats are attached to the wrong player, so these matches can't be trusted for
either purpose. Laver Cup's 28 bracketed scores are all consistent, and so are 27 other
Davis Cup tiebreak scores, so the error isn't systematic. TML's 2025 file settles two of
the 13: Abdul Rehman d. Vergara has the same winner with the tiebreak score reversed, while
for Pawelski v Tkemaladze TML lists the opposite winner.

**Not corrected.** `best_of` is loaded as given. 132 completed scores don't fit it (71 Davis
Cup, 61 NextGen Finals, which plays best of five short sets but is coded best of three),
which only matters if a future feature uses set counts.

## D-008 Stat sanity: remove a match's stats, keep the match

*2026-11-07, Milestone 1.*

**Chosen.** A match keeps its stats only if both sides have all nine stat values as whole
numbers, none negative, at least one side has serve points, and for each side:
- `first_in <= serve_points`, `first_won <= first_in`,
  `second_won + double_faults <= serve_points - first_in`, `bp_saved <= bp_faced`,
  `aces <= first_won + second_won`;
- no serve points only in a match cut short (retired or defaulted), since a player can retire
  before serving;
- serve points imply at least one service game;
- enough serve points for the service games: at least 4 per game, minus 3 per tiebreak set
  (the sources sometimes count a tiebreak as a service game, and the player may serve only 1
  point of it), minus 3 more in a match cut short (an unfinished last game), and never fewer
  than 1 point per game.

Otherwise the match stays in records, its stats become NULL (`has_stats = false`), and the
reason goes to `data/rejects/rejects.csv` and the quality report. Walkover stats are always
removed (they are placeholder zeros). CHECK constraints in `ingest/schema.sql` enforce the
rules that need only one row; the rules that need the score or both players are enforced in
`ingest/transform.py` and re-checked in SQL by the quality report and
`ingest/tests/test_loaded_data.py`.

**Evidence.** The spec's two rules have 0 violations in either source. 47 matches lost their
stats: 16 walkover placeholders, 14 with partial stats, 4 with impossible second-serve
numbers, 8 with serve points but no service games (5 TML matches at the 2026 Australian Open,
3 Sackmann), 4 with too few serve points (for example 26 points in 7 service games at 6-1
6-0, and Davis Cup 2017 AUS v USA, where the players have 2 and 0 serve points over 20
service games each), and 1 with no serve points in a completed five-set match (Davis Cup 2017
FIN v GEO).

**Revised after review.** The first version allowed zero serve points in any match and didn't
compare serve points with service games, so the last 13 of those matches had loaded with
stats. Service games are also compared with the score, but only as a flag for review (12
matches), because the sources disagree on whether a tiebreak counts as a service game.

## D-009 Player identity: reviewed merge and crosswalk files

*2026-11-07, Milestone 1. Approved by Nestor.*

**Chosen.** Three committed files, created by `uv run python -m ingest.players` and reviewed
by hand. Rerunning the script only adds rows, so existing IDs and decisions never change.
- `ingest/player_merges.csv`: 10 Sackmann IDs that duplicate another ID. 9 are automatic (same
  name and full birth date, for example Jakub Mensik 210084 to 210150) and 1 is manual (Coleman
  Wong, listed under two names with the same birth date, country and Wikidata ID). Canonical is
  the ID with the most matches. 4 match rows changed player as a result.
- `ingest/player_crosswalk.csv`: each TML code maps to a Sackmann ID or a new ID from 900001.
  Steps, in order: the same player in 2025 matches both sources have (274), name and birth
  date (110), the same birth date with a close name (8), a unique name where Sackmann has no
  birth date (7), manual links (2: Kaan Isik Kosaner, spelled "Isak" by Sackmann; Alex
  Hernandez, listed by Sackmann as Juan Alejandro Hernandez Serrano), and new players (4). The
  two weaker steps also require matching countries when both sources give one; each of their
  rows records the review date and what was checked.
- All three files hold IDs, methods and decisions only, with no names or birth dates (D-013).
- `ingest/player_review.csv`: possible duplicates the rules don't resolve. These are Sackmann
  IDs used in the loaded data that share a birth date and country, or a Wikidata ID, plus every
  new player with any Sackmann player born the same day. All 11 current entries are decided
  (3 same person, 4 different people, 4 new players), and the quality report shows how many
  are pending. Wikidata only prompts a review and never merges on its own, because father and
  son Martin Damm share one Wikidata ID.

Names are compared two ways, letters in order and words sorted, so "Bu Yunchaokete" matches
"Yunchaokete Bu" and "Ji Sung Nam" matches "Jisung Nam". A row whose player can't be mapped
is rejected, never guessed.

**Alternatives.** Switch every ID to ATP codes (Sackmann's file has none); fuzzy matching at
load time (not reviewable, and IDs could change between loads).

**Revised after review.** The first version split two players across two IDs (Coleman Wong
in Sackmann; Alex Hernandez between Sackmann and TML) and never flagged new IDs for review.
The review list and the two manual fixes close those gaps.

## D-010 Levels and dates

*2026-11-07, Milestone 1. Approved by Nestor.*

**Levels.** `matches.tourney_level` is one consistent code (G, M, A, F, D, O), and the file's
value is kept in `source_level`. Davis Cup is D (from the level code, never the name), TML's
`250` and `500` become A, and special events take their level and exhibition flag from the
reviewed table `ingest/special_events.csv` (11 names, including TML's "ATP Finals" and "Next
Gen ATP Finals"). Outside Davis Cup, a tournament coded F or O, or whose name contains
finals, cup, olymp, laver or next, must be in that table, or the load stops before writing
anything. Without this, a level filter would miss Tour Finals 2023 (coded A) and the 2016
and 2021 Olympics (coded A).

**Revised after review.** The first version guessed from names ("ends in Finals" became F),
which would have loaded a renamed NextGen event as a normal match with no warning.

**Dates and seasons.** `tourney_date` is the tournament start date for both sources (for
TML, the earliest match date of the tournament), and `date_from`/`date_to` filter on it.
`match_date` holds TML's real match date where known. The review found that TML's derived
start dates differ from Sackmann's by up to 2 days for some 2025 tournaments (not re-verified
here; it only affects date filters on the edges of a 2026 tournament).

**Season filter: approved spec change (2026-11-07).** "In 2025" can't be answered by dates
alone: 167 matches start in December of the previous year (United Cup, Brisbane, Hong Kong),
so a 2025 date filter would miss them. The shared filters gain `season`, which follows the
source file's season. The stats tools (Milestone 2), the Tennis Abstract checks and the eval
SQL all use `season` for questions that name a year.

## D-011 Rebuild everything in one transaction

*2026-11-07, Milestone 1.*

**Chosen.** Every load drops and recreates the tables and copies all rows inside one
Postgres transaction (DDL is transactional in Postgres).

**Alternatives.** Upserts keyed by match ID (harder to reason about deletions and corrections
in the source); loading into staging tables and swapping (more moving parts, for about 215,000
rows across nine tables, of which 33,334 are matches).

**No CASCADE (revised after review).** The first version dropped tables with `CASCADE`, which
would silently delete anything built on them, such as a Milestone 2 view. Now the load fails
instead: with a test view on `matches`, the load stopped with "cannot drop desired object(s)
because other objects depend on them", and the view and all 33,334 matches were still there.
Any such object must be added to `ingest/schema.sql`.

**Evidence.** Repeated loads give identical MD5 fingerprints for every table. A simulated
failure after the tables were dropped left the previous 33,334 matches in place.

## D-012 Keep the raw files in a `raw` schema for the evals

*2026-11-07, Milestone 1.*

**Chosen.** `raw.matches`, `raw.sackmann_players` and `raw.tml_players` hold the source files
unchanged, as text, with source, season and row number. Eval ground truth (Milestone 4) will
be computed from these tables only.

**Why.** The spec's independence rule says the evals never import the stats layer. If the
ground truth instead read `player_matches`, a reshape bug (for example swapping winner and
loser stats) would appear in both the answer and the expected answer, and the evals would
pass. The quality report also compares every loaded stat with its raw value (0 differences).

**Shared assumptions (revised after review).** "Independent" has limits, and they are stated
here so no eval result overclaims:
- Player identity is shared. The raw match rows hold TML codes for 2026 and Sackmann IDs
  before merging, so eval SQL must use `raw.player_merges` and `raw.player_crosswalk`, the
  same reviewed files the loader uses. The evals can't catch a mistake in those files; human
  review and `ingest/player_review.csv` are the safeguards.
- The eval SQL must re-implement, in its own code, the rules in D-006 (exhibitions, using
  `raw.special_events`), D-007 (which result types count), D-008 (which matches keep stats)
  and D-010 (levels and seasons).
- `raw` keeps blanks as empty strings, not NULL (1,394 rows have no `w_ace`), so eval SQL must
  handle `''` before casting.

## D-013 Data notice and personal data in a public repo

*2026-11-07, Milestone 1. Decided by Nestor.*

**Chosen.** The repo states its terms instead of waiting for permission. `DATA_LICENSE.md` and
the README credit both sources, say the project is non-commercial (no ads, payments or paid
features), say that raw data isn't included, list the changes made to the data, share derived
data under CC BY-NC-SA 4.0 (Sackmann's ShareAlike clause requires it; what comes from
TennisMyLife stays under its own terms), and say how to ask for a correction or removal. Committed files contain no player birth dates: the player ID files
keep only IDs, matching methods and review decisions, and the review tool prints names and
birth dates locally from the gitignored raw files. Test fixtures use made-up birth dates.
`ingest/tests/test_no_birth_dates.py` fails if any real birth date from the raw player files
appears in a file git would commit. It found three in test fixtures before they were fixed.

**Alternatives.** Email TennisMyLife and wait for an answer before publishing (slower, and
their public terms already allow non-commercial use); publish the player files with names and
birth dates (convenient for review, but it republishes part of TML's player file, and some
players are minors).

**Why.** A learning and portfolio project fits both sources' non-commercial terms. A notice
can't grant rights, but it documents that the use fits the terms and gives rights holders a
clear way to ask for changes. Keeping personal data out of the repo is cheap, and it's the
kind of judgment the project should show.

**Limits.** The notice stays true only while the project stays non-commercial. TennisMyLife
notes that third-party terms may also apply (the ATP's rights in the statistics); for a
non-commercial project the risk is low, and the requests process covers it. This is a reading
of the published terms, not legal advice.

## Open items

- Optional courtesy: tell TennisMyLife and Jeff Sackmann that the
  project uses their data under the terms in `DATA_LICENSE.md`. Not a blocker (D-013).
- Choose a license for the code (separate from the data licenses).
- The app footer (Milestone 5) must credit both sources and link to `DATA_LICENSE.md`.
- 13 Davis Cup matches have scores that contradict the listed winner (D-007). A third source
  (atptour.com or daviscup.com) could resolve them later.
- 12 completed matches have service games that don't fit their score (quality report,
  section 3). They keep their stats; check them against a third source when convenient.
- Evals: H04 varies between runs (D-023). Options: return each head-to-head score from the
  asked player's side as well as the winner's, so the model never rewrites one; run each
  question several times and report a pass rate. Decide before Milestone 7's case study.
- The local database role is still a superuser (read-only by setting, D-014). Production uses
  the restricted `tennis_app` role (D-025).

## D-014 Stats layer: which matches count, and what every answer carries

*2026-11-07, Milestone 2. Revised the same day after an independent review (see the end).*

**Chosen.** The seven tools in `api/stats.py` are plain functions over Postgres. They know
nothing about the LLM and return JSON-ready dicts.
- **One definition of "counts".** `SCOPE_SQL` applies the shared filters and labels why a
  match doesn't count: an exhibition (unless `include_exhibitions`), a walkover, an `unknown`
  result, and, only when filtering by surface or by opponent hand, a match where that value is
  unknown. Completed, retired and defaulted matches count. Stats use only counted matches with
  stats, and they always sum numerators and denominators (spec).
- **Every stats response carries its sample:** the filters as applied (defaults included),
  matches counted, matches with stats, the matches the opponent quit (retired or defaulted)
  and the ones the player quit, the first and last tournament dates covered, the count
  excluded for each reason, and the data window. `recent_form` describes the returned
  matches, and its excluded counts cover the dates they span.
- **Dates are named for what they are.** `tourney_date` is a tournament's start date in both
  sources; `match_date` is the day a match was played, which only TML (2026) has, so it is
  None for 2015-2025. `player_profile` returns the newest match with both dates, and the data
  window gives the first and last tournament dates plus the last match date. An agent asked
  "when did he last play?" reads `match_date`, and says when only the tournament is known.
- **Values carry their counts and unit**: `{"value", "numerator", "denominator", "unit"}`, with
  the value rounded to 4 decimals and None (never 0) when the denominator is 0. The unit is
  `fraction` (0.616 means 61.6%) or `per_match` (aces per match). Records use `win_rate`. The
  grounding check (Milestone 3) can point at a field such as `stats.first_serve_in.value`.
- **Serve vs pressure.** `serve_return_stats` returns the point stats and aces per match;
  `pressure_stats` returns break points saved and converted, so the two don't overlap.
- **Filters**: surface, date_from, date_to (both inclusive, on the tournament date),
  tourney_level, opponent_hand (spec), plus `season` (D-010) and `include_exhibitions`
  (D-006).
- **Outcomes stay distinct.** Bad arguments raise `ToolInputError` with a message safe to
  return to the model, before any query runs: unknown filters, wrong types, numbers that
  aren't plain ASCII digits or are out of range (a season outside 1900-2100, a player ID
  beyond Postgres INTEGER), and names longer than 100 characters. A player ID that doesn't
  exist raises `PlayerNotFound`, naming the argument (`player_id` or `opponent_id`). An empty
  sample is a normal answer: counts of 0 and None values.
- **Unknown opponent hand.** It affects 0.66% of player-match rows. When filtering by hand,
  those matches are excluded and counted. TML's match rows could fill 116 of them; not worth
  a second bio source for now.
- **Unknown surface.** 53 Davis Cup 2023 play-off matches have no surface. Without a surface
  filter they count, under "Unknown"; with one, they are excluded and counted.
- **Match order** (`recent_form`, `head_to_head`): tournament date, then TML's match date where
  it exists, then round, then match number, newest first. Within a round robin or a Davis Cup
  tie, Sackmann's match numbers aren't guaranteed to follow match order; this only matters
  when a player has several matches in one round of one event. In the pinned TML file, match
  numbers already follow match dates in every round robin, so no test can tell whether
  `match_date` is in the sort; it stays as a safeguard for later TML snapshots.
- **Name lookup never guesses** (spec: "ask instead of guessing"). `players.search_name` is
  built at load time by the same function that normalizes search text, so accents, hyphens,
  apostrophes and word order all compare equally. A name resolves to one player only by the
  exact name, or when it is the only name containing every typed word as the start of a word.
  Several such names return `ambiguous`. When no name matches, close spellings (`pg_trgm`)
  return `close_spellings` with candidates for the agent to confirm, even when there is only
  one, because a close spelling can be a different player ("Sascha Zverev" is spelled closer
  to Mischa than to Alexander). Candidate lists stop at 10 and say when there are more.
- **Safe SQL.** Every query is fixed text: a shared constant scope plus a constant body,
  joined once when the module loads. Values are always bound parameters; nothing from a caller
  is ever pasted into SQL.
- **Connections.** Read-only for the whole session (`default_transaction_read_only`), with a
  5-second statement timeout, and autocommit. Each tool runs inside one REPEATABLE READ
  transaction, so its queries see one consistent snapshot, and no transaction stays open
  between calls (which would block the next load's DROP). These settings guard against
  mistakes, not attacks: the database role is the local superuser and could switch them off.
  Milestone 3 adds a SELECT-only role for the API (open item).

**Review, 2026-11-07.** An independent review agent recomputed the tools for 160 players and
15 filter combinations, and 300 head-to-heads, with no differences. It found eight problems,
all reproduced and fixed: close spellings were accepted as the answer; the opponent-hand,
date and level filters, unknown results and stat-less matches had no test (a wrong
implementation still passed); tournament start dates were labelled as match dates; read-only
applied only inside tool transactions; some bad inputs raised internal errors and names had
no length cap; `retirements_counted` mixed up who quit, `win_pct` was a fraction and rates had
no unit; a surface filter dropped matches with no surface without counting them; and two
doc errors, plus database tests that skipped silently without `DATABASE_URL`. Each new test
was then checked by putting the old bug back (docs/stat-checks.md).

## D-015 How stats-layer test values are sourced

*2026-11-07, Milestone 2.*

**Chosen.** Every expected value in `api/tests/test_stats.py` comes from Tennis Abstract (7
values for Sinner's 2024 season: the record and six rates, read on 2026-11-07) or from
`api/tests/hand_checks.sh`, which computes them with `awk` from the raw CSV files and shares no
code with the stats layer. `docs/stat-checks.md` lists each value, its source and the tool's
result. All of them match.

**Tests must be able to fail.** A test that passes is only evidence if it would fail when the
rule it covers is broken. Each counting rule and validation check was verified by putting the
bug back in a copy of the code and confirming a test fails; the results are in
`docs/stat-checks.md`. Expected values come from samples chosen to exercise the rule (a
season with stat-less matches, an opponent of unknown hand), not from the easiest example.

**When Tennis Abstract disagrees.** The pinned data is the source of truth for tests, because
Tennis Abstract keeps updating. A disagreement is investigated and recorded in
`docs/stat-checks.md`, never "fixed" by editing the expected value. Tennis Abstract checks use
frozen seasons (2024), where both sources should agree.

## D-016 Indexes: none added

*2026-11-07, Milestone 2.*

**Evidence.** With the heaviest player (Alexander Zverev, 817 matches) and no filters,
`EXPLAIN ANALYZE` shows the tool queries using the existing `idx_pm_player_opponent` for the
player's rows and primary keys for the opponent and players, with one sequential scan of the
33,334-row `matches` table joined by hash. Execution takes 10-17 ms; end to end, a tool call
takes a median of 5-14 ms. Forcing index lookups on `matches` instead was slightly slower
(10.2 ms against 9.5 ms), so no index was added.

**Revisit** if the data grows by an order of magnitude (for example Challenger matches), or if
the tool call latency becomes a meaningful share of an agent request.

## D-017 Agent loop, model and limits

*2026-11-07, Milestone 3. Model, dependencies and refusal handling approved by Nestor.
D-022 replaced the model, effort and token budget on 2026-11-08.*

**Chosen.** `api/agent.py` runs the tool-use loop by hand with the Anthropic SDK (spec: no
agent framework). One loop serves `/report` and `/chat`: send the conversation, run any
tools the model asks for, send the results back, and repeat until it answers or hits a
limit. Each model call is streamed, which keeps long calls safe from HTTP timeouts and lets
`/chat` show text as it arrives.
- **Model and effort.** `ANTHROPIC_MODEL` is required; `.env.example` defaults to
  `claude-opus-5-5` ($4 / $20 per million input / output tokens). `claude-sonnet-5-5` costs
  half; the Milestone 4 evals will show whether its quality holds. `ANTHROPIC_EFFORT`
  defaults to `medium`. Thinking can't be turned off on Opus 5.5, and effort is the control.
- **Limits per request.** At most 8 tool steps (a step is one model turn that asks for
  tools; parallel calls in that turn count once), 24 tool calls in all (to bound database
  work), 60 seconds, and a budget of 250,000 tokens processed (input, cache reads and writes,
  and output). Each SDK call's timeout is the time left, and a stream is cut off at the
  deadline. 250,000 is a ceiling, not an expected cost; real usage is in the logs.
- **Outcomes are distinct.** `completed`, `step_limit`, `time_limit`, `token_limit`,
  `model_declined` (the model refused), `output_truncated` (hit the output limit) and
  `unexpected_stop`. Errors from the Anthropic API (rate limit, overload, rejected key) are
  separate again, and neither kind is ever turned into an empty answer.
- **Tool errors go back to the model** as `is_error` tool results with the stats layer's
  message, so it can fix the call or say what it couldn't find. An unexpected exception is
  reported to the model as "internal error in this tool" and logged by type only.
- **Refusals: a clear outcome, no automatic fallback** (Nestor). Anthropic recommends a
  beta `fallbacks` option that retries a declined request on another model. Tennis
  statistics are far from what the safety classifiers watch for, and the fallback adds a
  beta parameter plus code for a mid-answer switch that would rarely run. Revisit if the
  evals ever show a decline.
- **Prompt caching** uses the automatic `cache_control` setting, so each round of the loop
  reuses the conversation sent in the round before.
- **Tool schemas are not `strict`.** Inputs are a few small fields, the stats layer
  validates them, and a bad input comes back as an error the model can correct.
- **Dependencies** (Nestor): `anthropic` (2.6.0) and `fastapi` from the spec, plus `uvicorn`
  to serve the API and `httpx` (dev only) for FastAPI's test client.

**Tests** use a scripted fake model (`api/tests/fake_model.py`) with the real database, so
the loop, limits, outcomes and logging are tested without an API key. Each limit and rule
was checked by putting the bug back and confirming a test fails (12 of 12 caught).

## D-018 Grounding check

*2026-11-07, Milestone 3. Citation IDs and the minimum count added 2026-11-09, after the first
live report.*

**Chosen.** The report's schema (spec) is enforced with structured outputs, so the final
answer is always valid JSON in that shape. Each key stat names its source: `tool_call_id`
and `field`, a dotted path into that call's result (`stats.first_serve_in.value`,
`surfaces.0.win_rate.value`, `record.wins`). The `tool_call_id` is this run's short ID for
the call (`c1`, `c2`, ...), written as the first field of every tool result the model sees.
A report needs at least 4 key stats (the prompt asks for 4 to 8). `api/grounding.py` then
checks, for each one:
- the tool call exists in this run and didn't fail;
- the path exists and holds a number (not a string, a boolean or an object);
- the value equals that number (a tolerance of 1e-9: values are copied, not recomputed, so a
  rounded 0.62 for 0.6159 fails);
- `sample_matches` is a match count reported by that result: `sample.matches_counted`,
  `sample.matches_with_stats`, or the `matches` of an object on the path (one surface's row,
  a record). Win-loss records include `matches` for this reason.

On failure the errors go back to the model once, with a request to correct the report. A
second failure returns the report with status `unverified` and the errors listed (spec).

**Found in the first live report (2026-11-09).** The first version asked the model to cite
the API's own tool_use IDs (`toolu_01...`). The model can't see those: it cited tool names
(`surface_splits`) instead, failed the check, and on the retry returned no key stats at all,
which passed because an empty list has nothing to fail. The report came back `verified` with
no sources. The scripted fake model had hidden this, because its test script cited the IDs
directly. Fixes: the short ID in every result, the minimum of 4 key stats, and a fake model
that cites only what appears in a result. Each fix was checked by undoing it and seeing a test
fail. The next live report passed on the first attempt with 8 key stats, all grounded.

**Not checked here:** numbers in the narrative text. That's the "invented numbers" score in
the Milestone 4 evals (spec).

## D-019 API contract

*2026-11-07, Milestone 3.*

| Endpoint | Request | Success | Errors |
| --- | --- | --- | --- |
| `GET /health` | none | 200 `{status, database, llm_configured, data_window}` | 503 when the database is down |
| `GET /players/search?q=` | a name or part of one | 200 `{query, candidates, more_candidates}`, best first, at most 10 | 422 for text with no letters or over 100 characters |
| `POST /report` | `{player_id, opponent_id, surface}` | 200 with status `verified` or `unverified` | 422 bad input, 404 unknown player, 502 `incomplete` (a limit or a decline), 503 model not configured or rate limited |
| `POST /report/stream` | the same as `/report` | 200, server-sent events ending with the same body `/report` returns | the same 4xx as `/report`, before the stream opens; errors after that arrive as an `error` event |
| `POST /chat` | `{messages: [{role, content}, ...]}` | 200, server-sent events | 422 bad history (before the stream opens); errors after that arrive as an `error` event |

- **A report response** carries the report, the grounding result (`passed`, `attempts`,
  `errors`), the request with its date window, the evidence (every tool call with its
  `tool_call_id`, input and result, for the evidence view; key stats point into it) and usage
  (tokens, estimated cost, latency).
  The window is the two years up to the newest tournament in the data. Each report asks for
  the same tool calls, which makes reports comparable and the evals repeatable.
- **Reports take player IDs**, from `/players/search`, so a report never has to resolve a
  name. Chat resolves names with `resolve_player` and asks when a name is ambiguous.
- **Report stream events** (added in Milestone 5, D-024): `start` (request ID and the checked
  request), `model_call` (before each model call, with the tool calls so far), `tool_call` and
  `tool_result`, `checking` (before each grounding check, with the number of key stats),
  `correcting` (before the retry, with the number of errors), then `report` (the full body) or
  `error`. The report's text is never sent before it has been checked. `POST /report` runs the
  same code and returns only the last event.
- **Streams are marked `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`**,
  so a proxy doesn't compress or hold them, and send a `: keep-alive` comment every 10 seconds
  while a model call streams. A client that goes away stops the stream after the step in
  progress, and the request is logged as `client_disconnected` (D-024).
- **Chat events:** `start` (request ID), `tool_call` and `tool_result` (with the call's short
  `id`, as in reports), `text` (deltas), then `done` (outcome, usage, cost) or `error`. Log
  lines carry both the short `tool_call_id` and the API's `tool_use_id`.
- **Chat is stateless and accepts only text** (spec: the client sends the history). Turns
  must alternate from the user and end with the user, and are capped at 21 messages, 4,000
  characters each and 30,000 in all. The client never sends tool calls or results, so it
  can't hand the model fake "tool results". The model calls the tools again for each
  question, and the prompt tells it to recompute any number it uses.
- **Every response** has an `X-Request-ID` header, the same ID that is on that request's log
  lines. Error bodies are `{error: {kind, message}, request_id}`, with messages safe to show.
- **Simple by design:** endpoints are plain functions run in FastAPI's thread pool, with one
  database connection per request (a few milliseconds locally). Revisit with a connection
  pool if the deploy shows connection time matters.
- **Deferred to Milestone 6:** the per-IP rate limit and the daily spend cap, which the spec
  requires for public deploys. The per-request token budget already bounds a single request.

## D-020 Where the Anthropic API key lives

*2026-11-07, Milestone 3. Decided by Nestor, an extension of D-003.*

**Chosen.** `ANTHROPIC_API_KEY` goes in the gitignored `.env`, like `DATABASE_URL`. This is
an exception to Nestor's global rule that credentials are read only from 1Password: the
master copy stays in 1Password, and `.env` holds the working copy for this local project.

**Rules.**
- Nestor adds the key. Claude never opens `.env` or prints, logs or commits the key; checks
  only report whether it is set.
- The code passes the key to the SDK explicitly. Without it the app refuses to call the
  model (503 `llm_not_configured`); it never lets the SDK fall back to another credential on
  the machine, such as a saved CLI login.
- The logs never contain the key, the request headers or what users type in chat.
- Spend control: Nestor sets a monthly limit in the Anthropic Console (spec), and each
  request has a token budget (D-017). The daily spend cap comes with the deploy (M6).

**Alternative considered:** keeping the key only in 1Password and running every live
command through `op run` with Touch ID. Safer, but every test run against the model would
need an approval. Revisit for the deployed app, which will read the key from AWS Secrets
Manager (spec).

## D-021 Logging and cost estimates

*2026-11-07, Milestone 3.*

**Chosen.** Structured JSON lines on stdout (`api/logs.py`, standard library only), each
with the request ID:
- `http_request` for every request (method, path, status, latency);
- `report_start` or `chat_start` (player IDs and surface; for chat, only the message count
  and length);
- `model_call` for each call (latency, stop reason, input, output and cache tokens);
- `tool_call` for each tool call (step, ID, tool, input, ok or error, latency);
- `grounding` for each attempt (passed, errors);
- `request_end` (status or outcome, tokens, estimated cost, total latency).

**Cost** is estimated from the token counts and a price table in `api/agent.py` (Anthropic's
pricing page, checked 2026-11-08; a cache write costs 1.25x input, a cache read 0.05x on Opus
5.5 and Sonnet 5.5). A model missing from the table gets a cost of `null`, never 0. The first
table, from 2026-10-06, had Sonnet 5.5's cache reads at $0.20 instead of $0.10; the cost test
now checks both rows against the pricing page. When a call is cut off at the time limit, its
tokens are unknown, and `usage_complete` is false.

## D-022 Lower-cost model settings

*2026-11-08, Milestone 3. Decided by Nestor; replaces the model, effort and token budget in
D-017.*

**Context.** The project's model budget is small, with the Console's monthly
spend limit set to match. Opus 5.5 at medium effort, with three to five
full eval runs, could have cost $50 or more.

**Chosen.**
- **Model: `claude-sonnet-5-5`.** $2 / $10 per million input / output tokens, half of Opus
  5.5, and $0.10 for cache reads (pricing page, checked 2026-11-08). Anthropic's model guide
  says it handles multistep tool use well; the Milestone 4 evals measure whether it is good
  enough here.
- **Effort: `low`.** Output, thinking included, is the expensive part, and low effort keeps
  thinking short. Sonnet 5.5's API default is `high`, so the request always sends the level.
  The guide suggests `medium` as a starting point for multistep tool use, and says at `low`
  the model is more likely to stop before finishing a long task. The report asks for a fixed
  list of tool calls, so `low` should do; if live reports come back incomplete or the evals
  show weaker reports, raise `/report` to `medium` first.
- **Token budget: 120,000 per request.** Measured from the real system prompt, tool schemas,
  report prompt and tool results (Sinner vs Alcaraz on clay and on grass; Djokovic vs Gasquet
  on grass, which needs the fallback call), a report processes about 28,000 to 68,000 tokens
  including one grounding retry, at 3 to 4 characters per token. The largest single prompt is
  under 18,000 tokens. 120,000 leaves about twice the room, and a report that needed more
  would also be close to the 8-step limit.
- **Eval runs:** two full runs (baseline and final), with only the failing questions rerun in
  between.

**Estimated cost** before the live runs: about $0.05 to $0.15 per report and a few cents per
chat question. The budget stops a runaway request at roughly $1.50 even if every token were
output, which no real request comes near.

**Measured** in the first live runs (2026-11-09, Sinner vs Alcaraz on clay; tokens processed
are input, cache writes, cache reads and output; cost from the logs' price table):

| Request | Model calls | Tool calls | Tokens processed | Cost | Latency |
| --- | --- | --- | --- | --- | --- |
| Report, before the citation fix (retried, 2 extra tool calls) | 4 | 11 | 67,642 | $0.111 | 36.7 s |
| Report, after the fix (verified on the first attempt) | 2 | 9 | 23,536 | $0.065 | 16.5 s |
| Chat: "How has Alcaraz served on clay in 2025?" | 3 | 2 | 12,935 | $0.017 | 4.9 s |

Both are inside the estimates, the token budget and the 60-second limit; `low` effort
completed the report. One report is not a sample: the Milestone 4 evals record cost and
latency per question (spec). The chat answer's numbers were checked against
`serve_return_stats` and all match. The narrative is not checked yet: the second report's
summary garbles the clay head-to-head (2-3, Alcaraz ahead) as being in Sinner's favour, the
kind of error the evals' narrative score exists for.

**Alternative for later:** Claude Haiku 5.5 is $0.10 / $0.50 per million tokens for prompts
up to 100,000 tokens (pricing page, 2026-11-08), 20 times cheaper than Sonnet 5.5. Its
quality on these reports is unknown; the evals can compare it. Its price depends on prompt
length, so it isn't in the cost table yet, and its cost logs as `null` until it is.

## D-023 Evals: ground truth, questions and scoring

*2026-11-09, Milestone 4. Revised the same day after an independent review (below), and in
Milestone 5 when building the frontend showed that `excluded` sits next to `sample` in a tool
result, not inside it: counts like "2 of his 81 matches were walkovers" were never accepted.*

**Ground truth.** `evals/truth.py` computes every expected number in SQL over the `raw` tables
only, and never imports the stats layer or the loader (spec, independence rule; D-012). It
writes the rules of D-006 to D-010 again from this log: result types from the score, the
stats sanity rules, exhibitions and levels from `raw.special_events`, merges from
`raw.player_merges`, a year as a season. It covers the Sackmann seasons 2015-2025 only, so no
answer changes when TML refreshes 2026 (D-002). Checks, in `evals/tests/test_truth.py`:
- it reproduces values from named sources: Tennis Abstract and hand checks 1-4, 8, 10-15
  and 20 (records, serve and pressure stats, levels, inclusive dates, exhibitions, unknown
  results, no-surface matches);
- it agrees with the loader on all 30,616 Sackmann matches: result type, level, exhibition,
  stats kept, surface, winner and loser, with no duplicated rows. Two separate
  implementations of the same rules;
- it gives the same number as the stats tools for every expected value in the questions;
- its SQL reads only `raw` tables (checked for joins and comma joins) and it imports
  nothing from `api` or `ingest`.
Breaking each of 19 rules on purpose made a test fail (`docs/stat-checks.md`).

**Shared, so not independent.** Player identity (the reviewed merge files) and the CSV
parsing that fills `raw` are shared with the loader. A CSV parsing bug would reach both the
truth and the stats layer; only the `awk` hand checks, which read the files directly, would
catch it.

**Questions.** 43, in `evals/cases.py`: the spec's 40 in its five categories (10 single stat,
10 filtered stat, 8 head-to-head, 6 comparison, 6 refuse or caveat), plus 3 head-to-head
questions added from bugs found by hand (spec: add every bug found by hand as a new case).
Each names its years. Each is asked on its own through the chat path (`chat_system_prompt`,
`run_loop`), as the first question of a conversation.

**Scoring** (`evals/score.py`, `evals/run.py`) is deterministic and free: no model grades.
- **Numbers:** each expected number must appear in the answer: counts exactly (zero may be
  written as "none" or "won all"), rates within 0.5 percentage points (spec), averages such as
  aces per match within 0.05.
- **Tool choice:** the expected tool was called, without an error, for the right players,
  with the filters the question states; dates may differ by up to 7 days (a season's first
  event can start in late December). Filters the question doesn't state may be absent.
- **Invented numbers:** every number must match a number in that run's tool results or the
  question, at the precision it's written with (a fraction may be written as a percentage).
  Records ("11-8") must be a wins-losses pair from a result, or part of a real match score;
  counts ("905 of 1,774", "10 out of 14") must be a part-of-whole pair from a result. Years,
  dates and ordinals that name a serve, set or round are skipped.
- **Claims in words**, built from the ground truth: a head-to-head answer must not name the
  wrong leader ("in Sinner's favour", "Alcaraz trails") or call an uneven record split
  evenly; H09, which asks who led, must name the leader; a comparison answer must name the
  better player in its first sentence.
- **Refusal:** the answer matches the case's patterns, states no probability after
  declining to predict, and doesn't call a tool it shouldn't (stats for a player the user
  didn't pick, or for someone else instead).
- A question passes only if every check that applies passes and the run completed.

**Runner.** Each answer is written to the CSV as soon as it's scored. `--max-cost` fails
closed: a live run won't start for a model with no price, and a call cut off before its
usage arrived counts at its maximum cost. `--rescore` scores past answers again (free): calls
that succeeded are rerun on the same pinned data, calls that failed stay failed, and it
refuses a results file from a different data snapshot (`data_lock` column).

**Limits, so no score overclaims.**
- Regular expressions over prose: an unusual phrasing can pass a wrong claim or fail a
  right one. The reviewer's examples are tests; others will exist.
- The invented-number check is lenient for whole numbers: with 30 to 40 numbers in a run's
  tool results, a made-up integer often matches one by chance (37 of 101 in the review).
- Claims in words other than who leads, who is better and "split evenly" are not scored.
  Every answer is in the results CSV for reading.
- The prompt fixes were made after reading failures on these same questions, and one run per
  question can't show how often an answer varies. The first improved run passed H04 once
  and failed it in the next run (below).

**Process and results** (spec: baseline, group failures by cause, fix the top three, rerun).
See the results table below.

| Run (`evals/results/`) | Questions | Scored with | Passed | Cost | Mean time |
| --- | --- | --- | --- | --- | --- |
| `baseline` | 40 | the first scorer | 39/40 | $0.690 | 4.1 s |
| `baseline-rescored` | 40 | the final scorer | 37/40 | (same answers) | |
| `rerun-failures` | 6: the 3 failures and 3 new cases | the first scorer plus pairs | 6/6 | $0.127 | 4.6 s |
| `final` | 43 | the first scorer plus pairs | 43/43 | $0.765 | 4.0 s |
| `final-rescored` | 43 | the final scorer | 42/43 | (same answers) | |
| `final-v2` | 43 | the final scorer | 42/43 | $0.779 | 3.9 s |

On the spec's original 40 questions, scored the same way: baseline 37/40, `final-v2` 39/40.
`final-v2` by category: single stat 10/10, filtered stat 10/10, head-to-head 10/11,
comparison 6/6, refuse or caveat 6/6. The milestone spent about $2.43 on model calls,
including one live report to check the prompt change ($0.069, verified, the same 9 tool
calls as before).

**Failures grouped by cause** (baseline, read by hand as well as scored):
1. A number from general knowledge (S06: "a second-serve win rate under 50% is common").
2. A tally made up from a list of matches (H03: "Medvedev won 10 of 14" from 2019 to 2024,
   really 10 of 13; H04: "their last six finals split 3-3", really 4-2 to Alcaraz). The
   same kind of error as the Milestone 3 report's "2-3 clay record in Sinner's favour".
3. The scorer let both of those through, because each number appears somewhere in the
   results. The baseline scored 39/40 when 37/40 was true.

**Fixes:** the system prompt names these mistakes as things not to do, with the baseline's
examples (from general knowledge, from a list, in words); the scorer checks records and
counts as pairs and checks who leads; H09 to H11 turn the three hand-found bugs into
questions.

**What is still wrong.** H04 (the full Sinner-Alcaraz head-to-head, with a long list of
matches) came out differently in each of three runs: correct in `rerun-failures`, "the split
was even" in `final`, and in `final-v2` a Roland Garros final score restated "in Sinner's
scoring order" with two sets wrong. The tool gives each score from the winner's side, and
the model rewrites it. The prompt rule against tallies helped H03 and the new questions,
but one run per question can't show how often an answer goes wrong.

## D-024 Frontend

*2026-11-09, Milestone 5.*

**Stack.** `web/` is a Next.js app with TypeScript and Recharts (spec), pinned to exact
versions: Next 16.4.5, React 19.3.1, Recharts 3.10.1, and TypeScript 5.9.3 (not the new 7.0,
to avoid compatibility risk with Next). No other runtime dependency: plain CSS, no component
library. The two typefaces (Archivo, Newsreader) come through `next/font`, which downloads them
at build time and serves them from the app.

**The key stays on the server.** The browser only talks to the Next.js server, which forwards
exactly three routes to FastAPI: `players/search`, `report/stream` and `chat`
(`next.config.ts`; `API_URL`, default `http://127.0.0.1:8000`, is an address, not a secret).
The API's docs and `POST /report` aren't reachable through the app. The Anthropic key never
leaves FastAPI.

**Every number on screen comes from the run's tool results** (spec core rule), in
`web/lib/evidence.ts`. Each key number's value, sample and title are read from the tool result
it cites, never from the model's JSON; the model's figure appears only when it differs, as a
warning ("Didn't match the data: the report said 0.62"), and a number whose call or field is
missing is shown as not available. Opening one shows its tool call, filters, sample, exclusions,
and the exact field with its counts (for example `stats.break_points_saved.value = 0.6568 (111
of 169)`). Both charts pick calls by what the tool actually used (the result's player, filters
and the report's date window), not by the model's request. A gap is never drawn as zero, and a
note says why: no matches on that surface, not looked up in this report, or no matches with
stats; the serve chart says when a player's numbers cover all surfaces (the small-sample
fallback) and how many matches each rests on.

**Report prompt change for the surface chart.** The report used to call `surface_splits`
filtered to the report's surface, so the chart had only one surface. It now calls it for every
surface (same dates); the serve and break-point calls keep the surface filter. Each report still
makes the same 9 tool calls (D-019). A live report through the app after the change: verified
on the first attempt, 8 key numbers, 9 tool calls, 17.8 seconds, about $0.069.

**Chat.** The open report goes first in the history as context (a user request and the
report's text), then the last complete question-and-answer pairs, trimmed to the API's limits
(D-019). The stream is read with `fetch` (EventSource can't POST) and parsed in
`web/lib/sse.ts`. Answers render `**bold**` and `- ` bullets as React elements, never as HTML.

**Design.** A scouting card: cool chalk background, green-black ink, the player in navy and the
opponent in clay red, so colour always means the same person. Match setup reads as a sentence,
"Scout [opponent] for [player] on [surface]". One accent, optic yellow, marks the key number
whose evidence is open.

**Checks.** `npm --prefix web test` runs 19 tests with Node's own test runner (Node strips the
TypeScript types; no test library) on two real `/report` responses (one from before the
all-surfaces change, one after): key numbers from the evidence, including a mismatch and a
missing call; titles from the tool result; both charts' call selection, fallback, gaps and
notes; the stream parser (split chunks, CRLF and CR, comments); the report client against a
stand-in `fetch` (progress, an `error` event, a cut stream, a 4xx); the progress steps; and the
chat history (alternation, limits, cut-off answers left out). `next build` type-checks. The full flow was checked
by hand in a browser on 2026-11-09: player search and selection, a live report, the charts,
the evidence view, a streamed chat answer with its tool lookups, a 375-pixel-wide phone
layout with no sideways scrolling, and labelled inputs.

**Live progress for the report.** A report takes 15 to 40 seconds. The web app uses
`POST /report/stream` (D-019) and lists each step as it happens: choosing what to look up,
each lookup, writing, checking the key numbers, and the correction if a check fails. The
report itself appears only after its check. `POST /report` is unchanged, for curl and the evals.

**Streams were being held by the proxy (found while building this).** When the browser accepts
gzip, the Next.js proxy compressed the server-sent events and sent them all at the end: a chat
answer arrived as 10 bytes at 0.07 s and the rest at 3.8 s. So the chat panel hadn't been
streaming in the browser either; the earlier check only looked at the finished answer. The API
now marks its streams `no-transform` (the standard way to tell a proxy not to change a
response) and `X-Accel-Buffering: no`; through the proxy, with gzip accepted, the same answer
then arrived in 35 pieces over 4 seconds. An API test checks the headers on both streams.
Checked in the browser: the report's steps appeared as they happened (the first at 2 seconds,
nine lookups by 7 seconds), then the verified report (Medvedev for Zverev on hard, 9 tool
calls, 18.1 seconds, about $0.028 with the prompt cache warm).

**Revised after an independent review (2026-11-09).** A review agent found 16 problems; all
are fixed:
- Key numbers on an unverified report showed the model's own values and samples; the charts
  could say "no matches" for surfaces never looked up, and picked calls by the model's raw
  input. Both now read the tool results as above.
- The Next.js proxy closes a response after 30 seconds of silence, and the report stream is
  silent while the model writes. `experimental.proxyTimeout` is now 90 seconds, above the
  agent's 60-second limit, and both streams send a `: keep-alive` comment every 10 seconds
  while a model call streams. Checked with a stand-in API silent for 35 seconds: the event
  arrived through the proxy at 35.0 s.
- When the browser went away, the open model stream and the database connection were held
  until garbage collection, and nothing was logged. `api/streaming.py` now closes the stream's
  generator as soon as the client stops reading (after the step in progress, for a model call
  that is already running), which closes the model's HTTP stream and the connection and logs
  `request_end` with status `client_disconnected` and the tokens spent. Unexpected errors after
  a stream opens now end it with an `error` event and a log line; a model error's line includes
  the tokens and cost.
- The app had no credits footer, which the spec, D-001, D-013 and the CC BY-NC-SA licence
  require. It now credits both sources and points to `DATA_LICENSE.md`.
- A finished report cleared the chat; now the conversation stays and a note marks the change.
  Cut-off answers are no longer sent back to the model as if complete. The chat no longer
  claims its numbers are checked.
- Accessibility: the progress timer no longer re-announces every second (only new steps are
  announced); the player picker closes on blur, reopens with the down arrow, announces how many
  players match, and marks the keyboard choice with a bar in ink; field borders meet 3:1; the
  charts' empty tab stops are gone; chat answers are announced once finished.
- Smaller: the date line no longer claims every number is from the two-year window; progress
  says "Choosing more stats to look up" when a model call asks for more; inherited properties
  never resolve as fields; React keys are unique; the stream reader is released on errors.

**Not done.** No automated browser test (Playwright would be a new dependency; ask first). No
dark mode. Keep-alives depend on the model API sending events while it thinks; the 90-second
proxy timeout covers the case where it doesn't.

## D-025 Deployment: Vercel and Neon instead of AWS

*2026-11-09, Milestone 6. Decided by Nestor; replaces the spec's Docker image, AWS App Runner
and Secrets Manager, and D-020's plan for the deployed key.*

**Chosen.** One Vercel project on the free Hobby plan runs the site and the API as two
[Services](https://vercel.com/docs/services), and a free Neon database holds the data. Hosting
costs $0, and on both free plans a hit limit pauses the service instead of charging. Checked
against both companies' docs on 2026-11-09: Hobby is for non-commercial personal use (this
project is), functions may run 300 seconds (our limit is 60), Python streaming is supported, and
Python bundles may be 500 MB (ours is 47 MB). Neon's free plan has 1 GB of storage (we use 21 MB
for the stats tables, 39 MB with the raw tables) and sleeps after 5 minutes idle.

**Trade-offs.** No Docker image. Vercel Services is in beta; the
fallback is two separate Vercel projects. Hobby keeps logs for 1 hour, so `api_requests` is the
lasting record of requests (no user text and no IP addresses).

**Routing.** `vercel.json` lists the four public API routes (health, player search, report
stream, chat); anything else goes to the site and 404s. Vercel passes the full path, so a small
middleware removes the `/api` prefix and the same routes work locally. In production these
requests don't go through the Next.js proxy (D-024).

**Daily spend cap** (`api/spend.py`). Each model endpoint reserves an estimated cost before
calling the model, in one transaction under an advisory lock, so simultaneous requests can't
all fit under the cap; the row gets the real cost when the request ends. Serverless copies share
no memory, so the total is in the database. A request that dies keeps its estimate. If the total
can't be read, the model isn't called. With no cap set, the app refuses model calls; only local
development can opt out, with `ALLOW_NO_SPEND_CAP`. A first version relied on Vercel's `VERCEL`
variable to spot production, but that can be turned off in project settings, which would have
silently removed the cap. `/api/health` reports `spend_cap_active` so the go-live check can
confirm it. The cap can be passed by one request's excess over its estimate, so the Anthropic
Console's monthly limit stays as the hard stop.

**Per-IP limit.** Vercel's firewall, at the edge: 6 report or chat requests per 10 minutes per
IP, the one rate-limit rule Hobby allows. It's configured in the dashboard, so the go-live
checklist tests it. It keeps IP addresses out of our own database.

**Database role.** The API connects as `tennis_app` (`infra/neon_setup.sql`), which can read the
stats tables and write only `api_requests`. A test applies the script in a rolled-back
transaction and confirms what the role can and can't do. This closes the Milestone 3 item.
The role is created by `python -m infra.neon_setup`, in one transaction with that script. Neon
adds any role made in its Console, CLI or API to `neon_superuser`, which can write to every
table, and its SQL Editor keeps statements, passwords included, in the query history (Neon's
docs, checked 2026-11-09). The first version of the deploy guide used the Console; re-checking
it against the docs caught this before anything was created. The script now stops if the role
has more access than it should.

**Credentials.** `ANTHROPIC_API_KEY` and `DATABASE_URL` live in Vercel's environment variables,
with master copies in 1Password. Nestor enters them and runs the production data load: under his
rules assistants don't connect to production databases.

**Checks.** Vercel's own local dev server ran both services from `vercel.json`: the routes
resolved, unlisted API routes returned 404, and a live chat answer streamed in 33 pieces over 3.6
seconds. A simulated upload (only the files `.vercelignore` allows, only runtime dependencies)
imports the app. That simulation found that excluding `ingest/` would have crashed production,
since `api/stats.py` imports from it; a test now guards this. Each spend and role rule was broken
on purpose and a test failed. **Not yet checked:** anything on Vercel or Neon themselves, since
nothing has been deployed.

## D-026 The Clubhouse redesign and the Player stats page

*2026-11-10, after Milestone 6. Decided by Nestor; changes the spec's Frontend section and D-024's
design, typefaces and charts. Scouting stays the main product.*

**Screens.** Match setup, the loader and the report stay on `/`, as one client flow. `/players` is
new: one player's record by surface and by season, serve and return, break points, the last 10
matches and a head-to-head, with filters kept in the URL. It needs no model, so it costs nothing
per view and keeps working when the daily spend cap is reached. It starts empty until a player is
chosen. "Scout this player" and "Scout this match-up" carry the players to match setup through
`sessionStorage`.

**Player stats API.** `GET /players/{id}/stats` (`api/player_stats.py`) composes the existing tools
unchanged, so there is no new SQL and no new stat definition (D-014). The whole response reads one
snapshot and is cached (`public, max-age=300, s-maxage=3600`), since the data
only changes on a reload. It is the fifth public API route, after D-025's four. The per-IP limit
covers only report and chat, so varying the query string can reach the database uncached.
`player_profile` returns no birth date: a tool result reaches the model, and through a report's
evidence the browser, and some players are minors (D-013).

**Design.** Bottle green and chalk, Marcellus and Spectral through `next/font`, with a scoreboard
and an honours board. The loader's court takes the chosen surface's colour. Its score, net clip and
final state follow the stream's real events (`web/lib/loader.ts`); nothing is timed or estimated
except a 1.2-second pause on "Game" after a verified report.

**Charts.** The approved design draws the serve table and surface comparison in plain HTML and CSS,
which also reads better for screen readers. No component used Recharts any more, so it was removed.
`web/` now depends only on Next.js and React, with TypeScript for development.

**Numbers on screen.** D-024's rule stands. Two additions: percentages are computed from each
rate's counts, because the tool's `value` is already rounded and rounding it again could be 0.1 out
(37 of 43 showed 86.1%, and is 86.0%). And a game plan or note shows a large figure only when that
exact value is among the report's checked values; the rest of the text is shown as the model's prose.

**Flags.** Inline SVGs for the 41 most common countries in the data. A country without one shows
the monogram alone, so a flag is never wrong.

**How it was built and checked.** Five agents worked in separate worktrees on separate files (the
API, the shared foundation, setup and loader, report, Player stats), and were combined and tested
in one checkout. The combined app ran in a browser against the real API and database, with a
stand-in for the two model endpoints: search, keyboard selection, a clean report, a correction
(Deuce, net clip, Ad, Game), a failed report, leaving mid-report, source panels, chat, every filter,
Back and Forward, a bad link, the handoff to match setup, and 375 px with no sideways scrolling.
The setup bracket measured 0 px off the courts.

**Not checked.** The new route on Vercel and its CDN (nothing has been deployed); a real model
report through the new screens (the stream's format is unchanged); reduced motion in a live browser
(its CSS and logic are in place and the loader's logic is tested); browsers other than Chromium.

## D-027 Spanish and French

*2026-11-10.*

**Context.** Nestor asked for a language switch between English, Spanish and French, with the
default set by the visitor's location.

**Chosen.** The default is the visitor's saved choice (a `lang` cookie kept for a year), then the
first of their browser's languages the app has (`Accept-Language`, by preference, matched on the
base language, so `es-419` is Spanish), then English. No location or IP is used. A switch in the
nav (EN, ES, FR, each named in its own language for screen readers) changes the page in place, so
a report or a chat on screen stays; text the model already wrote stays in the language it was
written in.

- **Words.** Every word on screen is in `web/lib/messages/en.ts`, `es.ts` and `fr.ts`. English is
  the reference: the other two have its type, so a missing string or a wrong argument doesn't
  compile, and a test checks the same at run time. A guard test fails when a component holds words
  of its own. English output is unchanged, which the existing tests show. No package: the month
  names are in the messages, decimals use a comma and a space before the percent sign in Spanish
  and French, and country names come from the browser (`Intl.DisplayNames`). Player and tournament
  names stay as the data spells them.
- **Reports and chat.** `POST /report`, `/report/stream` and `/chat` take `language` (`en`, `es` or
  `fr`, default `en`); anything else is a 422 before any model call. Spanish and French add one
  rule to the prompt (write the text in that language, with a decimal comma and dates in words);
  the English prompts are byte-for-byte what they were, so the evals still describe them. Key
  numbers are checked exactly as before. A figure in the model's text is read as `75.7%` or
  `75,7 %`.
- **Rendering.** Pages read the cookie and header on the server, so the first HTML is already in
  the visitor's language, with no flash of English. They are therefore rendered per request rather
  than as static files, and served `private, no-store`, so a cache never hands one visitor another's
  language. On Vercel each page view is now a function call; at this traffic that's well within
  Hobby.

**Alternatives.** Defaulting by IP (Vercel already sends the visitor's country): Google's guidance
for multilingual sites advises against adapting content to a guessed location and recommends
visible links to switch; W3C treats the browser's language as a reasonable first guess when people
can override it and the choice is saved (both read 2026-11-10). A country isn't a language either:
Canada and Switzerland have no single answer, and a visitor abroad or on a VPN gets the wrong one.
A language in the URL (`/es/...`) would make links shareable per language and help search engines,
but changes every route, which a demo doesn't need. Translating in the browser after the page loads
would show English first.

**Checked.** 303 Python tests (10 new) and 185 web tests (13 new), the type check and the
production build. One real report in each language: both verified on the first attempt, 9 tool
calls each, $0.074 in Spanish and $0.073 in French, with decimal commas and no raw dates or
unrounded figures. The production build in a browser in all three languages, with a stand-in
replaying those two reports: the server-chosen language for seven browser settings and cookies,
the switch, setup, loader, report, source panels, chat, switching in the middle of a report, the
Player stats page, and 320 and 375 px. That found three layout faults, now fixed: the French
"Avantage" overflowed its flap, a Spanish button pushed past a phone's width, and the phone
header wrapped unevenly (its languages now sit beside the emblem, with the sections below).

**Not checked.** A native French speaker hasn't read the French. The evals are in English only. No
real chat answer in Spanish or French has been run.

## D-028 Milestone 7: a README a stranger can follow

*2026-11-10.*

**Chosen.** The README now walks a stranger from `git clone` to a running app, and
`docs/case-study.md` and `docs/demo.md` complete the milestone (spec). Each number in the case
study comes from this log or from the committed results in `evals/results/`.

**Checked by doing it.** The README was followed from a fresh clone of the public repository,
with its own Postgres container on another port, so the working database was never touched. That
found two problems:
- **The 2026 files no longer match.** TennisMyLife had changed `2025.csv` and `2026.csv` since
  the snapshot of 7 November, so the download stops with a mismatch, as designed (D-002). The
  README now gives the steps that accept a newer snapshot (`--relock`, then `ingest.players`),
  and names the five tests that pin 2026 dates or counts and so fail on it. The other 298 pass.
  The raw files can't be redistributed (D-013), so the original snapshot can't be shipped.
- **The first test run on a new database timed out.** Right after a load, Postgres has no
  planner statistics for the new rows, and the evals' check that compares the ground truth with
  the loader on every match hit its 60-second statement timeout (73 seconds, failed). The load
  now runs `ANALYZE` in its transaction: the same sequence then passed that check in 21 seconds,
  and the whole suite in 39. The load itself takes about 6 seconds.

**Not checked.** The README on another machine or operating system, and with Node.js versions
other than 23.11.
