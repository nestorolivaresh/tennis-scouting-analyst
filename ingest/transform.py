"""Turn raw match rows into rows for the core tables.

Everything here is a pure function of its inputs (no database, no files), so each rule
is unit-tested in ingest/tests/test_transform.py. ingest/load.py does the reading and
writing. docs/decisions.md (D-006 to D-012) explains the rules.
"""

from __future__ import annotations

import collections
import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable

# Stat columns in the source files, per side (w_ for winner, l_ for loser) ...
STAT_FIELDS = ["ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced"]
# ... and the matching player_matches columns, in the same order.
STAT_COLUMNS = [
    "aces", "double_faults", "serve_points", "first_in", "first_won",
    "second_won", "service_games", "bp_saved", "bp_faced",
]  # fmt: skip

MATCH_COLUMNS = [
    "match_id", "source", "season", "source_row", "tourney_id", "tourney_name",
    "tourney_level", "source_level", "is_exhibition", "tourney_date", "match_date",
    "surface", "round", "round_order", "match_num", "best_of", "score", "minutes",
    "winner_id", "loser_id", "result_type", "has_stats",
]  # fmt: skip
PLAYER_MATCH_COLUMNS = ["match_id", "player_id", "opponent_id", "won", "rank", *STAT_COLUMNS]

# Order of rounds within a tournament. RR comes before the knockout rounds that follow it
# (Tour Finals, United Cup); BR (Olympic bronze medal match) is played before the final.
ROUND_ORDER = {"R128": 1, "R64": 2, "R32": 3, "R16": 4, "RR": 5, "QF": 6, "SF": 7, "BR": 8, "F": 9}
LEVELS = {"G", "M", "A", "F", "D", "O"}
SURFACES = {"Hard", "Clay", "Grass", "Carpet"}
# Names that suggest a team event, a finals, the Olympics or an exhibition. Outside Davis Cup,
# a tournament with such a name (or coded F or O) must be listed in ingest/special_events.csv,
# or the load stops (D-010).
SPECIAL_NAME_RE = re.compile(r"finals|cup|olymp|laver|next", re.IGNORECASE)

SET_RE = re.compile(r"^(\d{1,2})-(\d{1,2})(?:\(\d+\))?$")
MATCH_TIEBREAK_RE = re.compile(r"^\[(\d{1,2})-(\d{1,2})\]$")


def to_int(text: str) -> int | None:
    """Parse a whole number; anything else (blank, '12.5', 'NA') is None."""
    text = text.strip()
    return int(text) if re.fullmatch(r"-?\d+", text) else None


def parse_date(text: str) -> dt.date | None:
    """Parse YYYYMMDD. Partial dates such as 19850000 return None."""
    text = text.strip()
    if not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return dt.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return None


def needs_special_mapping(source_level: str, tourney_name: str) -> bool:
    """True for rows whose level and exhibition flag must come from ingest/special_events.csv."""
    return source_level != "D" and (source_level in ("F", "O") or bool(SPECIAL_NAME_RE.search(tourney_name)))


def classify_event(
    source_level: str, tourney_name: str, special_events: dict[str, tuple[str, bool]]
) -> tuple[str, bool] | None:
    """Return (level, is_exhibition) for a row, using one consistent level code (D-010).

    The sources code the same event differently across seasons: Tour Finals is 'A' in 2023
    and 'F' elsewhere, the Olympics are 'A' in 2016 and 2021 but 'O' in 2024, and TML splits
    'A' into '250' and '500'. Special events come from the reviewed table instead of being
    guessed from their names. Returns None when the level can't be determined.
    """
    if source_level == "D":
        return ("D", False)
    if needs_special_mapping(source_level, tourney_name):
        return special_events.get(tourney_name.strip())
    if source_level in ("250", "500"):
        return ("A", False)
    if source_level in ("G", "M", "A"):
        return (source_level, False)
    return None


def sets_won_lost(score: str) -> tuple[int, int] | None:
    """Sets won by the match winner and by the loser, or None if any token isn't a set score."""
    tokens = score.split()
    if not tokens:
        return None
    won = lost = 0
    for token in tokens:
        match = SET_RE.match(token) or MATCH_TIEBREAK_RE.match(token)
        if not match:
            return None
        first, second = int(match.group(1)), int(match.group(2))
        won += first > second
        lost += second > first
    return won, lost


