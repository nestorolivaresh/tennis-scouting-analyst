// Run with: npm test (Node's own test runner; Node strips the TypeScript types).
// Fixtures are real /report responses (Sinner v Alcaraz on clay, 2026-11-09): `current` from
// the current prompt (win-loss over every surface), `clay` from before it (one surface).
// Expected values are read from their tool results, never typed in (spec: no hardcoded stats).

import assert from "node:assert/strict";
import { test } from "node:test";
import clayReport from "./fixtures/report-clay.json" with { type: "json" };
import currentReport from "./fixtures/report-current.json" with { type: "json" };
import {
  checkStat, dataThrough, describeExcluded, describeFilters, describeStat, describeValue, formatValue, groupKeyStats, hasCareerHeadToHead, honoursBoard, isSmallKeyStat,
  isTwoYearWindow, leadOf, ratePercent, resolvePath, round1, sampleLine, scalePosition, scoreboardTiles, serveChart, serveSampleLine, serveScale, shortNames, sourcePanel, surfaceChart,
} from "./evidence.ts";
import { eventName, roundName } from "./people.ts";
import type { Evidence, KeyStat, Rate, ReportResponse, ToolResult } from "./types.ts";

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
  assert.equal(formatValue(2.3043, { value: 2.3043, numerator: 53, denominator: 23, unit: "per_match" }), "2.3");
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

// ---------- the report screen ----------

type WinLoss = { matches: number; wins: number; losses: number; surface?: string };
type Match = { tourney_date: string; match_date: string | null; tournament: string; round: string; surface: string; result: string; score: string };

const headToHead = (evidence: Evidence[]) => evidence.find((e) => e.tool === "head_to_head")!;

/** The same head-to-head as if the tool had been called from the other player's side. */
function fromOtherSide(evidence: Evidence[]): Evidence[] {
  const copy = clone(evidence);
  const result = headToHead(copy).result as ToolResult & { record: WinLoss; by_surface: WinLoss[]; matches: Match[] };
  [result.player, result.opponent] = [result.opponent, result.player];
  for (const line of [result.record, ...result.by_surface]) [line.wins, line.losses] = [line.losses, line.wins];
  for (const m of result.matches) m.result = m.result === "W" ? "L" : "W";
  return copy;
}

const withoutHeadToHead = (evidence: Evidence[]) => evidence.filter((e) => e.tool !== "head_to_head");
const failedHeadToHead = (evidence: Evidence[]) => evidence.map((e) => (e.tool === "head_to_head" ? { ...e, result: null, error: "internal error in this tool" } : e));

test("scoreboard tiles: head-to-head and win rate read from the evidence, per player", () => {
  const result = headToHead(current.evidence).result as ToolResult & { record: WinLoss; by_surface: WinLoss[] };
  const clayLine = result.by_surface.find((r) => r.surface === "Clay")!;
  const tiles = scoreboardTiles(current.evidence, player, opponent, "Clay", window);
  assert.deepEqual([tiles.player.career.text, tiles.opponent.career.text], [String(result.record.wins), String(result.record.losses)]);
  assert.deepEqual([tiles.player.onSurface.text, tiles.opponent.onSurface.text], [String(clayLine.wins), String(clayLine.losses)]);
  assert.deepEqual([tiles.player.career.sample, tiles.player.onSurface.sample], [result.record.matches, clayLine.matches]);
  for (const [who, tile] of [[player, tiles.player.winRate], [opponent, tiles.opponent.winRate]] as const) {
    const call = current.evidence.find((e) => e.tool === "surface_splits" && e.result!.player!.player_id === who.player_id)!;
    const clay = (call.result!.surfaces as (WinLoss & { win_rate: Rate })[]).find((s) => s.surface === "Clay")!;
    assert.deepEqual([tile.text, tile.sample], [`${round1(100 * clay.win_rate.value!).toFixed(1)}%`, clay.matches]);
  }
});

test("scoreboard tiles: a head-to-head called from the other side gives each player their own wins", () => {
  assert.deepEqual(scoreboardTiles(fromOtherSide(current.evidence), player, opponent, "Clay", window), scoreboardTiles(current.evidence, player, opponent, "Clay", window));
});

