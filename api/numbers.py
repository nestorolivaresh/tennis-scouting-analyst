"""The numbers in model text, checked against the tool results of the same request (D-031).

The rules began as the evals' invented-number check (D-023), which now imports them from here,
so the evals measure the code the app runs. Numbers are read with regular expressions, so the
check is deterministic and free:
- a single number is found if a value in the results matches it at the precision it's written
  with (a fraction may be written as a percentage); a whole number written for a whole number
  must be equal. This is lenient: a whole number passes if the same number appears anywhere in
  the results;
- records ("11-8"), counts ("905 of 1,774") and runs of set scores must appear as pairs, which
  is stricter;
- years, ISO dates and ordinals that name a serve, set or round ("2nd serve") are skipped.
Spanish and French are read with a decimal comma, a space before "%", and "de" or "sur" for
counts (D-027). A number that reads differently in English ("1,774") is found if either
reading is, because a visitor who writes in English gets an English answer.
"""

from __future__ import annotations

import dataclasses
import functools
import logging
import operator
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from api.logs import log_event

DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
YEAR_RANGE = (1990, 2035)
LANGUAGES = ("en", "es", "fr")

NUMBER_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?!\.?\d)(\s*(?:%|percent\b|per cent\b))?(st|nd|rd|th)?"
    r"(\s+(?:serves?|sets?|rounds?|games?|tiebreaks?)\b)?",
    re.IGNORECASE,
)
# Spanish and French: thousands with a point or a space ("1.351", "1 351", also no-break
# spaces), a decimal comma ("61,6"), ordinals such as "5.º", "1er" and "5e", and the words for
# serves, sets and rounds. English forms are read too.
GROUP_SPACE = "[   ]"
ROMANCE_NUM = r"(\d{1,3}(?:(?:\.|" + GROUP_SPACE + r")\d{3})+|\d+)"
ROMANCE_NUMBER_RE = re.compile(
    r"(?<![\w.,])" + ROMANCE_NUM + r"([,.]\d+)?(?![.,]?\d)(\s*(?:%|percent\b|per cent\b|por ?ciento\b|pour ?cent\b))?"
    r"(\.?[ºª]|\.(?:er|os|as)\b|(?:st|nd|rd|th|er|re|e|ème|eme|nde)\b)?"
    r"(\s+(?:serves?|saques?|servicios?|services?|sets?|rounds?|rondas?|tours?|games?|juegos?|jeux|manches?"
    r"|tie-?breaks?|desempates?)\b)?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Number:
    value: float
    decimals: int
    percent: bool
    text: str
    start: int = 0  # where `text` is in the text read, so the app can mark it
    end: int = 0
    other: tuple[float, int] | None = None  # the English reading, when it differs: (value, decimals)


YEAR_BEFORE_RE = re.compile(r"\b(?:19|20)\d{2}[-–]$")  # "2019-" right before the "24" of "2019-24"


def _ends_a_year_range(text: str, start: int, end: int, plain: bool) -> bool:
    """Two digits right after a year and a hyphen ("2019-24"); "In 2024 — 15 wins" is a count."""
    return plain and end - start == 2 and bool(YEAR_BEFORE_RE.search(text[max(0, start - 5) : start]))


def _blank_dates(text: str) -> str:
    """ISO dates replaced by spaces of the same length, so positions stay true."""
    return DATE_RE.sub(lambda m: " " * len(m.group(0)), text)


def numbers_in(text: str, language: str = "en") -> list[Number]:
    """Every statistic-like number in the text: not years, dates, or ordinals that name a
    serve, set or round ("1st serve", "5th set"). Other ordinals ("ranked 161st") count."""
    if language != "en":
        return _romance_numbers_in(text)
    found = []
    for match in NUMBER_RE.finditer(_blank_dates(text)):
        whole, fraction, percent, ordinal, names_a_thing = match.groups()
        if ordinal and names_a_thing:
            continue
        value = float(whole.replace(",", "") + (fraction or ""))
        decimals = len(fraction) - 1 if fraction else 0
        if not percent and not fraction and "," not in whole and YEAR_RANGE[0] <= value <= YEAR_RANGE[1]:
            continue  # a year (1,999 serve points is not)
        if _ends_a_year_range(text, match.start(1), match.end(1), not percent and not fraction and not ordinal):
            continue
        text_seen = match.group(0)[: len(match.group(0)) - len(names_a_thing or "")].strip()
        found.append(Number(value, decimals, bool(percent), text_seen, match.start(), match.start() + len(text_seen)))
    return found


def _romance_numbers_in(text: str) -> list[Number]:
    found = []
    for match in ROMANCE_NUMBER_RE.finditer(_blank_dates(text)):
        whole, fraction, percent, ordinal, names_a_thing = match.groups()
        if ordinal and names_a_thing:
            continue
        grouped = not whole.isdigit()
        digits = re.sub(r"\D", "", whole)
        if not percent and not fraction and not grouped and YEAR_RANGE[0] <= int(digits) <= YEAR_RANGE[1]:
            continue
        if _ends_a_year_range(text, match.start(1), match.end(1), not percent and not fraction and not ordinal):
            continue
        value = float(digits + ("." + fraction[1:] if fraction else ""))
        decimals = len(fraction) - 1 if fraction else 0
        other = None
        if fraction and fraction[0] == "," and len(fraction) == 4 and not grouped:
            other = (float(digits + fraction[1:]), 0)  # "1,774": 1774 in English
        elif grouped and "." in whole and re.fullmatch(r"\d{1,3}\.\d{3}", whole) and not fraction:
            other = (float(whole), 3)  # "1.351": 1.351 in English
        text_seen = match.group(0)[: len(match.group(0)) - len(names_a_thing or "")].strip()
        found.append(Number(value, decimals, bool(percent), text_seen, match.start(), match.start() + len(text_seen), other))
    return found


# ---------- numbers written as words (D-032) ----------
# Only words that count something are read: followed by what they count ("five matches", "five
# straight wins"), or as either side of "a of b" ("five of his last six"). "One of the best",
# "no one", "second serve" and the Spanish and French articles "un", "una", "une" aren't.

NUMBER_WORDS = {
    "en": "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
          "seventeen eighteen nineteen twenty",
    "es": "cero _ dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis "
          "diecisiete dieciocho diecinueve veinte",
    "fr": "zéro _ deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize "
          "dix-sept dix-huit dix-neuf vingt",
}  # fmt: skip
WORD_VALUES = {lang: {w: i for i, w in enumerate(words.split()) if w != "_"} for lang, words in NUMBER_WORDS.items()}
COUNTED = {
    "en": r"matches|match|wins?|losses|loss|titles?|finals?|sets?|tiebreaks?|meetings?|aces?|double faults?|break points?"
          r"|points?|games?|tournaments?|times|seasons?|years?",
    "es": r"partidos?|victorias?|derrotas?|títulos?|finales?|sets?|desempates?|tie-?breaks?|enfrentamientos?|aces?|puntos?"
          r"|juegos?|torneos?|veces|temporadas?|años?",
    "fr": r"matchs?|victoires?|défaites?|titres?|finales?|sets?|tie-?breaks?|confrontations?|aces?|points?|jeux"
          r"|tournois|fois|saisons?|ans?|années?",
}  # fmt: skip
OF_WORDS = {"en": r"(?:out\s+)?of", "es": r"de|sobre", "fr": r"sur|des|de"}
DETERMINERS = {
    "en": r"his|her|their|the|its|all|those|these|last|first|past",
    "es": r"sus|los|las|el|la|estos|esos|últimos|ultimos|primeros",
    "fr": r"ses|les|leurs|ces|derniers|premiers",
}


def _word_patterns(language: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    words = "|".join(sorted(WORD_VALUES[language], key=len, reverse=True))
    side = r"(" + words + r"|\d+)"
    counted = re.compile(
        r"(?<![\w-])(" + words + r")(?![\w-])\s+(?:[^\W\d]+\s+)?(?:" + COUNTED[language] + r")\b", re.IGNORECASE
    )
    of_pair = re.compile(
        r"(?<![\w-])" + side + r"\s+(?:" + OF_WORDS[language] + r")\s+(?:(?:" + DETERMINERS[language] + r")\s+){0,2}" + side
        + r"(?![\w-])",
        re.IGNORECASE,
    )
    return counted, of_pair


WORD_PATTERNS = {language: _word_patterns(language) for language in LANGUAGES}


def _word_value(token: str, language: str) -> int | None:
    return int(token) if token.isdigit() else WORD_VALUES[language].get(token.lower())


def words_in(text: str, language: str = "en") -> list[Number]:
    """Number words that count something, as numbers ("five" in "won five matches")."""
    counted, of_pair = WORD_PATTERNS[language if language in WORD_PATTERNS else "en"]
    found: dict[int, Number] = {}
    for match in counted.finditer(text):
        value = _word_value(match.group(1), language)
        if value is not None:
            found[match.start(1)] = Number(float(value), 0, False, match.group(1), match.start(1), match.end(1))
    for match in of_pair.finditer(text):
        for i in (1, 2):
            token = match.group(i)
            if not token.isdigit():
                found[match.start(i)] = Number(float(_word_value(token, language)), 0, False, token, match.start(i), match.end(i))  # type: ignore[arg-type]
    return [found[start] for start in sorted(found)]


def _word_pair_spans(answer: str, pairs: Pairs, language: str) -> list[NotFound]:
    """Counts with a word on either side ("five of his last six") that no result states."""
    _, of_pair = WORD_PATTERNS[language if language in WORD_PATTERNS else "en"]
    found = []
    for match in of_pair.finditer(answer):
        a, b = match.group(1), match.group(2)
        if a.isdigit() and b.isdigit():
            continue  # read as digits, with the other counts
        if (_word_value(a, language), _word_value(b, language)) not in pairs.counts:
            found.append(NotFound(match.group(0), match.start(), match.end()))
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


def _reading_supported(value: float, decimals: int, percent: bool, pool: set[float]) -> bool:
    for true_value in pool:
        if decimals == 0 and not percent and true_value.is_integer():
            if value == true_value:  # a count written for a count: exact, so 1,263 for 1,262 is not found
                return True
        elif _close(value, decimals, true_value):
            return True
        if (percent or value > 1) and 0 <= true_value <= 1 and _close(value, decimals, 100 * true_value):
            return True
    return False


def is_supported(number: Number, pool: set[float]) -> bool:
    """Could this number have been read from the tool results? Fractions may be written as
    percentages (the system prompt allows it)."""
    readings = [(number.value, number.decimals)] + ([number.other] if number.other else [])
    return any(_reading_supported(value, decimals, number.percent, pool) for value, decimals in readings)


def invented(answer: str, pool: set[float], language: str = "en") -> list[str]:
    return [number.text for number in numbers_in(answer, language) if not is_supported(number, pool)]


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
# "8 de 10", "8 de sus 10", "8 sur 10", "8 des 10 derniers": a count in Spanish or French.
ROMANCE_OF_PAIR_RE = re.compile(
    r"(?<![\d.,])" + ROMANCE_NUM + r"\s+(?:de|sobre|sur|des)\s+"
    r"(?:(?:sus|los|las|el|la|estos|esos|ses|les|leurs|ces|últimos|ultimos|primeros|derniers|premiers)\s+){0,2}"
    + ROMANCE_NUM + r"(?![\d.,]\d)",
    re.IGNORECASE,
)
EN_MONTH = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?"
    r"|Nov(?:ember)?|Dec(?:ember)?"
)
ROMANCE_MONTH = (
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
    r"|janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre"
)
MONTH_BEFORE_RE = re.compile(r"\b(?:" + EN_MONTH + "|" + ROMANCE_MONTH + r")\.?\s*$", re.IGNORECASE)  # "May 2-23"
# After a pair, an English month only when capitalized: "3-3 may suggest" is not a date.
MONTH_AFTER_RE = re.compile(r"^\s*(?:de\s+)?(?:" + EN_MONTH + "|(?i:" + ROMANCE_MONTH + r"))\b")  # "2-23 May", "2-23 de mayo"
# A range of rally lengths ("1–3 shots", "7-9 shot rallies"), which is not a record.
SHOT_RANGE_AFTER_RE = re.compile(r"^\s*-?\s*(?:shots?|strokes?|golpes|coups)\b", re.IGNORECASE)
# One set score, as written in a result ("7-6(5)", "[10-8]") or an answer ("7–6(5)").
SET_TOKEN = r"\[?\d{1,2}" + DASH + r"\d{1,2}(?!\d)\]?(?:\(\d+\))?"
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
                # shot_patterns' charted matches are among the counted ones: "13 of his 21 were
                # charted" (D-039).
                charting = node.get("charting")
                charted = [charting["charted_matches"]] if isinstance(charting, dict) and ints(charting.get("charted_matches")) else []
                for part in [*(v for k, v in sample.items() if ints(v) and k != "matches_counted"), *left_out, *charted]:
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


@dataclass(frozen=True)
class NotFound:
    """A number, or a pair of numbers, that no tool result of the request states."""

    text: str
    start: int
    end: int


def _unsupported_pair_spans(answer: str, pairs: Pairs, language: str) -> list[NotFound]:
    text = _blank_dates(answer)
    found = []
    for run_match in SET_RUN_RE.finditer(text):
        run = _sets(run_match.group(0))
        if len(run) == 1:
            a, b = run[0]
            year_range = YEAR_RANGE[0] <= a <= YEAR_RANGE[1] and (YEAR_RANGE[0] <= b <= YEAR_RANGE[1] or b < 100)
            month_next_to = MONTH_BEFORE_RE.search(text[: run_match.start()]) or MONTH_AFTER_RE.search(text[run_match.end() :])
            if year_range or month_next_to or SHOT_RANGE_AFTER_RE.search(text[run_match.end() :]):
                continue
            if run[0] in pairs.records or _is_score_run(run, pairs.scores):
                continue
        elif _is_score_run(run, pairs.scores):
            continue
        found.append(NotFound(answer[run_match.start() : run_match.end()], run_match.start(), run_match.end()))
    for match in DASH_PAIR_RE.finditer(text):  # a record too big for a set score: "309-69", "7-128"
        a, b = match.groups()
        if max(len(a), len(b)) < 3 or (YEAR_RANGE[0] <= int(a) <= YEAR_RANGE[1] and (YEAR_RANGE[0] <= int(b) <= YEAR_RANGE[1] or len(b) <= 2)):
            continue
        if (int(a), int(b)) not in pairs.records:
            found.append(NotFound(answer[match.start() : match.end()], match.start(), match.end()))
    of_pairs = [OF_PAIR_RE] + ([ROMANCE_OF_PAIR_RE] if language != "en" else [])
    for pattern in of_pairs:
        for match in pattern.finditer(text):
            a, b = (int(re.sub(r"\D", "", group)) for group in match.groups())
            if match.group(2).isdigit() and YEAR_RANGE[0] <= b <= YEAR_RANGE[1]:
                continue  # "68 of his 2024 matches", "3 de 2024": a year, not a count
            if (a, b) not in pairs.counts:
                found.append(NotFound(answer[match.start() : match.end()], match.start(), match.end()))
    return found


def unsupported_pairs(answer: str, pairs: Pairs, language: str = "en") -> list[str]:
    """Records and counts in the answer that no tool result states. A single dash pair passes
    as a record, or as a set of a real score; several sets in a row must be part of a real
    score; "a of b" passes only as a count. Year ranges (2019-2024, 2019-24) and day ranges
    (May 2-23, 2-23 May) are skipped."""
    return [span.text for span in _unsupported_pair_spans(answer, pairs, language)]


# ---------- the check the app runs ----------


def _merged(spans: list[NotFound], text: str) -> list[NotFound]:
    """Overlapping spans as one (a count whose numbers are also not found)."""
    out: list[NotFound] = []
    for span in sorted(spans, key=lambda s: (s.start, -s.end)):
        if out and span.start < out[-1].end:
            last = out.pop()
            end = max(last.end, span.end)
            span = NotFound(text[last.start : end], last.start, end)
        out.append(span)
    return out


UNRESOLVED_CITATION = "[?]"  # what api/citations.py writes for a citation that names nothing


def _shot_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in DASH_PAIR_RE.finditer(text) if SHOT_RANGE_AFTER_RE.search(text[m.end() :])]


