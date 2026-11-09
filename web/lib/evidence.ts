// Everything the report view shows comes from the run's tool results ("evidence"), never
// from the model's text: each key number's value, sample and description, and both charts.
// Calls are matched on what the tool actually used (its result's player and filters), not on
// what the model asked for. When the evidence is missing, the view says so; it never shows 0.

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

const STAT_NAMES: Record<string, string> = {
  first_serve_in: "First serve in",
  first_serve_points_won: "First-serve points won",
  second_serve_points_won: "Second-serve points won",
  service_points_won: "Service points won",
  return_points_won: "Return points won",
  aces_per_match: "Aces per match",
  break_points_saved: "Break points saved",
  break_points_converted: "Break points converted",
  win_rate: "Win rate",
  wins: "Wins",
  losses: "Losses",
  matches: "Matches",
};

const LEVELS: Record<string, string> = {
  G: "Grand Slams", M: "Masters 1000", A: "ATP 250 and 500", F: "Tour Finals", D: "Davis Cup", O: "Olympics",
};

const TOLERANCE = 1e-9; // the grounding check's (api/grounding.py)

export function findEvidence(evidence: Evidence[], id: string): Evidence | undefined {
  return evidence.find((e) => e.tool_call_id === id);
}

/** Follow a dotted path ("surfaces.0.win_rate.value") through a tool result's own fields; also
 * return every object passed on the way, as api/grounding.py does. */
export function resolvePath(result: unknown, path: string): { found: boolean; value: unknown; seen: unknown[] } {
  let node: unknown = result;
  const seen: unknown[] = [result];
  for (const part of path.split(".")) {
    if (Array.isArray(node) && /^\d+$/.test(part) && Number(part) < node.length) node = node[Number(part)];
    else if (node && typeof node === "object" && !Array.isArray(node) && Object.hasOwn(node, part)) node = (node as Record<string, unknown>)[part];
    else return { found: false, value: undefined, seen };
    seen.push(node);
  }
  return { found: true, value: node, seen };
}

function isRate(x: unknown): x is Rate {
  return !!x && typeof x === "object" && "numerator" in x && "denominator" in x && "unit" in x;
}

function isNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

/** The match counts a stat from this result may cite (api/grounding.py, sample_sizes). */
function sampleSizes(result: ToolResult, seen: unknown[]): number[] {
  const counts = [result.sample?.matches_counted, result.sample?.matches_with_stats];
  for (const node of seen) {
    if (node && typeof node === "object" && !Array.isArray(node)) counts.push((node as Record<string, unknown>).matches as number);
  }
  return counts.filter((n): n is number => Number.isInteger(n));
}

export type StatCheck = {
  /** "matched": the value and sample are the tool's (as the grounding check found);
   * "mismatch": the model's figure differs from the tool's; "missing": no such call or field. */
  status: "matched" | "mismatch" | "missing";
  value: number | null; // the tool's value, never the model's
  rate: Rate | null;
  sample: number | null; // matches it rests on, from the tool result
  evidence: Evidence | undefined;
};

/** Read a key stat from the evidence and compare it with what the model wrote. */
export function checkStat(stat: KeyStat, evidence: Evidence[]): StatCheck {
  const source = findEvidence(evidence, stat.tool_call_id);
  if (!source?.result || source.error) return { status: "missing", value: null, rate: null, sample: null, evidence: source };
  const { found, value, seen } = resolvePath(source.result, stat.field);
  if (!found || !isNumber(value)) return { status: "missing", value: null, rate: null, sample: null, evidence: source };
  const parent = seen[seen.length - 2];
  const rate = stat.field.endsWith(".value") && isRate(parent) ? parent : null;
  const sizes = sampleSizes(source.result, seen);
  const matched = isNumber(stat.value) && Math.abs(stat.value - value) <= TOLERANCE && sizes.includes(stat.sample_matches);
  // The sample shown is the tool's: the stated one when it is one of the result's counts,
  // otherwise the count of the object the value sits in, or the result's sample.
  const nearest = [...seen].reverse().find((n) => n && typeof n === "object" && Number.isInteger((n as Record<string, unknown>).matches));
  const sample = sizes.includes(stat.sample_matches)
    ? stat.sample_matches
    : ((nearest as { matches?: number } | undefined)?.matches ?? source.result.sample?.matches_with_stats ?? null);
  return { status: matched ? "matched" : "mismatch", value, rate, sample, evidence: source };
}

