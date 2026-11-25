// The page side of the check on numbers in model text (D-031): marks land on the characters the
// API named, a span that doesn't line up is dropped, and the lines say what the check found.
// Spans are written by hand from the API's contract (api/numbers.py: positions in the checked text).

import assert from "node:assert/strict";
import { test } from "node:test";
import { type LiveTurn, applyChatEvent, finishedAnnouncement } from "./chat.ts";
import { MESSAGES } from "./i18n.ts";
import { checkStat, describeStat, sourcePanel } from "./evidence.ts";
import { answerBlocks, answerCheckLine, citationsIn, citedStat, fieldCitations, fieldSpans, glued, pieces, spansIn, textCheckLine } from "./numbers.ts";
import { placedParts } from "./plan.ts";
import saved from "./fixtures/player-stats-clay-2025.json" with { type: "json" };
import type { Evidence, NumberSpan, ReportCitation, ReportNumberCheck } from "./types.ts";

const span = (full: string, text: string, from = 0): NumberSpan => {
  const start = full.indexOf(text, from);
  return { text, start, end: start + text.length };
};

function markedTexts(full: string, spans: NumberSpan[]): string[] {
  return answerBlocks(full)
    .flatMap((b) => (b.kind === "p" ? b.runs : b.items.flat()))
    .flatMap((run) => pieces(run.text, run.at, spans).filter((p) => p.marked).map((p) => p.text));
}

test("marks land on the named characters through bold and bullet lists", () => {
  const answer = "On clay, **Alcaraz** served **66.0%** in.\n- Won 75 matches\n* Lost 10 of 14 finals\n\nAnd 66.0% again.";
  const spans = [span(answer, "66.0%"), span(answer, "75"), span(answer, "10 of 14"), span(answer, "66.0%", answer.indexOf("And"))];
  assert.deepEqual(markedTexts(answer, spans), ["66.0%", "75", "10 of 14", "66.0%"]);
  const blocks = answerBlocks(answer);
  assert.deepEqual(blocks.map((b) => b.kind), ["p", "ul", "p"]);
  assert.deepEqual(blocks[0].kind === "p" && blocks[0].runs.map((r) => [r.text, r.bold]), [
    ["On clay, ", false], ["Alcaraz", true], [" served ", false], ["66.0%", true], [" in.", false],
  ]);
});

test("a mark that crosses a bold edge is split, not lost", () => {
  const answer = "He won **10** of 14.";
  assert.deepEqual(markedTexts(answer, [{ text: "10** of 14", start: 9, end: 19 }]), ["10", " of 14"]);
});

test("a span that doesn't line up with the text is dropped", () => {
  const text = "Won 75 matches.";
  assert.deepEqual(spansIn(text, [{ text: "75", start: 4, end: 6 }, { text: "76", start: 4, end: 6 }, { text: "75", start: -1, end: 1 }]), [
    { text: "75", start: 4, end: 6 },
  ]);
  assert.deepEqual(pieces(text, 0, []), [{ text, marked: false, cite: null }]);
});

test("a report field gets only its own spans", () => {
  const check: ReportNumberCheck = {
    checked: 4,
    not_found: [
      { field: "strengths.1", text: "70.2%", start: 6, end: 11 },
      { field: "strengths.10", text: "70.2%", start: 6, end: 11 },
    ],
  };
  assert.deepEqual(fieldSpans(check, "strengths.1", "Holds 70.2% of service games."), [{ field: "strengths.1", text: "70.2%", start: 6, end: 11 }]);
  assert.deepEqual(fieldSpans(check, "strengths.0", "Holds 70.2% of service games."), []);
  assert.deepEqual(fieldSpans(undefined, "summary", "x"), []);
});

test("a game plan point's parts keep their place, the inference after capitalizing", () => {
  const point = "Serve wide on the deuce side. He won 61.6% there. Coaching inference: aim for 66.0% wide.";
  const { head, body, inference } = placedParts(point);
  assert.equal(point.slice(head.at, head.at + head.text.length), head.text);
  assert.equal(point.slice(body.at, body.at + body.text.length), body.text);
  assert.equal(inference?.text, "Aim for 66.0% wide.");
  const spans = [span(point, "66.0%")];
  assert.deepEqual(pieces(inference!.text, inference!.at, spans).filter((p) => p.marked).map((p) => p.text), ["66.0%"]);
  assert.deepEqual(pieces(body.text, body.at, spans).filter((p) => p.marked), []);
});

