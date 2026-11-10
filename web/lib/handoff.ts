// Carries the players chosen on the Player stats page to match setup. A blocked or empty store
// is simply no handoff, and what comes back from the store is checked before it is trusted.

import type { Candidate } from "./types.ts";

const KEY = "clubhouse-handoff";

/** Fired when the Scouting link is used while already on that route, to go back to match setup. */
export const BACK_TO_SETUP = "scouting:back-to-setup";

export interface Handoff {
  player?: Candidate;
  opponent?: Candidate;
}

export function saveHandoff(handoff: Handoff): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(handoff));
  } catch {
    // no store on the server, or the browser blocks it: setup just starts empty
  }
}

/** Returns the handoff and clears it, so it applies once. Null when there is none to use. */
export function takeHandoff(): Handoff | null {
  try {
    const stored = sessionStorage.getItem(KEY);
    if (stored === null) return null;
    sessionStorage.removeItem(KEY);
    return checked(JSON.parse(stored));
  } catch {
    return null;
  }
}

function checked(value: unknown): Handoff | null {
  if (!isRecord(value)) return null;
  const player = value.player === undefined ? undefined : candidate(value.player);
  const opponent = value.opponent === undefined ? undefined : candidate(value.opponent);
  if (player === null || opponent === null) return null;
  if (!player && !opponent) return null;
  if (player && opponent && player.player_id === opponent.player_id) return null;
  return { ...(player && { player }), ...(opponent && { opponent }) };
}

function candidate(value: unknown): Candidate | null {
  if (!isRecord(value)) return null;
  const { player_id, name, country, hand, matches_loaded, last_tourney_date } = value;
  if (typeof player_id !== "number" || !Number.isInteger(player_id) || player_id <= 0) return null;
  if (typeof name !== "string" || !name.trim()) return null;
  if (typeof matches_loaded !== "number" || !Number.isInteger(matches_loaded) || matches_loaded < 0) return null;
  if (!isStringOrNull(country) || !isStringOrNull(hand) || !isStringOrNull(last_tourney_date)) return null;
  return { player_id, name, country, hand, matches_loaded, last_tourney_date };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringOrNull(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}
