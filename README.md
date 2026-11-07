# Tennis Scouting Analyst

An AI scouting analyst over public ATP match data. A coach picks a player, an opponent and a
surface, and gets a scouting report where every number comes from tested code, not from the
model's memory. Evals with independent ground truth check that the answers are correct.

**Status:** Milestone 1 (ingestion and quality checks). See [SPEC.md](SPEC.md) for the plan,
[docs/data-audit.md](docs/data-audit.md) for what the raw data contains,
[docs/quality-report.md](docs/quality-report.md) for what was loaded, and
[docs/decisions.md](docs/decisions.md) for the choices made so far.

## Run it locally

Requirements: [uv](https://docs.astral.sh/uv/), Docker, and Python 3.12 (uv can install it).

```bash
cp .env.example .env                           # then set a local POSTGRES_PASSWORD (and the same in DATABASE_URL)
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
