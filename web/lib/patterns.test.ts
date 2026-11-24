// Expected values are read from the saved API response (fixtures/player-stats-clay-2025.json:
// Carlos Alcaraz, clay, 2025) or written from the page's rules (D-029, D-030).

import assert from "node:assert/strict";
import { test } from "node:test";
import { checkStat, describeFilters, describeStat, describeValue, groupKeyStats } from "./evidence.ts";
import saved from "./fixtures/player-stats-clay-2025.json" with { type: "json" };
import { MESSAGES, type T } from "./i18n.ts";
import { type ShotPatterns, type TourComparison, setNote, setRows, shotView, tourView } from "./patterns.ts";
import type { PlayerStats } from "./player-stats.ts";
import type { Evidence, KeyStat } from "./types.ts";

const clone = (): PlayerStats => structuredClone(saved) as unknown as PlayerStats;

test("set rows give each share with what it counts", () => {
  const rows = setRows(clone().set_patterns);
  assert.deepEqual(rows.map((r) => [r.title, r.value, r.counts]), [
    ["Tiebreaks won", "80.0%", "8 of 10 tiebreaks"],
    ["Deciding sets won", "100.0%", "5 of 5 deciding sets"],
    ["Won after winning the first set", "100.0%", "17 of 17 matches"],
    ["Won after losing the first set", "80.0%", "4 of 5 matches"],
  ]);
  assert.deepEqual(rows.map((r) => r.small), [false, true, false, true]); // under 10 is a small sample
  assert.equal(setNote(clone().set_patterns), "Read from the scores of 22 completed matches; 1 retirement or default left out.");
});

test("a set share with nothing to count is missing, not 0", () => {
  const block = clone().set_patterns;
  block.stats.tiebreaks_won = { value: null, numerator: 0, denominator: 0, unit: "fraction" };
  const [row] = setRows(block);
  assert.equal(row.value, "No data");
  assert.equal(row.counts, "Nothing to count for this filter");
  assert.equal(row.hasBar, false);
});

test("the tour view gives the figure, the rank among ranked players and the median", () => {
  const view = tourView(clone().tour);
  const serve = view.rows.find((r) => r.key === "service_points_won")!;
  assert.deepEqual(serve, { key: "service_points_won", title: "Service points won", value: "64.8%", rank: "20th of 66", median: "63.0%" });
  assert.equal(view.rows.find((r) => r.key === "return_points_won")!.rank, "1st of 66");
  assert.equal(view.note, "Ranked among the 66 players with at least 10 matches with stats under the same filters. 1st is the highest figure.");
  assert.ok(!view.rows.some((r) => r.key === "aces_per_match"), "an average isn't a share, so it isn't in the table");
});

test("below the threshold the player keeps their figures, with no rank", () => {
  const block: TourComparison = clone().tour;
  block.tour = { ...block.tour, player_qualifies: false };
  for (const line of Object.values(block.stats)) line.rank = null;
  const view = tourView(block);
  assert.ok(view.rows.every((r) => r.rank === "Not ranked" && r.value !== "No data"));
  assert.equal(view.note, "Fewer than 10 matches with stats here, so no rank. 66 players qualify.");
});

test("ranks read as ordinals in every language", () => {
  const view = (t: T) => tourView(clone().tour, t).rows.find((r) => r.key === "return_points_won")!.rank;
  assert.equal(view(MESSAGES.fr), "1er sur 66");
  assert.equal(view(MESSAGES.es), "1.º de 66");
});

test("shot view: serve direction by court, rally lengths and net points, from the charted matches", () => {
  const view = shotView(clone().shots);
  assert.equal(view.charted, 16);
  assert.match(view.note, /^From 16 charted matches \(2,748 points\)/);
  assert.match(view.note, /not every match played\.$/);
  const deuce = view.first.find((r) => r.court === "Deuce court")!;
  assert.deepEqual(deuce.cells.map((c) => [c.side, c.value, c.counts]), [
    ["Wide", "59.6%", "267 of 448"],
    ["Body", "12.7%", "57 of 448"],
    ["T", "27.7%", "124 of 448"],
  ]);
  const longest = view.rallies.find((r) => r.key === "10_plus")!;
  assert.deepEqual([longest.title, longest.value, longest.counts], ["10 shots or more", "54.0%", "116 of 215 points"]);
  assert.deepEqual(view.net.map((r) => [r.title, r.value, r.counts]), [
    ["Net points won", "71.4%", "222 of 311 net points"],
    ["Points played at the net", "11.3%", "311 of 2,748 points"],
  ]);
});

