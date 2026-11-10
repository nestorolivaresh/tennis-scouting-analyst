// Expected values are read from the saved API response (fixtures/player-stats-clay-2025.json:
// Carlos Alcaraz, clay, 2025, with Jannik Sinner as the opponent) or written from the page's rules.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import saved from "./fixtures/player-stats-clay-2025.json" with { type: "json" };
import {
  type PlayerStats,
  type RecordSummary,
  againstView,
  bioLine,
  boardNumbers,
  candidateFromProfile,
  countedNote,
  coverageLine,
  findCandidate,
  formView,
  isBadLink,
  matchupHandoff,
  pageHref,
  parseQuery,
  queryForPlayer,
  scoutHandoff,
  seasonNote,
  seasonRows,
  serveGroups,
  showingText,
  sourceFacts,
  statsUrl,
  sumRecords,
  surfaceTiles,
  withAgainst,
  withPlayer,
  withSeason,
  withSurface,
  withoutFilters,
} from "./player-stats.ts";
import type { Candidate, Rate } from "./types.ts";

const data = saved as unknown as PlayerStats;
const playerOnly = parseQuery(new URLSearchParams("id=207989"))!;
const clay2025 = parseQuery(new URLSearchParams("id=207989&surface=Clay&season=2025&against=206173"))!;
const noRate: Rate = { value: null, numerator: 0, denominator: 0, unit: "fraction" };
const noRecord: RecordSummary = { matches: 0, wins: 0, losses: 0, win_rate: noRate };

function clone(): PlayerStats {
  return structuredClone(data);
}

function row(stats: PlayerStats, key: string) {
  const found = serveGroups(stats).flatMap((g) => g.rows).find((r) => r.key === key);
  assert.ok(found, `no row ${key}`);
  return found;
}

const sinner: Candidate = {
  player_id: 206173, name: "Jannik Sinner", country: "ITA", hand: "R", matches_loaded: 400, last_tourney_date: "2026-10-26",
};

// ---------- the fixture ----------

test("the saved response is the Clay 2025 Alcaraz one and holds no birth date", () => {
  assert.equal(data.profile.player.player_id, 207989);
  assert.deepEqual(data.filters, { surface: "Clay", season: 2025 });
  assert.equal(data.head_to_head?.opponent.player_id, 206173);
  assert.doesNotMatch(readFileSync(new URL("./fixtures/player-stats-clay-2025.json", import.meta.url), "utf8"), /birth/);
});

// ---------- the URL ----------

test("with no id no player is chosen yet, whatever else the URL says", () => {
  assert.equal(parseQuery(new URLSearchParams("")), null);
  assert.equal(parseQuery(new URLSearchParams("id=%20%20")), null);
  assert.equal(parseQuery(new URLSearchParams("surface=Clay&season=2025&against=206173")), null);
});

test("the first player picked starts with no filters", () => {
  assert.deepEqual(queryForPlayer(207989), playerOnly);
  assert.equal(pageHref(queryForPlayer(206173)), "/players?id=206173");
});

test("the URL's values are read as given, so the API can refuse the bad ones", () => {
  assert.deepEqual(parseQuery(new URLSearchParams("id=abc&surface=Mud&season=soon&against=-1")), {
    id: "abc", surface: "Mud", season: "soon", against: "-1",
  });
  assert.equal(statsUrl(parseQuery(new URLSearchParams("id=207989&surface=Mud&season=soon"))!), "/api/players/207989/stats?surface=Mud&season=soon");
});

test("empty parameters count as not set", () => {
  assert.deepEqual(parseQuery(new URLSearchParams("id=207989&surface=&season=&against=")), playerOnly);
});

test("the page address round-trips through parsing", () => {
  assert.equal(pageHref(clay2025), "/players?id=207989&surface=Clay&season=2025&against=206173");
  assert.deepEqual(parseQuery(new URLSearchParams(pageHref(clay2025).split("?")[1])), clay2025);
  assert.equal(pageHref(playerOnly), "/players?id=207989");
});

