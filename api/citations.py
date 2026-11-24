"""Citations in model text: the model writes `[[c2:stats.first_serve_in.value]]` where a
number from a tool result goes, and the app writes the value (D-032).

A citation names a tool call by the short ID written at the top of its result and a field by
the dotted path key stats use (D-018). It's replaced with the field's value, formatted the
way the page shows numbers (web/lib/evidence.ts, formatValue): a fraction as a percentage with
one decimal, a per-match average with one decimal, a count as a whole number, text as written.
A citation that doesn't resolve becomes "[?]" and is reported, so it's never silently dropped.
"""

from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from api.grounding import resolve_path

CITATION_RE = re.compile(r"\[\[\s*(c\d+)\s*:\s*([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\s*\]\]")
MAX_CITATION = 120  # characters from "[[" to "]]"; anything longer isn't a citation
UNRESOLVED = "[?]"
NBSP, NNBSP = " ", " "


@dataclass(frozen=True)
class Citation:
    """Where a citation was written into the rendered text, and what it cites. `ok` is False
    for one that didn't resolve, shown as "[?]"."""

    tool_call_id: str
    field: str
    text: str
    start: int
    end: int
    ok: bool
    numeric: bool = True  # False for text written in (a score, a name): only numbers open a source card


def _group(digits: str, separator: str) -> str:
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", separator, digits)


def format_int(n: int, language: str) -> str:
    """As the page writes counts (toLocaleString): 1,262 / 1262 and 12.345 / 1 262."""
    sign, digits = ("-" if n < 0 else ""), str(abs(n))
    if language == "es":
        return sign + (_group(digits, ".") if len(digits) >= 5 else digits)
    if language == "fr":
        return sign + _group(digits, NNBSP)
    return sign + _group(digits, ",")


def _decimal(text: str, language: str) -> str:
    return text.replace(".", ",") if language in ("es", "fr") else text


def _round1(x: float) -> float:
    """As the page's round1: Math.round(x * 10) / 10, halves rounded up."""
    y = x * 10
    whole = math.floor(y)
    return (whole + 1 if y - whole >= 0.5 else whole) / 10


