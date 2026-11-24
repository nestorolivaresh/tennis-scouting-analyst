// Expected values are read from saved API responses (the season_path block of GET
// /players/{id}/stats?season=2025 for Jannik Sinner and Alexander Zverev, from the local database)
// or written from the page's rules (D-035). No count is typed here.

import assert from "node:assert/strict";
import { test } from "node:test";
import sinnerSaved from "./fixtures/season-path-sinner-2025.json" with { type: "json" };
import zverevSaved from "./fixtures/season-path-zverev-2025.json" with { type: "json" };
import { checkStat, describeStat, groupKeyStats } from "./evidence.ts";
import { EN, MESSAGES } from "./i18n.ts";
import { longDate } from "./people.ts";
import { type SeasonPath, endedText, pathView } from "./season-path.ts";
import type { Evidence, KeyStat } from "./types.ts";

const sinner = (): SeasonPath => structuredClone(sinnerSaved) as unknown as SeasonPath;
const zverev = (): SeasonPath => structuredClone(zverevSaved) as unknown as SeasonPath;

test("each tournament reads as how it ended, with its last match and its record", () => {
  const view = pathView(sinner());
  assert.equal(view.title, "Season path, 2025");
  assert.equal(view.rows.length, sinnerSaved.events.length);
  const { summary } = sinnerSaved;
  assert.equal(view.summary, `${summary.events} tournaments, ${summary.titles} titles, ${summary.record.wins}-${summary.record.losses} in counted matches.`);
  const ao = view.rows[0];
  assert.deepEqual([ao.date, ao.event, ao.surface, ao.swatch, ao.ended, ao.title], [longDate(sinnerSaved.events[0].tourney_date), "Australian Open", "Hard", "sw-hard", "Won the title", true]);
  const cincinnati = view.rows.find((r) => r.event === "Cincinnati Masters")!;
  assert.deepEqual([cincinnati.ended, cincinnati.last], ["Lost in the final", "Last match: lost to Alcaraz, 0-5 RET"]);
  assert.equal(view.rows.find((r) => r.event === "US Open")?.event, "US Open"); // the data's "Us Open", named properly
  assert.deepEqual(ao.matches.map((m) => m.round), ["Round of 128", "Round of 64", "Round of 32", "Round of 16", "Quarterfinal", "Semifinal", "Final"]);
});

test("a walkover is listed, marked not counted, and kept out of the win-loss", () => {
  const view = pathView(zverev());
  const event = zverevSaved.events.find((e) => e.walkovers > 0)!;
  const row = view.rows.find((r) => r.event === event.tournament)!;
  assert.equal(row.record, `${event.record.wins}-${event.record.losses}`);
  assert.equal(row.matches.length, event.record.matches + event.walkovers);
  assert.deepEqual(row.matches.filter((m) => !m.counted).map((m) => m.score), event.matches.filter((m) => !m.counted).map((m) => m.score));
  assert.ok(row.matches.some((m) => !m.counted));
});

test("round robins, team events and Davis Cup ties say so, with no title from one player's matches", () => {
  const rows = pathView(zverev()).rows;
  const ended = (name: string) => rows.find((r) => r.event === name)?.ended;
  assert.equal(ended("Tour Finals"), "Out in the round robin");
  assert.equal(ended("United Cup"), "Team event, group stage");
  assert.ok(rows.filter((r) => r.event.startsWith("Davis Cup")).every((r) => r.ended === "Davis Cup tie" && !r.title));
});

test("every way a tournament can end has words in every language", () => {
  const cases = [
    [{ outcome: "title", round: "F" }, "Won the title", "Ganó el título", "A remporté le titre"],
    [{ outcome: "lost", round: "R32" }, "Lost in the round of 32", "Perdió en la ronda de 32", "Battu en 16e de finale"],
    [{ outcome: "lost", round: "QF" }, "Lost in the quarterfinal", "Perdió en cuartos de final", "Battu en quart de finale"],
    [{ outcome: "withdrew", round: "SF" }, "Withdrew before the semifinal", "Se dio de baja antes de la semifinal", "Forfait en demi-finale"],
    [{ outcome: "team", round: "F" }, "Team event, played up to the final", "Evento por equipos, jugó hasta la final", "Épreuve par équipes, jusqu'en finale"],
    [{ outcome: "bronze", round: "BR" }, "Won the bronze medal", "Ganó la medalla de bronce", "A remporté la médaille de bronze"],
    [{ outcome: "fourth", round: "BR" }, "Lost the bronze medal match", "Perdió el partido por el bronce", "A perdu le match pour la médaille de bronze"],
    [{ outcome: "no_later_match", round: "QF" }, "No later match in the data", "Sin partidos posteriores en los datos", "Aucun match plus tard dans les données"],
  ] as const;
  for (const [event, en, es, fr] of cases) {
    assert.deepEqual([endedText(event, EN), endedText(event, MESSAGES.es), endedText(event, MESSAGES.fr)], [en, es, fr]);
  }
});

test("a season with no tournaments says so instead of showing an empty table", () => {
  const path = sinner();
  path.events = [];
  path.filters = { ...path.filters, surface: "Grass" };
  const view = pathView(path);
  assert.deepEqual([view.rows, view.summary, view.empty], [[], null, "No tournaments on grass in 2025."]);
});

test("the source card describes the season path's own filters and sample", () => {
  const view = pathView(sinner());
  assert.equal(view.source.tool, "Season path");
  assert.equal(view.source.filters, "2025 season.");
  assert.match(view.source.sample, new RegExp(`^${sinnerSaved.sample.matches_counted} matches`));
});

test("a report citing a tournament's record names the tournament", () => {
  const evidence: Evidence[] = [{ tool_call_id: "c1", tool: "season_path", input: {}, result: sinner() as never, error: null }];
  const stat: KeyStat = { label: "", value: 5, tool_call_id: "c1", field: "events.5.record.wins", sample_matches: 6 };
  assert.equal(checkStat(stat, evidence).status, "matched");
  assert.equal(describeStat(stat, evidence[0]).title, "Jannik Sinner: wins at Cincinnati Masters");
  assert.deepEqual(groupKeyStats([stat], evidence).map((g) => g.name), ["Recent form"]);
});
