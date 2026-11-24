"""How well the check on numbers in model text works (D-031), measured on saved eval answers.
Free: no model calls. The tool calls of each answer are run again on the same pinned data, as
`--rescore` does, so the check sees the results the model saw.

    uv run --env-file .env python -m evals.number_check m8-m9

Two measurements, written to evals/results/number-check-<label>.csv and -summary.csv:
- false flags: numbers in the real answers that the check marks. The eval scorer already uses
  this check, so a run that passed has none by construction; each one needs a person to say
  whether the answer or the check was wrong;
- injected errors: each number the check finds in an answer is changed, one at a time, by a
  set amount (a percentage by 0.3, 1 or 5 points; a decimal by 0.3 or 1; a whole number by 1, 2
  or 10%; one side of a record, score or "a of b" count by 1), and the check is run again. A
  change that disappears at the number's written precision isn't counted. An injected number is
  caught when a mark covers it. One that isn't caught matches some other value in the results,
  which is the check's known leniency: it measures how often that happens on real answers.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from typing import Any

from api.agent import execute_tool
from api.db import connect as connect_api
from api.numbers import SET_RUN_RE, OF_PAIR_RE, check_answer, numbers_in
from evals.run import RESULTS_DIR, data_lock

RATE_DELTAS = (0.3, 1.0, 5.0)  # percentage points
COUNT_DELTAS = (1, 2, "10%")
CORE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def formatted(original: str, value: float) -> str:
    """`value` written the way `original` writes its number: same decimals, same thousands commas."""
    core = CORE.search(original)
    assert core is not None
    digits = core.group(0)
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    text = f"{value:,.{decimals}f}" if "," in digits else f"{value:.{decimals}f}"
    return original[: core.start()] + text + original[core.end() :]


def injections(answer: str, question: str) -> list[tuple[str, str, str, str, int, int]]:
    """(kind, change, original text, new answer, start, end of the changed text in the new answer)."""
    out = []
    asked = {n.value for n in numbers_in(question)}
    for number in numbers_in(answer):
        if number.value in asked or re.search(r"(st|nd|rd|th)$", number.text):
            continue  # the user's own number, or an ordinal ("161st")
        if number.percent:
            changes = [(f"{sign}{d}pp", number.value + sign_value * d) for d in RATE_DELTAS for sign, sign_value in (("+", 1), ("-", -1))]
            kind = "percentage"
        elif number.decimals:
            changes = [(f"{sign}{d}", number.value + sign_value * d) for d in (0.3, 1.0) for sign, sign_value in (("+", 1), ("-", -1))]
            kind = "decimal"
        else:
            changes = []
            for d in COUNT_DELTAS:
                step = max(1, round(number.value * 0.1)) if d == "10%" else d
                changes += [(f"+{d}", number.value + step), (f"-{d}", number.value - step)]
            kind = "whole number"  # counts, but also days of the month, ranks and the like
        for change, value in changes:
            if value < 0 or (number.percent and value > 100):
                continue
            new = formatted(number.text, value)
            if new == number.text:
                continue  # written to its precision, the change disappears ("100%" less 0.3 points)
            text = answer[: number.start] + new + answer[number.end :]
            out.append((kind, change, number.text, text, number.start, number.start + len(new)))
    for pattern, kind in ((SET_RUN_RE, "record_or_score"), (OF_PAIR_RE, "a_of_b")):
        for match in pattern.finditer(answer):
            first = re.search(r"\d[\d,]*", match.group(0))
            assert first is not None
            value = int(first.group(0).replace(",", ""))
            new = formatted(first.group(0), value + 1)
            start = match.start() + first.start()
            text = answer[:start] + new + answer[match.start() + first.end() :]
            out.append((kind, "+1 on one side", match.group(0), text, match.start(), match.end() + len(new) - len(first.group(0))))
    return out


def caught(check: dict[str, Any], start: int, end: int) -> bool:
    return any(s["start"] < end and start < s["end"] for s in check["not_found"])


def measure(label: str) -> int:
    lock = data_lock()
    conn = connect_api()
    rows, false_flags, numbers_read = [], [], 0
    try:
        with (RESULTS_DIR / f"{label}.csv").open() as f:
            saved = list(csv.DictReader(f))
        for old in saved:
            if old.get("data_lock") != lock:
                raise SystemExit(f"{label}.csv was run on data {old.get('data_lock')!r}, not {lock}; the results would differ")
            results = [execute_tool(conn, c["tool"], c["input"]) for c in json.loads(old["tool_calls"]) if c["ok"]]
            answer, question = old["answer"], old["question"]
            check = check_answer(answer, results, [question])
            numbers_read += check["checked"]
            false_flags += [(old["id"], s["text"]) for s in check["not_found"]]
            flagged = check["not_found"]
            for kind, change, original, text, start, end in injections(answer, question):
                if any(s["start"] < end and start < s["end"] for s in flagged):
                    continue  # already flagged as written: a mark here says nothing about the change
                hit = caught(check_answer(text, results, [question]), start, end)
                rows.append({"id": old["id"], "kind": kind, "change": change, "original": original, "injected": text[start:end], "caught": hit})
    finally:
        conn.close()

    out = RESULTS_DIR / f"number-check-{label}.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "kind", "change", "original", "injected", "caught"])
        writer.writeheader()
        writer.writerows(rows)
    groups: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for row in rows:
        groups[(row["kind"], row["change"].lstrip("+-").replace(" on one side", ""))].append(row["caught"])
        groups[(row["kind"], "all")].append(row["caught"])
        if row["kind"] == "whole number":
            small = int(row["original"].replace(",", "")) <= 20  # the number as the answer wrote it
            groups[(row["kind"], "all, value 20 or less" if small else "all, value over 20")].append(row["caught"])
    summary = [
        {"kind": kind, "change": change, "injected": len(hits), "caught": sum(hits), "caught_share": round(sum(hits) / len(hits), 3)}
        for (kind, change), hits in sorted(groups.items())
    ]
    summary.append({"kind": "real answers", "change": f"{len(saved)} answers, {numbers_read} numbers",
                    "injected": 0, "caught": len(false_flags), "caught_share": ""})  # fmt: skip
    with (RESULTS_DIR / f"number-check-{label}-summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["kind", "change", "injected", "caught", "caught_share"])
        writer.writeheader()
        writer.writerows(summary)
    for line in summary:
        print(line)
    for case_id, text in false_flags:
        print(f"flagged in a real answer: {case_id}: {text}")
    return 0


if __name__ == "__main__":
    csv.field_size_limit(10**8)
    sys.exit(measure(sys.argv[1] if len(sys.argv) > 1 else "m8-m9"))