def _to_fixed1(x: float) -> str:
    """As JavaScript's toFixed(1): the exact binary value, halves rounded up (4.25 is "4.3";
    Python's own format would give "4.2")."""
    return str(Decimal(x).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def format_value(value: Any, unit: str | None, rate: Mapping[str, Any] | None, language: str) -> str | None:
    """The value as the page shows it, or None when it can't be shown in text."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    if unit == "fraction":
        den = rate.get("denominator") if rate else None
        num = rate.get("numerator") if rate else None
        exact = isinstance(num, int) and isinstance(den, int) and den > 0 and rate is not None and rate.get("value") == value
        pct = _round1(100 * num / den) if exact else _round1(100 * value)  # type: ignore[operator]
        return _decimal(f"{pct:.1f}", language) + ("%" if language == "en" else NBSP + "%")
    if unit == "per_match":
        den = rate.get("denominator") if rate else None
        num = rate.get("numerator") if rate else None
        exact = isinstance(num, int) and isinstance(den, int) and den > 0 and rate is not None and rate.get("value") == value
        return _decimal(_to_fixed1(num / den if exact else value), language)  # type: ignore[operator]
    if isinstance(value, int) or float(value).is_integer():
        return format_int(int(value), language)
    return _decimal(f"{value}", language)


def _unit_of(seen: list[Any], key: str) -> tuple[str | None, Mapping[str, Any] | None]:
    """The unit of the value at the end of a path: its own rate's, or, for a decimal figure
    beside a rate (tour_comparison's tour_median beside value), that rate's. A whole number
    beside it (the rank, players_ranked) is a count, and so is any count kept inside a rate
    (numerator, denominator, set_patterns' matches)."""
    parent = seen[-2] if len(seen) >= 2 else None
    if isinstance(parent, Mapping):
        if "unit" in parent:
            return (parent.get("unit"), parent) if key == "value" else (None, None)
        sibling = parent.get("value")
        if isinstance(sibling, Mapping) and "unit" in sibling and isinstance(seen[-1], float):
            return sibling.get("unit"), None
    return None, None


def _is_rate(node: Any) -> bool:
    return isinstance(node, Mapping) and "unit" in node and "value" in node


def resolve_field(results: Mapping[str, Any], tool_call_id: str, field: str, language: str) -> tuple[str | None, str, bool]:
    """The text a citation stands for (None when it doesn't resolve), and the field it names.
    In tour_comparison a stat's line holds its figure as a rate (`stats.service_points_won.value`
    is a rate), so the line and the rate stand for each other: a citation of a rate means its
    value, and one of a rate's key on the line ("stats.service_points_won.numerator") means that
    key of the line's rate. The field returned is written out in full, as the page resolves it."""
    result = results.get(tool_call_id)
    if not isinstance(result, Mapping):
        return None, field, False
    found, value, seen = resolve_path(result, field)
    if not found and "." in field:
        line, key = field.rsplit(".", 1)
        line_found, node, _ = resolve_path(result, line)
        if line_found and isinstance(node, Mapping) and _is_rate(node.get("value")) and key in node["value"] and key not in node:
            field = f"{line}.value.{key}"
            found, value, seen = resolve_path(result, field)
    if found and _is_rate(value):
        field = f"{field}.value"
        found, value, seen = resolve_path(result, field)
    if not found:
        return None, field, False
    unit, rate = _unit_of(seen, field.split(".")[-1])
    return format_value(value, unit, rate, language), field, not isinstance(value, str)


def resolve(results: Mapping[str, Any], tool_call_id: str, field: str, language: str) -> str | None:
    """The text a citation stands for, or None when it doesn't resolve."""
    return resolve_field(results, tool_call_id, field, language)[0]


def _replace(match_text: str, results: Mapping[str, Any], language: str) -> tuple[str, str, str, bool, bool]:
    match = CITATION_RE.fullmatch(match_text)
    if match is None:
        return UNRESOLVED, "", match_text.strip("[]").strip(), False, False
    call_id, field = match.group(1), match.group(2)
    text, field, numeric = resolve_field(results, call_id, field, language)
    return (text, call_id, field, True, numeric) if text is not None else (UNRESOLVED, call_id, field, False, False)


class Renderer:
    """Renders citations in text that arrives in pieces. `feed` returns what can be shown now;
    a citation split across pieces is held back until it closes (or proves not to be one).
    `results` is read when a citation closes, so it sees the tool calls made so far."""

    def __init__(self, results: Callable[[], Mapping[str, Any]], language: str = "en"):
        self.results, self.language = results, language
        self.pending, self.shown = "", 0
        self.citations: list[Citation] = []

    def _emit_citation(self, raw: str) -> str:
        text, call_id, field, ok, numeric = _replace(raw, self.results(), self.language)
        self.citations.append(Citation(call_id, field, text, self.shown, self.shown + len(text), ok, numeric))
        self.shown += len(text)
        return text

    def _emit(self, text: str) -> str:
        self.shown += len(text)
        return text

    def feed(self, piece: str) -> str:
        self.pending += piece
        out = []
        while self.pending:
            open_at = self.pending.find("[[")
            if open_at < 0:
                keep = 1 if self.pending.endswith("[") else 0  # may be the first half of "[["
                out.append(self._emit(self.pending[: len(self.pending) - keep]))
                self.pending = self.pending[len(self.pending) - keep :]
                break
            out.append(self._emit(self.pending[:open_at]))
            self.pending = self.pending[open_at:]
            close_at = self.pending.find("]]", 2)
            nested = self.pending.find("[[", 1)
            if nested >= 0 and (close_at < 0 or nested < close_at):
                # Another "[[" before this one closes: this one is broken ("[[c1:x] and [[c1:y]]").
                # It ends at its first "]", shown as "[?]"; without one, it's plain text ("[[[c1:x]]]").
                broken = self.pending[:nested]
                bracket = broken.find("]")
                if bracket >= 0:
                    out.append(self._emit_citation(broken[: bracket + 1]))
                    out.append(self._emit(broken[bracket + 1 :]))
                else:
                    out.append(self._emit(broken))
                self.pending = self.pending[nested:]
                continue
            if close_at >= 0 and close_at + 2 <= MAX_CITATION:
                out.append(self._emit_citation(self.pending[: close_at + 2]))
                self.pending = self.pending[close_at + 2 :]
            elif close_at >= 0 or len(self.pending) > MAX_CITATION:
                out.append(self._emit("[["))  # too long to be a citation: plain text
                self.pending = self.pending[2:]
            else:
                break  # wait for the rest
        return "".join(out)

    def flush(self) -> str:
        """The end of the text: anything held back is plain text."""
        rest, self.pending = self.pending, ""
        return self._emit(rest)


def render(text: str, results: Mapping[str, Any], language: str = "en") -> tuple[str, list[Citation]]:
    """A whole text at once, as the streaming renderer would give it."""
    renderer = Renderer(lambda: results, language)
    rendered = renderer.feed(text) + renderer.flush()
    return rendered, renderer.citations


def results_by_id(tool_calls: Mapping[str, Any]) -> dict[str, Any]:
    """A run's tool results by short ID (`c1`); a failed call has none."""
    return {call_id: call.result for call_id, call in tool_calls.items() if call.error is None and call.result is not None}
