// Expected values are read from the saved API response (fixtures/matchup-clay.json: GET /matchup
// for Jannik Sinner against Carlos Alcaraz on clay, from the local database) or written from the
// page's rules (D-033). No count is typed here.

import assert from "node:assert/strict";
import { test } from "node:test";
import saved from "./fixtures/matchup-clay.json" with { type: "json" };
import { EN, MESSAGES } from "./i18n.ts";
import { longDate } from "./people.ts";
import {
  type Matchup,
  headToHeadView,
  headerView,
  matchupUrl,
  parsePrepQuery,
  prepHref,
  prepLink,
  recordView,
  serveView,
  setsView,
  shotsView,
  whereWords,
  withPrepSurface,
  withScope,
} from "./prep.ts";
import type { Rate } from "./types.ts";

const clone = (): Matchup => structuredClone(saved) as unknown as Matchup;
const params = (search: string) => new URLSearchParams(search);
type Counts = Pick<Rate, "numerator" | "denominator">;
const pct = (r: Counts) => EN.pct(((100 * r.numerator) / r.denominator).toFixed(1));
const countsOf = (r: Counts, unit: string) => `${EN.countOf(r.numerator, r.denominator)} ${unit}`;
/** The saved response's blocks as the "all" scope would filter them: no surface. */
const allSurfaces = (): Pick<Matchup, "scope" | "sides"> => {
  const m = clone();
  for (const side of Object.values(m.sides)) for (const block of Object.values(side)) block.filters = { ...block.filters, surface: null };
  return { scope: "all", sides: m.sides };
};

// ---------- the URL ----------

test("the address holds both players, the surface and a scope other than the default", () => {
  const query = parsePrepQuery(params("player=206173&opponent=207989&surface=Clay"));
  assert.deepEqual(query, { player: "206173", opponent: "207989", surface: "Clay", scope: null });
  assert.equal(prepHref(query!), "/prep?player=206173&opponent=207989&surface=Clay");
  assert.equal(prepHref(withScope(query!, "all")), "/prep?player=206173&opponent=207989&surface=Clay&scope=all");
  assert.equal(prepHref(withScope(withScope(query!, "all"), "surface")), prepHref(query!));
  assert.equal(matchupUrl({ ...query!, surface: "Clay" }), "/api/matchup?player_id=206173&opponent_id=207989&surface=Clay");
  assert.equal(matchupUrl({ ...withScope(query!, "all"), surface: "Clay" }), "/api/matchup?player_id=206173&opponent_id=207989&surface=Clay&scope=all");
});

test("an address without both players is no match-up; one without a surface still names them", () => {
  assert.equal(parsePrepQuery(params("player=206173")), null);
  assert.equal(parsePrepQuery(params("player=206173&opponent= ")), null);
  const noSurface = parsePrepQuery(params("player=206173&opponent=207989"));
  assert.equal(noSurface?.surface, null);
  assert.equal(prepHref(withPrepSurface(noSurface!, "Grass")), "/prep?player=206173&opponent=207989&surface=Grass");
  assert.equal(prepLink(206173, 207989, null), "/prep?player=206173&opponent=207989");
});

test("values the API must judge are passed on as written, so its error is what the page shows", () => {
  const odd = parsePrepQuery(params("player=abc&opponent=207989&surface=Ice&scope=both"))!;
  assert.equal(matchupUrl({ ...odd, surface: "Ice" }), "/api/matchup?player_id=abc&opponent_id=207989&surface=Ice&scope=both");
});

// ---------- header ----------

test("the header gives the report's window in words and the two scopes", () => {
  const m = clone();
  const view = headerView(m);
  assert.equal(view.window, EN.prepWindow(longDate(saved.window.date_from), longDate(saved.window.date_to)));
  assert.match(view.window, /^Tournaments starting \d+ \w+ \d{4} to \d+ \w+ \d{4}, the same two years a report uses\.$/);
  assert.deepEqual(view.scopes.map((s) => [s.id, s.label, s.pressed]), [["surface", "On clay", true], ["all", "All surfaces", false]]);
  assert.equal(whereWords(m), "on clay");
  assert.equal(whereWords({ ...m, scope: "all" }), "on all surfaces");
});

// ---------- head-to-head ----------