test("the API call says opponent_id where the page says against", () => {
  assert.equal(statsUrl(clay2025), "/api/players/207989/stats?surface=Clay&season=2025&opponent_id=206173");
  assert.equal(statsUrl(playerOnly), "/api/players/207989/stats");
});

test("an id from the URL can't change which address is called", () => {
  assert.equal(statsUrl({ ...playerOnly, id: "1/../../chat?x=1" }), "/api/players/1%2F..%2F..%2Fchat%3Fx%3D1/stats");
});

test("choosing a tile, a year or clearing changes only that part of the URL", () => {
  assert.equal(withSurface(clay2025, "Hard").surface, "Hard");
  assert.equal(withSurface(clay2025, "All").surface, null);
  assert.equal(withSurface(clay2025, "All").season, "2025");
  assert.equal(withSeason(clay2025, 2024).season, "2024");
  assert.equal(withSeason(clay2025, null).season, null);
  assert.deepEqual(withoutFilters(clay2025), { id: "207989", surface: null, season: null, against: "206173" });
  assert.equal(withAgainst(clay2025, null).against, null);
  assert.equal(withAgainst(playerOnly, 104925).against, "104925");
});

test("a new player keeps the filters and the comparison", () => {
  assert.deepEqual(withPlayer(clay2025, 104925), { id: "104925", surface: "Clay", season: "2025", against: "206173" });
});

test("looking up the player being compared with drops the comparison, which the API would refuse", () => {
  assert.deepEqual(withPlayer(clay2025, 206173), { id: "206173", surface: "Clay", season: "2025", against: null });
});

test("only the link's own errors take away the retry", () => {
  assert.equal(isBadLink(404), true);
  assert.equal(isBadLink(422), true);
  assert.equal(isBadLink(503), false);
  assert.equal(isBadLink(500), false);
  assert.equal(isBadLink(429), false);
});

// ---------- the board ----------

test("the board shows the filtered record", () => {
  assert.deepEqual(boardNumbers(data.record.overall), { matches: "23", won: "22", lost: "1", winRate: "95.7%", hasWinRate: true });
});

test("a 0-0 record keeps its true counts and has no win rate", () => {
  assert.deepEqual(boardNumbers(noRecord), { matches: "0", won: "0", lost: "0", winRate: "No data", hasWinRate: false });
});

test("the Showing line says what the numbers cover", () => {
  assert.equal(showingText(data.filters), "Showing clay courts, 2025.");
  assert.equal(showingText({ surface: null, season: null }), "Showing every surface, every season.");
  assert.equal(showingText({ surface: "Grass", season: null }), "Showing grass courts, every season.");
});

test("the coverage line uses the data's own dates, and says nothing about them before they arrive", () => {
  assert.match(coverageLine(data.data_window), /^ATP tour-level singles from 2015, through 1 November 2026\. /);
  assert.match(coverageLine(null), /^ATP tour-level singles\. Every number/);
});

test("the bio reads as the design's when everything is known", () => {
  assert.equal(bioLine(data.profile, "Spain"), "Spain, right-handed, 183 cm. Ranked 3 at Vienna, Nov 2026.");
});

test("the bio leaves out what isn't known, with no gaps or stray punctuation", () => {
  const known = { country: "ESP", hand: "R", height_cm: 183, latest_rank: data.profile.latest_rank };
  const cases: [typeof known | Record<string, unknown>, string | null, string][] = [
    [{ ...known, height_cm: null }, "Spain", "Spain, right-handed. Ranked 3 at Vienna, Nov 2026."],
    [{ ...known, hand: null }, "Spain", "Spain, 183 cm. Ranked 3 at Vienna, Nov 2026."],
    [{ ...known, country: null }, null, "Right-handed, 183 cm. Ranked 3 at Vienna, Nov 2026."],
    [{ ...known, country: null, hand: null }, null, "183 cm. Ranked 3 at Vienna, Nov 2026."],
    [{ ...known, latest_rank: null }, "Spain", "Spain, right-handed, 183 cm."],
    [{ country: null, hand: null, height_cm: null, latest_rank: data.profile.latest_rank }, null, "Ranked 3 at Vienna, Nov 2026."],
    [{ country: null, hand: null, height_cm: null, latest_rank: null }, null, ""],
  ];
  for (const [profile, country, expected] of cases) {
    assert.equal(bioLine(profile as never, country), expected);
  }
});

