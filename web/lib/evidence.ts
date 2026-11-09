// Everything the report view shows comes from the run's tool results ("evidence"), never
// from the model's text: the evidence behind each key stat, and both charts. When the
// evidence a chart needs is missing, the chart says so instead of showing zeros.

import type { Evidence, KeyStat, PlayerRef, Rate, Sample, Surface, ToolResult } from "./types.ts";
import { SURFACES } from "./types.ts";

export const TOOL_NAMES: Record<string, string> = {
  resolve_player: "Player lookup",
  player_profile: "Player profile",
  surface_splits: "Win-loss by surface",
  serve_return_stats: "Serve and return stats",
  pressure_stats: "Break points",
  head_to_head: "Head-to-head",
  recent_form: "Recent form",
};

const LEVELS: Record<string, string> = {
  G: "Grand Slams", M: "Masters 1000", A: "ATP 250 and 500", F: "Tour Finals", D: "Davis Cup", O: "Olympics",
};

export function findEvidence(evidence: Evidence[], id: string): Evidence | undefined {
  return evidence.find((e) => e.tool_call_id === id);
}

/** Follow a dotted path ("surfaces.0.win_rate.value"); also return the object holding the
 * value, which for a rate carries its numerator and denominator. */
export function resolvePath(result: unknown, path: string): { found: boolean; value: unknown; parent: unknown } {
  let node: unknown = result;
  let parent: unknown = undefined;
  for (const part of path.split(".")) {
    parent = node;
    if (Array.isArray(node) && /^\d+$/.test(part) && Number(part) < node.length) node = node[Number(part)];
    else if (node && typeof node === "object" && !Array.isArray(node) && part in node) node = (node as Record<string, unknown>)[part];
    else return { found: false, value: undefined, parent: undefined };
  }
  return { found: true, value: node, parent };
}

function isRate(x: unknown): x is Rate {
  return !!x && typeof x === "object" && "numerator" in x && "denominator" in x && "unit" in x;
}

/** What a key stat means, read from its evidence: the rate it belongs to, if any. */
export function rateFor(stat: KeyStat, evidence: Evidence | undefined): Rate | null {
  if (!evidence?.result) return null;
  const { found, parent } = resolvePath(evidence.result, stat.field);
  return found && stat.field.endsWith(".value") && isRate(parent) ? parent : null;
}

/** The filters a tool call used, in words. Only the ones that were set. */
export function describeFilters(filters: Record<string, unknown> | undefined): string[] {
  if (!filters) return [];
  const out: string[] = [];
  if (filters.surface) out.push(`${filters.surface} courts`);
  if (filters.season) out.push(`${filters.season} season`);
  if (filters.date_from && filters.date_to) out.push(`Tournaments starting ${filters.date_from} to ${filters.date_to}`);
  else if (filters.date_from) out.push(`Tournaments starting from ${filters.date_from}`);
  else if (filters.date_to) out.push(`Tournaments starting up to ${filters.date_to}`);
  const levels = filters.tourney_level;
  if (Array.isArray(levels) && levels.length) out.push(levels.map((l) => LEVELS[String(l)] ?? String(l)).join(", "));
  else if (typeof levels === "string") out.push(LEVELS[levels] ?? levels);
  if (filters.opponent_hand === "L") out.push("Left-handed opponents");
  if (filters.opponent_hand === "R") out.push("Right-handed opponents");
  if (filters.include_exhibitions) out.push("Exhibitions included");
  return out;
}

/** What the tool left out, in words. Only the counts above zero. */
export function describeExcluded(excluded: Record<string, number> | undefined): string[] {
  const names: Record<string, [one: string, many: string]> = {
    walkovers: ["walkover", "walkovers"],
    exhibitions: ["exhibition", "exhibitions"],
    unknown_results: ["match with an unclear result", "matches with an unclear result"],
    unknown_surface: ["match with no surface recorded", "matches with no surface recorded"],
    unknown_opponent_hand: ["match against an opponent of unknown hand", "matches against opponents of unknown hand"],
  };
  return Object.entries(excluded ?? {})
    .filter(([, n]) => n > 0)
    .map(([key, n]) => `${n} ${(names[key] ?? [key, key])[n === 1 ? 0 : 1]}`);
}

// ---------- charts ----------

function callsFor(evidence: Evidence[], tool: string, player: PlayerRef): Evidence[] {
  return evidence.filter((e) => e.tool === tool && !e.error && e.result && e.input.player_id === player.player_id);
}

export interface SurfaceRow {
  surface: Surface;
  player: number | null; // win rate as a percentage
  opponent: number | null;
  playerRecord: string | null;
  opponentRecord: string | null;
}

export interface ChartData<Row> {
  rows: Row[];
  sources: string[]; // tool_call_ids
  missing: string[]; // what the chart couldn't find, in words
}

/** Win rate by surface for both players, from surface_splits calls without a surface filter
 * (one row per surface). A call filtered to one surface only fills that surface. */
