// Splitting the model's game-plan points, the figures allowed beside them, and how a streamed
// chat answer ends. Fixtures are real /report responses; expected figures are read from their
// tool results or from the model's own text, never typed in as statistics.

import assert from "node:assert/strict";
import { test } from "node:test";
import currentReport from "./fixtures/report-current.json" with { type: "json" };
import { CUT_OFF_MESSAGE, type LiveTurn, applyChatEvent, closeTurn, contextLabel, finishedAnnouncement, reportContext } from "./chat.ts";
import { type CheckedPercent, checkedPercents, round1, serveChart, shortNames } from "./evidence.ts";
import { capitalized, findFigure, parsePlanItem } from "./plan.ts";
import type { ReportResponse } from "./types.ts";

const current = currentReport as unknown as ReportResponse;
const { player, opponent, surface } = current.request;
const window = current.request;
const names = shortNames(player, opponent);
const plan = current.report!.game_plan;
const checked = checkedPercents(current);

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const squeeze = (text: string) => text.replace(/\s+/g, " ").trim();

test("a normal game-plan point splits into head, body and inference", () => {
  assert.deepEqual(parsePlanItem(plan[0]), {
    head: "Hold serve through first-serve points.",
    body: plan[0].slice(plan[0].indexOf("Sinner wins"), plan[0].indexOf(" Coaching inference")),
    inference: plan[0].slice(plan[0].indexOf("protect that")),
  });
});

test("a point with no inference keeps everything in the head and body", () => {
  const last = plan[plan.length - 1];
  assert.ok(!/coaching inference/i.test(last));
  const parsed = parsePlanItem(last);
  assert.equal(parsed.inference, null);
  assert.equal(squeeze(`${parsed.head} ${parsed.body}`), squeeze(last));
});

test("a decimal or a score never ends the first sentence", () => {
  assert.equal(parsePlanItem("Sinner wins 75.7% of first-serve points. He leads.").head, "Sinner wins 75.7% of first-serve points.");
  assert.equal(parsePlanItem(plan[3]).head, "Use the Monte Carlo 2026 template, which Sinner won 7-6(5) 6-3.");
  assert.equal(parsePlanItem("He won 7-6(5). Then he lost.").head, "He won 7-6(5).");
  assert.equal(parsePlanItem("Win 6-4 7-6(3) at 68.7%. Then rest.").body, "Then rest.");
  assert.equal(parsePlanItem("Beat the No. 1 seed in St. Petersburg vs. J. Sinner. Then rest.").head, "Beat the No. 1 seed in St. Petersburg vs. J. Sinner.");
});

test("the inference is found whatever its case or spacing", () => {
  for (const marker of ["Coaching inference:", "coaching inference:", "COACHING INFERENCE:", "Coaching  Inference :"]) {
    assert.deepEqual(parsePlanItem(`Serve wide. ${marker} go to the body.`), { head: "Serve wide.", body: "", inference: "go to the body." });
  }
});

test("text that doesn't fit is rendered whole, with nothing lost", () => {
  const cases = [
    "Serve wide on the ad side",
    "Serve wide. Coaching inference:",
    "Coaching inference: be patient.",
    "One. Coaching inference: first. Coaching inference: second.",
    "lower case start. and no capitals after.",
    "...",
    "",
  ];
  for (const text of [...cases, ...plan, ...current.report!.strengths, ...current.report!.weaknesses]) {
    const { head, body, inference } = parsePlanItem(text);
    const rebuilt = [head, body, inference === null ? "" : `Coaching inference: ${inference}`].filter(Boolean).join(" ");
    assert.equal(squeeze(rebuilt).toLowerCase(), squeeze(text).replace(/coaching\s+inference\s*:/gi, "coaching inference:").toLowerCase(), text);
  }
  assert.equal(parsePlanItem("Serve wide on the ad side").head, "Serve wide on the ad side");
  assert.deepEqual(parsePlanItem("Coaching inference: be patient."), { head: "", body: "", inference: "be patient." });
  assert.equal(capitalized("protect that edge"), "Protect that edge");
});

test("a figure comes from the text only when the evidence has that value", () => {
  const firstServe = serveChart(current.evidence, player, opponent, surface, window).rows.find((r) => r.metric === "First-serve points won")!;
  const figure = findFigure(plan[0], checked, names)!;
  assert.equal(figure.text, `${firstServe.player!.toFixed(1)}%`);
  assert.equal(figure.sub, `against ${firstServe.opponent!.toFixed(1)}% for ${names.opponent}`);
  assert.equal(figure.sample, firstServe.playerSample);

  const secondServe = serveChart(current.evidence, player, opponent, surface, window).rows.find((r) => r.metric === "Second-serve points won")!;
  assert.deepEqual([findFigure(plan[1], checked, names)!.text, findFigure(plan[1], checked, names)!.sub],
    [`${secondServe.opponent!.toFixed(1)}%`, `${names.opponent}, against ${secondServe.player!.toFixed(1)}% for ${names.player}`]);
});