def result_type(score: str) -> str:
    """Classify how the match ended, from the score text (D-007)."""
    upper = score.upper()
    if "W/O" in upper or "WALKOVER" in upper:
        return "walkover"
    if "RET" in upper:
        return "retired"
    if "DEF" in upper:
        return "defaulted"
    sets = sets_won_lost(score)
    if sets and sets[0] > sets[1]:
        return "completed"
    return "unknown"  # empty, abandoned ('ABD'), or a score the winner didn't win


def games_in_score(score: str) -> tuple[int, int]:
    """Total games in the set scores, and how many sets went to a tiebreak (7-6 or 6-7).
    Match tiebreaks written in brackets, such as [10-8], aren't counted."""
    games = tiebreaks = 0
    for token in score.split():
        match = SET_RE.match(token)
        if match:
            first, second = int(match.group(1)), int(match.group(2))
            games += first + second
            tiebreaks += {first, second} == {6, 7}
    return games, tiebreaks


def stats_problem(winner: list[int | None], loser: list[int | None], score: str) -> str | None:
    """Return why a match's stats can't be trusted, or None if they pass (D-008).

    Expects the 9 STAT_FIELDS values for each side and the match score. Each service game
    has at least 4 points, with two allowances: a tiebreak may be counted as a service game
    with as little as 1 point served, and in a match cut short (retired or defaulted) the
    last game may be unfinished. Only a match cut short may have a player with no serve points.
    """
    values = winner + loser
    if any(value is None for value in values):
        return "some stat columns are missing or not whole numbers"
    if any(value < 0 for value in values):
        return "negative stat"
    if winner[2] == 0 and loser[2] == 0:
        return "no serve points recorded for either player"
    cut_short = result_type(score) in ("retired", "defaulted")
    _, tiebreaks = games_in_score(score)
    for side, stats in (("winner", winner), ("loser", loser)):
        ace, df, svpt, first_in, first_won, second_won, games, bp_saved, bp_faced = stats
        second_serve_points = svpt - first_in
        if svpt == 0 and not cut_short:
            return f"{side}: no serve points in a match that wasn't cut short"
        if svpt > 0 and games == 0:
            return f"{side}: serve points but no service games"
        # Every service game has at least one point, and at least four unless it's a tiebreak
        # or the unfinished last game of a match cut short.
        if svpt < max(games, 4 * games - 3 * tiebreaks - (3 if cut_short else 0)):
            return f"{side}: fewer serve points than its service games need"
        if first_in > svpt:
            return f"{side}: first serves in > serve points"
        if first_won > first_in:
            return f"{side}: first-serve points won > first serves in"
        if second_won + df > second_serve_points:
            return f"{side}: second-serve points won + double faults > second-serve points"
        if bp_saved > bp_faced:
            return f"{side}: break points saved > break points faced"
        if ace > first_won + second_won:
            return f"{side}: aces > serve points won"
    return None


@dataclass
class FileResult:
    """Rows produced from one source file, plus everything that was rejected or noted."""

    matches: list[dict] = field(default_factory=list)
    player_matches: list[tuple] = field(default_factory=list)
    rejects: list[dict] = field(default_factory=list)
    notes: collections.Counter = field(default_factory=collections.Counter)


def tournament_start_dates(rows: list[dict]) -> dict[str, dt.date]:
    """Earliest valid date per tourney_id. TML gives each match's own date (D-010)."""
    starts: dict[str, dt.date] = {}
    for row in rows:
        date = parse_date(row["tourney_date"])
        if date and (row["tourney_id"] not in starts or date < starts[row["tourney_id"]]):
            starts[row["tourney_id"]] = date
    return starts