def check_text(text: str, pool: set[float], pairs: Pairs, language: str = "en") -> tuple[int, list[NotFound]]:
    """How many numbers the text has, and the ones not found, in order. A citation that didn't
    resolve (D-032) counts as a number, not found."""
    labels = _shot_ranges(text)  # "1–3 shots" names a rally length: its numbers aren't claims
    numbers = [n for n in numbers_in(text, language) + words_in(text, language) if not any(a <= n.start and n.end <= b for a, b in labels)]
    spans = [NotFound(n.text, n.start, n.end) for n in numbers if not is_supported(n, pool)]
    unresolved = [NotFound(m.group(0), m.start(), m.end()) for m in re.finditer(re.escape(UNRESOLVED_CITATION), text)]
    spans += unresolved + _unsupported_pair_spans(text, pairs, language) + _word_pair_spans(text, pairs, language)
    return len(numbers) + len(unresolved), _merged(spans, text)


def evidence_of(results: Iterable[Any], user_texts: Sequence[str] = (), language: str = "en") -> tuple[set[float], Pairs]:
    """What a request's text may quote: every value in its tool results, and the numbers in
    the user's own words."""
    results = [r for r in results if r is not None]
    pool = set().union(set(), *(values_in(r) for r in results))
    for said in user_texts:
        for number in numbers_in(said, language):
            pool.add(number.value)
            if number.other:
                pool.add(number.other[0])
    pairs = functools.reduce(operator.or_, (pairs_in(r) for r in results), Pairs())
    return pool, pairs