test("a number that isn't in the evidence gives no figure", () => {
  assert.equal(findFigure("Hold serve. Sinner wins 12.3% of something.", checked, names), null);
  assert.equal(findFigure(plan[3], checked, names), null); // scores and counts are not figures
  assert.equal(findFigure(plan[4], checked, names), null);
  assert.equal(findFigure("Hold serve.", [], names), null);
});

test("only exact one-decimal percentages are read, and the first checked one is used", () => {
  assert.equal(findFigure(plan[2], checked, names)!.text.endsWith(".0%"), true); // "about 46%" is skipped
  const value = checked.find((c) => c.side === "player")!.value;
  assert.equal(findFigure(`Serve. It was ${value}0% there.`, checked, names), null);
  assert.equal(findFigure(`Serve. It was 1${value}% there.`, checked, names), null);
  assert.equal(findFigure(`Serve. Not 12.3% but ${value}% there.`, checked, names)!.text, `${value}%`);
});

test("the coach's inference never supplies a figure", () => {
  const value = checked[0].value;
  assert.equal(findFigure(`Hold serve. Coaching inference: aim for ${value}% here.`, checked, names), null);
});

test("a mismatched key number is not a checked value", () => {
  const fromKeyStats = (data: ReportResponse) => checkedPercents(data).filter((c) => c.side === null).map((c) => c.value);
  const data = clone(current);
  const stat = data.report!.key_stats[0];
  const toolValue = round1(100 * stat.value).toFixed(1);
  assert.ok(fromKeyStats(current).includes(toolValue));
  stat.value = 0.123; // the model's figure no longer matches the tool's
  assert.ok(!fromKeyStats(data).includes(toolValue));
  assert.equal(fromKeyStats(data).length, fromKeyStats(current).length - 1);
});

test("the comparison is left out when the same value sits in two rows and the text doesn't settle it", () => {
  const twice: CheckedPercent[] = [
    { value: "64.5", side: "opponent", against: "69.8", sample: 29 },
    { value: "64.5", side: "player", against: "65.7", sample: 32 },
  ];
  assert.deepEqual(findFigure("He wins 64.5% of them.", twice, names), { text: "64.5%", sub: null, sample: null, small: false });
  assert.equal(findFigure("He wins 64.5% against 69.8%.", twice, names)!.sub, `${names.opponent}, against 69.8% for ${names.player}`);
});

test("a figure resting on under 10 matches is marked small", () => {
  const few: CheckedPercent[] = [{ value: "50.0", side: "player", against: "40.0", sample: 9 }];
  assert.equal(findFigure("Serve. He wins 50.0% against 40.0%.", few, names)!.small, true);
  assert.equal(findFigure("Serve. He wins 50.0% against 40.0%.", [{ ...few[0], sample: 10 }], names)!.small, false);
});

// ---------- chat ----------

const answer = (over: Partial<LiveTurn> = {}): LiveTurn => ({ role: "assistant", content: "", complete: false, activity: [], done: false, ...over });

test("chat context is the report as a first exchange, and nothing for an unfinished report", () => {
  const context = reportContext(current);
  assert.deepEqual(context.map((m) => m.role), ["user", "assistant"]);
  assert.ok(context[1].content.includes(current.report!.summary));
  assert.deepEqual(reportContext({ ...current, report: null }), []);
  assert.equal(contextLabel(current), `${opponent.name} for ${player.name}, ${surface.toLowerCase()}`);
});

test("a chat answer that stops early is marked and never counts as complete", () => {
  const partial = applyChatEvent(answer(), { event: "text", data: { delta: "Sinner " } });
  const stopped = applyChatEvent(partial, { event: "done", data: { outcome: "max_tokens", message: "It ran out of room." } });
  assert.deepEqual([stopped.done, stopped.complete, stopped.error, stopped.content], [true, false, "It ran out of room.", "Sinner "]);
  const fine = applyChatEvent(partial, { event: "done", data: { outcome: "completed", message: null } });
  assert.deepEqual([fine.done, fine.complete, fine.error], [true, true, undefined]);
  const failed = applyChatEvent(partial, { event: "error", data: { kind: "stream_cut", message: "Cut." } });
  assert.deepEqual([failed.done, failed.complete, failed.error], [true, false, "Cut."]);
});

test("a stream that ends without a final event is closed as cut off, and a finished answer is left alone", () => {
  const cut = closeTurn(answer({ content: "Sinner " }), CUT_OFF_MESSAGE);
  assert.deepEqual([cut.done, cut.complete, cut.error, cut.content], [true, false, CUT_OFF_MESSAGE, "Sinner "]);
  const finished = answer({ content: "Done.", complete: true, done: true });
  assert.equal(closeTurn(finished, "Stopped."), finished);
});

test("an answer is announced once: nothing while it streams, all of it when it ends", () => {
  assert.equal(finishedAnnouncement(answer({ content: "Half of an" })), "");
  assert.equal(finishedAnnouncement(answer({ content: "All of it.", done: true, complete: true })), "All of it.");
  assert.equal(finishedAnnouncement(answer({ content: "Half.", done: true, error: "Stopped." })), "Half. Stopped.");
  assert.equal(finishedAnnouncement(undefined), "");
});