test("scoreboard tiles: missing evidence is missing, never 0", () => {
  const none = scoreboardTiles([], player, opponent, "Clay", window);
  for (const row of [none.player, none.opponent]) {
    for (const tile of [row.career, row.onSurface, row.winRate]) assert.deepEqual([tile.status, tile.text, tile.sample], ["no_data", "No data", null]);
  }
  assert.equal(scoreboardTiles(failedHeadToHead(current.evidence), player, opponent, "Clay", window).player.career.text, "No data");
  assert.equal(scoreboardTiles(withoutHeadToHead(current.evidence), player, opponent, "Clay", window).opponent.onSurface.text, "No data");
});

test("scoreboard tiles: never having met is 'No matches', and a real 0 stays 0", () => {
  const evidence = clone(current.evidence);
  const result = headToHead(evidence).result as ToolResult & { record: WinLoss; by_surface: WinLoss[] };
  result.by_surface = result.by_surface.filter((r) => r.surface !== "Clay");
  const tiles = scoreboardTiles(evidence, player, opponent, "Clay", window);
  assert.deepEqual([tiles.player.onSurface.status, tiles.player.onSurface.text], ["no_matches", "No matches"]);
  assert.equal(tiles.player.career.status, "ok"); // only that surface is empty
  Object.assign(result.record, { matches: 0, wins: 0, losses: 0 });
  assert.equal(scoreboardTiles(evidence, player, opponent, "Clay", window).player.career.text, "No matches");
  const sweep = clone(current.evidence);
  Object.assign((headToHead(sweep).result as ToolResult & { record: WinLoss }).record, { matches: 3, wins: 3, losses: 0 });
  const swept = scoreboardTiles(sweep, player, opponent, "Clay", window).opponent.career;
  assert.deepEqual([swept.status, swept.text], ["ok", "0"]);
});

test("scoreboard tiles: a head-to-head narrowed by date or level can't fill a career figure", () => {
  const evidence = clone(current.evidence);
  headToHead(evidence).result!.filters = { ...headToHead(evidence).result!.filters, date_from: window.date_from };
  assert.equal(scoreboardTiles(evidence, player, opponent, "Clay", window).player.career.status, "no_data");
  assert.equal(hasCareerHeadToHead(evidence, player, opponent), false);
  assert.equal(honoursBoard(evidence, player, opponent).status, "not_looked_up");
});

test("scoreboard tiles: a head-to-head filtered to the report's surface fills only that tile", () => {
  const evidence = clone(current.evidence);
  const result = headToHead(evidence).result as ToolResult & { record: WinLoss };
  result.filters = { ...result.filters, surface: "Clay" };
  const tiles = scoreboardTiles(evidence, player, opponent, "Clay", window);
  assert.deepEqual([tiles.player.career.status, tiles.player.onSurface.text], ["no_data", String(result.record.wins)]);
});

test("the data's end date and the two-year window come from the evidence and the request", () => {
  const first = current.evidence[0].result!.data_window as { last_match_date: string };
  assert.equal(dataThrough(current.evidence), first.last_match_date);
  assert.equal(dataThrough([]), null);
  assert.equal(isTwoYearWindow(window), true);
  assert.equal(isTwoYearWindow({ date_from: "2025-01-01", date_to: "2026-10-26" }), false);
  assert.equal(isTwoYearWindow({ date_from: "2022-02-28", date_to: "2024-02-29" }), true);
});

test("honours board: every meeting, newest first, with the winner from each match's result", () => {
  const board = honoursBoard(current.evidence, player, opponent);
  assert.equal(board.status, "ok");
  if (board.status !== "ok") return;
  const result = headToHead(current.evidence).result as ToolResult & { record: WinLoss; matches: Match[] };
  assert.equal(board.rows.length, result.matches.length);
  assert.deepEqual(board.wins, { player: result.record.wins, opponent: result.record.losses });
  board.rows.forEach((row, i) => {
    const match = result.matches[i];
    assert.equal(row.winner, match.result === "W" ? "player" : "opponent", match.tournament);
    assert.deepEqual([row.event, row.round, row.score, row.surface], [eventName(match.tournament), roundName(match.round), match.score, match.surface]);
    if (i) assert.ok(board.rows[i - 1].date >= row.date);
  });
  assert.ok(board.rows.some((r) => r.winner === "player") && board.rows.some((r) => r.winner === "opponent"));
});

