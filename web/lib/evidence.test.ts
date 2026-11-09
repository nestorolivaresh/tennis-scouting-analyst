// Run with: npm test (node's own test runner; Node strips the TypeScript types).
// The fixture is a real /report response (Sinner v Alcaraz on clay, 2026-11-09). Expected
// values are read from its tool results, never typed in (spec: no hardcoded statistics).

import assert from "node:assert/strict";
import { test } from "node:test";
import report from "./fixtures/report-clay.json" with { type: "json" };
import {
  describeExcluded, describeFilters, findEvidence, formatStat, rateFor, resolvePath, sampleLine, serveChart, surfaceChart,
} from "./evidence.ts";
import { SseParser } from "./sse.ts";
import type { Evidence, KeyStat, ReportResponse } from "./types.ts";

const r = report as unknown as ReportResponse;
const { player, opponent } = r.request;

test("every key stat points at a tool call whose result holds its value", () => {
  for (const stat of r.report!.key_stats) {
    const evidence = findEvidence(r.evidence, stat.tool_call_id);
    assert.ok(evidence, stat.tool_call_id);
    const { found, value } = resolvePath(evidence.result, stat.field);
    assert.ok(found, stat.field);
    assert.equal(value, stat.value);
  }
});

test("a rate's evidence carries its counts, and it is shown as a percentage", () => {
  const stat = r.report!.key_stats.find((s) => s.field.endsWith(".value"))!;
  const rate = rateFor(stat, findEvidence(r.evidence, stat.tool_call_id))!;
  assert.equal(rate.unit, "fraction");
  assert.ok(rate.value !== null && Math.abs(rate.value - rate.numerator / rate.denominator) < 5e-5); // 4 places
  assert.match(formatStat(stat, rate), /^\d{1,3}\.\d%$/);
  const count: KeyStat = { ...stat, field: "record.wins", value: 7 };
  assert.equal(formatStat(count, null), "7");
});

test("paths that don't exist are reported, not guessed", () => {
  const evidence = r.evidence[0];
  assert.equal(resolvePath(evidence.result, "surfaces.9.win_rate.value").found, false);
  assert.equal(resolvePath(evidence.result, "nothing.here").found, false);
});

test("filters, exclusions and samples in words", () => {
  assert.deepEqual(describeFilters({ surface: "Clay", date_from: "2024-10-26", date_to: "2026-10-26", season: null }), [
    "Clay courts", "Tournaments starting 2024-10-26 to 2026-10-26",
  ]);
  assert.deepEqual(describeFilters({ season: 2024, tourney_level: ["G", "M"], opponent_hand: "L" }), [
    "2024 season", "Grand Slams, Masters 1000", "Left-handed opponents",
  ]);
  assert.deepEqual(describeExcluded({ walkovers: 2, exhibitions: 1, unknown_results: 0 }), ["2 walkovers", "1 exhibition"]);
  assert.match(sampleLine({ matches_counted: 70, matches_with_stats: 68, opponent_retired_or_defaulted: 0,
    player_retired_or_defaulted: 0, first_tourney_date: "2022-01-03", last_tourney_date: "2022-11-14" })!, /^70 matches \(68 with stats\)/);
});

test("serve chart: both players' rates, from the calls filtered to the report's surface", () => {
  const chart = serveChart(r.evidence, player, opponent, "Clay");
  assert.deepEqual(chart.missing, []);
  const serveCall = r.evidence.find((e) => e.tool === "serve_return_stats" && e.input.player_id === player.player_id)!;
  const firstIn = (serveCall.result!.stats as Record<string, { value: number }>).first_serve_in.value;
  assert.equal(chart.rows[0].metric, "First serve in");
  assert.equal(chart.rows[0].player, Math.round(1000 * firstIn) / 10);
  assert.ok(chart.rows.every((row) => row.player !== null && row.opponent !== null));
  assert.equal(chart.sources.length, 4); // serve and pressure calls for each player
});

test("surface chart says which surfaces it has when the calls were filtered to one", () => {
  const chart = surfaceChart(r.evidence, player, opponent);
  const clay = chart.rows.find((row) => row.surface === "Clay")!;
  assert.ok(clay.player !== null && clay.opponent !== null);
  assert.equal(chart.rows.find((row) => row.surface === "Hard")!.player, null); // not in this run's results: null, never 0
});

test("a chart with no evidence lists what is missing", () => {
  const none: Evidence[] = [];
  assert.deepEqual(surfaceChart(none, player, opponent).missing, [
    `${player.name}'s win-loss by surface`, `${opponent.name}'s win-loss by surface`,
  ]);
  assert.equal(serveChart(none, player, opponent, "Clay").missing.length, 4);
});

test("failed tool calls are never used", () => {
  const failed = r.evidence.map((e) => ({ ...e, error: "internal error in this tool", result: null }));
  assert.equal(serveChart(failed, player, opponent, "Clay").missing.length, 4);
});

test("the stream parser handles events split across chunks", () => {
  const parser = new SseParser();
  const text = 'event: start\ndata: {"request_id": "abc"}\n\nevent: text\ndata: {"delta": "Hi"}\n\n';
  const events = [...text].flatMap((char) => parser.feed(char)); // one character at a time
  assert.deepEqual(events, [
    { event: "start", data: { request_id: "abc" } },
    { event: "text", data: { delta: "Hi" } },
  ]);
  assert.equal(parser.incomplete, false);
  parser.feed('event: text\ndata: {"del');
  assert.equal(parser.incomplete, true);
});

test("report progress: each real step, newest one in progress, failures marked", async () => {
  const { progressSteps } = await import("./progress.ts");
  const names = new Map([[player.player_id, player.name], [opponent.player_id, opponent.name]]);
  const events = [
    { event: "start", data: { request_id: "r", request: r.request } },
    { event: "model_call", data: { call: 1, tool_calls_so_far: 0 } },
    { event: "tool_call", data: { id: "c1", tool: "surface_splits", input: { player_id: player.player_id, filters: {} } } },
    { event: "tool_result", data: { id: "c1", tool: "surface_splits", ok: true, error: null } },
    { event: "tool_call", data: { id: "c2", tool: "head_to_head", input: { player_id: player.player_id, opponent_id: opponent.player_id } } },
  ] as const;
  const running = progressSteps([...events] as never, names);
  assert.deepEqual(running.map((s) => [s.text, s.state]), [
    ["Choosing which stats to look up", "done"],
    [`Win-loss by surface: ${player.name}, every surface`, "done"],
    [`Head-to-head: ${player.name} and ${opponent.name}`, "active"],
  ]);
  const later = progressSteps([
    ...events,
    { event: "tool_result", data: { id: "c2", tool: "head_to_head", ok: false, error: "internal error in this tool" } },
    { event: "model_call", data: { call: 2, tool_calls_so_far: 2 } },
    { event: "checking", data: { attempt: 1, key_stats: 6 } },
    { event: "correcting", data: { errors: 1 } },
    { event: "model_call", data: { call: 3, tool_calls_so_far: 2 } },
  ] as never, names);
  assert.deepEqual(later.slice(2).map((s) => [s.text, s.state]), [
    [`Head-to-head: ${player.name} and ${opponent.name} (failed)`, "failed"],
    ["Writing the report", "done"],
    ["Checking 6 key numbers against the data", "done"],
    ["1 number didn't match; asking for a corrected report", "done"],
    ["Rewriting the report with the corrections", "active"],
  ]);
});