/** What a key stat is, in words, from the tool result: whose number, which measure, which
 * filters. The model's own label is not used, since nothing checks it. */
export function describeStat(stat: KeyStat, source: Evidence | undefined): { title: string; filters: string[] } {
  const result = source?.result;
  if (!result) return { title: `Tool call ${stat.tool_call_id} (not in this report's results)`, filters: [] };
  const parts = stat.field.split(".");
  const key = parts.find((p) => p in STAT_NAMES && p !== "matches") ?? parts[parts.length - 1];
  let measure = STAT_NAMES[key] ?? stat.field;
  const listName = parts[0];
  if ((listName === "surfaces" || listName === "by_surface") && /^\d+$/.test(parts[1] ?? "")) {
    const row = (result[listName] as { surface?: string }[] | undefined)?.[Number(parts[1])];
    if (row?.surface) measure = `${row.surface} ${measure.toLowerCase()}`;
  }
  if (source.tool === "head_to_head") measure = `head-to-head ${measure.charAt(0).toLowerCase()}${measure.slice(1)}`;
  if (source.tool === "recent_form") measure = `${measure} in the last ${String(result.n ?? "")} matches`;
  const who = result.opponent ? `${result.player?.name} against ${result.opponent.name}` : (result.player?.name ?? "");
  const title = `${who}: ${measure.charAt(0).toLowerCase()}${measure.slice(1)}`;
  return { title, filters: describeFilters(result.filters as Record<string, unknown> | undefined) };
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

export type Window = { date_from: string; date_to: string };

/** Successful calls of one tool for one player inside the report's window, judged by the
 * result (what the tool actually did), not by the model's request. */
function callsFor(evidence: Evidence[], tool: string, who: PlayerRef, window: Window): Evidence[] {
  return evidence.filter((e) => {
    const f = (e.result?.filters ?? {}) as Record<string, unknown>;
    return e.tool === tool && !e.error && e.result && e.result.player?.player_id === who.player_id
      && f.date_from === window.date_from && f.date_to === window.date_to && !f.season && !f.tourney_level
      && !f.opponent_hand && !f.include_exhibitions;
  });
}

type SurfaceCell = { winRate: number | null; record: string | null; status: "ok" | "no_matches" | "not_looked_up" };

export interface SurfaceRow {
  surface: Surface;
  player: number | null; // win rate as a percentage, or null for a gap
  opponent: number | null;
  playerCell: SurfaceCell;
  opponentCell: SurfaceCell;
}

export interface ChartData<Row> {
  rows: Row[];
  sources: string[]; // tool_call_ids
  notes: string[]; // gaps and caveats, in words
}

/** Win rate by surface for both players. Uses a call over every surface when there is one, so a
 * missing surface means no matches there; a call filtered to one surface fills only that one,
 * and the others are "not looked up", never "no matches". */
export function surfaceChart(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, window: Window): ChartData<SurfaceRow> {
  const sources: string[] = [];
  const notes: string[] = [];
  const cells = (who: PlayerRef): Map<string, SurfaceCell> => {
    const calls = callsFor(evidence, "surface_splits", who, window);
    const all = calls.find((c) => !c.result?.filters?.surface);
    const used = all ? [all] : calls;
    if (!used.length) notes.push(`${who.name}'s win-loss by surface isn't in this report's results.`);
    const map = new Map<string, SurfaceCell>();
    for (const call of used) {
      sources.push(call.tool_call_id);
      for (const r of ((call.result as ToolResult).surfaces ?? []) as { surface: string; wins: number; losses: number; win_rate: Rate }[]) {
        const value = r.win_rate.value;
        map.set(r.surface, { winRate: value === null ? null : round1(100 * value), record: `${r.wins}-${r.losses}`, status: "ok" });
      }
    }
    for (const surface of SURFACES) {
      if (map.has(surface)) continue;
      map.set(surface, { winRate: null, record: null, status: all ? "no_matches" : "not_looked_up" });
    }
    const unlooked = SURFACES.filter((s) => map.get(s)!.status === "not_looked_up");
    if (used.length && unlooked.length) notes.push(`${who.name}: ${unlooked.join(" and ").toLowerCase()} not looked up in this report.`);
    return map;
  };
  const mine = cells(player);
  const theirs = cells(opponent);
  const rows = SURFACES.map((surface) => {
    const p = mine.get(surface)!;
    const o = theirs.get(surface)!;
    return { surface, player: p.winRate, opponent: o.winRate, playerCell: p, opponentCell: o };
  });
  return { rows, sources, notes };
}

export interface ServeRow {
  metric: string;
  player: number | null;
  opponent: number | null;
  playerCounts: string | null; // "3,693 of 5,996"
  opponentCounts: string | null;
}

const SERVE_METRICS: [tool: string, key: string][] = [
  ["serve_return_stats", "first_serve_in"],
  ["serve_return_stats", "first_serve_points_won"],
  ["serve_return_stats", "second_serve_points_won"],
  ["serve_return_stats", "service_points_won"],
  ["serve_return_stats", "return_points_won"],
  ["pressure_stats", "break_points_saved"],
  ["pressure_stats", "break_points_converted"],
];

/** Serve, return and break-point rates for both players, from the calls on the report's surface;
 * when a player only has the all-surfaces fallback (a small sample on the surface), that is
 * used and said. Gaps (no call, or no matches with stats) are explained in the notes. */
export function serveChart(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, surface: Surface, window: Window): ChartData<ServeRow> & { scope: string } {
  const sources = new Set<string>();
  const notes: string[] = [];
  const scopes = new Set<string>();
  const rates = (who: PlayerRef) => {
    const out = new Map<string, Rate>();
    for (const tool of ["serve_return_stats", "pressure_stats"]) {
      const calls = callsFor(evidence, tool, who, window);
      const onSurface = calls.find((c) => c.result?.filters?.surface === surface);
      const anySurface = calls.find((c) => !c.result?.filters?.surface);
      const call = onSurface ?? anySurface;
      if (!call) {
        notes.push(`${who.name}'s ${TOOL_NAMES[tool].toLowerCase()} aren't in this report's results.`);
        continue;
      }
      sources.add(call.tool_call_id);
      scopes.add(onSurface ? surface.toLowerCase() : "all surfaces");
      if (!onSurface) notes.push(`${who.name}'s ${TOOL_NAMES[tool].toLowerCase()} cover all surfaces, because the ${surface.toLowerCase()} sample was small.`);
      const result = call.result as ToolResult;
      notes.push(`${who.name}'s ${TOOL_NAMES[tool].toLowerCase()}: ${result.sample?.matches_with_stats ?? "an unknown number of"} matches with stats.`);
      for (const [key, rate] of Object.entries((result.stats ?? {}) as Record<string, Rate>)) out.set(`${tool}.${key}`, rate);
    }
    return out;
  };
  const mine = rates(player);
  const theirs = rates(opponent);
  const pct = (r?: Rate) => (r && r.value !== null ? round1(100 * r.value) : null);
  const counts = (r?: Rate) => (r && r.value !== null ? `${r.numerator.toLocaleString("en-US")} of ${r.denominator.toLocaleString("en-US")}` : null);
  const rows = SERVE_METRICS.map(([tool, key]) => {
    const p = mine.get(`${tool}.${key}`);
    const o = theirs.get(`${tool}.${key}`);
    for (const [who, rate] of [[player, p], [opponent, o]] as const) {
      if (rate && rate.value === null) notes.push(`${who.name}: no ${STAT_NAMES[key].toLowerCase()} figure (no matches with stats for it).`);
    }
    return { metric: STAT_NAMES[key], player: pct(p), opponent: pct(o), playerCounts: counts(p), opponentCounts: counts(o) };
  });
  return { rows, sources: [...sources], notes, scope: scopes.size === 1 ? [...scopes][0] : "mixed surfaces" };
}

export function round1(x: number): number {
  return Math.round(x * 10) / 10;
}

/** A value as the coach should read it: rates as percentages with one decimal, per-match
 * averages with one decimal, counts as whole numbers. */
export function formatValue(value: number, rate: Rate | null): string {
  if (rate?.unit === "fraction") return `${round1(100 * value).toFixed(1)}%`;
  if (rate?.unit === "per_match") return value.toFixed(1);
  return Number.isInteger(value) ? value.toLocaleString("en-US") : String(value);
}

export function sampleLine(sample: Sample | undefined): string | null {
  if (!sample) return null;
  const range = sample.first_tourney_date && sample.last_tourney_date
    ? `, tournaments from ${sample.first_tourney_date} to ${sample.last_tourney_date}`
    : "";
  const stats = sample.matches_with_stats === sample.matches_counted ? "all with stats" : `${sample.matches_with_stats} with stats`;
  return `${sample.matches_counted} ${sample.matches_counted === 1 ? "match" : "matches"} (${stats})${range}`;
}
