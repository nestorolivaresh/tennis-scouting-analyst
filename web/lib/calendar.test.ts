// Expected values are read from the saved API response (fixtures/calendar-2025-indian-wells.json:
// GET /calendar?season=2025&event=404 from the local database) or written from the page's rules
// (D-036). No result is typed here.

import assert from "node:assert/strict";
import { test } from "node:test";
import saved from "./fixtures/calendar-2025-indian-wells.json" with { type: "json" };
import {
  type CalendarResponse,
  type Tournament,
  calendarHref,
  calendarUrl,
  finalView,
  historyView,
  monthGroups,
  parseCalendarQuery,
  seasonChoices,
  withEvent,
  withSeason,
} from "./calendar.ts";
import { MESSAGES } from "./i18n.ts";

const clone = (): CalendarResponse => structuredClone(saved) as unknown as CalendarResponse;

test("the address holds the season and an open tournament; the API judges both", () => {
  const query = parseCalendarQuery(new URLSearchParams("season=2025&event=404"));
  assert.deepEqual(query, { season: "2025", event: "404" });
  assert.equal(calendarHref(query), "/calendar?season=2025&event=404");
  assert.equal(calendarUrl(query), "/api/calendar?season=2025&event=404");
  assert.equal(calendarHref(withEvent(query, null)), "/calendar?season=2025");
  assert.equal(calendarHref(withSeason(query, 2019)), "/calendar?season=2019"); // a new season closes the history
  assert.equal(calendarUrl(parseCalendarQuery(new URLSearchParams(""))), "/api/calendar");
  assert.equal(calendarUrl(parseCalendarQuery(new URLSearchParams("season=abc"))), "/api/calendar?season=abc");
});

test("tournaments are grouped by the month they start in, in date order", () => {
  const groups = monthGroups(clone().calendar);
  assert.equal(groups.flatMap((g) => g.rows).length, saved.calendar.count);
  assert.equal(groups[0].title, "December 2024"); // the United Cup starts before the season's year (D-010)
  assert.equal(groups[1].title, "January 2025");
  const codes = groups.flatMap((g) => g.rows.map((r) => r.code));
  assert.deepEqual(codes, saved.calendar.tournaments.map((t) => t.event_code));
});

test("a final reads as who beat whom, with the score and links to both players", () => {
  const iw = clone().calendar.tournaments.find((t) => t.event_code === 404)!;
  const view = finalView(iw);
  const { winner, runner_up: runnerUp, score } = saved.calendar.tournaments.find((t) => t.event_code === 404)!.final!;
  assert.equal(view.text, `${winner.name} beat ${runnerUp.name}`);
  assert.equal(view.score, score);
  assert.equal(view.winner?.href, `/players?id=${winner.player_id}`);
  assert.equal(MESSAGES.en.calBeatOpponent(runnerUp.name, score), `beat ${runnerUp.name}, ${score}`);
  assert.equal(MESSAGES.es.calBeatOpponent("Rune", null), "venció a Rune");
  const row = monthGroups(clone().calendar).flatMap((g) => g.rows).find((r) => r.code === 404)!;
  assert.deepEqual([row.event, row.level, row.surface, row.swatch], ["Indian Wells Masters", "Masters 1000", "Hard", "sw-hard"]);
});

test("a team event, a missing final and an unclear one name no winner", () => {
  const united = clone().calendar.tournaments.find((t) => t.tournament === "United Cup")!;
  assert.deepEqual(finalView(united), { winner: null, runnerUp: null, text: "Team event: no single winner", score: null });
  const base = clone().calendar.tournaments[1];
  const missing: Tournament = { ...base, status: "no_final", final: null };
  assert.equal(finalView(missing).text, "No final in the data yet");
  assert.equal(finalView({ ...missing, status: "unclear" }).text, "The final's result is unclear in the data");
});

test("the history lists every edition, newest first, naming a year only when the name changed", () => {
  const view = historyView(clone().history!);
  assert.equal(view.title, "Indian Wells Masters through the years");
  assert.deepEqual(view.rows.map((r) => r.year), saved.history.editions.map((e) => e.season));
  assert.ok(view.rows.every((r) => r.name === null));
  const moved = clone().history!;
  moved.editions[3] = { ...moved.editions[3], tournament: "Somewhere Else" };
  assert.equal(historyView(moved).rows[3].name, "Somewhere Else");
});

test("the seasons to choose run from the data's first to its newest, newest first", () => {
  const seasons = seasonChoices(saved.calendar.data_window);
  assert.equal(seasons[0], Number(saved.calendar.data_window.last_tourney_date.slice(0, 4)));
  assert.equal(seasons[seasons.length - 1], Number(saved.calendar.data_window.first_tourney_date.slice(0, 4)));
  assert.deepEqual(seasonChoices({ first_tourney_date: null, last_tourney_date: null, last_match_date: null }), []);
});

test("the calendar reads in Spanish and French", () => {
  const es = monthGroups(clone().calendar, MESSAGES.es);
  assert.equal(es[1].title, "Enero de 2025");
  const fr = historyView(clone().history!, MESSAGES.fr);
  assert.equal(fr.title, "Indian Wells Masters au fil des ans");
  assert.match(fr.rows[0].final.text, / a battu /);
});
