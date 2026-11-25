// The match prep page (D-033): both players side by side, from GET /matchup. Every figure is read
// from a block of the response and described from that block's own tool, filters and sample. A
// rate with nothing to divide by stays missing; it never becomes 0.

import { describeExcluded, describeFilters, ratePercent, withLongDates } from "./evidence.ts";
import { EN, type T, surfaceWords } from "./i18n.ts";
import { type PatternRow, type SetPatterns, type ShotDirectionView, type ShotPatterns, type ShotView, setRows, shotDirectionView, shotView } from "./patterns.ts";
import { eventName, lastName, longDate, roundName } from "./people.ts";
import {
  type DataWindow,
  type HeadToHead,
  type MatchEntry,
  type Profile,
  type RecordSummary,
  type SourceFacts,
  type StatBlock,
  type SurfaceSplits,
  pageHref,
  sourceFacts,
} from "./player-stats.ts";
import type { Rate } from "./types.ts";

// ---------- the response ----------

export interface Side {
  record: SurfaceSplits;
  serve_return: StatBlock;
  pressure: StatBlock;
  set_patterns: SetPatterns;
  shots: ShotPatterns;
}

export interface MatchupHeadToHead extends HeadToHead {
  by_surface: (RecordSummary & { surface: string })[];
  matches: MatchEntry[];
}

export type Scope = "surface" | "all";

export interface Matchup {
  player: Profile;
  opponent: Profile;
  surface: string;
  scope: Scope;
  window: { date_from: string; date_to: string };
  data_window: DataWindow;
  head_to_head: MatchupHeadToHead;
  sides: { player: Side; opponent: Side };
}

type Who = "player" | "opponent";
const OTHER: Record<Who, Who> = { player: "opponent", opponent: "player" };
const SMALL_SAMPLE = 10;

// ---------- the URL ----------

/** The page's state, as text from the URL. Nothing is checked here: the API validates every
 * value and its error is what the page shows. */
export interface PrepQuery {
  player: string;
  opponent: string;
  surface: string | null;
  scope: string | null;
}

/** The page's state from its URL, or null when it doesn't name both players. */
export function parsePrepQuery(params: { get(name: string): string | null }): PrepQuery | null {
  const read = (name: string) => params.get(name)?.trim() || null;
  const [player, opponent] = [read("player"), read("opponent")];
  return player && opponent ? { player, opponent, surface: read("surface"), scope: read("scope") } : null;
}

export function prepHref(query: PrepQuery): string {
  const params = new URLSearchParams({ player: query.player, opponent: query.opponent });
  if (query.surface) params.set("surface", query.surface);
  if (query.scope) params.set("scope", query.scope);
  return `/prep?${params}`;
}

/** The page for two players, from anywhere that has their ids. With no surface, the page asks. */
export function prepLink(playerId: number, opponentId: number, surface: string | null): string {
  return prepHref({ player: String(playerId), opponent: String(opponentId), surface, scope: null });
}

/** The browser's address for this page's data, through the app's /api proxy. */
export function matchupUrl(query: PrepQuery & { surface: string }): string {
  const params = new URLSearchParams({ player_id: query.player, opponent_id: query.opponent, surface: query.surface });
  if (query.scope) params.set("scope", query.scope);
  return `/api/matchup?${params}`;
}

/** "surface" is the default, so it stays out of the address. */
export function withScope(query: PrepQuery, scope: Scope): PrepQuery {
  return { ...query, scope: scope === "all" ? "all" : null };
}

export function withPrepSurface(query: PrepQuery, surface: string): PrepQuery {
  return { ...query, surface };
}

// ---------- figures ----------

function figure(key: string, title: string, rate: Rate | undefined, unit: string, small: boolean, source: PatternRow["source"], t: T): PatternRow {
  const pct = rate ? ratePercent(rate) : null;
  return {
    key,
    title,
    value: pct === null ? t.noData : t.pct(pct.toFixed(1)),
    counts: rate && pct !== null ? `${t.countOf(rate.numerator, rate.denominator)} ${unit}` : t.noStatsFilter,
    small: pct !== null && small,
    hasBar: pct !== null,
    width: pct ?? 0,
    tick: null,
    source,
  };
}

type Described = Pick<StatBlock, "player" | "filters">;

/** The page shows two players, so each source card says whose figure it is. Its filters read
 * like a report's source card, the report's window included, with dates in words. */
function owned(source: SourceFacts, block: Described, t: T): SourceFacts {
  const filters = describeFilters(block.filters, t).join("; ");
  return { ...source, tool: `${source.tool}, ${t.panelFor(block.player.name)}`, filters: filters ? `${withLongDates(filters, t)}.` : source.filters };
}