test("a country the app has no name for is shown as the data's code", () => {
  assert.equal(bioLine({ country: "XKX", hand: "L", height_cm: null, latest_rank: null }, null), "XKX, left-handed.");
});

test("the ranking falls back to the tournament's date when the match date is missing", () => {
  const latest_rank = { rank: 12, tournament: "Us Open", tourney_date: "2024-08-26", match_date: null };
  assert.equal(bioLine({ country: null, hand: null, height_cm: null, latest_rank }, null), "Ranked 12 at US Open, Aug 2024.");
});

// ---------- record by surface ----------

test("tiles come from the all-surfaces block, whatever surface is filtered", () => {
  assert.deepEqual(
    surfaceTiles(data.by_surface, clay2025).map((t) => [t.name, t.rate, t.record, t.on]),
    [
      ["All surfaces", "89.7%", "70-8", false],
      ["Hard", "86.0%", "37-6", false],
      ["Clay", "95.7%", "22-1", true],
      ["Grass", "91.7%", "11-1", false],
    ],
  );
});

test("a rate reads as its counts do, not as the API's rounded value rounded again", () => {
  const hard = data.by_surface.surfaces.find((s) => s.surface === "Hard");
  assert.deepEqual(hard?.win_rate, { value: 0.8605, numerator: 37, denominator: 43, unit: "fraction" });
  assert.equal(surfaceTiles(data.by_surface, playerOnly)[1].rate, "86.0%");
});

test("with no surface in the URL the All surfaces tile is chosen", () => {
  assert.deepEqual(surfaceTiles(data.by_surface, playerOnly).map((t) => t.on), [true, false, false, false]);
});

test("a surface in the URL is matched whatever its case, as the API does", () => {
  assert.deepEqual(surfaceTiles(data.by_surface, { ...playerOnly, surface: "clay" }).map((t) => t.on), [false, false, true, false]);
});

test("a valid surface with no tile, Carpet, chooses no tile rather than All surfaces", () => {
  assert.deepEqual(surfaceTiles(data.by_surface, { ...playerOnly, surface: "Carpet" }).map((t) => t.on), [false, false, false, false]);
});

test("a surface with no matches says so and has no record", () => {
  const tiles = surfaceTiles({ overall: noRecord, surfaces: [] }, playerOnly);
  for (const tile of tiles) {
    assert.equal(tile.rate, "No matches");
    assert.equal(tile.hasRate, false);
    assert.equal(tile.record, "");
  }
});

// ---------- the counted note ----------

test("the counted note gives the sample, in long dates, and the retirements above zero", () => {
  assert.equal(
    countedNote(data.record, "Carlos Alcaraz"),
    "Counts 23 matches in tournaments starting 7 April 2025 to 26 May 2025. Retirements and defaults count: 1 by opponents, 0 by Alcaraz.",
  );
});

test("the retirements aren't mentioned when there are none", () => {
  const record = clone().record;
  record.sample.opponent_retired_or_defaulted = 0;
  assert.equal(countedNote(record, "Carlos Alcaraz"), "Counts 23 matches in tournaments starting 7 April 2025 to 26 May 2025.");
});

test("what was left out is listed from the block's own counts", () => {
  const record = clone().record;
  record.sample.opponent_retired_or_defaulted = 0;
  record.excluded.walkovers = 1;
  record.excluded.exhibitions = 2;
  assert.match(countedNote(record, "Carlos Alcaraz"), /1 walkover, 2 exhibitions left out\.$/);
});