test("the head-to-head reads from the player's side, with every meeting newest first", () => {
  const view = headToHeadView(clone());
  const h2h = saved.head_to_head;
  const clay = h2h.by_surface.find((s) => s.surface === "Clay")!;
  assert.equal(view.career, `Sinner ${h2h.record.wins}, Alcaraz ${h2h.record.losses} across every meeting in the data.`);
  assert.equal(view.onSurface, `Sinner ${clay.wins}, Alcaraz ${clay.losses} on clay.`);
  assert.equal(view.small, clay.matches < 10);
  assert.equal(view.rows.length, h2h.matches.length);
  h2h.matches.forEach((match, i) => {
    const row = view.rows[i];
    assert.equal(row.winner, match.result === "W" ? "Sinner" : "Alcaraz");
    assert.equal(row.score, match.player_score);
    assert.equal(row.date, longDate(match.match_date ?? match.tourney_date));
  });
  assert.equal(view.scoreHeader, "Score, Sinner's games first");
});

test("with no meeting on the surface, it says so", () => {
  const m = clone();
  m.head_to_head.by_surface = m.head_to_head.by_surface.filter((s) => s.surface !== "Clay");
  const view = headToHeadView(m);
  assert.equal(view.onSurface, "No meetings on clay.");
  assert.equal(view.small, false);
});

// ---------- each serve against the other's return ----------

test("each serve figure is set against the returner's figure for the same points", () => {
  const m = clone();
  for (const server of ["player", "opponent"] as const) {
    const returner = server === "player" ? "opponent" : "player";
    const view = serveView(m, server);
    assert.deepEqual(view.rows.map((r) => [r.serve.key, r.ret?.key ?? null]), [
      ["first_serve_in", null],
      ["first_serve_points_won", "first_serve_return_points_won"],
      ["second_serve_points_won", "second_serve_return_points_won"],
      ["service_points_won", "return_points_won"],
      ["break_points_saved", "break_points_converted"],
    ]);
    const serve = saved.sides[server].serve_return.stats.second_serve_points_won;
    const ret = saved.sides[returner].serve_return.stats.second_serve_return_points_won;
    const row = view.rows[2];
    assert.deepEqual([row.serve.value, row.serve.counts], [pct(serve), countsOf(serve, "second-serve points")]);
    assert.deepEqual([row.ret!.value, row.ret!.counts], [pct(ret), countsOf(ret, "second-serve return points")]);
    const saved_ = saved.sides[server].pressure.stats.break_points_saved;
    assert.equal(view.rows[4].serve.value, pct(saved_));
  }
  const sinner = serveView(m, "player");
  assert.deepEqual([sinner.title, sinner.serving, sinner.returning], ["When Sinner serves", "Sinner serving", "Alcaraz returning"]);
  assert.equal(sinner.note, "Sinner's serve on clay, against Alcaraz's return on clay. Open a number to see its source.");
});

test("each source card names whose figure it is", () => {
  const view = serveView(clone(), "player");
  assert.equal(view.rows[1].serve.source.tool, "Serve and return stats, for Jannik Sinner");
  assert.equal(view.rows[1].ret!.source.tool, "Serve and return stats, for Carlos Alcaraz");
  assert.equal(view.rows[4].ret!.source.tool, "Break points, for Carlos Alcaraz");
  const [from, to] = [longDate(saved.window.date_from), longDate(saved.window.date_to)];
  assert.equal(view.rows[1].ret!.source.filters, `Clay courts; Tournaments starting ${from} to ${to}.`);
  assert.equal(serveView({ ...clone(), ...allSurfaces() }, "player").rows[1].ret!.source.filters, `Tournaments starting ${from} to ${to}.`);
});

test("a rate with nothing to count is missing, not 0", () => {
  const m = clone();
  m.sides.opponent.serve_return.stats.second_serve_return_points_won = { value: null, numerator: 0, denominator: 0, unit: "fraction" };
  const row = serveView(m, "player").rows[2];
  assert.deepEqual([row.ret!.value, row.ret!.counts, row.ret!.hasBar, row.ret!.small], ["No data", "No matches with stats for this filter", false, false]);
});

test("fewer than 10 matches with stats marks a small sample", () => {
  const m = clone();
  m.sides.opponent.serve_return.sample = { ...m.sides.opponent.serve_return.sample, matches_with_stats: 9 };
  assert.equal(serveView(m, "player").rows[1].ret!.small, true);
  assert.equal(serveView(m, "player").rows[1].serve.small, saved.sides.player.serve_return.sample.matches_with_stats < 10);
});

// ---------- sets, charted patterns and records ----------