export function surfaceChart(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef): ChartData<SurfaceRow> {
  const sources: string[] = [];
  const missing: string[] = [];
  const bySurface = (who: PlayerRef) => {
    const calls = callsFor(evidence, "surface_splits", who);
    const call = calls.find((c) => !c.input.filters?.surface) ?? calls[0];
    if (!call) {
      missing.push(`${who.name}'s win-loss by surface`);
      return new Map<string, { matches: number; wins: number; losses: number; win_rate: Rate }>();
    }
    sources.push(call.tool_call_id);
    const rows = ((call.result as ToolResult).surfaces ?? []) as { surface: string; matches: number; wins: number; losses: number; win_rate: Rate }[];
    return new Map(rows.map((r) => [r.surface, r]));
  };
  const mine = bySurface(player);
  const theirs = bySurface(opponent);
  const pct = (r?: { win_rate: Rate }) => (r && r.win_rate.value !== null ? round1(100 * r.win_rate.value) : null);
  const record = (r?: { wins: number; losses: number }) => (r ? `${r.wins}-${r.losses}` : null);
  const rows = SURFACES.map((surface) => ({
    surface,
    player: pct(mine.get(surface)),
    opponent: pct(theirs.get(surface)),
    playerRecord: record(mine.get(surface)),
    opponentRecord: record(theirs.get(surface)),
  }));
  return { rows, sources, missing };
}

export interface ServeRow {
  metric: string;
  player: number | null;
  opponent: number | null;
  playerCounts: string | null; // "3,693 of 5,996"
  opponentCounts: string | null;
}

const SERVE_METRICS: [tool: string, key: string, label: string][] = [
  ["serve_return_stats", "first_serve_in", "First serve in"],
  ["serve_return_stats", "first_serve_points_won", "First-serve points won"],
  ["serve_return_stats", "second_serve_points_won", "Second-serve points won"],
  ["serve_return_stats", "service_points_won", "Service points won"],
  ["serve_return_stats", "return_points_won", "Return points won"],
  ["pressure_stats", "break_points_saved", "Break points saved"],
  ["pressure_stats", "break_points_converted", "Break points converted"],
];

/** Serve, return and break-point rates for both players, preferring the calls filtered to the
 * report's surface (the report falls back to all surfaces when a sample is small). */
export function serveChart(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, surface: Surface): ChartData<ServeRow> {
  const sources = new Set<string>();
  const missing: string[] = [];
  const pick = (who: PlayerRef, tool: string) => {
    const calls = callsFor(evidence, tool, who);
    return calls.find((c) => c.input.filters?.surface === surface) ?? calls[0];
  };
  const rates = (who: PlayerRef) => {
    const out = new Map<string, Rate>();
    for (const tool of ["serve_return_stats", "pressure_stats"]) {
      const call = pick(who, tool);
      if (!call) {
        missing.push(`${who.name}'s ${TOOL_NAMES[tool].toLowerCase()}`);
        continue;
      }
      sources.add(call.tool_call_id);
      const stats = ((call.result as ToolResult).stats ?? {}) as Record<string, Rate>;
      for (const [key, rate] of Object.entries(stats)) out.set(`${tool}.${key}`, rate);
    }
    return out;
  };
  const mine = rates(player);
  const theirs = rates(opponent);
  const pct = (r?: Rate) => (r && r.value !== null ? round1(100 * r.value) : null);
  const counts = (r?: Rate) => (r && r.value !== null ? `${r.numerator.toLocaleString("en-US")} of ${r.denominator.toLocaleString("en-US")}` : null);
  const rows = SERVE_METRICS.map(([tool, key, metric]) => ({
    metric,
    player: pct(mine.get(`${tool}.${key}`)),
    opponent: pct(theirs.get(`${tool}.${key}`)),
    playerCounts: counts(mine.get(`${tool}.${key}`)),
    opponentCounts: counts(theirs.get(`${tool}.${key}`)),
  }));
  return { rows, sources: [...sources], missing };
}

export function round1(x: number): number {
  return Math.round(x * 10) / 10;
}

/** A key stat's value as the coach should read it: rates as percentages with one decimal,
 * per-match averages with one decimal, counts as whole numbers. */
export function formatStat(stat: KeyStat, rate: Rate | null): string {
  if (rate?.unit === "fraction") return `${round1(100 * stat.value).toFixed(1)}%`;
  if (rate?.unit === "per_match") return stat.value.toFixed(1);
  return Number.isInteger(stat.value) ? stat.value.toLocaleString("en-US") : String(stat.value);
}

export function sampleLine(sample: Sample | undefined): string | null {
  if (!sample) return null;
  const range = sample.first_tourney_date && sample.last_tourney_date
    ? `, tournaments from ${sample.first_tourney_date} to ${sample.last_tourney_date}`
    : "";
  const stats = sample.matches_with_stats === sample.matches_counted ? "all with stats" : `${sample.matches_with_stats} with stats`;
  return `${sample.matches_counted} ${sample.matches_counted === 1 ? "match" : "matches"} (${stats})${range}`;
}
