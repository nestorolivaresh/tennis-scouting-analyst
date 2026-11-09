"""Run the evals: ask each question through the chat agent, score the answer against ground
truth from evals/truth.py, and write the results to evals/results/<label>.csv (spec, Evals).

    uv run --env-file .env python -m evals.run --dry-run            # ground truth only, free
    uv run --env-file .env python -m evals.run --label final         # every question (costs money)
    uv run --env-file .env python -m evals.run --label rerun --only S01,F05
    uv run --env-file .env python -m evals.run --rescore baseline    # score old answers again, free

Each question is asked on its own, the way /chat receives a first question, with the same
system prompt. Each answer is written to the CSV as soon as it's scored, so a crash keeps
what was paid for. The run stops before the next question once its cost passes --max-cost;
it refuses to start for a model with no price, and counts a call cut off before its usage
arrived at its maximum possible cost, so the cap never fails open.
"""

from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import operator
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import anthropic

from api.agent import Limits, Run, Settings, run_loop
from api.chat import chat_system_prompt
from api.db import connect as connect_api
from evals import score
from evals.cases import CASES, COUNTS, NAMES, Case, Expect
from evals.truth import Totals, connect as connect_truth, totals

RESULTS_DIR = Path(__file__).parent / "results"
DATA_LOCK = Path(__file__).parent.parent / "ingest" / "data.lock.json"
CATEGORIES = ("single_stat", "filtered_stat", "head_to_head", "comparison", "refuse_or_caveat")
FIELDS = [
    "label", "id", "category", "passed", "outcome", "numbers_ok", "tools_ok", "invented_ok", "refusal_ok", "claims_ok",
    "missing_numbers", "missing_tools", "invented_numbers", "failed_claims", "expected", "tool_calls", "model",
    "effort", "model_calls", "tokens", "cost_usd", "latency_s", "data_lock", "question", "answer",
]  # fmt: skip


def data_lock() -> str:
    """Which pinned data snapshot a run used (D-002), so a rescore can refuse another one."""
    return hashlib.sha256(DATA_LOCK.read_bytes()).hexdigest()[:12]


def kind(expect: Expect) -> str:
    if expect.stat in COUNTS:
        return "count"
    return "average" if expect.stat == "aces_per_match" else "rate"


def expected_values(conn, case: Case) -> list[dict[str, Any]]:
    """Each expected number, computed from the raw tables."""
    values = []
    for expect in case.expects:
        t: Totals = totals(conn, expect.player, expect.filters, expect.opponent)
        value = getattr(t, expect.stat) if expect.stat in COUNTS else t.stat(expect.stat)
        if value is None:
            raise ValueError(f"{case.id}: {expect.stat} has no value (no matches?); fix the case")
        values.append({"stat": expect.stat, "player": expect.player, "opponent": expect.opponent,
                       "value": value, "kind": kind(expect), "matches": t.matches,
                       "matches_with_stats": t.matches_with_stats})  # fmt: skip
    return values


def generated_claims(case: Case, expected: list[dict]) -> tuple[list[str], list[str]]:
    """Checks on claims in words, built from the ground truth: a head-to-head answer must not
    name the wrong leader or call an uneven record "split evenly"; a comparison answer must
    name the better player in its first sentence."""
    must: list[str] = []
    must_not: list[str] = []
    if case.category == "head_to_head" and len(expected) == 2:
        wins, losses = expected[0]["value"], expected[1]["value"]
        player, opponent = NAMES[expected[0]["player"]], NAMES[expected[0]["opponent"]]
        if wins != losses:
            leader, trailer = (player, opponent) if wins > losses else (opponent, player)
            must_not += [*score.wrong_leader(leader, trailer), score.SPLIT_EVEN]
            if case.asks_who_leads:
                must.append(score.right_leader(leader, trailer))
    if case.category == "comparison" and len(expected) == 2:
        first, second = expected
        winner, loser = (first, second) if first["value"] > second["value"] else (second, first)
        better, worse = score.better_first(NAMES[winner["player"]], NAMES[loser["player"]])
        must.append(better)
        must_not.append(worse)
    return must, must_not


