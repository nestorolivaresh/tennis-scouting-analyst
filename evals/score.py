"""Scoring one answer (spec, Evals: what the runner scores). Pure functions, no I/O.

Numbers are read from the answer's text with a regular expression, so the checks are
deterministic and free to run. The trade-offs, recorded in docs/decisions.md (D-023):
- an expected number counts as found if any number in the answer matches it, so a
  coincidental match can pass;
- a number counts as supported (not invented) if it matches any number in the run's tool
  results or the question, at the precision it's written with, so the invented-number check
  is lenient rather than strict; records ("11-8") and counts ("905 of 1,774") are checked as
  pairs, which is stricter;
- years, ISO dates and ordinals that name a serve, set or round ("2nd serve") are skipped.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

RATE_TOLERANCE_PP = 0.5  # spec: 0.5 percentage points for rates
AVERAGE_TOLERANCE = 0.05  # averages such as aces per match, written to one decimal

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?!\.?\d)(\s*(?:%|percent\b|per cent\b))?(st|nd|rd|th)?"
    r"(\s+(?:serves?|sets?|rounds?|games?|tiebreaks?)\b)?",
    re.IGNORECASE,
)
YEAR_RANGE = (1990, 2035)


@dataclass(frozen=True)
class Number:
    value: float
    decimals: int
    percent: bool
    text: str


def numbers_in(text: str) -> list[Number]:
    """Every statistic-like number in the text: not years, dates, or ordinals that name a
    serve, set or round ("1st serve", "5th set"). Other ordinals ("ranked 161st") count."""
    found = []
    for match in NUMBER_RE.finditer(DATE_RE.sub(" ", text)):
        whole, fraction, percent, ordinal, names_a_thing = match.groups()
        if ordinal and names_a_thing:
            continue
        value = float(whole.replace(",", "") + (fraction or ""))
        decimals = len(fraction) - 1 if fraction else 0
        if not percent and not fraction and "," not in whole and YEAR_RANGE[0] <= value <= YEAR_RANGE[1]:
            continue  # a year (1,999 serve points is not)
        text_seen = match.group(0)[: len(match.group(0)) - len(names_a_thing or "")].strip()
        found.append(Number(value, decimals, bool(percent), text_seen))
    return found


def values_in(data: Any) -> set[float]:
    """Every number in a tool result: numeric fields, and digit runs inside text (scores,
    dates, names), so quoting a score like 7-6(5) is never "invented"."""
    values: set[float] = set()
    if isinstance(data, bool) or data is None:
        return values
    if isinstance(data, (int, float)):
        values.add(float(data))
    elif isinstance(data, str):
        values.update(float(digits) for digits in re.findall(r"\d+", data))
    elif isinstance(data, dict):
        for value in data.values():
            values |= values_in(value)
    elif isinstance(data, (list, tuple)):
        for value in data:
            values |= values_in(value)
    return values


def _close(written: float, decimals: int, true_value: float) -> bool:
    """True if `written` is within one unit of its last written place of `true_value`, so a
    value rounded or cut to that many places counts."""
    return abs(written - true_value) <= 10**-decimals + 1e-9


def is_supported(number: Number, pool: set[float]) -> bool:
    """Could this number have been read from the tool results? Fractions may be written as
    percentages (the system prompt allows it)."""
    for value in pool:
        if _close(number.value, number.decimals, value):
            return True
        if (number.percent or number.value > 1) and 0 <= value <= 1 and _close(number.value, number.decimals, 100 * value):
            return True
    return False


def invented(answer: str, pool: set[float]) -> list[str]:
    return [number.text for number in numbers_in(answer) if not is_supported(number, pool)]


# ---------- pairs: records ("11-8") and counts ("905 of 1,774") ----------
# Checking numbers one by one misses a wrong tally made of real numbers: in the baseline,
# "Medvedev won 10 of 14" (it was 10 of 13) and "they split 3-3" (it was 4-2) passed because
# 3, 10 and 14 each appear somewhere in the tool results. A pair must appear as a pair.

NUM = r"(\d{1,3}(?:,\d{3})+|\d+)"
DASH = r"\s*[-–—]\s*"
DASH_PAIR_RE = re.compile(r"(?<![\d.,])(\d{1,4})" + DASH + r"(\d{1,4})(?![\d.,]\d)")
OF_PAIR_RE = re.compile(
    r"(?<![\d.,])" + NUM + r"\s+(?:out\s+)?of\s+(?:(?:his|her|their|the|its|all|those|these|last|first|past)\s+){0,2}"
    + NUM + r"(?![\d.,]\d)",
    re.IGNORECASE,
)
MONTH = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
MONTH_BEFORE_RE = re.compile(r"\b(?:" + MONTH + r")\.?\s*$", re.IGNORECASE)
# One set score, as written in a result ("7-6(5)", "[10-8]") or an answer ("7–6(5)").
SET_TOKEN = r"\[?\d{1,2}" + DASH + r"\d{1,2}\]?(?:\(\d+\))?"
SET_RUN_RE = re.compile(r"(?<![\d.,])" + SET_TOKEN + r"(?:\s+" + SET_TOKEN + r")*")


@dataclass(frozen=True)
class Pairs:
    """What a run's tool results state as pairs. `records`: wins and losses (either order);
    `counts`: a part of a whole (wins of matches, numerator of denominator, an excluded or
    flagged count of the matches); `scores`: each match score as a list of sets."""

    records: frozenset[tuple[int, int]] = frozenset()
    counts: frozenset[tuple[int, int]] = frozenset()
    scores: tuple[tuple[tuple[int, int], ...], ...] = ()

    def __or__(self, other: Pairs) -> Pairs:
        return Pairs(self.records | other.records, self.counts | other.counts, self.scores + other.scores)


def _sets(text: str) -> tuple[tuple[int, int], ...]:
    return tuple((int(a), int(b)) for a, b in re.findall(r"(\d{1,2})" + DASH + r"(\d{1,2})", text))


def pairs_in(data: Any) -> Pairs:
    records: set[tuple[int, int]] = set()
    counts: set[tuple[int, int]] = set()
    scores: list[tuple[tuple[int, int], ...]] = []

    def ints(*values):
        return all(isinstance(v, int) and not isinstance(v, bool) for v in values)

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            wins, losses, matches = node.get("wins"), node.get("losses"), node.get("matches")
            if ints(wins, losses):
                records.update({(wins, losses), (losses, wins)})
                if ints(matches):
                    counts.update({(wins, matches), (losses, matches)})
            if ints(node.get("numerator"), node.get("denominator")):
                counts.add((node["numerator"], node["denominator"]))
            sample, excluded = node.get("sample"), node.get("excluded")
            if isinstance(sample, dict) and ints(sample.get("matches_counted")):
                # A tool result's sample and excluded counts (siblings in every stats result) as
                # parts of the matches counted, or of every match looked at (counted plus
                # excluded): "1 of the 79", "2 of his 81 matches were walkovers".
                counted = sample["matches_counted"]
                left_out = [v for v in (excluded or {}).values() if ints(v)] if isinstance(excluded, dict) else []
                total = counted + sum(left_out)
                for part in [*(v for k, v in sample.items() if ints(v) and k != "matches_counted"), *left_out]:
                    counts.update({(part, counted), (part, total)})
            for k, value in node.items():
                walk(value, k)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value, key)
        elif isinstance(node, str) and key == "score" and _sets(node):
            scores.append(_sets(node))

    walk(data)
    return Pairs(frozenset(records), frozenset(counts), tuple(scores))


def _is_score_run(run: tuple[tuple[int, int], ...], scores: tuple[tuple[tuple[int, int], ...], ...]) -> bool:
    """Is this run of sets part of a match score, as written or from the other player's side?"""
    mirrored = tuple((b, a) for a, b in run)
    for score in scores:
        for i in range(len(score) - len(run) + 1):
            if score[i : i + len(run)] in (run, mirrored):
                return True
    return False