test("honours board: the winner follows the side the call took, and rows are put in date order", () => {
  const forward = honoursBoard(current.evidence, player, opponent);
  assert.deepEqual(honoursBoard(fromOtherSide(current.evidence), player, opponent), forward);
  const shuffled = clone(current.evidence);
  (headToHead(shuffled).result as ToolResult & { matches: Match[] }).matches.reverse();
  assert.deepEqual(honoursBoard(shuffled, player, opponent), forward);
});

test("honours board: a result that is neither a win nor a loss names no winner", () => {
  const evidence = clone(current.evidence);
  (headToHead(evidence).result as ToolResult & { matches: Match[] }).matches[0].result = "?";
  const board = honoursBoard(evidence, player, opponent);
  assert.ok(board.status === "ok" && board.rows[0].winner === null);
});

test("honours board: 'not looked up' and 'no meetings' are told apart", () => {
  assert.deepEqual(honoursBoard(withoutHeadToHead(current.evidence), player, opponent), { status: "not_looked_up" });
  assert.deepEqual(honoursBoard(failedHeadToHead(current.evidence), player, opponent), { status: "not_looked_up" });
  const evidence = clone(current.evidence);
  (headToHead(evidence).result as ToolResult & { matches: Match[] }).matches = [];
  assert.deepEqual(honoursBoard(evidence, player, opponent), { status: "no_meetings" });
  assert.deepEqual(honoursBoard(current.evidence, opponent, { player_id: 1, name: "Someone Else" }), { status: "not_looked_up" });
});

test("honours board: a tournament starting in the last days of December is the next year's", () => {
  const evidence = clone(current.evidence);
  const matches = (headToHead(evidence).result as ToolResult & { matches: Match[] }).matches;
  Object.assign(matches[0], { tourney_date: "2024-12-29", match_date: null });
  Object.assign(matches[1], { tourney_date: "2024-12-18", match_date: null });
  Object.assign(matches[2], { tourney_date: "2024-12-30", match_date: "2024-12-31" });
  const board = honoursBoard(evidence, player, opponent);
  assert.ok(board.status === "ok");
  if (board.status !== "ok") return;
  assert.deepEqual(board.rows.filter((r) => r.date.startsWith("2024-12")).map((r) => [r.date, r.year]), [
    ["2024-12-30", "2024"], ["2024-12-29", "2025"], ["2024-12-18", "2024"],
  ]);
});

test("who is ahead is computed from the two figures, and a gap names nobody", () => {
  assert.deepEqual(leadOf(61.4, 65.7), { side: "opponent", gap: "4.3" });
  assert.deepEqual(leadOf(75.7, 68.7), { side: "player", gap: "7.0" });
  assert.deepEqual(leadOf(50, 50), { side: "level", gap: "0.0" });
  assert.deepEqual(leadOf(null, 50), { side: null, gap: null });
  assert.deepEqual(leadOf(50, null), { side: null, gap: null });
});

test("the dumbbell scale is 40% to 80%, widened only when a figure falls outside", () => {
  const chart = serveChart(current.evidence, player, opponent, "Clay", window);
  assert.deepEqual(serveScale(chart.rows), { min: 40, max: 80 });
  assert.equal(scalePosition(60, { min: 40, max: 80 }), 50);
  const row = { ...chart.rows[0], player: 31.2, opponent: 83.1 };
  assert.deepEqual(serveScale([row]), { min: 30, max: 90 });
  assert.deepEqual(serveScale([{ ...row, player: null, opponent: null }]), { min: 40, max: 80 });
});

test("the serve table's sample line, and the per-tool notes when the samples differ", () => {
  const names = shortNames(player, opponent);
  const chart = serveChart(current.evidence, player, opponent, "Clay", window);
  const [mine, theirs] = [chart.matchesWithStats.player[0], chart.matchesWithStats.opponent[0]];
  assert.equal(serveSampleLine(chart, player, opponent, "Clay"), `Clay matches with stats: ${mine} for ${names.player}, ${theirs} for ${names.opponent}.`);
  assert.deepEqual(chart.caveats, []); // only the sample lines were notes here
  const evidence = clone(current.evidence);
  evidence.find((e) => e.tool === "pressure_stats" && e.result!.player!.player_id === player.player_id)!.result!.sample!.matches_with_stats -= 1;
  assert.equal(serveSampleLine(serveChart(evidence, player, opponent, "Clay", window), player, opponent, "Clay"), null);
  assert.equal(serveSampleLine(serveChart([], player, opponent, "Clay", window), player, opponent, "Clay"), null);
});

