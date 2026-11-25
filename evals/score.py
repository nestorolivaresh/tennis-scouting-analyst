"""Scoring one answer (spec, Evals: what the runner scores). Pure functions, no I/O.

Numbers are read from the answer's text with regular expressions, so the checks are
deterministic and free to run. The trade-offs, recorded in docs/decisions.md (D-023):
- an expected number counts as found if any number in the answer matches it, so a
  coincidental match can pass;
- the invented-number check is the one the app runs on chat answers and report text
  (`api/numbers.py`, D-031), imported here so the evals measure it: a number counts as supported
  if it matches any number in the run's tool results or the question, at the precision it's
  written with, so it is lenient rather than strict; records ("11-8") and counts ("905 of
  1,774") are checked as pairs, which is stricter;
- years, ISO dates and ordinals that name a serve, set or round ("2nd serve") are skipped.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from api.numbers import (  # noqa: F401 - the scorer's number rules, kept importable from here
    DATE_RE,
    NUMBER_RE,
    YEAR_RANGE,
    Number,
    Pairs,
    check_answer,
    invented,
    is_supported,
    numbers_in,
    pairs_in,
    unsupported_pairs,
    values_in,
)

RATE_TOLERANCE_PP = 0.5  # spec: 0.5 percentage points for rates
AVERAGE_TOLERANCE = 0.05  # averages such as aces per match, written to one decimal


# A count of zero is often written in words: "Federer won none", "Djokovic won all 5".
ZERO_WORDS = (
    r"\b(none|zero|no (wins|losses|matches|victories|defeats)|won (all|every|each)|lost (all|every|each)"
    r"|unbeaten|undefeated|without (a )?(win|loss|losing|winning)|never (lost|won|beat))\b"
)


# A set's games, "6-4" or "7–6", for scores; a tiebreak's points in parentheses are dropped first.
GAMES_RE = re.compile(r"(?<!\d)(?<!\d\.)(\d{1,2})\s*[-–—]\s*(\d{1,2})(?!\d|\.\d)")


def set_games(text: str) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in GAMES_RE.findall(re.sub(r"\([^)]*\)", " ", text))]


def contains_expected(answer: str, value: float | str, kind: str) -> bool:
    """kind: "count" (exact), "rate" (a fraction; 0.5 percentage points either way, written
    as a percentage or a fraction), "average" (0.05 either way), "name" (a last name, as a whole
    word, case ignored) or "score" (every set's games in order, winner's first, the tiebreak
    points optional: "4-6 7-5 7-5")."""
    if kind == "name":
        return re.search(rf"\b{re.escape(str(value))}\b", answer, re.IGNORECASE) is not None
    if kind == "score":
        sets, found = set_games(str(value)), set_games(answer)
        return bool(sets) and any(found[i : i + len(sets)] == sets for i in range(len(found) - len(sets) + 1))
    if kind == "count" and value == 0 and re.search(ZERO_WORDS, answer, re.IGNORECASE):
        return True
    for number in numbers_in(answer):
        if kind == "count":
            if not number.percent and number.decimals == 0 and number.value == value:
                return True
        elif kind == "rate":
            if (number.percent or number.value > 1) and abs(number.value - 100 * value) <= RATE_TOLERANCE_PP + 1e-9:
                return True
            if not number.percent and number.value <= 1 and number.decimals and abs(number.value - value) <= RATE_TOLERANCE_PP / 100:
                return True
        elif kind == "average":
            if not number.percent and abs(number.value - value) <= AVERAGE_TOLERANCE + 1e-9:
                return True
        else:
            raise ValueError(f"unknown kind {kind!r}")
    return False


# ---------- tool calls ----------


def _norm(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in ("season", "event_code"):
        return int(value) if str(value).isdigit() else str(value)
    if key in ("date_from", "date_to"):
        try:
            return dt.date.fromisoformat(str(value)).isoformat()
        except ValueError:
            return str(value)
    if key == "tourney_level":
        codes = value if isinstance(value, (list, tuple)) else [value]
        return frozenset(str(code).upper() for code in codes)
    if key in ("surface", "opponent_hand"):
        return str(value).casefold()
    return value


DATE_SLACK_DAYS = 7  # "from 2019" may be written as date_from 2018-12-31 to catch a season's first event


def _same(key: str, given: Any, expected: Any) -> bool:
    if key in ("date_from", "date_to") and given is not None:
        try:
            gap = dt.date.fromisoformat(str(given)) - dt.date.fromisoformat(str(expected))
        except ValueError:
            return False
        return abs(gap.days) <= DATE_SLACK_DAYS
    return _norm(key, given) == _norm(key, expected)


def call_matches(
    call: dict[str, Any], tool: str, player: int | None, opponent: int | None, filters: dict, inputs: dict | None = None
) -> bool:
    """Did this successful tool call ask for what the check expects? `inputs` are top-level
    arguments (a season, an event code); `filters` are inside `filters`. Dates may differ by up
    to DATE_SLACK_DAYS."""
    if call["tool"] != tool or call.get("error"):
        return False
    args = call["input"] if isinstance(call["input"], dict) else {}
    if not all(_same(key, args.get(key), value) for key, value in (inputs or {}).items()):
        return False
    if player is not None:
        ids = {str(args.get("player_id")), str(args.get("opponent_id"))} if opponent else {str(args.get("player_id"))}
        if ids != ({str(player), str(opponent)} if opponent else {str(player)}):
            return False
    given = args.get("filters") or {}
    if not isinstance(given, dict):
        return False
    return all(_same(key, given.get(key), value) for key, value in filters.items())


def matches_all(patterns: tuple[str, ...], text: str) -> bool:
    return all(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def matches_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


# ---------- claims in words: who leads, who is better ----------
# Built from the ground truth by the runner, so no case types a name in by hand. Regular
# expressions over prose can still be fooled by unusual phrasing; D-023 lists the limits.

LEAD_WORDS = r"(?:leads?|led|is ahead|was ahead|(?:holds?|held|has|had) (?:the |an? |a \d+[-–—]\d+ )?(?:edge|lead|advantage|upper hand))"
TRAIL_WORDS = r"(?:trails?|trailed|is behind|was behind)"
SPLIT_EVEN = r"\bsplit\b[^.;]{0,25}\b(?:even|evenly|level)\b|\b(?:even|level)\b[^.;]{0,10}\bsplit\b"
COMPARATIVE = r"(?:higher|more|better|greater|bigger|larger)"
SENTENCE_CHAR = r"(?:(?![.!?]\s)[\s\S])"  # stays within one sentence (decimals like 51.0 are fine)


def _within_sentence_without(name: str) -> str:
    return rf"(?:(?!\b{re.escape(name)}\b)(?![.!?;]\s)[\s\S])"


def wrong_leader(leader: str, trailer: str) -> tuple[str, ...]:
    """Ways of saying the trailing player leads: "Sinner leads", "in Sinner's favour",
    "led by Sinner", "Alcaraz trails". The leader's name in between breaks a match, so
    "Sinner and Alcaraz: Alcaraz leads" is fine."""
    t, l = re.escape(trailer), re.escape(leader)
    return (
        rf"\b{t}\b{_within_sentence_without(leader)}{{0,30}}?\b{LEAD_WORDS}\b",
        rf"\b{t}(?:'s|’s)? favou?r\b",
        rf"\bled by {t}\b",
        rf"\b{l}\b{_within_sentence_without(trailer)}{{0,30}}?\b{TRAIL_WORDS}\b",
    )


def right_leader(leader: str, trailer: str) -> str:
    l, t = re.escape(leader), re.escape(trailer)
    return (
        rf"\b{l}\b{_within_sentence_without(trailer)}{{0,40}}?\b(?:{LEAD_WORDS}|won \d+ of)\b"
        rf"|\bled by {l}\b|\b{t}\b{_within_sentence_without(leader)}{{0,30}}?\b{TRAIL_WORDS}\b"
    )


def better_first(winner: str, loser: str) -> tuple[str, str]:
    """(must, must_not) for a comparison: the first sentence names the better player before a
    comparative ("Medvedev won more ..."), and doesn't put the other player there instead."""
    w, lo = re.escape(winner), re.escape(loser)
    must = rf"\A{SENTENCE_CHAR}*?\b{w}\b{SENTENCE_CHAR}*?\b{COMPARATIVE}\b"
    must_not = rf"\A{SENTENCE_CHAR}*?\b{lo}\b{_within_sentence_without(winner)}*?\b{COMPARATIVE}\b{SENTENCE_CHAR}*?\bthan\b"
    return must, must_not
