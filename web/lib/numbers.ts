// The API's check on the numbers in model text (D-031), turned into what the page shows: which
// parts of a piece of text to mark, and one line saying what the check found. The check itself
// runs on the server (api/numbers.py), where the evals measure it.

import { EN, type T } from "./i18n.ts";
import type { Citation, KeyStat, NumberCheck, NumberSpan, ReportCitation, ReportNumberCheck } from "./types.ts";

/** The spans that really are where they say in `text`. A span that doesn't line up is dropped,
 * so a mark can never land on the wrong words; the check's line still names it. */
export function spansIn(text: string, spans: readonly NumberSpan[]): NumberSpan[] {
  return spans.filter((s) => s.start >= 0 && s.end > s.start && text.slice(s.start, s.end) === s.text);
}

export interface Piece {
  text: string;
  marked: boolean; // inside a number the check didn't find
  cite: number | null; // inside citation `cite` of the list given
}

type Range = { start: number; end: number };

/** A part of a checked text, starting at `at` in it, split where a mark or a citation starts or
 * ends. A record made of two citations and not found is marked across both. */
export function pieces(part: string, at: number, spans: readonly Range[], cites: readonly Range[] = []): Piece[] {
  const cuts = new Set([0, part.length]);
  for (const r of [...spans, ...cites]) {
    for (const edge of [r.start - at, r.end - at]) if (edge > 0 && edge < part.length) cuts.add(edge);
  }
  const edges = [...cuts].sort((a, b) => a - b);
  const out: Piece[] = [];
  for (let i = 0; i + 1 < edges.length; i += 1) {
    const [from, to] = [at + edges[i], at + edges[i + 1]];
    const marked = spans.some((s) => s.start <= from && to <= s.end);
    const index = cites.findIndex((c) => c.start <= from && to <= c.end);
    const cite = index < 0 ? null : index;
    const last = out[out.length - 1];
    const text = part.slice(edges[i], edges[i + 1]);
    if (last && last.marked === marked && last.cite === cite) last.text += text;
    else out.push({ text, marked, cite });
  }
  return out.length ? out : [{ text: part, marked: false, cite: null }];
}

export interface GluedPiece extends Piece {
  lead: string; // opening punctuation just before a cited number, kept on its line
  tail: string; // closing punctuation just after it
}

const OPENING = /[([{“‘"'¿¡«]+$/;
const CLOSING = /^[)\]}”’"'.,;:!?%»]+/;

/** Each piece, with the punctuation that touches a cited number moved next to it, so a line can't
 * break between "(" and the number or between the number and ")" (a cited number is a button,
 * and a line may break on either side of one). Only punctuation marked the same way moves, so a
 * mark still covers exactly what it did. */
export function glued(list: readonly Piece[]): GluedPiece[] {
  const out: GluedPiece[] = list.map((p) => ({ ...p, lead: "", tail: "" }));
  out.forEach((piece, i) => {
    if (piece.cite === null) return;
    const [before, after] = [out[i - 1], out[i + 1]];
    const lead = before && before.cite === null && before.marked === piece.marked ? before.text.match(OPENING)?.[0] : undefined;
    if (before && lead) {
      piece.lead = lead;
      before.text = before.text.slice(0, -lead.length);
    }
    const tail = after && after.cite === null && after.marked === piece.marked ? after.text.match(CLOSING)?.[0] : undefined;
    if (after && tail) {
      piece.tail = tail;
      after.text = after.text.slice(tail.length);
    }
  });
  return out;
}

/** The citations that really are where they say in `text` (D-032); like a mark, one that
 * doesn't line up is dropped, so a button can never land on the wrong words. */
export function citationsIn<C extends Citation>(text: string, cites: readonly C[]): C[] {
  return cites.filter((c) => c.start >= 0 && c.end > c.start && c.end <= text.length && text.slice(c.start, c.end) === c.text);
}

/** One report field's citations, as positions in that field's text. */
export function fieldCitations(cites: readonly ReportCitation[] | undefined, field: string, text: string): ReportCitation[] {
  return citationsIn(text, (cites ?? []).filter((c) => c.text_field === field));
}

/** A cited number as a key stat, so its source reads like a key number's (checkStat,
 * sourcePanel). It states no value or sample of its own: both come from the tool result. */
export function citedStat(cite: Citation): KeyStat {
  return { label: "", value: Number.NaN, tool_call_id: cite.tool_call_id, field: cite.field, sample_matches: Number.NaN };
}

/** One report field's spans ("summary", "strengths.0"), checked against that field's text. */
export function fieldSpans(check: ReportNumberCheck | null | undefined, field: string, text: string): NumberSpan[] {
  if (!check) return [];
  return spansIn(text, check.not_found.filter((s) => s.field === field));
}

/** The line under a finished chat answer: what the check found, or that it couldn't run (null).
 * Nothing for an answer with no numbers, or one that never finished (undefined). */
export function answerCheckLine(check: NumberCheck | null | undefined, t: T = EN): string | null {
  if (check === null) return t.answerNotChecked;
  if (!check || check.checked === 0) return null;
  const missing = check.not_found.map((s) => s.text);
  return missing.length ? t.answerNumbersNotFound(missing) : t.answerNumbersFound(check.checked);
}

/** The sentence about a finished report's written text, next to its status. A report written
 * before the check existed (undefined), or whose check failed (null), says its text wasn't
 * checked. */
export function textCheckLine(check: ReportNumberCheck | null | undefined, t: T = EN): string | null {
  if (check === undefined || check === null) return t.textNotChecked;
  if (check.checked === 0) return null;
  const missing = check.not_found.map((s) => s.text);
  return missing.length ? t.textNumbersNotFound(missing) : t.textNumbersFound(check.checked);
}

// ---------- a chat answer's layout, with positions ----------

/** A run of answer text, `at` its position in the whole answer. */
export interface Run {
  text: string;
  at: number;
  bold: boolean;
}

export type Block = { kind: "p"; runs: Run[] } | { kind: "ul"; items: Run[][] };

/** The chat model sometimes answers with **bold** and "- " bullet lists: just those two are laid
 * out, and every run keeps its position in the answer, so a mark lands where the check said. */
export function answerBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  let items: Run[][] = [];
  const flush = () => {
    if (items.length) blocks.push({ kind: "ul", items });
    items = [];
  };
  const runs = (line: string, at: number): Run[] => {
    let offset = at;
    return line.split(/(\*\*[^*]+\*\*)/g).flatMap((part) => {
      const start = offset;
      offset += part.length;
      if (!part) return [];
      const bold = part.startsWith("**") && part.endsWith("**") && part.length > 4;
      return [bold ? { text: part.slice(2, -2), at: start + 2, bold } : { text: part, at: start, bold }];
    });
  };
  let at = 0;
  for (const line of text.split("\n")) {
    const bullet = line.match(/^(\s*[-*]\s+)(.*)$/);
    if (bullet) {
      items.push(runs(bullet[2], at + bullet[1].length));
    } else {
      flush();
      if (line.trim()) blocks.push({ kind: "p", runs: runs(line, at) });
    }
    at += line.length + 1;
  }
  flush();
  return blocks;
}