test("the line under an answer says what the check found, in each language", () => {
  const missing = { checked: 6, not_found: [{ text: "66.0%", start: 0, end: 5 }, { text: "10 of 14", start: 9, end: 17 }, { text: "75", start: 20, end: 22 }] };
  assert.equal(answerCheckLine(missing), "Not found in the data this answer looked up: 66.0%, 10 of 14 and 75. They're underlined.");
  assert.equal(answerCheckLine({ checked: 1, not_found: [missing.not_found[2]] }), "Not found in the data this answer looked up: 75. It's underlined.");
  assert.equal(answerCheckLine({ checked: 9, not_found: [] }), "All 9 numbers in this answer were found in the data it looked up or in your questions.");
  assert.equal(answerCheckLine({ checked: 0, not_found: [] }), null);
  assert.equal(answerCheckLine(undefined), null); // the answer never finished
  assert.equal(answerCheckLine(null), "The numbers in this answer couldn't be checked."); // the check failed
  assert.equal(answerCheckLine(missing, MESSAGES.es), "No están en los datos que consultó esta respuesta: 66.0%, 10 of 14 y 75. Aparecen subrayadas.");
  assert.equal(answerCheckLine({ checked: 2, not_found: [] }, MESSAGES.fr), "Les 2 chiffres de cette réponse figurent dans les données consultées ou dans vos questions.");
});

test("the report's status says what the check found in its text", () => {
  assert.equal(textCheckLine({ checked: 12, not_found: [] }), "All 12 numbers in the written text were found in the stats data.");
  assert.equal(
    textCheckLine({ checked: 12, not_found: [{ field: "summary", text: "123.4%", start: 0, end: 6 }] }),
    "One number in the written text wasn't found in the stats data: 123.4%. It's underlined.",
  );
  assert.equal(textCheckLine({ checked: 0, not_found: [] }), null);
  assert.equal(textCheckLine(null), "The written text around them isn't checked the same way."); // the check failed
  assert.equal(textCheckLine(undefined), "The written text around them isn't checked the same way."); // saved before the check
});

test("a finished answer keeps its check, and a screen reader hears it once", () => {
  const turn: LiveTurn = { role: "assistant", content: "Won 75.", complete: false, activity: [], done: false };
  const numbers = { checked: 1, not_found: [{ text: "75", start: 4, end: 6 }] };
  const done = applyChatEvent(turn, { event: "done", data: { outcome: "completed", message: null, numbers } });
  assert.deepEqual(done.numbers, numbers);
  assert.equal(finishedAnnouncement(done), "Won 75. Not found in the data this answer looked up: 75. It's underlined.");
  assert.equal(finishedAnnouncement(turn), "");
});

test("a cited number is its own piece, and a record made of two is marked across both", () => {
  const text = "He went 11-3 and served 61.6%.";
  const cites = [{ start: 8, end: 10 }, { start: 11, end: 12 }, { start: 24, end: 29 }];
  const marks = [{ text: "11-3", start: 8, end: 12 }];
  assert.deepEqual(pieces(text, 0, marks, cites), [
    { text: "He went ", marked: false, cite: null },
    { text: "11", marked: true, cite: 0 },
    { text: "-", marked: true, cite: null },
    { text: "3", marked: true, cite: 1 },
    { text: " and served ", marked: false, cite: null },
    { text: "61.6%", marked: false, cite: 2 },
    { text: ".", marked: false, cite: null },
  ]);
  assert.deepEqual(pieces("served 61.6%.", 17, [], cites).filter((p) => p.cite !== null).map((p) => [p.text, p.cite]), [["61.6%", 2]]);
});

test("citations outside the text are dropped, and a report field gets only its own", () => {
  const cites: ReportCitation[] = [
    { text_field: "summary", text: "61.6", start: 0, end: 4, tool_call_id: "c1", field: "record.wins" },
    { text_field: "summary", text: "61.6", start: 30, end: 34, tool_call_id: "c1", field: "record.wins" },
    { text_field: "game_plan.0", text: "61.6", start: 0, end: 4, tool_call_id: "c1", field: "record.wins" },
  ];
  assert.deepEqual(fieldCitations(cites, "summary", "61.6% in."), [cites[0]]);
  const at = (text: string, start: number, end: number) => ({ text, start, end, tool_call_id: "c1", field: "x" });
  assert.deepEqual(citationsIn("ab", [at("ab", 0, 3), at("b", 0, 1), at("a", 0, 1)]), [at("a", 0, 1)]); // must line up
  assert.deepEqual(fieldCitations(undefined, "summary", "x"), []);
});

