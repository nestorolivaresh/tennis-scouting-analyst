"""Load the pinned raw files into Postgres, then write the quality report.

Usage: uv run --env-file .env python -m ingest.load

1. Check every raw file against ingest/data.lock.json, and refuse to load anything else.
2. Transform the rows (ingest/transform.py), resolving player IDs with the reviewed
   files from ingest/players.py.
3. Rebuild every table in one transaction, so a failure leaves the previous data as it was.
4. Write data/rejects/rejects.csv and docs/quality-report.md.

Running it twice gives identical tables; the fingerprints in the report show it.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from ingest import players as player_files
from ingest import quality
from ingest.download import LOCK_PATH, RAW_DIR, SACKMANN_SEASONS, TML_SEASON, verify
from ingest.transform import (
    LEVELS,
    MATCH_COLUMNS,
    PLAYER_MATCH_COLUMNS,
    needs_special_mapping,
    player_row,
    to_int,
    transform_file,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "ingest" / "schema.sql"
SPECIAL_EVENTS_PATH = ROOT / "ingest" / "special_events.csv"
REJECTS_PATH = ROOT / "data" / "rejects" / "rejects.csv"
REPORT_PATH = ROOT / "docs" / "quality-report.md"

SEASON_FILES = [("sackmann", year, RAW_DIR / "sackmann" / f"atp_matches_{year}.csv") for year in SACKMANN_SEASONS]
SEASON_FILES.append(("tml", TML_SEASON, RAW_DIR / "tml" / f"{TML_SEASON}.csv"))
SPECIAL_EVENT_COLUMNS = ["tourney_name", "level", "is_exhibition", "note"]

# raw.matches columns after (source, season, row_num), in schema order.
RAW_MATCH_COLUMNS = [
    "tourney_id", "tourney_name", "surface", "draw_size", "tourney_level", "indoor", "tourney_date",
    "match_num", "winner_id", "winner_seed", "winner_entry", "winner_name", "winner_hand", "winner_ht",
    "winner_ioc", "winner_age", "loser_id", "loser_seed", "loser_entry", "loser_name", "loser_hand",
    "loser_ht", "loser_ioc", "loser_age", "score", "best_of", "round", "minutes",
    "w_ace", "w_df", "w_svpt", "w_1stIn", "w_1stWon", "w_2ndWon", "w_SvGms", "w_bpSaved", "w_bpFaced",
    "l_ace", "l_df", "l_svpt", "l_1stIn", "l_1stWon", "l_2ndWon", "l_SvGms", "l_bpSaved", "l_bpFaced",
    "winner_rank", "winner_rank_points", "loser_rank", "loser_rank_points",
]  # fmt: skip
SACKMANN_PLAYER_COLUMNS = ["player_id", "name_first", "name_last", "hand", "dob", "ioc", "height", "wikidata_id"]
TML_PLAYER_COLUMNS = ["id", "player", "atpname", "birthdate", "weight", "height", "turnedpro", "birthplace", "coaches", "hand", "backhand", "ioc"]
PLAYER_COLUMNS = ["player_id", "full_name", "hand", "birth_date", "country", "height_cm", "search_name"]
REJECT_FIELDS = ["source", "season", "row_num", "action", "reason", "tourney_id", "tourney_name", "round", "winner_name", "loser_name", "score"]


def check_hashes() -> list[str]:
    problems = []
    for source, spec in json.loads(LOCK_PATH.read_text()).items():
        for name, entry in spec["files"].items():
            path = RAW_DIR / source / name
            problem = verify(path.read_bytes(), entry) if path.exists() else "missing; run ingest.download"
            if problem:
                problems.append(f"{source}/{name}: {problem}")
    return problems


def load_special_events(rows: list[dict]) -> dict[str, tuple[str, bool]]:
    """Tournament name -> (level, is_exhibition), from the reviewed ingest/special_events.csv."""
    events = {}
    for row in rows:
        if row["level"] not in LEVELS or row["is_exhibition"] not in ("true", "false"):
            raise ValueError(f"special_events.csv: bad row {row}")
        events[row["tourney_name"]] = (row["level"], row["is_exhibition"] == "true")
    return events


def copy_rows(cur: psycopg.Cursor, table: str, columns: list[str], rows) -> None:
    """Bulk-insert rows with COPY. Table and column names are quoted identifiers, never data."""
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(*table.split(".")), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with cur.copy(statement) as copy:
        for row in rows:
            copy.write_row(row)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set. Run with: uv run --env-file .env python -m ingest.load", file=sys.stderr)
        return 2
    problems = check_hashes()
    if problems:
        print("Refusing to load files that don't match the lock file:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1

    merge_rows = player_files.read_rows(player_files.MERGES_PATH)
    merges = {int(row["duplicate_id"]): int(row["canonical_id"]) for row in merge_rows}
    crosswalk_rows = player_files.read_rows(player_files.CROSSWALK_PATH)
    special_rows = player_files.read_rows(SPECIAL_EVENTS_PATH)
    special_events = load_special_events(special_rows)
    review_rows = player_files.read_rows(player_files.REVIEW_PATH)
    crosswalk = {row["tml_id"]: int(row["player_id"]) for row in crosswalk_rows}
    sackmann_players = player_files.read_rows(RAW_DIR / "sackmann" / "atp_players.csv")
    tml_players = player_files.read_rows(RAW_DIR / "tml" / "ATP_Database.csv")
    sackmann_by_id = {int(p["player_id"]): p for p in sackmann_players if p["player_id"].isdigit()}
    tml_by_id = {p["id"]: p for p in tml_players}
    new_players = {pid: tml_id for tml_id, pid in crosswalk.items() if pid >= player_files.NEW_ID_START}

    def map_sackmann(raw_id: str) -> int | None:
        player_id = to_int(raw_id)
        player_id = merges.get(player_id, player_id)
        return player_id if player_id in sackmann_by_id else None

    def map_tml(raw_id: str) -> int | None:
        player_id = crosswalk.get(raw_id)
        player_id = merges.get(player_id, player_id)
        return player_id if player_id in sackmann_by_id or player_id in new_players else None

    raw_rows: dict[tuple[str, int], list[dict]] = {}
    for source, season, path in SEASON_FILES:
        rows = player_files.read_rows(path)
        unexpected = set(rows[0]) - set(RAW_MATCH_COLUMNS)
        if unexpected:
            print(f"{path.name} has columns the schema doesn't know: {sorted(unexpected)}", file=sys.stderr)
            return 1
        raw_rows[(source, season)] = rows

    # A special-looking event that isn't in the reviewed table stops the load before anything
    # is written, so a renamed or new event can't slip in with the wrong level (D-010).
    unmapped = sorted(
        {(row["tourney_name"], row["tourney_level"]) for rows in raw_rows.values() for row in rows
         if needs_special_mapping(row["tourney_level"], row["tourney_name"]) and row["tourney_name"].strip() not in special_events}
    )  # fmt: skip
    if unmapped:
        print("Add these events to ingest/special_events.csv before loading:\n  "
              + "\n  ".join(f"{name!r} (level {level})" for name, level in unmapped), file=sys.stderr)  # fmt: skip
        return 1

    # Transform every season file. Duplicate match IDs across files are rejected, not merged.
    matches, player_matches, rejects = [], [], []
    notes: collections.Counter = collections.Counter()
    seen: set[str] = set()
    for source, season, _ in SEASON_FILES:
        rows = raw_rows[(source, season)]
        result = transform_file(rows, source, season, map_sackmann if source == "sackmann" else map_tml, special_events)
        rejects += result.rejects
        notes += result.notes
        for i, match in enumerate(result.matches):
            if match["match_id"] in seen:
                rejects.append({"source": source, "season": season, "row_num": match["source_row"],
                                "action": "row_rejected", "reason": f"duplicate match_id {match['match_id']}"})  # fmt: skip
                continue
            seen.add(match["match_id"])
            matches.append(match)
            player_matches += result.player_matches[2 * i : 2 * i + 2]

    used_ids = sorted({m["winner_id"] for m in matches} | {m["loser_id"] for m in matches})
    players = []
    for player_id in used_ids:
        if player_id in sackmann_by_id:
            p = sackmann_by_id[player_id]
            row = player_row(player_id, player_files.full_name(p), p["hand"], p["dob"], p["ioc"], p["height"])
        else:
            p = tml_by_id[new_players[player_id]]
            row = player_row(player_id, p["player"], p["hand"], p["birthdate"], p["ioc"], p["height"])
        players.append((*row, " ".join(player_files.name_tokens(row[1]))))  # search_name

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:  # one transaction
        cur.execute(SCHEMA_PATH.read_text())
        copy_rows(
            cur,
            "raw.matches",
            ["source", "season", "row_num", *RAW_MATCH_COLUMNS],
            (
                (source, season, row_num, *(row.get(column) for column in RAW_MATCH_COLUMNS))
                for (source, season), rows in raw_rows.items()
                for row_num, row in enumerate(rows, start=1)
            ),
        )
        copy_rows(cur, "raw.sackmann_players", SACKMANN_PLAYER_COLUMNS, ([p[c] for c in SACKMANN_PLAYER_COLUMNS] for p in sackmann_players))
        copy_rows(cur, "raw.tml_players", TML_PLAYER_COLUMNS, ([p[c] for c in TML_PLAYER_COLUMNS] for p in tml_players))
        copy_rows(cur, "raw.player_merges", player_files.MERGE_FIELDS, ([r[c] for c in player_files.MERGE_FIELDS] for r in merge_rows))
        copy_rows(cur, "raw.player_crosswalk", player_files.CROSSWALK_FIELDS, ([r[c] for c in player_files.CROSSWALK_FIELDS] for r in crosswalk_rows))
        copy_rows(cur, "raw.special_events", SPECIAL_EVENT_COLUMNS, ([r[c] for c in SPECIAL_EVENT_COLUMNS] for r in special_rows))
        copy_rows(cur, "players", PLAYER_COLUMNS, players)
        copy_rows(cur, "matches", MATCH_COLUMNS, ([m[c] for c in MATCH_COLUMNS] for m in matches))
        copy_rows(cur, "player_matches", PLAYER_MATCH_COLUMNS, player_matches)
    print(f"loaded {len(matches):,} matches, {len(player_matches):,} player rows, {len(players):,} players; {len(rejects):,} rejects")

    # Rejected rows and removed stats are written out with a reason, never dropped silently.
    REJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REJECTS_PATH, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=REJECT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for reject in sorted(rejects, key=lambda r: (r["season"], r["source"], r["row_num"], r["action"])):
            raw = raw_rows[(reject["source"], reject["season"])][reject["row_num"] - 1]
            writer.writerow({**reject, **{k: raw[k] for k in REJECT_FIELDS[5:]}})
    print(f"wrote {REJECTS_PATH.relative_to(ROOT)}")

    tml_season_rows = raw_rows[("tml", TML_SEASON)]
    tml_ids_used = {r["winner_id"] for r in tml_season_rows} | {r["loser_id"] for r in tml_season_rows}
    summary = quality.LoadSummary(
        rejects=rejects,
        notes=notes,
        merged_rows=sum(
            1 for (source, _), rows in raw_rows.items() if source == "sackmann"
            for row in rows if to_int(row["winner_id"]) in merges or to_int(row["loser_id"]) in merges
        ),
        crosswalk_methods=collections.Counter(r["method"] for r in crosswalk_rows if r["tml_id"] in tml_ids_used),
        review_decisions=collections.Counter(r["decision"] or "pending" for r in review_rows),
    )  # fmt: skip
    with psycopg.connect(database_url) as conn:
        report = quality.build_report(conn, summary, generated_on=dt.date.today())
    REPORT_PATH.write_text(report)
    print(f"wrote {REPORT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
