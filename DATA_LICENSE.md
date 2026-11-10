# Data sources and licenses

This is a non-commercial learning and portfolio project. It has no ads, payments or paid
features, and it isn't meant to make money. Nothing in this repository is offered for
commercial use.

## Sources

**Seasons 2015-2025, player biographies and the data dictionary.** "Tennis databases,
files, and algorithms" by Jeff Sackmann / [Tennis Abstract](https://www.tennisabstract.com/),
licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
The project uses the final commit of the `tennis_atp` repository (`712be0c`, 8 June 2026).
That repository was removed from GitHub in 2026; the files were retrieved from public forks and
checked against the commit's file hashes (`ingest/data.lock.json`).

**Season 2026.** The [TennisMyLife ATP match database](https://stats.tennismylife.org/tennis-match-database).
Its public terms allow personal, educational and non-commercial research use, and don't allow
redistributing the raw CSV files.

## What this repository contains

- **No raw data.** `ingest/download.py` downloads the source files into `data/`, which is not
  committed. Anyone who downloads them uses them under the original terms above.
- **Data derived from the sources**, for non-commercial use only and with the same attribution:
  - `docs/data-audit.md` and `docs/quality-report.md` (counts and summaries);
  - `ingest/player_merges.csv`, `ingest/player_crosswalk.csv` and `ingest/player_review.csv`
    (player IDs, matching methods and review decisions);
  - `web/lib/fixtures/` (example app responses, with match results and stats);
  - `evals/cases.py` and `evals/results/` (eval questions and results).

  What comes from Sackmann's data is shared under
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), as his license requires.
  What comes from the TennisMyLife data stays under TennisMyLife's terms above and isn't
  relicensed here. That covers the TennisMyLife IDs in `ingest/player_crosswalk.csv`, and the
  2026 matches in the summaries and fixtures.
- **Changes made to the data.** The project reshapes matches to one row per player,
  normalizes tournament levels, merges duplicate player IDs, removes stats that fail sanity
  checks, and maps TennisMyLife players to Sackmann IDs. `docs/decisions.md` explains each
  change.
- **Code.** The code's license is separate from the data licenses and hasn't been chosen yet.

## Personal data

Player information is limited to what the analysis needs. Committed files contain no player
birth dates, and some players in the data are minors. Names appear only where a document
needs an example.

## Requests

If you hold rights in this data, or you are a player and want something corrected or
removed, please open an issue in this repository. Requests are handled promptly.