def score_case(case: Case, expected: list[dict], answer: str, calls: list[dict], outcome: str) -> dict[str, Any]:
    pool = set().union(*(score.values_in(call["result"]) for call in calls)) | {n.value for n in score.numbers_in(case.question)}
    missing_numbers = [e for e in expected if not score.contains_expected(answer, e["value"], e["kind"])]
    missing_tools = [
        check.tool for check in case.tools
        if not any(score.call_matches(call, check.tool, check.player, check.opponent, check.filters) for call in calls)
    ]  # fmt: skip
    results_pairs = functools.reduce(operator.or_, (score.pairs_in(call["result"]) for call in calls), score.Pairs())
    invented = score.invented(answer, pool) + score.unsupported_pairs(answer, results_pairs)

    must, must_not = generated_claims(case, expected)
    if case.claims:
        must, must_not = [*must, *case.claims.must], [*must_not, *case.claims.must_not]
    failed_claims = [f"missing: {p}" for p in must if not score.matches_all((p,), answer)]
    failed_claims += [f"said: {p}" for p in must_not if score.matches_any((p,), answer)]
    claims_ok = not failed_claims if (must or must_not) else None

    refusal_ok = None
    if case.refusal:
        used = {call["tool"] for call in calls}
        refusal_ok = (
            score.matches_all(case.refusal.must, answer)
            and not score.matches_any(case.refusal.must_not, answer)
            and not used & set(case.refusal.forbid_tools)
        )
    passed = (
        outcome == "completed" and not missing_numbers and not missing_tools and not invented
        and refusal_ok is not False and claims_ok is not False
    )  # fmt: skip
    return {
        "passed": passed,
        "numbers_ok": not missing_numbers if expected else None,
        "tools_ok": not missing_tools if case.tools else None,
        "invented_ok": not invented,
        "refusal_ok": refusal_ok,
        "claims_ok": claims_ok,
        "missing_numbers": [f"{e['stat']} {e['player']}: {e['value']:.4g}" for e in missing_numbers],
        "missing_tools": missing_tools,
        "invented_numbers": invented,
        "failed_claims": failed_claims,
    }


def ask(client, conn, settings: Settings, question: str) -> tuple[Run, float]:
    """One question, one run. Any failure becomes the run's outcome, so it is recorded and
    the remaining questions still run; Ctrl-C stops the whole run."""
    run = Run(model=settings.model, messages=[{"role": "user", "content": question}], started=time.monotonic())
    started = time.monotonic()
    try:
        for _ in run_loop(client, conn, settings, run, chat_system_prompt(conn), Limits()):
            pass
    except anthropic.APIError as error:
        run.outcome = f"api_error: {type(error).__name__}"
    except Exception as error:  # noqa: BLE001 - recorded, never hidden
        run.outcome = f"error: {type(error).__name__}"
    return run, time.monotonic() - started


def worst_case_call_cost(model: str) -> float:
    """The most one model call can cost: its whole output allowance at the output price."""
    run = Run(model=model, messages=[])
    run.tokens["output_tokens"] = Limits().max_output_tokens
    return run.cost_usd


def charged(run: Run, model: str) -> float:
    """What a run cost, counting a call cut off before its usage arrived at its maximum."""
    return (run.cost_usd or 0) + (0 if run.usage_complete else worst_case_call_cost(model))


def summarize(rows: list[dict]) -> list[dict]:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    summary = []
    for category in (*CATEGORIES, "all"):
        group = rows if category == "all" else by_category.get(category, [])
        if not group:
            continue

        def rate(key):
            scored = [row[key] for row in group if row[key] is not None]
            return f"{sum(scored)}/{len(scored)}" if scored else ""

        costs = [row["cost_usd"] for row in group]
        summary.append({
            "category": category, "questions": len(group), "passed": rate("passed"), "numbers_ok": rate("numbers_ok"),
            "tools_ok": rate("tools_ok"), "invented_ok": rate("invented_ok"), "refusal_ok": rate("refusal_ok"),
            "claims_ok": rate("claims_ok"),
            "cost_usd": round(sum(costs), 4) if all(c is not None for c in costs) else "unknown",
            "mean_latency_s": round(sum(row["latency_s"] for row in group) / len(group), 1),
            "tokens": sum(row["tokens"] for row in group),
        })  # fmt: skip
    return summary


def csv_row(row: dict) -> dict:
    return {key: json.dumps(value) if isinstance(value, (list, dict)) else value for key, value in row.items()}


