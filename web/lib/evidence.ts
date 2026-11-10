// Everything the report view shows comes from the run's tool results ("evidence"), never
// from the model's text: each key number's value, sample and description, and both charts.
// Calls are matched on what the tool actually used (its result's player and filters), not on
// what the model asked for. When the evidence is missing, the view says so; it never shows 0.

import { EN, type T, surfaceWords } from "./i18n.ts";
import { eventName, lastName, longDate, roundName } from "./people.ts";
import type { Evidence, KeyStat, PlayerRef, Rate, ReportResponse, Sample, Surface, ToolResult } from "./types.ts";
import { SURFACES } from "./types.ts";

/** The English names. Every function here that writes words takes a language (lib/i18n.ts, D-027),
 * English by default. */
export const TOOL_NAMES: Record<string, string> = EN.tools;
const STAT_NAMES: Record<string, string> = EN.stats;

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
export function describeStat(stat: KeyStat, source: Evidence | undefined, t: T = EN): { title: string; filters: string[] } {
  const result = source?.result;
  if (!result) return { title: t.toolCallMissing(stat.tool_call_id), filters: [] };
  const parts = stat.field.split(".");
  const key = parts.find((p) => p in STAT_NAMES && p !== "matches") ?? parts[parts.length - 1];
  let measure = (Object.hasOwn(t.stats, key) ? t.stats[key] : undefined) ?? stat.field;
  const listName = parts[0];
  if ((listName === "surfaces" || listName === "by_surface") && /^\d+$/.test(parts[1] ?? "")) {
    const row = (result[listName] as { surface?: string }[] | undefined)?.[Number(parts[1])];
    if (row?.surface) measure = t.measureOnSurface(measure, surfaceWords(t, row.surface));
  }
  if (source.tool === "head_to_head") measure = t.measureHeadToHead(measure);
  if (source.tool === "recent_form") measure = t.measureRecent(measure, String(result.n ?? ""));
  const who = result.opponent ? t.playerAgainst(result.player?.name, result.opponent.name) : (result.player?.name ?? "");
  const title = `${who}: ${measure.charAt(0).toLowerCase()}${measure.slice(1)}`;
  return { title, filters: describeFilters(result.filters as Record<string, unknown> | undefined, t) };
}

/** The filters a tool call used, in words. Only the ones that were set. */
export function describeFilters(filters: Record<string, unknown> | undefined, t: T = EN): string[] {
  if (!filters) return [];
  const out: string[] = [];
  const level = (code: string) => (Object.hasOwn(t.levels, code) ? t.levels[code] : code);
  if (filters.surface) out.push(surfaceWords(t, String(filters.surface)).courtsCap);
  if (filters.season) out.push(t.seasonFilter(String(filters.season)));
  if (filters.date_from && filters.date_to) out.push(t.tournamentsBetween(String(filters.date_from), String(filters.date_to)));
  else if (filters.date_from) out.push(t.tournamentsFrom(String(filters.date_from)));
  else if (filters.date_to) out.push(t.tournamentsUpTo(String(filters.date_to)));
  const levels = filters.tourney_level;
  if (Array.isArray(levels) && levels.length) out.push(levels.map((l) => level(String(l))).join(", "));
  else if (typeof levels === "string") out.push(level(levels));
  if (filters.opponent_hand === "L") out.push(t.leftHandedOpponents);
  if (filters.opponent_hand === "R") out.push(t.rightHandedOpponents);
  if (filters.include_exhibitions) out.push(t.exhibitionsIncluded);
  return out;
}

