// The loader's state, from event sequences shaped like a real POST /report/stream run: the tool
// calls are the saved report's own, in the order api/agent.py and api/report.py send them.

import assert from "node:assert/strict";
import { test } from "node:test";
import currentReport from "./fixtures/report-current.json" with { type: "json" };
import { ALL_SCORES, GAME_HOLD_MS, flapPosition, loaderState, loaderStatus, nextShot, reportHold } from "./loader.ts";
import { progressSteps } from "./progress.ts";
import type { Evidence, Report, ReportEvent, ReportResponse } from "./types.ts";

const report = currentReport as unknown as ReportResponse;
const { player, opponent } = report.request;
const names = new Map([[player.player_id, player.name], [opponent.player_id, opponent.name]]);
const verifiedReport = report.report as Report;

const start: ReportEvent = { event: "start", data: { request_id: report.request_id, request: report.request } };
const model = (call: number, tool_calls_so_far: number): ReportEvent => ({ event: "model_call", data: { call, tool_calls_so_far } });
const checking = (attempt: number): ReportEvent => ({ event: "checking", data: { attempt, key_stats: verifiedReport.key_stats.length } });
const correcting = (errors: number): ReportEvent => ({ event: "correcting", data: { errors } });
const toolCall = (e: Evidence): ReportEvent => ({ event: "tool_call", data: { id: e.tool_call_id, tool: e.tool, input: e.input } });
const toolResult = (e: Evidence, ok = true): ReportEvent => ({
  event: "tool_result",
  data: { id: e.tool_call_id, tool: e.tool, ok, error: ok ? null : "internal error in this tool" },
});
const lookup = (e: Evidence): ReportEvent[] => [toolCall(e), toolResult(e)];

const [first, second] = report.evidence;
const allLookups = report.evidence.flatMap(lookup);
const lookupCount = report.evidence.length;
const toTheReport = [start, model(1, 0), ...allLookups, model(2, lookupCount)];

const state = (events: ReportEvent[], final: ReportResponse | null = null, seconds = 0) => loaderState(events, final, seconds);
/** The stage after each event arrives, as the page sees them one at a time. */
const stagesAlong = (events: ReportEvent[]) => events.map((_, i) => state(events.slice(0, i + 1)).stage);

const WAITING_NOTE = "The report appears once every key number has been checked against the data.";

test("before any step has arrived the board is on 15, looking up the stats", () => {
  for (const events of [[], [start]]) {
    const s = state(events);
    assert.equal(s.stage, "look");
    assert.equal(s.score, "15");
    assert.deepEqual(s.scores, ["15", "30", "40", "Game"]);
    assert.equal(s.title, "Looking up the stats");
    assert.equal(s.note, `0 seconds so far. ${WAITING_NOTE}`);
    assert.equal(s.corrections, 0);
  }
  assert.equal(loaderStatus(state([]), []), "Starting");
});

test("a clean run goes look, write, check, in step with the events", () => {
  const run = [...toTheReport, checking(1)];
  assert.deepEqual(stagesAlong(run), [
    "look", // start
    "look", // the first model call chooses the stats
    ...Array(allLookups.length).fill("look"),
    "write", // the model call that nothing has followed
    "check",
  ]);
  assert.equal(state(toTheReport).score, "30");
  assert.equal(state(toTheReport).title, "Writing the report");
  assert.equal(state(run).score, "40");
  assert.equal(state(run).title, "Checking the numbers");
  assert.deepEqual(state(run).scores, ["15", "30", "40", "Game"]);
});

test("writing is not reached while lookups continue", () => {
  const secondRound = [start, model(1, 0), ...lookup(first), model(2, 1), toolCall(second)];
  assert.equal(state(secondRound).stage, "look"); // a lookup still out
  assert.equal(state([...secondRound, toolResult(second)]).stage, "look"); // the model hasn't been called since
  assert.equal(state([...secondRound, toolResult(second)]).title, "Looking up the stats");
  assert.equal(state([...secondRound, toolResult(second), model(3, 2)]).stage, "write");
  // While call 2 is running nothing yet shows that it will look up more; its tool_call settles it.
  assert.deepEqual(stagesAlong(secondRound).slice(-2), ["write", "look"]);
});

test("the first model call is choosing stats even with nothing after it", () => {
  assert.equal(state([start, model(1, 0)]).stage, "look");
});

test("a failed lookup doesn't change the stage and shows as failed on the card", () => {
  const failed = [start, model(1, 0), toolCall(first), toolResult(first, false)];
  assert.equal(state(failed).stage, "look");
  const steps = progressSteps(failed, names);
  assert.equal(steps[steps.length - 1].state, "failed");
  assert.match(loaderStatus(state(failed), steps), /\(failed\)$/);
  assert.equal(state([...failed, model(2, 1)]).stage, "write");
});

test("a correction goes check, deuce while rewriting, then advantage", () => {
  const run = [...toTheReport, checking(1), correcting(1), model(3, lookupCount), checking(2)];
  assert.deepEqual(stagesAlong(run).slice(-4), ["check", "deuce", "deuce", "adv"]);

  const failedCheck = state(run.slice(0, -2));
  assert.equal(failedCheck.score, "Deuce");
  assert.equal(failedCheck.title, "1 number didn't match; asking for a corrected report");
  assert.equal(failedCheck.corrections, 1);

  const rewriting = state(run.slice(0, -1));
  assert.equal(rewriting.stage, "deuce");
  assert.equal(rewriting.title, "Rewriting the report with the corrections");

  const again = state(run);
  assert.equal(again.score, "Ad");
  assert.equal(again.title, "Checking the numbers again");
  assert.deepEqual(again.scores, ["15", "30", "40", "Deuce", "Ad", "Game"]);
});