def write_summary(label: str, rows: list[dict]) -> None:
    if not rows:
        print("no questions were run", file=sys.stderr)
        return
    summary = summarize(rows)
    with (RESULTS_DIR / f"{label}-summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    for line in summary:
        print(line)


class ResultsFile:
    """The results CSV, written one row at a time."""

    def __init__(self, label: str):
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        self.file = (RESULTS_DIR / f"{label}.csv").open("w", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=FIELDS)
        self.writer.writeheader()

    def write(self, row: dict) -> None:
        self.writer.writerow(csv_row(row))
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def rescore(label: str, cases: tuple[Case, ...], expected: dict[str, list[dict]]) -> int:
    """Score a past run's answers again with the current scorer and ground truth. Calls that
    succeeded are rerun on the same pinned data, so their results are the ones the model saw;
    calls that failed stay failed. The answers, outcomes and costs are kept as recorded."""
    from api.agent import execute_tool

    by_id = {case.id: case for case in cases}
    lock = data_lock()
    conn, rows = connect_api(), []
    out = ResultsFile(f"{label}-rescored")
    try:
        with (RESULTS_DIR / f"{label}.csv").open() as f:
            for old in csv.DictReader(f):
                case = by_id.get(old["id"])
                if case is None:
                    continue
                if old.get("data_lock") and old["data_lock"] != lock:
                    raise SystemExit(f"{label}.csv was run on data {old['data_lock']}, not {lock}; rescoring would mislead")
                calls = []
                for call in json.loads(old["tool_calls"]):
                    if not call["ok"]:
                        calls.append({**call, "result": None, "error": call.get("error") or "failed in the original run"})
                        continue
                    try:
                        result = execute_tool(conn, call["tool"], call["input"])
                    except Exception as e:
                        raise SystemExit(f"{old['id']}: a call that succeeded in {label} now fails ({e}); data changed?")
                    calls.append({**call, "result": result, "error": None})
                result = score_case(case, expected[case.id], old["answer"], calls, old["outcome"])
                row = {**{key: old.get(key, "") for key in FIELDS}, **result, "label": f"{label}-rescored",
                       "tool_calls": json.loads(old["tool_calls"]), "expected": public(expected[case.id]),
                       "cost_usd": float(old["cost_usd"]) if old["cost_usd"] else None,
                       "latency_s": float(old["latency_s"]), "tokens": int(old["tokens"]), "data_lock": lock}  # fmt: skip
                out.write(row)
                rows.append(row)
    finally:
        out.close()
        conn.close()
    write_summary(f"{label}-rescored", rows)
    return 0


def public(expected: list[dict]) -> list[dict]:
    return [{k: e[k] for k in ("stat", "player", "opponent", "value", "matches")} for e in expected]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--label", help="results go to evals/results/<label>.csv")
    parser.add_argument("--only", help="comma-separated case IDs, e.g. S01,F05")
    parser.add_argument("--max-cost", type=float, default=2.0, help="stop once the run has cost this much (USD)")
    parser.add_argument("--dry-run", action="store_true", help="compute ground truth only; no model calls")
    parser.add_argument("--rescore", metavar="LABEL", help="score evals/results/LABEL.csv again with the current "
                        "scorer, rerunning its successful tool calls on the pinned data; no model calls")  # fmt: skip
    args = parser.parse_args(argv)

    cases = CASES
    if args.only:
        wanted = set(args.only.split(","))
        cases = tuple(case for case in CASES if case.id in wanted)
        if unknown := wanted - {case.id for case in cases}:
            parser.error(f"unknown case IDs: {sorted(unknown)}")
    if not (args.dry_run or args.rescore) and not args.label:
        parser.error("--label is required unless --dry-run or --rescore")

    truth_conn = connect_truth()
    expected = {case.id: expected_values(truth_conn, case) for case in cases}
    truth_conn.close()
    if args.rescore:
        return rescore(args.rescore, cases, expected)
    if args.dry_run:
        for case in cases:
            shown = ", ".join(f"{e['stat']}={e['value']:.4g} (n={e['matches']})" for e in expected[case.id]) or "no numbers"
            print(f"{case.id} {case.category:17} {shown}")
        return 0

    settings = Settings.from_env()
    if Run(model=settings.model, messages=[]).cost_usd is None:
        parser.error(f"no price for {settings.model} in api/agent.py PRICES_PER_MTOK, so --max-cost can't work; add it first")
    client, conn = settings.client(), connect_api()
    rows, spent, lock = [], 0.0, data_lock()
    out = ResultsFile(args.label)
    try:
        for case in cases:
            if spent >= args.max_cost:
                print(f"stopping: spent ${spent:.2f}, over --max-cost ${args.max_cost:.2f}", file=sys.stderr)
                break
            run, latency = ask(client, conn, settings, case.question)
            spent += charged(run, settings.model)
            calls = [
                {"tool": call.name, "input": call.input, "result": call.result, "error": call.error}
                for call in run.tool_calls.values()
            ]
            result = score_case(case, expected[case.id], run.final_text, calls, run.outcome or "")
            row = {
                "label": args.label, "id": case.id, "category": case.category, "outcome": run.outcome, **result,
                "expected": public(expected[case.id]),
                "tool_calls": [{"tool": c["tool"], "input": c["input"], "ok": c["error"] is None, "error": c["error"]}
                               for c in calls],
                "model": settings.model, "effort": settings.effort, "model_calls": run.model_calls,
                "tokens": run.total_tokens, "cost_usd": run.cost_usd, "latency_s": round(latency, 1),
                "data_lock": lock, "question": case.question, "answer": run.final_text,
            }  # fmt: skip
            out.write(row)
            rows.append(row)
            mark = "pass" if result["passed"] else "FAIL"
            print(f"{case.id} {mark}  ${run.cost_usd or 0:.3f}  {latency:4.1f}s  {run.outcome}", flush=True)
    except KeyboardInterrupt:
        print(f"interrupted after {len(rows)} questions; their results are saved", file=sys.stderr)
    finally:
        out.close()
        conn.close()
    write_summary(args.label, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