test("with no charted match the shot view says so and shows no figure", () => {
  const block: ShotPatterns = clone().shots;
  block.charting = { ...block.charting, charted_matches: 0, points_charted: 0 };
  const view = shotView(block);
  assert.equal(view.charted, 0);
  assert.match(view.note, /^No charted matches for this filter\./);
});

// ---------- the report's key numbers (evidence.ts) ----------

const evidence = (tool: string, result: Record<string, unknown>): Evidence[] => [
  { tool_call_id: "c1", tool, input: {}, result: { tool, player: { player_id: 207989, name: "Carlos Alcaraz" }, ...result } as never, error: null },
];
const keyStat = (field: string, value: number, sample: number): KeyStat => ({ label: "", value, tool_call_id: "c1", field, sample_matches: sample });

test("a charted or set-pattern card gives the matches the figures rest on, out of the window's", () => {
  // Found live on 2026-11-24: the cards gave the whole window ("378 matches") as the sample of
  // figures read from fewer charted or completed matches. Counts from the saved response.
  const data = clone();
  const shots = data.shots as unknown as ShotPatterns;
  const counted = saved.shots.sample.matches_counted;
  const whole = (n: number, part: string) => new RegExp(`^${n} ${part} matches, out of ${counted} matches \\(all with stats\\), tournaments from `);
  assert.ok(saved.shots.charting.charted_matches < counted && saved.set_patterns.scores_read.completed_matches < counted); // exercises the rule
  const view = shotView(shots);
  assert.match(view.source.sample, whole(saved.shots.charting.charted_matches, "charted"));
  assert.match(view.rallies[0].source.sample, whole(saved.shots.rally_length.matches, "charted"));
  assert.match(view.net[0].source.sample, whole(saved.shots.net_points.matches, "charted"));
  assert.match(setRows(data.set_patterns)[3].source.sample, whole(saved.set_patterns.scores_read.completed_matches, "completed"));
  assert.match(setRows(data.set_patterns, MESSAGES.fr)[3].source.sample, new RegExp(`^${saved.set_patterns.scores_read.completed_matches} matchs terminés, sur ${counted} matchs`));
});

test("a charted serve direction is described from its path, with its counts", () => {
  const shots = clone().shots as unknown as Record<string, unknown>;
  const ev = evidence("shot_patterns", shots);
  const stat = keyStat("serve_direction.first_serves_in.deuce.wide.value", 0.596, 16);
  const check = checkStat(stat, ev);
  assert.equal(check.status, "matched");
  assert.equal(describeStat(stat, ev[0]).title, "Carlos Alcaraz: first serves in on the deuce court going wide");
  assert.equal(describeValue(stat, check), "267 of 448, 59.6%");
  assert.deepEqual(groupKeyStats([stat], ev).map((g) => g.name), ["Charted"]);
});

test("a tour rank is described as a rank among the ranked players", () => {
  const ev = evidence("tour_comparison", clone().tour as unknown as Record<string, unknown>);
  const stat = keyStat("stats.return_points_won.rank", 1, 23);
  const check = checkStat(stat, ev);
  assert.equal(describeStat(stat, ev[0]).title, "Carlos Alcaraz: rank for return points won among tour players");
  assert.equal(describeValue(stat, check), "1st of 66 players");
});

test("the opponent-ranking filter is said in words", () => {
  assert.deepEqual(describeFilters({ season: 2023, opponent_rank_max: 10 }), ["2023 season", "Opponents ranked 10 or better"]);
});
