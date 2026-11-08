"""Grounding check: every key stat in a report must match a value from a tool result in the
same run (spec, Grounding check; docs/decisions.md D-018).

A key stat names where its number came from: the tool call's ID and a dotted path into that
call's result, such as "stats.break_points_saved.value" or "surfaces.0.win_rate.value". The
check looks the path up and compares. It also checks the stated sample size against the
match counts that result reported. Narrative text isn't checked here; the evals do that.
"""

from __future__ import annotations

from typing import Any

from api.agent import ToolCall

TOLERANCE = 1e-9  # values are copied, not recomputed, so they must match exactly


def resolve_path(result: Any, path: str) -> tuple[bool, Any, list[Any]]:
    """Follow a dotted path through dicts and lists. Returns (found, value, objects passed on
    the way, including the root), so the caller can look for match counts along the path."""
    node, seen = result, [result]
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return False, None, seen
        seen.append(node)
    return True, node, seen


def sample_sizes(result: dict[str, Any], seen: list[Any]) -> set[int]:
    """Match counts a stat from this result may cite: the sample's counts, and the `matches`
    count of any object on the stat's path (one surface's row, the overall record)."""
    sample = result.get("sample") or {}
    counts = [sample.get("matches_counted"), sample.get("matches_with_stats")]
    counts += [node.get("matches") for node in seen if isinstance(node, dict)]  # head_to_head's is a list
    return {count for count in counts if isinstance(count, int) and not isinstance(count, bool)}


def check_report(report: Any, tool_calls: dict[str, ToolCall]) -> list[str]:
    """Return one error per problem; an empty list means every key stat is grounded."""
    if not isinstance(report, dict) or not isinstance(report.get("key_stats"), list):
        return ["the report has no key_stats list"]
    errors = []
    for i, stat in enumerate(report["key_stats"]):
        where = f"key_stats[{i}] ({stat.get('label', 'no label')!r})" if isinstance(stat, dict) else f"key_stats[{i}]"
        if not isinstance(stat, dict):
            errors.append(f"{where} is not an object")
            continue
        call = tool_calls.get(stat.get("tool_call_id"))
        if call is None:
            errors.append(f"{where}: tool_call_id {stat.get('tool_call_id')!r} is not a tool call from this run")
            continue
        if call.error is not None or not isinstance(call.result, dict):
            errors.append(f"{where}: tool call {call.id} failed, so it has no values")
            continue
        found, value, seen = resolve_path(call.result, str(stat.get("field", "")))
        if not found:
            errors.append(f"{where}: field {stat.get('field')!r} does not exist in the {call.name} result")
            continue
        if not _is_number(value):
            errors.append(f"{where}: field {stat.get('field')!r} is {value!r}, not a number")
            continue
        if not _is_number(stat.get("value")) or abs(stat["value"] - value) > TOLERANCE:
            errors.append(f"{where}: value {stat.get('value')!r} does not match {value!r} at {stat['field']}")
        sizes = sample_sizes(call.result, seen)
        if stat.get("sample_matches") not in sizes:
            errors.append(
                f"{where}: sample_matches {stat.get('sample_matches')!r} is not a match count from that result "
                f"({sorted(sizes)})"
            )
    return errors


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