test("a cited number's source reads like a key number's, from the tool result alone", () => {
  // Expected words from the saved response (fixtures/player-stats-clay-2025.json: Alcaraz, clay 2025).
  const evidence: Evidence[] = [{ tool_call_id: "c1", tool: "shot_patterns", input: {}, result: saved.shots as never, error: null }];
  const stat = citedStat({ text: "59.6%", start: 0, end: 5, tool_call_id: "c1", field: "serve_direction.first_serves_in.deuce.wide.value" });
  const check = checkStat(stat, evidence);
  assert.equal(describeStat(stat, check.evidence).title, "Carlos Alcaraz: first serves in on the deuce court going wide");
  assert.equal(sourcePanel(stat, check)?.value, "267 of 448, 59.6%");
  assert.equal(checkStat(citedStat({ text: "1", start: 0, end: 1, tool_call_id: "c9", field: "x" }), evidence).status, "missing");
});

test("a finished answer keeps its citations and their evidence", () => {
  const turn: LiveTurn = { role: "assistant", content: "Won 11.", complete: false, activity: [], done: false };
  const citations = [{ text: "11", start: 4, end: 6, tool_call_id: "c1", field: "record.wins" }];
  const evidence: Evidence[] = [{ tool_call_id: "c1", tool: "head_to_head", input: {}, result: null, error: "x" }];
  const done = applyChatEvent(turn, { event: "done", data: { outcome: "completed", message: null, citations, evidence } });
  assert.deepEqual([done.citations, done.evidence], [citations, evidence]);
});

test("a cited tour median reads on its card as in the text", () => {
  // Found by the review: the card showed 0.6234 where the text said 62.3%.
  const result = { tool: "tour_comparison", player: { player_id: 1, name: "A" }, stats: {
    service_points_won: { value: { value: 0.65, numerator: 65, denominator: 100, unit: "fraction" }, rank: 3, players_ranked: 10, tour_median: 0.6234 },
    aces_per_match: { value: { value: 4.4, numerator: 44, denominator: 10, unit: "per_match" }, rank: 2, players_ranked: 10, tour_median: 3.25 },
  } };
  const evidence: Evidence[] = [{ tool_call_id: "c1", tool: "tour_comparison", input: {}, result: result as never, error: null }];
  const panel = (field: string) => {
    const stat = citedStat({ text: "", start: 0, end: 0, tool_call_id: "c1", field });
    return sourcePanel(stat, checkStat(stat, evidence))?.value;
  };
  assert.equal(panel("stats.service_points_won.tour_median"), "62.3%");
  assert.equal(panel("stats.aces_per_match.tour_median"), "3.3");
});

// ---------- keeping punctuation with a cited number ----------

test("a cited number keeps the punctuation that touches it on its line", () => {
  const list = [
    { text: "from (", marked: false, cite: null },
    { text: "75", marked: false, cite: 0 },
    { text: ") charted matches, and ", marked: false, cite: null },
    { text: "122", marked: false, cite: 1 },
    { text: ".", marked: false, cite: null },
  ];
  const out = glued(list);
  assert.deepEqual(out.map((p) => [p.lead, p.text, p.tail]), [
    ["", "from ", ""],
    ["(", "75", ")"],
    ["", " charted matches, and ", ""],
    ["", "122", "."],
    ["", "", ""],
  ]);
  assert.equal(out.map((p) => p.lead + p.text + p.tail).join(""), list.map((p) => p.text).join("")); // no text lost or added
});

test("punctuation marked differently, a space, or another citation stays where it is", () => {
  const marked = glued([{ text: "(", marked: true, cite: null }, { text: "75", marked: false, cite: 0 }]);
  assert.deepEqual([marked[0].text, marked[1].lead], ["(", ""]);
  const spaced = glued([{ text: "( ", marked: false, cite: null }, { text: "75", marked: false, cite: 0 }]);
  assert.equal(spaced[1].lead, "");
  const record = glued([{ text: "11", marked: false, cite: 0 }, { text: "-", marked: false, cite: null }, { text: "3", marked: false, cite: 1 }]);
  assert.deepEqual(record.map((p) => [p.lead, p.text, p.tail]), [["", "11", ""], ["", "-", ""], ["", "3", ""]]);
});
