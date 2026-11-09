// The event stream: the parser, the report client (with a stand-in fetch), the progress steps,
// and the chat history sent with each question.

import assert from "node:assert/strict";
import { test } from "node:test";
import currentReport from "./fixtures/report-current.json" with { type: "json" };
import { ApiFailure, streamReport } from "./api.ts";
import { MAX_CHARS, MAX_PAIRS, type Turn, buildHistory } from "./chat.ts";
import { progressSteps } from "./progress.ts";
import { SseParser } from "./sse.ts";
import type { ReportEvent, ReportResponse } from "./types.ts";

const report = currentReport as unknown as ReportResponse;
const { player, opponent } = report.request;

test("the parser handles events split anywhere, CRLF and CR line endings, and comments", () => {
  const parser = new SseParser();
  const text = ': keep-alive\r\n\r\nevent: start\r\ndata: {"request_id": "abc"}\r\n\r\nevent: text\rdata: {"delta": "Hi"}\r\r';
  const events = [...[...text].flatMap((char) => parser.feed(char)), ...parser.finish()]; // one character at a time
  assert.deepEqual(events, [
    { event: "start", data: { request_id: "abc" } },
    { event: "text", data: { delta: "Hi" } },
  ]);
  assert.equal(parser.incomplete, false);
  parser.feed('event: text\ndata: {"del');
  assert.equal(parser.incomplete, true);
});

function fakeFetch(body: string, status = 200) {
  return async () => new Response(body, { status, headers: { "content-type": status === 200 ? "text/event-stream" : "application/json" } });
}

const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

test("streamReport passes progress on and resolves with the checked report", async (t) => {
  const seen: string[] = [];
  t.mock.method(globalThis, "fetch", fakeFetch(sse("start", { request_id: "r", request: report.request })
    + ": keep-alive\n\n" + sse("model_call", { call: 1, tool_calls_so_far: 0 }) + sse("report", report)));
  const result = await streamReport({ player_id: 1, opponent_id: 2, surface: "Clay" }, (e) => seen.push(e.event));
  assert.deepEqual(seen, ["start", "model_call"]);
  assert.equal(result.request_id, report.request_id);
});

test("streamReport turns an error event, a cut stream and a 4xx into ApiFailure", async (t) => {
  const body = { player_id: 1, opponent_id: 2, surface: "Clay" as const };
  t.mock.method(globalThis, "fetch", fakeFetch(sse("error", { kind: "model_rate_limited", message: "Slow down." })));
  await assert.rejects(streamReport(body, () => {}), (e: unknown) => e instanceof ApiFailure && e.kind === "model_rate_limited");
  t.mock.method(globalThis, "fetch", fakeFetch(sse("start", { request_id: "r", request: report.request })));
  await assert.rejects(streamReport(body, () => {}), (e: unknown) => e instanceof ApiFailure && e.kind === "stream_cut");
  t.mock.method(globalThis, "fetch", fakeFetch(JSON.stringify({ error: { kind: "player_not_found", message: "no player" } }), 404));
  await assert.rejects(streamReport(body, () => {}), (e: unknown) => e instanceof ApiFailure && e.message === "no player");
});

test("progress: each real step, the newest one in progress, failures marked", () => {
  const names = new Map([[player.player_id, player.name], [opponent.player_id, opponent.name]]);
  const events: ReportEvent[] = [
    { event: "start", data: { request_id: "r", request: report.request } },
    { event: "model_call", data: { call: 1, tool_calls_so_far: 0 } },
    { event: "tool_call", data: { id: "c1", tool: "surface_splits", input: { player_id: player.player_id, filters: {} } } },
    { event: "tool_result", data: { id: "c1", tool: "surface_splits", ok: true, error: null } },
    { event: "tool_call", data: { id: "c2", tool: "head_to_head", input: { player_id: player.player_id, opponent_id: opponent.player_id } } },
  ];
  assert.deepEqual(progressSteps(events, names).map((s) => [s.text, s.state]), [
    ["Choosing which stats to look up", "done"],
    [`Win-loss by surface: ${player.name}, every surface`, "done"],
    [`Head-to-head: ${player.name} and ${opponent.name}`, "active"],
  ]);
  const later = progressSteps([
    ...events,
    { event: "tool_result", data: { id: "c2", tool: "head_to_head", ok: false, error: "internal error in this tool" } },
    { event: "model_call", data: { call: 2, tool_calls_so_far: 2 } },
    { event: "tool_call", data: { id: "c3", tool: "serve_return_stats", input: { player_id: opponent.player_id, filters: {} } } },
    { event: "tool_result", data: { id: "c3", tool: "serve_return_stats", ok: true, error: null } },
    { event: "model_call", data: { call: 3, tool_calls_so_far: 3 } },
    { event: "checking", data: { attempt: 1, key_stats: 6 } },
    { event: "correcting", data: { errors: 1 } },
    { event: "model_call", data: { call: 4, tool_calls_so_far: 3 } },
  ], names);
  assert.deepEqual(later.slice(2).map((s) => [s.text, s.state]), [
    [`Head-to-head: ${player.name} and ${opponent.name} (failed)`, "failed"],
    ["Choosing more stats to look up", "done"], // a model call followed by more lookups
    [`Serve and return stats: ${opponent.name}, all surfaces`, "done"],
    ["Writing the report", "done"],
    ["Checking 6 key numbers against the data", "done"],
    ["1 number didn't match; asking for a corrected report", "done"],
    ["Rewriting the report with the corrections", "active"],
  ]);
});

// ---------- chat history ----------

const turn = (role: Turn["role"], content: string, complete = true): Turn => ({ role, content, complete });
const context = [
  { role: "user" as const, content: "Write a scouting report." },
  { role: "assistant" as const, content: "The report." },
];

test("chat history: context, complete pairs, then the question, alternating from the user", () => {
  const history = buildHistory(context, [turn("user", "q1"), turn("assistant", "a1"), turn("user", "q2"), turn("assistant", "cut off", false)], "q3");
  assert.deepEqual(history.map((m) => m.content), ["Write a scouting report.", "The report.", "q1", "a1", "q3"]); // never the cut-off answer
  history.forEach((m, i) => assert.equal(m.role, i % 2 === 0 ? "user" : "assistant"));
});

test("chat history stays within the API's limits", () => {
  const long = "x".repeat(10_000);
  const turns = Array.from({ length: 30 }, (_, i) => turn(i % 2 === 0 ? "user" : "assistant", long));
  const history = buildHistory(context, turns, long);
  assert.ok(history.length <= 21 && history.length <= context.length + 2 * MAX_PAIRS + 1);
  assert.ok(history.every((m) => m.content.length <= MAX_CHARS));
  assert.ok(history.reduce((n, m) => n + m.content.length, 0) <= 30_000);
  assert.equal(history[history.length - 1].role, "user");
});