/** What the tool left out, in words. Only the counts above zero. */
export function describeExcluded(excluded: Record<string, number> | undefined, t: T = EN): string[] {
  const names = t.excludedNames;
  return Object.entries(excluded ?? {})
    .filter(([, n]) => n > 0)
    .map(([key, n]) => `${n} ${(Object.hasOwn(names, key) ? names[key] : [key, key])[n === 1 ? 0 : 1]}`);
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

type SurfaceCell = { winRate: number | null; record: string | null; matches: number | null; status: "ok" | "no_matches" | "not_looked_up" };

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
export function surfaceChart(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, window: Window, t: T = EN): ChartData<SurfaceRow> {
  const sources: string[] = [];
  const notes: string[] = [];
  const cells = (who: PlayerRef): Map<string, SurfaceCell> => {
    const calls = callsFor(evidence, "surface_splits", who, window);
    const all = calls.find((c) => !c.result?.filters?.surface);
    const used = all ? [all] : calls;
    if (!used.length) notes.push(t.surfacesMissing(who.name));
    const map = new Map<string, SurfaceCell>();
    for (const call of used) {
      sources.push(call.tool_call_id);
      for (const r of ((call.result as ToolResult).surfaces ?? []) as { surface: string; matches: number; wins: number; losses: number; win_rate: Rate }[]) {
        map.set(r.surface, { winRate: ratePercent(r.win_rate), record: `${r.wins}-${r.losses}`, matches: r.matches, status: "ok" });
      }
    }
    for (const surface of SURFACES) {
      if (map.has(surface)) continue;
      map.set(surface, { winRate: null, record: null, matches: null, status: all ? "no_matches" : "not_looked_up" });
    }
    const unlooked = SURFACES.filter((s) => map.get(s)!.status === "not_looked_up");
    if (used.length && unlooked.length) notes.push(t.notLookedUp(who.name, unlooked.map((s) => surfaceWords(t, s).lower).join(` ${t.and} `)));
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
  playerSample: number | null; // matches with stats behind the figure
  opponentSample: number | null;
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
export function serveChart(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, surface: Surface, window: Window, t: T = EN): ChartData<ServeRow> & {
  scope: string;
  caveats: string[]; // the notes without the per-tool "N matches with stats" lines
  matchesWithStats: { player: number[]; opponent: number[] }; // one count per tool that was called
} {
  const sources = new Set<string>();
  const notes: string[] = [];
  const sampleNotes = new Set<string>();
  const withStats = new Map<string, number>();
  const scopes = new Set<string>();
  const rates = (who: PlayerRef) => {
    const out = new Map<string, Rate>();
    for (const tool of ["serve_return_stats", "pressure_stats"]) {
      const calls = callsFor(evidence, tool, who, window);
      const onSurface = calls.find((c) => c.result?.filters?.surface === surface);
      const anySurface = calls.find((c) => !c.result?.filters?.surface);
      const call = onSurface ?? anySurface;
      if (!call) {
        notes.push(t.toolMissing(who.name, t.tools[tool]));
        continue;
      }
      sources.add(call.tool_call_id);
      scopes.add(onSurface ? surface.toLowerCase() : "all surfaces");
      if (!onSurface) notes.push(t.toolAllSurfaces(who.name, t.tools[tool], surfaceWords(t, surface)));
      const result = call.result as ToolResult;
      const sampleNote = t.toolSample(who.name, t.tools[tool], result.sample?.matches_with_stats ?? null);
      notes.push(sampleNote);
      sampleNotes.add(sampleNote);
      if (result.sample) withStats.set(`${who.player_id}.${tool}`, result.sample.matches_with_stats);
      for (const [key, rate] of Object.entries((result.stats ?? {}) as Record<string, Rate>)) out.set(`${tool}.${key}`, rate);
    }
    return out;
  };
  const mine = rates(player);
  const theirs = rates(opponent);
  const pct = (r?: Rate) => (r ? ratePercent(r) : null);
  const counts = (r?: Rate) => (r && r.value !== null ? t.countOf(r.numerator, r.denominator) : null);
  const rows = SERVE_METRICS.map(([tool, key]) => {
    const p = mine.get(`${tool}.${key}`);
    const o = theirs.get(`${tool}.${key}`);
    for (const [who, rate] of [[player, p], [opponent, o]] as const) {
      if (rate && rate.value === null) notes.push(t.noFigure(who.name, t.stats[key]));
    }
    return {
      metric: t.stats[key], player: pct(p), opponent: pct(o), playerCounts: counts(p), opponentCounts: counts(o),
      playerSample: withStats.get(`${player.player_id}.${tool}`) ?? null,
      opponentSample: withStats.get(`${opponent.player_id}.${tool}`) ?? null,
    };
  });
  const countsFor = (who: PlayerRef) => ["serve_return_stats", "pressure_stats"].flatMap((tool) => withStats.get(`${who.player_id}.${tool}`) ?? []);
  return {
    rows, sources: [...sources], notes, scope: scopes.size === 1 ? [...scopes][0] : "mixed surfaces",
    caveats: notes.filter((note) => !sampleNotes.has(note)),
    matchesWithStats: { player: countsFor(player), opponent: countsFor(opponent) },
  };
}

export function round1(x: number): number {
  return Math.round(x * 10) / 10;
}

/** A rate as a percentage with one decimal, from its counts. The tool's `value` is already
 * rounded to four places, so rounding that again can be 0.1 out: 37 of 43 is 86.0%, not 86.1%. */
export function ratePercent(rate: Rate): number | null {
  return rate.value !== null && rate.denominator > 0 ? round1((100 * rate.numerator) / rate.denominator) : null;
}

/** A value as the coach should read it: rates as percentages with one decimal, per-match
 * averages with one decimal, counts as whole numbers. */
export function formatValue(value: number, rate: Rate | null, t: T = EN): string {
  if (rate?.unit === "fraction") return t.pct((ratePercent(rate) ?? round1(100 * value)).toFixed(1));
  if (rate?.unit === "per_match") return t.dec((rate.denominator > 0 ? rate.numerator / rate.denominator : value).toFixed(1));
  return Number.isInteger(value) ? t.int(value) : t.dec(String(value));
}

export function sampleLine(sample: Sample | undefined, t: T = EN): string | null {
  if (!sample) return null;
  const range = sample.first_tourney_date && sample.last_tourney_date
    ? t.sampleRange(sample.first_tourney_date, sample.last_tourney_date)
    : "";
  const stats = sample.matches_with_stats === sample.matches_counted ? t.allWithStats : t.someWithStats(sample.matches_with_stats);
  return t.sampleSummary(sample.matches_counted, stats, range);
}

// ---------- the report screen ----------

const SMALL_SAMPLE = 10; // api/report.py

export function isSmallSample(matches: number | null | undefined): boolean {
  return typeof matches === "number" && matches < SMALL_SAMPLE;
}

export function matchCount(n: number, t: T = EN): string {
  return t.matchCount(n);
}

export function meetingCount(n: number, t: T = EN): string {
  return t.meetingCount(n);
}

/** Surnames for tight spots, or full names when the two players share one. */
export function shortNames(player: PlayerRef, opponent: PlayerRef): { player: string; opponent: string } {
  const [a, b] = [lastName(player.name), lastName(opponent.name)];
  return a === b ? { player: player.name, opponent: opponent.name } : { player: a, opponent: b };
}

/** The newest date the loaded data reaches, or null when no tool result says. */
export function dataThrough(evidence: Evidence[]): string | null {
  for (const e of evidence) {
    if (e.error || !e.result) continue;
    const window = e.result.data_window as { last_match_date?: string | null; last_tourney_date?: string | null } | undefined;
    const date = window?.last_match_date ?? window?.last_tourney_date;
    if (date) return date;
  }
  return null;
}

/** Whether the report's window is the usual two years up to the newest tournament (api/report.py). */
export function isTwoYearWindow({ date_from, date_to }: Window): boolean {
  const year = Number(date_to.slice(0, 4));
  const rest = date_to.slice(4);
  return date_from === `${year - 2}${rest}` || (rest === "-02-29" && date_from === `${year - 2}-02-28`);
}

type HeadToHeadCall = { result: ToolResult; forward: boolean };

/** Successful head-to-head calls for this pair, in either direction, that cover every meeting
 * (or every meeting on one surface). A call narrowed any other way can't fill a career figure. */
function headToHeadCalls(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef): HeadToHeadCall[] {
  return evidence.flatMap((e) => {
    const result = e.result;
    if (e.tool !== "head_to_head" || e.error || !result) return [];
    const [a, b] = [result.player?.player_id, result.opponent?.player_id];
    const forward = a === player.player_id && b === opponent.player_id;
    if (!forward && !(a === opponent.player_id && b === player.player_id)) return [];
    const f = (result.filters ?? {}) as Record<string, unknown>;
    if (f.date_from || f.date_to || f.season || f.tourney_level || f.opponent_hand || f.include_exhibitions) return [];
    return [{ result, forward }];
  });
}

const careerCall = (calls: HeadToHeadCall[]) => calls.find((c) => !c.result.filters?.surface);

/** Whether the report has a head-to-head over every meeting, as "covers every meeting" claims. */
export function hasCareerHeadToHead(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef): boolean {
  return careerCall(headToHeadCalls(evidence, player, opponent)) !== undefined;
}

export interface Tile {
  status: "ok" | "no_matches" | "no_data";
  text: string;
  sample: number | null; // the matches or meetings behind it
}

export interface ScoreboardRow {
  career: Tile;
  onSurface: Tile;
  winRate: Tile;
}

const noData = (t: T): Tile => ({ status: "no_data", text: t.noData, sample: null });
const noMatches = (t: T): Tile => ({ status: "no_matches", text: t.noMatches, sample: null });

type WinLoss = { matches: number; wins: number; losses: number };

/** Each player's wins from a record kept from one player's side. Never met is "No matches"; an
 * unreadable record is "No data". A real count of 0, when they have met, is shown as 0. */
function winTiles(record: WinLoss | undefined, forward: boolean, t: T): [mine: Tile, theirs: Tile] {
  if (!record || !isNumber(record.matches) || !isNumber(record.wins) || !isNumber(record.losses)) return [noData(t), noData(t)];
  if (record.matches === 0) return [noMatches(t), noMatches(t)];
  const tile = (n: number): Tile => ({ status: "ok", text: String(n), sample: record.matches });
  return forward ? [tile(record.wins), tile(record.losses)] : [tile(record.losses), tile(record.wins)];
}

/** The scoreboard's numbers, per player: career head-to-head, head-to-head on the report's
 * surface and the win rate on that surface in the report's window. */
export function scoreboardTiles(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, surface: Surface, window: Window, t: T = EN): { player: ScoreboardRow; opponent: ScoreboardRow } {
  const calls = headToHeadCalls(evidence, player, opponent);
  const career = careerCall(calls);
  const filtered = calls.find((c) => c.result.filters?.surface === surface);
  const [myCareer, theirCareer] = career ? winTiles(career.result.record as WinLoss | undefined, career.forward, t) : [noData(t), noData(t)];
  let [mineOn, theirsOn]: [Tile, Tile] = [noData(t), noData(t)];
  if (career) {
    const surfaces = career.result.by_surface as (WinLoss & { surface: string })[] | undefined;
    const line = surfaces?.find((r) => r.surface === surface);
    // A call over every meeting lists only the surfaces they played on.
    [mineOn, theirsOn] = line || !surfaces ? winTiles(line, career.forward, t) : [noMatches(t), noMatches(t)];
  } else if (filtered) {
    [mineOn, theirsOn] = winTiles(filtered.result.record as WinLoss | undefined, filtered.forward, t);
  }
  const row = surfaceChart(evidence, player, opponent, window, t).rows.find((r) => r.surface === surface)!;
  const rate = (cell: SurfaceCell): Tile => {
    if (cell.status === "no_matches") return noMatches(t);
    if (cell.status === "not_looked_up" || cell.winRate === null) return noData(t);
    return { status: "ok", text: t.pct(cell.winRate.toFixed(1)), sample: cell.matches };
  };
  return {
    player: { career: myCareer, onSurface: mineOn, winRate: rate(row.playerCell) },
    opponent: { career: theirCareer, onSurface: theirsOn, winRate: rate(row.opponentCell) },
  };
}

export interface HonoursRow {
  date: string;
  year: string;
  event: string;
  round: string;
  surface: string | null;
  winner: "player" | "opponent" | null; // null when the result isn't recorded as a win or loss
  score: string | null;
}

export type Honours =
  | { status: "not_looked_up" }
  | { status: "no_meetings" }
  | { status: "ok"; rows: HonoursRow[]; wins: { player: number; opponent: number } };

type MatchEntry = {
  tourney_date: string;
  match_date: string | null;
  tournament: string;
  surface: string | null;
  round: string;
  result: string;
  score: string | null;
};

/** The real match date where the data has one. Otherwise the tournament's: one starting from 26
 * December on is the next season's first event (D-010), played mostly in January. */
function meetingYear(tourneyDate: string, matchDate: string | null): string {
  if (matchDate) return matchDate.slice(0, 4);
  const [year, month, day] = tourneyDate.split("-").map(Number);
  return String(month === 12 && day >= 26 ? year + 1 : year);
}

/** Every meeting, newest first, from a head-to-head over all of them. Each winner comes from that
 * match's result, read from the side the tool call took. */
export function honoursBoard(evidence: Evidence[], player: PlayerRef, opponent: PlayerRef, t: T = EN): Honours {
  const call = careerCall(headToHeadCalls(evidence, player, opponent));
  const matches = call?.result.matches as MatchEntry[] | undefined;
  if (!call || !Array.isArray(matches)) return { status: "not_looked_up" };
  if (matches.length === 0) return { status: "no_meetings" };
  const rows = [...matches]
    .sort((a, b) => b.tourney_date.localeCompare(a.tourney_date))
    .map((m): HonoursRow => {
      const won = m.result === "W" ? true : m.result === "L" ? false : null;
      return {
        date: m.tourney_date,
        year: meetingYear(m.tourney_date, m.match_date),
        event: eventName(m.tournament),
        round: roundName(m.round, t),
        surface: m.surface,
        winner: won === null ? null : won === call.forward ? "player" : "opponent",
        score: m.score,
      };
    });
  const count = (side: HonoursRow["winner"]) => rows.filter((r) => r.winner === side).length;
  return { status: "ok", rows, wins: { player: count("player"), opponent: count("opponent") } };
}

export interface Lead {
  side: "player" | "opponent" | "level" | null; // null when a figure is missing
  gap: string | null; // percentage points, one decimal
}

/** Who is ahead and by how much, from the two figures as shown. */
export function leadOf(player: number | null, opponent: number | null): Lead {
  if (player === null || opponent === null) return { side: null, gap: null };
  const gap = round1(Math.abs(player - opponent));
  if (gap === 0) return { side: "level", gap: "0.0" };
  return { side: player > opponent ? "player" : "opponent", gap: gap.toFixed(1) };
}

/** The dumbbell scale: 40% to 80%, widened in tens only when a figure falls outside it. */
export function serveScale(rows: ServeRow[]): { min: number; max: number } {
  const values = rows.flatMap((r) => [r.player, r.opponent]).filter((v): v is number => v !== null);
  const min = Math.min(40, ...values.map((v) => Math.floor(v / 10) * 10));
  const max = Math.max(80, ...values.map((v) => Math.ceil(v / 10) * 10));
  return { min: Math.max(0, min), max: Math.min(100, max) };
}

export function scalePosition(value: number, scale: { min: number; max: number }): number {
  return ((value - scale.min) / (scale.max - scale.min)) * 100;
}

/** "Clay matches with stats: 32 for Sinner, 29 for Alcaraz." Null when a player's serve and
 * pressure samples differ or one is missing, so the per-tool notes are shown instead. */
export function serveSampleLine(
  chart: Pick<ReturnType<typeof serveChart>, "scope" | "matchesWithStats">,
  player: PlayerRef, opponent: PlayerRef, surface: Surface, t: T = EN,
): string | null {
  const single = (counts: number[]) => (counts.length && counts.every((n) => n === counts[0]) ? counts[0] : null);
  const [mine, theirs] = [single(chart.matchesWithStats.player), single(chart.matchesWithStats.opponent)];
  if (mine === null || theirs === null) return null;
  const names = shortNames(player, opponent);
  const words = chart.scope === surface.toLowerCase() ? surfaceWords(t, surface) : null;
  return t.serveSampleLine(words, mine, names.player, theirs, names.opponent);
}

/** A percentage this report's evidence backs, as one-decimal text ("75.7"), with the row it came
 * from when there is one. */
export interface CheckedPercent {
  value: string;
  side: "player" | "opponent" | null;
  against: string | null; // the other player's figure in the same row
  sample: number | null;
}

/** The report's checked percentages: the two charts' rows and the key stats that matched. */
export function checkedPercents(data: ReportResponse): CheckedPercent[] {
  const { player, opponent, surface } = data.request;
  const out: CheckedPercent[] = [];
  const add = (mine: number | null, theirs: number | null, mySample: number | null, theirSample: number | null) => {
    const text = (x: number | null) => (x === null ? null : x.toFixed(1));
    if (mine !== null) out.push({ value: text(mine)!, side: "player", against: text(theirs), sample: mySample });
    if (theirs !== null) out.push({ value: text(theirs)!, side: "opponent", against: text(mine), sample: theirSample });
  };
  for (const r of serveChart(data.evidence, player, opponent, surface, data.request).rows) add(r.player, r.opponent, r.playerSample, r.opponentSample);
  for (const r of surfaceChart(data.evidence, player, opponent, data.request).rows) add(r.player, r.opponent, r.playerCell.matches, r.opponentCell.matches);
  for (const stat of data.report?.key_stats ?? []) {
    const check = checkStat(stat, data.evidence);
    if (check.status === "matched" && check.value !== null && check.rate?.unit === "fraction") {
      out.push({ value: (ratePercent(check.rate) ?? round1(100 * check.value)).toFixed(1), side: null, against: null, sample: check.sample });
    }
  }
  return out;
}

export interface KeyStatGroup {
  name: string;
  rows: { stat: KeyStat; index: number }[];
}

const GROUP_ORDER = ["Win rate", "Serve", "Return", "Pressure", "Head-to-head", "Recent form", "Other"];

function groupName(stat: KeyStat, source: Evidence | undefined): string {
  switch (source?.result ? source.tool : null) {
    case "surface_splits": return "Win rate";
    case "serve_return_stats": return stat.field.includes("return_points") ? "Return" : "Serve";
    case "pressure_stats": return "Pressure";
    case "head_to_head": return "Head-to-head";
    case "recent_form": return "Recent form";
    default: return "Other";
  }
}

/** The key numbers in the design's groups, keeping the report's order inside each. */
export function groupKeyStats(stats: KeyStat[], evidence: Evidence[]): KeyStatGroup[] {
  const rows = stats.map((stat, index) => ({ stat, index }));
  return GROUP_ORDER
    .map((name) => ({ name, rows: rows.filter(({ stat }) => groupName(stat, findEvidence(evidence, stat.tool_call_id)) === name) }))
    .filter((group) => group.rows.length > 0);
}

/** Under 10 matches: for a figure built from match stats, under 10 matches that have them. */
export function isSmallKeyStat(stat: KeyStat, check: StatCheck): boolean {
  if (check.sample === null) return false;
  const withStats = stat.field.startsWith("stats.") ? check.evidence?.result?.sample?.matches_with_stats : undefined;
  return isSmallSample(Math.min(check.sample, withStats ?? check.sample));
}

/** The surface of a per-surface line such as "by_surface.1.wins", or null for any other field. */
function surfaceOfField(stat: KeyStat, result: ToolResult): string | null {
  const [list, index] = stat.field.split(".");
  if ((list !== "surfaces" && list !== "by_surface") || !/^\d+$/.test(index ?? "")) return null;
  return (result[list] as { surface?: string }[] | undefined)?.[Number(index)]?.surface ?? null;
}

const COUNTED: Record<string, string> = EN.counted;

/** The counts behind a key number, in words: "444 of 786 second-serve points, 56.5%". Null when
 * this field has no wording here, so the value is shown on its own. */
export function describeValue(stat: KeyStat, check: StatCheck, t: T = EN): string | null {
  const result = check.evidence?.result;
  if (check.value === null || !result) return null;
  const parts = stat.field.split(".");
  const key = parts.find((p) => p in COUNTED || p === "win_rate" || p === "aces_per_match") ?? parts[parts.length - 1];
  const shown = formatValue(check.value, check.rate, t);
  const headToHead = check.evidence?.tool === "head_to_head";
  if (check.rate) {
    const { numerator: n, denominator: d } = check.rate;
    if (key in COUNTED) return t.valueCounted(n, d, t.counted[key], shown);
    if (key === "win_rate") return t.valueWinRate(n, headToHead ? t.meetingCount(d) : t.matchCount(d), shown);
    if (key === "aces_per_match") return t.valueAces(n, t.matchCount(d), shown);
    return null;
  }
  if (key !== "wins" && key !== "losses") return null;
  const parent = resolvePath(result, parts.slice(0, -1).join(".")).value as { matches?: number } | undefined;
  if (!isNumber(parent?.matches)) return null;
  const surface = surfaceOfField(stat, result);
  return t.valueRecord(key, check.value, t.sampleOf(parent.matches, headToHead, surface ? surfaceWords(t, surface) : null));
}

function inWords(items: string[], t: T): string {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} ${t.and} ${items[items.length - 1]}`;
}

const withLongDates = (text: string, t: T) => text.replace(/\d{4}-\d{2}-\d{2}/g, (iso) => longDate(iso, t));

export interface SourcePanel {
  source: string;
  filters: string;
  sample: string;
  leftOut: string;
  value: string;
  field: string;
}

/** What a key number's source panel says, all read from the tool result. Null when the result
 * it cites isn't in the report. */
export function sourcePanel(stat: KeyStat, check: StatCheck, t: T = EN): SourcePanel | null {
  const source = check.evidence;
  const result = source?.result;
  if (!source || !result) return null;
  const tool = (Object.hasOwn(t.tools, source.tool) ? t.tools[source.tool] : undefined) ?? source.tool;
  const who = result.opponent ? t.panelPair(result.player?.name, result.opponent.name) : t.panelFor(result.player?.name);
  const headToHead = source.tool === "head_to_head";
  const every = headToHead ? t.noFilterMeetings : t.noFilterMatches;
  const surface = surfaceOfField(stat, result);
  const words = surface ? surfaceWords(t, surface) : null;
  const filters = describeStat(stat, source, t).filters.join("; ") || every;
  const line = sampleLine(result.sample, t);
  const sample = line === null ? t.notReported : words && check.sample !== null ? t.panelSurfaceSample(check.sample, words, headToHead, line) : line;
  const excluded = describeExcluded(result.excluded, t);
  return {
    source: t.panelSource(tool, who, source.tool_call_id),
    filters: `${withLongDates(filters, t)}${words ? t.panelSurfaceLine(words) : ""}`,
    sample: withLongDates(sample, t),
    leftOut: excluded.length ? inWords(excluded, t) : t.nothing,
    value: check.value === null ? t.notFound : (describeValue(stat, check, t) ?? formatValue(check.value, check.rate, t)),
    field: check.value === null ? stat.field : `${stat.field} = ${check.value}`,
  };
}