function ownedRows(rows: PatternRow[], block: Described, t: T): PatternRow[] {
  return rows.map((row) => ({ ...row, source: owned(row.source, block, t) }));
}

/** "on clay", or "on all surfaces" when the page shows every surface. */
export function whereWords(m: Pick<Matchup, "surface" | "scope">, t: T = EN): string {
  return m.scope === "all" ? t.onAllSurfaces : surfaceWords(t, m.surface).on;
}

const names = (m: Matchup) => ({ player: lastName(m.player.player.name), opponent: lastName(m.opponent.player.name) });

// ---------- header ----------

export interface ScopeChoice {
  id: Scope;
  label: string;
  pressed: boolean;
}

export interface HeaderView {
  window: string;
  scopes: ScopeChoice[];
}

export function headerView(m: Matchup, t: T = EN): HeaderView {
  return {
    window: t.prepWindow(longDate(m.window.date_from, t), longDate(m.window.date_to, t)),
    scopes: [
      { id: "surface", label: surfaceWords(t, m.surface).onCap, pressed: m.scope === "surface" },
      { id: "all", label: t.scopeAllSurfaces, pressed: m.scope === "all" },
    ],
  };
}

// ---------- head-to-head ----------

export interface MeetingRow {
  key: string;
  date: string;
  event: string;
  round: string;
  surface: string;
  swatch: string | null;
  winner: string;
  playerWon: boolean;
  score: string;
}

export interface HeadToHeadView {
  career: string;
  onSurface: string;
  small: boolean;
  scoreHeader: string;
  note: string | null;
  rows: MeetingRow[];
}

const SWATCHES = new Set(["hard", "clay", "grass"]);

/** Every meeting, on any date, read from the player's side: the head-to-head tool is asked with
 * the player first, so W is the player's win and player_score has the player's games first. */
export function headToHeadView(m: Matchup, t: T = EN): HeadToHeadView {
  const h2h = m.head_to_head;
  const who = names(m);
  const w = surfaceWords(t, m.surface);
  const on = h2h.by_surface.find((s) => s.surface === m.surface);
  const excluded = describeExcluded(h2h.excluded, t);
  return {
    career: h2h.record.matches ? t.againstRecord(who.player, h2h.record.wins, who.opponent, h2h.record.losses, "") : t.noMeetings(""),
    onSurface: on?.matches ? t.againstRecord(who.player, on.wins, who.opponent, on.losses, w.on) : t.noMeetings(w.on),
    small: Boolean(on?.matches && on.matches < SMALL_SAMPLE),
    scoreHeader: t.colScoreFrom(who.player),
    note: excluded.length ? t.leftOutList(excluded.join(", ")) : null,
    rows: h2h.matches.map((match, i): MeetingRow => {
      const swatch = match.surface?.toLowerCase() ?? null;
      const won = match.result === "W";
      return {
        key: `${match.tourney_date}-${match.round}-${i}`,
        date: longDate(match.match_date ?? match.tourney_date, t),
        event: eventName(match.tournament),
        round: roundName(match.round, t),
        surface: match.surface ? surfaceWords(t, match.surface).lower : t.unknownSurface,
        swatch: swatch && SWATCHES.has(swatch) ? `sw-${swatch}` : null,
        winner: won ? who.player : who.opponent,
        playerWon: won,
        score: match.player_score ?? match.score ?? t.noScore,
      };
    }),
  };
}

// ---------- each serve against the other's return ----------

// Each serve figure, and the returner's figure for the same points: their return of first
// serves, of second serves, of every serve, and their break points converted against the
// server's saved. First serve in has no return side.
const PAIRS: [serve: string, ret: string | null][] = [
  ["first_serve_in", null],
  ["first_serve_points_won", "first_serve_return_points_won"],
  ["second_serve_points_won", "second_serve_return_points_won"],
  ["service_points_won", "return_points_won"],
  ["break_points_saved", "break_points_converted"],
];
const FROM_PRESSURE = new Set(["break_points_saved", "break_points_converted"]);

function serveFigure(key: string, side: Side, t: T): PatternRow {
  const block = FROM_PRESSURE.has(key) ? side.pressure : side.serve_return;
  const small = block.sample.matches_with_stats < SMALL_SAMPLE;
  return figure(key, t.stats[key], block.stats[key], t.serveUnits[key], small, owned(sourceFacts(block, t), block, t), t);
}

export interface ServePair {
  key: string;
  serve: PatternRow;
  ret: PatternRow | null;
}