test("set figures line up by stat, with the completed matches on each card", () => {
  const view = setsView(clone());
  const [p, o] = [saved.sides.player.set_patterns, saved.sides.opponent.set_patterns];
  assert.equal(view.note, `Read from the scores of completed matches on clay: ${p.scores_read.completed_matches} for Sinner, ${o.scores_read.completed_matches} for Alcaraz.`);
  assert.deepEqual(view.rows.map((r) => r.key), ["tiebreaks_won", "deciding_sets_won", "won_after_winning_first_set", "won_after_losing_first_set"]);
  const tiebreaks = view.rows[0];
  assert.equal(tiebreaks.player.value, pct(p.stats.tiebreaks_won));
  assert.equal(tiebreaks.opponent.value, pct(o.stats.tiebreaks_won));
  assert.match(tiebreaks.opponent.source.sample, new RegExp(`^${o.scores_read.completed_matches} completed matches, out of `));
  assert.equal(tiebreaks.opponent.source.tool, "Set patterns, for Carlos Alcaraz");
});

test("charted figures carry each player's charted matches", () => {
  const view = shotsView(clone());
  const [p, o] = [saved.sides.player.shots, saved.sides.opponent.shots];
  assert.match(view.note, new RegExp(`shot by shot on clay: ${p.charting.charted_matches} for Sinner, ${o.charting.charted_matches} for Alcaraz\\.`));
  assert.deepEqual(view.sides.map((s) => [s.who, s.title, s.secondTitle, s.none]), [
    ["player", "Sinner: first serves in, by direction", "Sinner: second serves, by direction (double faults included)", null],
    ["opponent", "Alcaraz: first serves in, by direction", "Alcaraz: second serves, by direction (double faults included)", null],
  ]);
  assert.deepEqual(view.rallies.map((r) => r.key), ["1_3", "4_6", "7_9", "10_plus"]);
  assert.match(view.net[0].opponent.source.sample, new RegExp(`^${o.net_points.matches} charted matches, out of `));
  assert.match(view.sides[1].view.source.sample, new RegExp(`^${o.charting.charted_matches} charted matches, out of `));
  assert.equal(view.sides[1].view.source.tool, "Charted shot patterns, for Carlos Alcaraz");
});

test("a player with no charted match gets a sentence, and their figures stay missing", () => {
  const m = clone();
  const shots = m.sides.opponent.shots;
  shots.charting = { ...shots.charting, charted_matches: 0, points_charted: 0 };
  for (const band of Object.values(shots.rally_length.points_won)) Object.assign(band, { value: null, numerator: 0, denominator: 0 });
  const view = shotsView(m);
  assert.equal(view.sides[1].none, "No charted matches for Alcaraz on clay.");
  assert.ok(view.rallies.every((r) => r.opponent.value === "No data" && !r.opponent.hasBar));
});

test("each record gives the win rate, the win-loss and a link to the player's stats", () => {
  const cards = recordView(clone());
  const [p, o] = [saved.sides.player.record.overall, saved.sides.opponent.record.overall];
  assert.deepEqual(cards.map((c) => [c.name, c.line, c.href, c.linkText]), [
    ["Jannik Sinner", `${p.wins}-${p.losses} on clay`, "/players?id=206173", "Sinner's player stats"],
    ["Carlos Alcaraz", `${o.wins}-${o.losses} on clay`, "/players?id=207989", "Alcaraz's player stats"],
  ]);
  assert.deepEqual([cards[1].figure.value, cards[1].figure.counts], [pct(o.win_rate), countsOf(o.win_rate, "matches")]);
});

// ---------- languages ----------

test("the page reads in Spanish and French", () => {
  const m = clone();
  assert.equal(serveView(m, "opponent", MESSAGES.es).title, "Cuando saca Alcaraz");
  assert.equal(serveView(m, "player", MESSAGES.es).rows[2].ret!.source.tool, "Estadísticas de saque y resto, de Carlos Alcaraz");
  assert.equal(headToHeadView(m, MESSAGES.fr).scoreHeader, "Score, jeux de Sinner d'abord");
  assert.match(setsView(m, MESSAGES.fr).note, /^Lu dans les scores des matchs terminés sur terre battue : /);
});

test("shot direction shows for each player who has it, with their name on its source (D-038)", async () => {
  const shots = (await import("./fixtures/shots-sinner-roland-garros-2024.json", { with: { type: "json" } })).default;
  const before = shotsView(clone());
  assert.ok(before.sides.every((s) => s.direction === null)); // the saved response predates shot direction
  const m = clone();
  m.sides.player.shots = { ...m.sides.player.shots, shot_direction: shots.shot_direction } as never;
  const view = shotsView(m);
  const sinner = view.sides[0];
  assert.equal(sinner.directionTitle, "Sinner: shot direction");
  assert.equal(sinner.direction?.source.tool, "Charted shot patterns, for Jannik Sinner");
  assert.equal(view.sides[1].direction, null);
});
