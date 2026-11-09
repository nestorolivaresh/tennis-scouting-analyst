// Run with: npm test (Node's own test runner; Node strips the TypeScript types).
// Fixtures are real /report responses (Sinner v Alcaraz on clay, 2026-11-09): `current` from
// the current prompt (win-loss over every surface), `clay` from before it (one surface).
// Expected values are read from their tool results, never typed in (spec: no hardcoded stats).

import assert from "node:assert/strict";
import { test } from "node:test";
import clayReport from "./fixtures/report-clay.json" with { type: "json" };
import currentReport from "./fixtures/report-current.json" with { type: "json" };
import {
  checkStat, describeExcluded, describeFilters, describeStat, formatValue, resolvePath, round1, sampleLine, serveChart, surfaceChart,
} from "./evidence.ts";
import type { Evidence, KeyStat, Rate, ReportResponse } from "./types.ts";

const current = currentReport as unknown as ReportResponse;
const clay = clayReport as unknown as ReportResponse;
const { player, opponent } = current.request;
const window = { date_from: current.request.date_from, date_to: current.request.date_to };

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));

test("a verified report's key numbers all match their tool results, and show the tool's value", () => {
  for (const stat of current.report!.key_stats) {
    const check = checkStat(stat, current.evidence);
    assert.equal(check.status, "matched", stat.field);
    assert.equal(check.value, resolvePath(check.evidence!.result, stat.field).value);
    assert.equal(check.sample, stat.sample_matches);
  }
});

test("an unverified number shows the tool's value, not the model's, and is marked", () => {
  const stat = current.report!.key_stats.find((s) => s.field.endsWith(".value"))!;
  const wrong: KeyStat = { ...stat, value: stat.value + 0.03 };
  const check = checkStat(wrong, current.evidence);
  assert.equal(check.status, "mismatch");
  assert.equal(check.value, stat.value); // the data's value
  const missing = checkStat({ ...stat, tool_call_id: "c42" }, current.evidence);
  assert.deepEqual([missing.status, missing.value, missing.sample], ["missing", null, null]);
  const wrongSample = checkStat({ ...stat, sample_matches: 99_999 }, current.evidence);
  assert.equal(wrongSample.status, "mismatch");
  assert.notEqual(wrongSample.sample, 99_999); // the sample shown is the tool's
});

test("a failed tool call or an inherited property never resolves", () => {
  const stat = current.report!.key_stats[0];
  const failed = current.evidence.map((e) => ({ ...e, error: "internal error in this tool", result: null }));
  assert.equal(checkStat(stat, failed).status, "missing");
  assert.equal(resolvePath({ record: { wins: 1 } }, "record.constructor").found, false);
});

test("key numbers are described from the tool result, not the model's label", () => {
  for (const stat of current.report!.key_stats) {
    const source = current.evidence.find((e) => e.tool_call_id === stat.tool_call_id)!;
    const { title, filters } = describeStat(stat, source);
    assert.ok(title.startsWith(source.result!.player!.name), title);
    assert.deepEqual(filters, describeFilters(source.result!.filters as Record<string, unknown>));
  }
  const h2h = current.evidence.find((e) => e.tool === "head_to_head")!;
  assert.match(describeStat({ label: "", value: 1, tool_call_id: h2h.tool_call_id, field: "record.wins", sample_matches: 1 }, h2h).title,
    new RegExp(`^${player.name} against ${opponent.name}: head-to-head wins$`));
});

