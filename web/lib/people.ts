// How names, dates and the data's tournament and round codes read on screen. Dates are read and
// written in UTC, so a date never shifts with the viewer's timezone. Words come from the language
// passed in (lib/i18n.ts), English by default.

import { EN, type T } from "./i18n.ts";

const words = (name: string) => name.trim().split(/\s+/).filter(Boolean);

function firstLetter(word: string): string {
  return /\p{L}/u.exec(word)?.[0].toUpperCase() ?? "";
}

/** First letters of the first and last words: "Francis Casey Alcantara" is "FA". */
export function initials(name: string): string {
  const parts = words(name);
  if (parts.length < 2) return firstLetter(parts[0] ?? "");
  return firstLetter(parts[0]) + firstLetter(parts[parts.length - 1]);
}

const PARTICLES = new Set(["al", "da", "de", "del", "della", "den", "der", "di", "dos", "du", "el", "la", "le", "ten", "ter", "van", "von"]);

// The data has no hyphen or other mark that these two words are one surname. Listed for players
// with enough matches to appear on screen; anyone else falls back to the last word.
const TWO_WORD_SURNAMES = new Set([
  "auger aliassime", "barrios vera", "bautista agut", "budkov kjaer", "carballes baena", "carreno busta",
  "davidovich fokina", "diaz acosta", "dutra silva", "garcia lopez", "gimeno traver", "haider maurer",
  "merida aguilar", "mpetshi perricard", "seyboth wild", "ugo carabelli", "zapata miralles",
]);

/** The surname as a player is known by it: "Alcaraz", "De Minaur", "Bautista Agut". */
export function lastName(name: string): string {
  const parts = words(name);
  if (parts.length < 2) return parts[0] ?? "";
  if (parts.length > 2 && TWO_WORD_SURNAMES.has(parts.slice(-2).join(" ").toLowerCase())) return parts.slice(-2).join(" ");
  let start = parts.length - 1;
  while (start > 1 && PARTICLES.has(parts[start - 1].toLowerCase())) start -= 1;
  return parts.slice(start).join(" ");
}

const ISO = /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/;

function utcDate(iso: string): Date | null {
  const match = ISO.exec(iso);
  if (!match) return null;
  // With a time and no offset, Date would read it as the viewer's local time.
  const date = new Date(iso.includes("T") && !match[1] ? `${iso}Z` : iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "17 February 2020". Text that isn't an ISO date comes back unchanged. */
export function longDate(iso: string, t: T = EN): string {
  const date = utcDate(iso);
  return date ? t.longDate(date.getUTCDate(), date.getUTCMonth(), date.getUTCFullYear()) : iso;
}

/** "Oct 2026". Text that isn't an ISO date comes back unchanged. */
export function monthYear(iso: string, t: T = EN): string {
  const date = utcDate(iso);
  return date ? t.monthYear(date.getUTCMonth(), date.getUTCFullYear()) : iso;
}

const EVENT_NAMES = new Map([
  ["ATP Rio de Janeiro", "Rio de Janeiro"],
  ["Atp Cup", "ATP Cup"],
  ["NextGen Finals", "Next Gen Finals"],
  ["Rio De Janeiro", "Rio de Janeiro"],
  ["St Petersburg", "St. Petersburg"],
  ["Us Open", "US Open"],
  ["s Hertogenbosch", "'s-Hertogenbosch"],
]);

/** A tournament's name as it reads on screen, from the spelling in the data. */
export function eventName(raw: string): string {
  const name = raw.trim();
  // Davis Cup ties are stored with the round and teams: "Davis Cup Finals QF: ITA vs ARG".
  if (/^Davis Cup Finals\b/.test(name)) return "Davis Cup Finals";
  if (/^Davis Cup\b/.test(name)) return "Davis Cup";
  return EVENT_NAMES.get(name) ?? name;
}

/** The round's name; a code this doesn't know comes back unchanged. */
export function roundName(code: string, t: T = EN): string {
  return Object.hasOwn(t.rounds, code) ? t.rounds[code] : code;
}

/** "right-handed" or "left-handed"; null when the hand isn't known. */
export function handName(code: string | null | undefined, t: T = EN): string | null {
  if (code === "R") return t.rightHanded;
  if (code === "L") return t.leftHanded;
  return null;
}