export interface ServeView {
  server: Who;
  title: string;
  note: string;
  serving: string;
  returning: string;
  rows: ServePair[];
}

/** When `server` serves: each of their serve figures against the other player's return. */
export function serveView(m: Matchup, server: Who, t: T = EN): ServeView {
  const returner = OTHER[server];
  const who = names(m);
  const where = whereWords(m, t);
  return {
    server,
    title: t.servesTitle(who[server]),
    note: t.servesNote(who[server], who[returner], where),
    serving: t.serving(who[server]),
    returning: t.returning(who[returner]),
    rows: PAIRS.map(([serve, ret]) => ({
      key: serve,
      serve: serveFigure(serve, m.sides[server], t),
      ret: ret ? serveFigure(ret, m.sides[returner], t) : null,
    })),
  };
}

// ---------- the same figure for both players ----------

export interface TwoRow {
  key: string;
  title: string;
  player: PatternRow;
  opponent: PatternRow;
}

function pairUp(player: PatternRow[], opponent: PatternRow[]): TwoRow[] {
  return player.map((row, i) => {
    const other = opponent[i];
    if (other?.key !== row.key) throw new Error(`rows out of step: ${row.key} and ${other?.key}`);
    return { key: row.key, title: row.title, player: row, opponent: other };
  });
}

export interface SetsView {
  note: string;
  rows: TwoRow[];
}

export function setsView(m: Matchup, t: T = EN): SetsView {
  const who = names(m);
  const [p, o] = [m.sides.player.set_patterns, m.sides.opponent.set_patterns];
  return {
    note: t.prepSetsNote(who.player, p.scores_read.completed_matches, who.opponent, o.scores_read.completed_matches, whereWords(m, t)),
    rows: pairUp(ownedRows(setRows(p, t), p, t), ownedRows(setRows(o, t), o, t)),
  };
}

export interface ChartedSide {
  who: Who;
  title: string;
  secondTitle: string;
  /** Set when the player has no charted match here; the serve-direction table is then left out. */
  none: string | null;
  view: ShotView;
  /** Shot direction (D-038); null for a response cached before it existed, or none charted. */
  direction: ShotDirectionView | null;
  directionTitle: string;
}

export interface ShotsView {
  note: string;
  sides: ChartedSide[];
  rallies: TwoRow[];
  net: TwoRow[];
}

function ownedDirection(shots: ShotPatterns, t: T): ShotDirectionView | null {
  const view = shotDirectionView(shots, t);
  return view && { ...view, source: owned(view.source, shots, t) };
}

export function shotsView(m: Matchup, t: T = EN): ShotsView {
  const who = names(m);
  const where = whereWords(m, t);
  const view = (side: Who): ShotView => {
    const shots = m.sides[side].shots;
    const v = shotView(shots, t);
    return { ...v, source: owned(v.source, shots, t), rallies: ownedRows(v.rallies, shots, t), net: ownedRows(v.net, shots, t) };
  };
  const views = { player: view("player"), opponent: view("opponent") };
  return {
    note: t.prepShotsNote(who.player, views.player.charted, who.opponent, views.opponent.charted, where),
    sides: (["player", "opponent"] as const).map((side) => ({
      who: side,
      title: t.firstServesInFor(who[side]),
      secondTitle: t.secondServesFor(who[side]),
      none: views[side].charted ? null : t.noChartedFor(who[side], where),
      view: views[side],
      direction: ownedDirection(m.sides[side].shots, t),
      directionTitle: t.shotDirFor(who[side]),
    })),
    rallies: pairUp(views.player.rallies, views.opponent.rallies),
    net: pairUp(views.player.net, views.opponent.net),
  };
}

// ---------- records ----------

export interface RecordCard {
  who: Who;
  name: string;
  figure: PatternRow;
  line: string;
  href: string;
  linkText: string;
}

export function recordView(m: Matchup, t: T = EN): RecordCard[] {
  const where = whereWords(m, t);
  return (["player", "opponent"] as const).map((side) => {
    const block = m.sides[side].record;
    const { overall } = block;
    const profile = m[side];
    return {
      who: side,
      name: profile.player.name,
      figure: figure("win_rate", t.stats.win_rate, overall.win_rate, t.matchesWord, overall.matches < SMALL_SAMPLE, owned(sourceFacts(block, t), block, t), t),
      line: t.recordLine(overall.wins, overall.losses, where),
      href: pageHref({ id: String(profile.player.player_id), surface: null, season: null, against: null }),
      linkText: t.playerStatsOf(lastName(profile.player.name)),
    };
  });
}
