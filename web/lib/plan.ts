// The model writes game-plan points and scouting notes as free text. This splits a point into
// its parts for display, and finds the figure to show beside it. A figure is shown only when the
// same percentage is in the report's checked values; the text alone never puts a number on screen.

import { type CheckedPercent, isSmallSample } from "./evidence.ts";
import { EN, type T } from "./i18n.ts";

export interface PlanItem {
  head: string; // the first sentence
  body: string;
  inference: string | null; // what follows "Coaching inference:"
}

const INFERENCE = /coaching\s+inference\s*:/i;

// Sentence-ending punctuation before a space and something that can start a sentence. Decimals
// ("75.7%") have no space after the point; scores ("7-6(5)") have no point at all.
const SENTENCE_END = /[.!?]+["'”’»)\]]*(?=\s+["'“‘«¿¡(\[]?[\p{Lu}\d])/gu;
const ABBREVIATIONS = new Set(["st", "vs", "v", "mr", "mrs", "dr", "jr", "sr", "mt", "ft", "e.g", "i.e"]);

function isAbbreviation(word: string, following: string): boolean {
  const bare = word.replace(/^["'“‘(\[]+/, "");
  if (/^\p{Lu}$/u.test(bare)) return true; // an initial: "J. Sinner"
  if (bare === "No" && /^\s+\d/.test(following)) return true; // "No. 1", where "no." alone can end a sentence
  return ABBREVIATIONS.has(bare.toLowerCase());
}

function firstSentenceEnd(text: string): number {
  for (const match of text.matchAll(SENTENCE_END)) {
    const end = match.index + match[0].length;
    const word = /\S*$/.exec(text.slice(0, match.index))![0];
    if (match[0].startsWith(".") && isAbbreviation(word, text.slice(end))) continue;
    return end;
  }
  return text.length;
}

/** Splits a point. Text that doesn't fit stays whole in the head, so nothing is ever lost. */
export function parsePlanItem(text: string): PlanItem {
  const whole = text.trim();
  const marker = INFERENCE.exec(whole);
  const inference = marker ? whole.slice(marker.index + marker[0].length).trim() : "";
  const facts = (marker && inference ? whole.slice(0, marker.index) : whole).trim();
  const end = firstSentenceEnd(facts);
  return { head: facts.slice(0, end).trim(), body: facts.slice(end).trim(), inference: inference || null };
}

/** The inference is written mid-sentence in lower case; on its own line it starts with a capital. */
export function capitalized(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export interface Figure {
  text: string; // "75.7%"
  sub: string | null; // "against 68.7% for Alcaraz"
  sample: number | null;
  small: boolean;
}

// Exactly one decimal, so "about 46%" and "75.70%" are not read as figures. Spanish and French
// write "75,7 %": the comma and the space before the sign are read too (D-027).
const PERCENT = /(\d{1,3}[.,]\d)[   ]?%/g;

/** The figure for a point: the first percentage in its facts (not the coach's inference) that is
 * also a checked value. The comparison is added only when the text gives the other player's
 * figure too, because the same value can sit in more than one row. */
export function findFigure(text: string, checked: CheckedPercent[], names: { player: string; opponent: string }, t: T = EN): Figure | null {
  const { head, body } = parsePlanItem(text);
  const stated = [...`${head} ${body}`.matchAll(PERCENT)].map((m) => m[1].replace(",", "."));
  const value = stated.find((v) => checked.some((c) => c.value === v));
  if (value === undefined) return null;
  const sources = checked.filter((c) => c.value === value);
  const paired = sources.filter((c) => c.against !== null && stated.includes(c.against));
  const source = new Set(paired.map((c) => `${c.side} ${c.against}`)).size === 1 ? paired[0] : null;
  let sub: string | null = null;
  const against = t.pct(source?.against ?? "");
  if (source) sub = source.side === "player" ? t.figureAgainst(against, names.opponent) : t.figureOpponent(names.opponent, against, names.player);
  const samples = new Set(sources.map((c) => c.sample));
  const sample = source ? source.sample : samples.size === 1 ? [...samples][0] : null;
  return { text: t.pct(value), sub, sample, small: source ? isSmallSample(source.sample) : sources.some((c) => isSmallSample(c.sample)) };
}
