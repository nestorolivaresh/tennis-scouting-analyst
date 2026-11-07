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
data under CC BY-NC-SA 4.0 (Sackmann's ShareAlike clause requires it), and say how to ask for
a correction or removal. Committed files contain no player birth dates: the player ID files
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

## Decisions needed in Milestone 2

- `recent_form` ordering: many matches share a player, tournament, date and round (round
  robins, Davis Cup ties). Pick a fixed tiebreaker; TML has `match_date` for 2026, but whether
  Sackmann's `match_num` follows match order is unverified.
- `opponent_hand` filter: 13% of players have an unknown hand. Decide whether their matches
  are excluded and report how many were left out.
- Tennis Abstract disagreements: decide which source wins when Tennis Abstract differs from
  the pinned data (it keeps updating; the pinned data doesn't).
- Player bios: a TML player linked to a Sackmann ID keeps Sackmann's missing values even
  when TML has them (for example Jia Hu's birth date). Decide whether to fill gaps from TML.