test("no matches is said as no matches", () => {
  const record = clone().record;
  record.sample = { ...record.sample, matches_counted: 0, matches_with_stats: 0, opponent_retired_or_defaulted: 0, first_tourney_date: null, last_tourney_date: null };
  assert.equal(countedNote(record, "Carlos Alcaraz"), "No matches for this filter.");
  record.filters = { ...record.filters, surface: null, season: null };
  assert.equal(countedNote(record, "Carlos Alcaraz"), "No matches in the data.");
});

// ---------- season by season ----------

test("each season's row comes from its own record", () => {
  const rows = seasonRows(data.seasons, clay2025);
  const y2025 = rows.find((r) => r.season === 2025);
  assert.deepEqual([y2025?.label, y2025?.record, y2025?.rate, y2025?.on], ["2025", "22-1", "95.7%", true]);
  assert.equal(y2025?.width, 95.65);
  assert.deepEqual(rows.filter((r) => r.on).map((r) => r.label), ["2025"]);
});

test("the All seasons row comes first and adds up the seasons under the page's surface filter", () => {
  const [all] = seasonRows(data.seasons, clay2025);
  const expected = data.seasons.reduce((sum, s) => [sum[0] + s.overall.wins, sum[1] + s.overall.losses], [0, 0]);
  assert.equal(all.label, "All seasons");
  assert.equal(all.season, null);
  assert.equal(all.record, `${expected[0]}-${expected[1]}`);
  assert.equal(all.on, false);
  assert.equal(seasonRows(data.seasons, playerOnly)[0].on, true);
});

test("a season with no matches on this surface says so, and never 0.0%", () => {
  const rows = seasonRows([{ season: 2021, overall: noRecord }], playerOnly);
  assert.deepEqual([rows[1].label, rows[1].rate, rows[1].record, rows[1].width], ["2021", "No matches", "", 0]);
});

test("a player with no seasons has one All seasons row saying no matches", () => {
  const rows = seasonRows([], playerOnly);
  assert.equal(rows.length, 1);
  assert.deepEqual([rows[0].rate, rows[0].record], ["No matches", ""]);
});

test("adding nothing up gives a missing rate, not zero", () => {
  assert.equal(sumRecords([]).win_rate.value, null);
  assert.equal(sumRecords([noRecord, noRecord]).win_rate.value, null);
});

test("the season note names the surface it covers", () => {
  assert.equal(seasonNote(data.filters), "On clay. Choose a year to filter the page.");
  assert.equal(seasonNote({ surface: null, season: 2025 }), "Every surface. Choose a year to filter the page.");
});

// ---------- serve and return ----------

test("a rate shows its value and the counts behind it", () => {
  const first = row(data, "first_serve_in");
  assert.equal(first.value, "66.3%");
  assert.equal(first.counts, "1,262 of 1,904 serve points");
  assert.equal(first.width, 66.28);
  assert.equal(row(data, "first_serve_points_won").counts, "868 of 1,262 first-serve points");
});

test("rows read from their own tool's block, in the design's groups", () => {
  assert.deepEqual(serveGroups(data).map((g) => [g.name, g.rows.length]), [["On serve", 6], ["On return", 2]]);
  assert.equal(row(data, "break_points_saved").counts, "93 of 142 break points faced");
  assert.equal(row(data, "break_points_saved").source.tool, "Break points");
  assert.equal(row(data, "return_points_won").source.tool, "Serve and return stats");
});

test("aces per match is an average with no bar", () => {
  const aces = row(data, "aces_per_match");
  assert.equal(aces.value, "2.3");
  assert.equal(aces.counts, "53 aces in 23 matches");
  assert.equal(aces.hasBar, false);
  assert.equal(aces.tick, null);
});