def transform_file(
    rows: list[dict],
    source: str,
    season: int,
    map_player: Callable[[str], int | None],
    special_events: dict[str, tuple[str, bool]],
) -> FileResult:
    """Build matches and player_matches rows from one season file.

    `map_player` turns the file's player ID into the project's player_id, or returns None
    when the player can't be identified (the row is then rejected, never guessed).
    `special_events` maps a tournament name to (level, is_exhibition) for special events.
    """
    result = FileResult()
    starts = tournament_start_dates(rows) if source == "tml" else {}

    for row_num, row in enumerate(rows, start=1):

        def reject(reason: str, action: str = "row_rejected") -> None:
            result.rejects.append(
                {"source": source, "season": season, "row_num": row_num, "action": action, "reason": reason}
            )

        event = classify_event(row["tourney_level"], row["tourney_name"], special_events)
        level, is_exhibition = event if event else (None, False)
        row_date = parse_date(row["tourney_date"])
        tourney_date = starts.get(row["tourney_id"]) if source == "tml" else row_date
        match_num = to_int(row["match_num"])
        best_of = to_int(row["best_of"])
        winner_id, loser_id = map_player(row["winner_id"]), map_player(row["loser_id"])

        if level is None:
            reject(f"unknown tourney_level {row['tourney_level']!r}")
            continue
        if tourney_date is None or row_date is None:
            reject(f"invalid tourney_date {row['tourney_date']!r}")
            continue
        if row["round"] not in ROUND_ORDER:
            reject(f"unknown round {row['round']!r}")
            continue
        if match_num is None:
            reject(f"match_num is not a whole number: {row['match_num']!r}")
            continue
        if best_of not in (3, 5):
            reject(f"invalid best_of {row['best_of']!r}")
            continue
        if winner_id is None or loser_id is None:
            unknown = [pid for pid, mapped in ((row["winner_id"], winner_id), (row["loser_id"], loser_id)) if mapped is None]
            reject(f"unmapped player id {', '.join(unknown)}")
            continue
        if winner_id == loser_id:
            reject("winner and loser are the same player")
            continue

        score = row["score"].strip()
        outcome = result_type(score)
        winner_stats = [to_int(row[f"w_{name}"]) for name in STAT_FIELDS]
        loser_stats = [to_int(row[f"l_{name}"]) for name in STAT_FIELDS]
        has_stats = False
        if any(row[f"{side}_{name}"].strip() for side in "wl" for name in STAT_FIELDS):
            problem = "walkover rows carry placeholder stats" if outcome == "walkover" else stats_problem(winner_stats, loser_stats, score)
            if problem:
                reject(problem, action="stats_removed")
            else:
                has_stats = True
        if not has_stats:
            winner_stats = loser_stats = [None] * len(STAT_FIELDS)

        surface = row["surface"] if row["surface"] in SURFACES else None
        if surface is None:
            result.notes[f"surface missing or unknown ({row['surface'] or 'empty'})"] += 1
        if level != row["tourney_level"]:
            result.notes[f"level {row['tourney_level']} -> {level} ({row['tourney_name']})"] += 1
        sets = sets_won_lost(score)
        if outcome == "completed" and sets[0] != best_of // 2 + 1:
            result.notes[f"completed score doesn't fit best_of {best_of} (level {level})"] += 1

        match_id = f"{row['tourney_id']}-{match_num}"
        result.matches.append(
            {
                "match_id": match_id,
                "source": source,
                "season": season,
                "source_row": row_num,
                "tourney_id": row["tourney_id"],
                "tourney_name": row["tourney_name"],
                "tourney_level": level,
                "source_level": row["tourney_level"],
                "is_exhibition": is_exhibition,
                "tourney_date": tourney_date,
                "match_date": row_date if source == "tml" else None,
                "surface": surface,
                "round": row["round"],
                "round_order": ROUND_ORDER[row["round"]],
                "match_num": match_num,
                "best_of": best_of,
                "score": score or None,
                "minutes": to_int(row["minutes"]),
                "winner_id": winner_id,
                "loser_id": loser_id,
                "result_type": outcome,
                "has_stats": has_stats,
            }
        )
        result.player_matches.append(
            (match_id, winner_id, loser_id, True, to_int(row["winner_rank"]), *winner_stats)
        )
        result.player_matches.append(
            (match_id, loser_id, winner_id, False, to_int(row["loser_rank"]), *loser_stats)
        )
    return result


def player_row(player_id: int, full_name: str, hand: str, birth_date: str, country: str, height: str) -> tuple:
    """One players row. Hand other than R or L (U, A, blank) is stored as unknown (NULL),
    and a height outside 140-230 cm is treated as missing (some TML rows are misaligned)."""
    height_cm = to_int(height)
    return (
        player_id,
        " ".join(full_name.split()),
        hand if hand in ("R", "L") else None,
        parse_date(birth_date),
        country.strip() or None,
        height_cm if height_cm is not None and 140 <= height_cm <= 230 else None,
    )