test("a later check always has its flap, so the window is never empty", () => {
  const s = state([...toTheReport, checking(2)]);
  assert.equal(s.stage, "adv");
  assert.equal(flapPosition("Ad", s), "now");
});

test("the short score list holds until a correction happens, then the long one stays", () => {
  const beforeCorrection = [...toTheReport, checking(1)];
  assert.equal(state(beforeCorrection).scores.includes("Deuce"), false);
  assert.equal(state([...beforeCorrection, correcting(2)]).scores.includes("Deuce"), true);
  assert.equal(state([...beforeCorrection, correcting(2)]).title, "2 numbers didn't match; asking for a corrected report");
  const finished = state([...beforeCorrection, correcting(2), model(3, lookupCount), checking(2)], report);
  assert.equal(finished.score, "Game");
  assert.deepEqual(finished.scores, ALL_SCORES);
});

test("more lookups during the rewrite stay on deuce", () => {
  const extra = report.evidence[2];
  const run = [...toTheReport, checking(1), correcting(1), model(3, lookupCount), toolCall(extra), toolResult(extra), model(4, lookupCount + 1)];
  assert.deepEqual(stagesAlong(run).slice(-5), ["deuce", "deuce", "deuce", "deuce", "deuce"]);
  assert.equal(state(run.slice(0, -1)).title, "Choosing more stats to look up");
  assert.equal(state(run).title, "Rewriting the report with the corrections");
});

test("a report that wasn't valid JSON corrects without a first check", () => {
  const run = [...toTheReport, correcting(1), model(3, lookupCount), checking(2)];
  assert.deepEqual(stagesAlong(run).slice(-4), ["write", "deuce", "deuce", "adv"]);
  assert.deepEqual(state(run).scores, ALL_SCORES);
});

test("a verified report is Game, and says how many numbers were checked", () => {
  const five = { ...report, report: { ...verifiedReport, key_stats: verifiedReport.key_stats.slice(0, 5) } };
  const s = state([...toTheReport, checking(1)], five, 21);
  assert.equal(s.stage, "done");
  assert.equal(s.score, "Game");
  assert.equal(s.title, "The report is ready");
  assert.equal(s.note, "All 5 key numbers match the stats data.");
  assert.equal(loaderStatus(s, progressSteps([...toTheReport, checking(1)], names)), "The report is ready");
});

test("an unverified or incomplete report never claims its numbers match", () => {
  const run = [...toTheReport, checking(1), correcting(1), model(3, lookupCount), checking(2)];
  const unverified: ReportResponse = { ...report, status: "unverified", grounding: { passed: false, attempts: 2, errors: ["stats.first_serve_in.value is wrong"] } };
  const incomplete: ReportResponse = { ...report, status: "incomplete", report: null, message: "The report hit a limit." };
  for (const final of [unverified, incomplete]) {
    const s = state(run, final, 30);
    assert.notEqual(s.stage, "done");
    assert.notEqual(s.score, "Game");
    assert.doesNotMatch(s.note, /match the stats data/);
  }
});

test("only a verified report waits on Game, and not with reduced motion", () => {
  assert.equal(reportHold(report, false), GAME_HOLD_MS);
  assert.equal(GAME_HOLD_MS, 1200);
  assert.equal(reportHold(report, true), 0);
  assert.equal(reportHold({ ...report, status: "unverified" }, false), 0);
  assert.equal(reportHold({ ...report, status: "incomplete", report: null }, false), 0);
});

test("the timer is in the note and never in the status line", () => {
  const run = [start, model(1, 0), toolCall(first)];
  const steps = progressSteps(run, names);
  assert.equal(state(run, null, 1).note, `1 second so far. ${WAITING_NOTE}`);
  assert.equal(state(run, null, 40).note, `40 seconds so far. ${WAITING_NOTE}`);
  assert.equal(loaderStatus(state(run, null, 1), steps), loaderStatus(state(run, null, 40), steps));
  assert.equal(loaderStatus(state(run, null, 40), steps), steps[steps.length - 1].text);
});

test("flaps: the one showing, the ones turned over, the ones waiting", () => {
  const positions = (s: ReturnType<typeof state>) => ALL_SCORES.map((label) => flapPosition(label, s));
  // On a clean run Deuce and Ad never leave their waiting place, even at Game.
  assert.deepEqual(positions(state([])), ["now", "next", "next", "next", "next", "next"]);
  assert.deepEqual(positions(state([...toTheReport, checking(1)], report)), ["past", "past", "past", "next", "next", "now"]);
  // A correction brings Deuce in from its waiting place.
  const failed = [...toTheReport, checking(1), correcting(1)];
  assert.deepEqual(positions(state(failed)), ["past", "past", "past", "now", "next", "next"]);
  assert.deepEqual(positions(state([...failed, model(3, lookupCount), checking(2)], report)), ["past", "past", "past", "past", "past", "now"]);
});

test("shots: the net clip plays once per correction, only at deuce", () => {
  assert.deepEqual(nextShot("look", 0, 0), { shot: "rally", clipped: 0 });
  assert.deepEqual(nextShot("deuce", 1, 0), { shot: "clip", clipped: 1 });
  assert.deepEqual(nextShot("deuce", 1, 1), { shot: "rally", clipped: 1 }); // already played for this one
  assert.deepEqual(nextShot("adv", 1, 0), { shot: "rally", clipped: 0 }); // too late: no longer at deuce
  assert.deepEqual(nextShot("deuce", 2, 1), { shot: "clip", clipped: 2 });
  assert.equal(nextShot("done", 1, 1).shot, "finish");
});