def unsupported_pairs(answer: str, pairs: Pairs) -> list[str]:
    """Records and counts in the answer that no tool result states. A single dash pair passes
    as a record, or as a set of a real score; several sets in a row must be part of a real
    score; "a of b" passes only as a count. Year ranges (2019-2024, 2019-24) and day ranges
    (May 2-23) are skipped."""
    text = DATE_RE.sub(" ", answer)
    found = []
    for run_match in SET_RUN_RE.finditer(text):
        run = _sets(run_match.group(0))
        if len(run) == 1:
            a, b = run[0]
            year_range = YEAR_RANGE[0] <= a <= YEAR_RANGE[1] and (YEAR_RANGE[0] <= b <= YEAR_RANGE[1] or b < 100)
            if year_range or MONTH_BEFORE_RE.search(text[: run_match.start()]):
                continue
            if run[0] in pairs.records or _is_score_run(run, pairs.scores):
                continue
        elif _is_score_run(run, pairs.scores):
            continue
        found.append(run_match.group(0).strip())
    for match in OF_PAIR_RE.finditer(text):
        a, b = (int(group.replace(",", "")) for group in match.groups())
        if (a, b) not in pairs.counts:
            found.append(match.group(0))
    return found


# A count of zero is often written in words: "Federer won none", "Djokovic won all 5".
ZERO_WORDS = (
    r"\b(none|zero|no (wins|losses|matches|victories|defeats)|won (all|every|each)|lost (all|every|each)"
    r"|unbeaten|undefeated|without (a )?(win|loss|losing|winning)|never (lost|won|beat))\b"
)


def contains_expected(answer: str, value: float, kind: str) -> bool:
    """kind: "count" (exact), "rate" (a fraction; 0.5 percentage points either way, written
    as a percentage or a fraction) or "average" (0.05 either way)."""
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
    if key == "season":
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


def call_matches(call: dict[str, Any], tool: str, player: int | None, opponent: int | None, filters: dict) -> bool:
    """Did this successful tool call ask for what the check expects? Dates may differ by up to
    DATE_SLACK_DAYS."""
    if call["tool"] != tool or call.get("error"):
        return False
    args = call["input"] if isinstance(call["input"], dict) else {}
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