test("two players with one surname keep their full names", () => {
  assert.deepEqual(shortNames({ player_id: 1, name: "Alexander Zverev" }, { player_id: 2, name: "Mischa Zverev" }), { player: "Alexander Zverev", opponent: "Mischa Zverev" });
  assert.deepEqual(shortNames(player, opponent), { player: "Sinner", opponent: "Alcaraz" });
});

test("key numbers are grouped as in the design, keeping the report's order", () => {
  const groups = groupKeyStats(current.report!.key_stats, current.evidence);
  assert.deepEqual(groups.map((g) => g.name), ["Win rate", "Serve", "Pressure", "Head-to-head"]);
  assert.equal(groups.flatMap((g) => g.rows).length, current.report!.key_stats.length);
  for (const group of groups) assert.deepEqual(group.rows.map((r) => r.index), [...group.rows.map((r) => r.index)].sort((a, b) => a - b));
  const missing = groupKeyStats([{ ...current.report!.key_stats[0], tool_call_id: "c42" }], current.evidence);
  assert.deepEqual(missing.map((g) => g.name), ["Other"]);
});

test("the small-sample tag is under 10 matches, by the matches with stats for a stat", () => {
  const stats = current.report!.key_stats;
  const small = (stat: KeyStat) => isSmallKeyStat(stat, checkStat(stat, current.evidence));
  assert.equal(small(stats.find((s) => s.field === "by_surface.1.wins")!), true); // the clay meetings
  assert.equal(small(stats.find((s) => s.field === "record.wins")!), false);
  const evidence = clone(current.evidence);
  const stat = stats.find((s) => s.field.startsWith("stats."))!;
  assert.equal(isSmallKeyStat(stat, checkStat(stat, evidence)), false);
  evidence.find((e) => e.tool_call_id === stat.tool_call_id)!.result!.sample!.matches_with_stats = 9;
  assert.equal(isSmallKeyStat(stat, checkStat(stat, evidence)), true);
});

test("a key number's source panel is read from the tool result", () => {
  const stats = current.report!.key_stats;
  const panelFor = (field: string, tool: string) => {
    const stat = stats.find((s) => s.field === field && current.evidence.find((e) => e.tool_call_id === s.tool_call_id)!.tool === tool)!;
    const check = checkStat(stat, current.evidence);
    return { stat, check, panel: sourcePanel(stat, check)! };
  };
  const serve = panelFor("stats.second_serve_points_won.value", "serve_return_stats");
  assert.equal(serve.panel.value, `${serve.check.rate!.numerator} of ${serve.check.rate!.denominator} second-serve points, ${formatValue(serve.check.value!, serve.check.rate)}`);
  assert.equal(serve.panel.field, `${serve.stat.field} = ${serve.check.value}`);
  assert.ok(serve.panel.source.endsWith(`(call ${serve.stat.tool_call_id})`));
  assert.match(serve.panel.filters, /^Clay courts; Tournaments starting \d+ \w+ \d{4} to \d+ \w+ \d{4}$/);

  const clayWins = panelFor("by_surface.1.wins", "head_to_head");
  assert.equal(clayWins.panel.value, `${clayWins.check.value} wins from ${clayWins.check.sample} clay meetings`);
  assert.equal(clayWins.panel.filters, "None: every meeting in the data. This is the clay line.");
  assert.ok(clayWins.panel.sample.startsWith(`${clayWins.check.sample} clay meetings, out of `));

  const career = panelFor("record.wins", "head_to_head");
  assert.equal(describeValue(career.stat, career.check), `${career.check.value} wins from ${career.check.sample} meetings`);

  const missing: KeyStat = { ...stats[0], tool_call_id: "c42" };
  assert.equal(sourcePanel(missing, checkStat(missing, current.evidence)), null);
});

test("rates are shown from their counts, not from the tool's rounded value", () => {
  // 37 of 43 is 86.05% only after the tool rounds it to 0.8605; the true figure is 86.0%.
  const rate = { value: 0.8605, numerator: 37, denominator: 43, unit: "fraction" } as const;
  assert.equal(formatValue(0.8605, rate), "86.0%");
  assert.equal(ratePercent(rate), 86);
  assert.equal(ratePercent({ value: null, numerator: 0, denominator: 0, unit: "fraction" }), null);
});