test("values are formatted by their unit", () => {
  const rate: Rate = { value: 0.65678, numerator: 111, denominator: 169, unit: "fraction" };
  assert.equal(formatValue(rate.value!, rate), `${round1(100 * rate.value!).toFixed(1)}%`);
  assert.equal(formatValue(2.3043, { ...rate, unit: "per_match" }), "2.3");
  assert.equal(formatValue(1262, null), "1,262");
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

// ---------- charts ----------

test("surface chart: every surface from the all-surfaces calls; a surface missing there had no matches", () => {
  const chart = surfaceChart(current.evidence, player, opponent, window);
  assert.deepEqual(chart.sources.length, 2);
  for (const row of chart.rows) {
    for (const [who, cell] of [[player, row.playerCell], [opponent, row.opponentCell]] as const) {
      const call = current.evidence.find((e) => e.tool === "surface_splits" && e.result!.player!.player_id === who.player_id)!;
      const data = (call.result!.surfaces as { surface: string; wins: number; losses: number }[]).find((s) => s.surface === row.surface);
      assert.equal(cell.status, data ? "ok" : "no_matches");
      if (data) assert.equal(cell.record, `${data.wins}-${data.losses}`);
    }
  }
});

test("surface chart: a call filtered to one surface never claims 'no matches' elsewhere", () => {
  const chart = surfaceChart(clay.evidence, clay.request.player, clay.request.opponent,
    { date_from: clay.request.date_from, date_to: clay.request.date_to });
  const hard = chart.rows.find((r) => r.surface === "Hard")!;
  assert.deepEqual([hard.player, hard.playerCell.status], [null, "not_looked_up"]);
  assert.equal(chart.rows.find((r) => r.surface === "Clay")!.playerCell.status, "ok");
  assert.ok(chart.notes.some((n) => n.includes("not looked up")));
});

test("serve chart: the calls on the report's surface, with sample sizes in the notes", () => {
  const chart = serveChart(current.evidence, player, opponent, "Clay", window);
  assert.equal(chart.scope, "clay");
  const call = current.evidence.find((e) => e.tool === "serve_return_stats" && e.result!.player!.player_id === player.player_id)!;
  const firstIn = (call.result!.stats as Record<string, Rate>).first_serve_in;
  assert.deepEqual([chart.rows[0].metric, chart.rows[0].player], ["First serve in", round1(100 * firstIn.value!)]);
  assert.ok(chart.notes.some((n) => n.includes(`${call.result!.sample!.matches_with_stats} matches with stats`)));
});

test("serve chart: the all-surfaces fallback is used only when needed, and said", () => {
  const evidence = clone(current.evidence);
  const call = evidence.find((e) => e.tool === "serve_return_stats" && e.result!.player!.player_id === opponent.player_id)!;
  call.result!.filters = { ...call.result!.filters, surface: null }; // as if the clay sample had been too small
  const chart = serveChart(evidence, player, opponent, "Clay", window);
  assert.equal(chart.scope, "mixed surfaces");
  assert.ok(chart.notes.some((n) => n.startsWith(`${opponent.name}'s serve and return stats cover all surfaces`)));
});

test("charts ignore calls outside the report's window or with other filters", () => {
  const evidence = clone(current.evidence).map((e) => ({ ...e, result: e.result && { ...e.result, filters: { ...e.result.filters, date_from: "2015-01-01" } } }));
  const chart = serveChart(evidence as Evidence[], player, opponent, "Clay", window);
  assert.ok(chart.rows.every((r) => r.player === null && r.opponent === null));
  assert.equal(surfaceChart(evidence as Evidence[], player, opponent, window).sources.length, 0);
});

test("a rate with no matches behind it is a gap with a note, never zero", () => {
  const evidence = clone(current.evidence);
  const call = evidence.find((e) => e.tool === "pressure_stats" && e.result!.player!.player_id === player.player_id)!;
  (call.result!.stats as Record<string, Rate>).break_points_saved.value = null;
  const chart = serveChart(evidence, player, opponent, "Clay", window);
  assert.equal(chart.rows.find((r) => r.metric === "Break points saved")!.player, null);
  assert.ok(chart.notes.some((n) => n.includes("no break points saved figure")));
});

test("failed tool calls are never used", () => {
  const failed = current.evidence.map((e) => ({ ...e, error: "internal error in this tool", result: null }));
  const chart = serveChart(failed, player, opponent, "Clay", window);
  assert.equal(chart.sources.length, 0);
  assert.equal(chart.notes.length, 4);
});