test("a null rate is No data, not 0.0%", () => {
  const stats = clone();
  stats.serve_return.stats.first_serve_in = noRate;
  stats.serve_return.stats.aces_per_match = { ...noRate, unit: "per_match" };
  stats.serve_return.sample = { ...stats.serve_return.sample, matches_with_stats: 0 };
  const first = row(stats, "first_serve_in");
  assert.equal(first.value, "No data");
  assert.equal(first.counts, "No matches with stats for this filter");
  assert.equal(first.width, 0);
  assert.equal(first.small, false);
  assert.equal(row(stats, "aces_per_match").value, "No data");
  assert.equal(row(stats, "aces_per_match").counts, "No matches with stats for this filter");
});

test("a real 0% is a figure, not missing", () => {
  const stats = clone();
  stats.pressure.stats.break_points_converted = { value: 0, numerator: 0, denominator: 7, unit: "fraction" };
  const row0 = row(stats, "break_points_converted");
  assert.equal(row0.value, "0.0%");
  assert.equal(row0.counts, "0 of 7 break points earned");
});

test("a rate missing from the response is shown as missing", () => {
  const stats = clone();
  delete stats.serve_return.stats.first_serve_in;
  assert.equal(row(stats, "first_serve_in").value, "No data");
});

test("Small sample is under 10 matches with stats, read from that row's own block", () => {
  const stats = clone();
  assert.equal(row(stats, "first_serve_in").small, false);
  stats.serve_return.sample.matches_with_stats = 10;
  assert.equal(row(stats, "first_serve_in").small, false);
  stats.serve_return.sample.matches_with_stats = 9;
  assert.equal(row(stats, "first_serve_in").small, true);
  assert.equal(row(stats, "break_points_saved").small, false);
});

test("the brass tick marks the career figure, only when a filter is on", () => {
  const career = data.career.serve_return.stats.first_serve_in.value as number;
  assert.equal(row(data, "first_serve_in").tick, 100 * career);
  const unfiltered = clone();
  unfiltered.filters = { surface: null, season: null };
  assert.equal(row(unfiltered, "first_serve_in").tick, null);
});

test("no tick is drawn when the career figure is missing", () => {
  const stats = clone();
  stats.career.serve_return.stats.first_serve_in = noRate;
  assert.equal(row(stats, "first_serve_in").tick, null);
});

test("the Source panel describes the block in words, with long dates", () => {
  assert.deepEqual(sourceFacts(data.serve_return), {
    tool: "Serve and return stats",
    filters: "Clay courts, 2025 season.",
    sample: "23 matches (all with stats), tournaments from 7 April 2025 to 26 May 2025.",
    left: "Nothing.",
  });
});

test("the Source panel reads each block's own filters and left-out counts", () => {
  const stats = clone();
  stats.pressure.excluded.walkovers = 2;
  assert.equal(sourceFacts(stats.pressure).left, "2 walkovers.");
  stats.pressure.filters = { ...stats.pressure.filters, surface: null, season: null };
  assert.equal(sourceFacts(stats.pressure).filters, "None: every surface and season.");
  assert.equal(sourceFacts(stats.serve_return).filters, "Clay courts, 2025 season.");
});

test("a block with no matches doesn't claim all of them had stats", () => {
  const block = clone().serve_return;
  block.sample = { ...block.sample, matches_counted: 0, matches_with_stats: 0, first_tourney_date: null, last_tourney_date: null };
  assert.equal(sourceFacts(block).sample, "No matches counted.");
});

// ---------- against ----------

test("the head-to-head is the block's record, in the filter's words", () => {
  assert.deepEqual(againstView(data.head_to_head!), { title: "Against Jannik Sinner", text: "Alcaraz 2, Sinner 0 on clay in 2025.", note: null });
});

test("with no filters the head-to-head covers every meeting", () => {
  const h2h = clone().head_to_head!;
  h2h.filters = { ...h2h.filters, surface: null, season: null };
  h2h.record = { ...h2h.record, matches: 17, wins: 10, losses: 7 };
  assert.equal(againstView(h2h).text, "Alcaraz 10, Sinner 7 across every meeting in the data.");
});