def check_answer(text: str, results: Iterable[Any], user_texts: Sequence[str] = (), language: str = "en") -> dict[str, Any]:
    """A chat answer: {"checked": how many numbers it has, "not_found": [{text, start, end}]},
    positions in characters of `text`."""
    pool, pairs = evidence_of(results, user_texts, language)
    checked, not_found = check_text(text, pool, pairs, language)
    return {"checked": checked, "not_found": [dataclasses.asdict(span) for span in not_found]}


REPORT_TEXT_FIELDS = ("strengths", "weaknesses", "game_plan", "data_caveats")


def check_report_text(report: Any, results: Iterable[Any], language: str = "en") -> dict[str, Any]:
    """A report's written text: summary, strengths, weaknesses, game plan and data caveats.
    Each number not found names its field ("summary", "game_plan.2") and its position there."""
    pool, pairs = evidence_of(results, (), language)
    texts: list[tuple[str, str]] = []
    if isinstance(report, dict):
        if isinstance(report.get("summary"), str):
            texts.append(("summary", report["summary"]))
        for name in REPORT_TEXT_FIELDS:
            items = report.get(name)
            if isinstance(items, list):
                texts += [(f"{name}.{i}", item) for i, item in enumerate(items) if isinstance(item, str)]
    checked, not_found = 0, []
    for field, text in texts:
        count, spans = check_text(text, pool, pairs, language)
        checked += count
        not_found += [{"field": field, **dataclasses.asdict(span)} for span in spans]
    return {"checked": checked, "not_found": not_found}


def checked_numbers(request_id: str, check: Any, *args: Any) -> dict[str, Any] | None:
    """Runs a check and logs what it found. The check is extra information about an answer
    that is already paid for, so if it fails, the answer stands without it (None) and the
    failure is logged; it never costs the answer."""
    try:
        result = check(*args)
    except Exception as e:  # noqa: BLE001 - logged by type, never hidden
        log_event("number_check_failed", logging.ERROR, request_id=request_id, error_type=type(e).__name__)
        return None
    log_event("number_check", request_id=request_id, checked=result["checked"], not_found=len(result["not_found"]))
    return result


def for_browser(text: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Positions in `text` as JavaScript counts them, in UTF-16 units: a character beyond the
    Basic Multilingual Plane (an emoji) is one character here and two there."""

    def utf16(index: int) -> int:
        return index + sum(1 for ch in text[:index] if ord(ch) > 0xFFFF)

    return [{**item, "start": utf16(item["start"]), "end": utf16(item["end"])} for item in items]