test("no meetings is said with the filter context, and never as a 0-0 record", () => {
  const h2h = clone().head_to_head!;
  h2h.record = noRecord;
  assert.equal(againstView(h2h).text, "No meetings on clay in 2025.");
  h2h.filters = { ...h2h.filters, surface: null, season: null };
  assert.equal(againstView(h2h).text, "No meetings in the data.");
});

test("walkovers left out of the head-to-head are mentioned", () => {
  const h2h = clone().head_to_head!;
  h2h.excluded.walkovers = 1;
  assert.equal(againstView(h2h).note, "1 walkover left out.");
});

// ---------- last 10 matches ----------

test("the form table is the returned matches, in the page's words", () => {
  const form = formView(data.recent_form);
  assert.equal(form.title, "Last 10 matches");
  assert.equal(form.note, "Newest first, on clay in 2025. Won 10 of these 10.");
  assert.deepEqual(
    (({ date, event, round, surface, swatch, opponent, rank, won, score }) => ({ date, event, round, surface, swatch, opponent, rank, won, score }))(form.rows[0]),
    { date: "May 2025", event: "Roland Garros", round: "Final", surface: "clay", swatch: "sw-clay", opponent: "Jannik Sinner", rank: "No. 1", won: true, score: "4-6 6-7(4) 6-4 7-6(3) 7-6(2)" },
  );
});

test("the title counts what was returned", () => {
  const form = clone().recent_form;
  form.matches = form.matches.slice(0, 4);
  assert.equal(formView(form).title, "Last 4 matches");
  form.matches = form.matches.slice(0, 1);
  assert.equal(formView(form).title, "Last match");
});

test("no matches says so, with or without a filter", () => {
  const form = clone().recent_form;
  form.matches = [];
  assert.equal(formView(form).note, "No matches on clay in 2025.");
  assert.deepEqual(formView(form).rows, []);
  form.filters = { ...form.filters, surface: null, season: null };
  assert.equal(formView(form).note, "No matches in the data.");
});

test("missing match details are said to be missing", () => {
  const form = clone().recent_form;
  form.matches[0] = { ...form.matches[0], surface: null, score: null, opponent: { ...form.matches[0].opponent, rank: null } };
  const [first] = formView(form).rows;
  assert.equal(first.surface, "unknown surface");
  assert.equal(first.swatch, null);
  assert.equal(first.rank, "No ranking in the data");
  assert.equal(first.score, "No score in the data");
});

test("a match on a surface with no swatch has none", () => {
  const form = clone().recent_form;
  form.matches[0] = { ...form.matches[0], surface: "Carpet" };
  assert.equal(formView(form).rows[0].swatch, null);
  assert.equal(formView(form).rows[0].surface, "carpet");
});

// ---------- handing off to scouting ----------

const alcaraz: Candidate = {
  player_id: 207989, name: "Carlos Alcaraz", country: "ESP", hand: "R", matches_loaded: 389, last_tourney_date: "2026-10-26",
};

test("a candidate is built from the API's profile", () => {
  assert.deepEqual(candidateFromProfile(data.profile), alcaraz);
});

test("a player with no matches loaded still makes a valid candidate", () => {
  const profile = { ...clone().profile, last_match: null, country: null, hand: null };
  assert.deepEqual(candidateFromProfile(profile), { ...alcaraz, last_tourney_date: null, country: null, hand: null });
});

test("Scout {name} makes this player the one scouted, the opponent in setup", () => {
  assert.deepEqual(scoutHandoff(data.profile), { opponent: alcaraz });
});

test("Scout this match-up scouts this player, for the player compared with", () => {
  assert.deepEqual(matchupHandoff(data.profile, sinner), { opponent: alcaraz, player: sinner });
});

test("the search result is matched on id, not on name", () => {
  const namesake = { ...sinner, player_id: 1 };
  const result = { query: "Jannik Sinner", candidates: [namesake, sinner], more_candidates: false };
  assert.equal(findCandidate(result, 206173), sinner);
  assert.equal(findCandidate(result, 999), null);
});
