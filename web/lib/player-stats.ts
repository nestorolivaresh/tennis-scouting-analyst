// The Player stats page's URL and data shaping. Every figure comes from a block of the API's
// response (GET /players/{id}/stats) and is described from that block's own tool, filters, sample
// and excluded counts. A rate with nothing to divide by stays missing; it never becomes 0.

import { TOOL_NAMES, describeExcluded, describeFilters, formatValue, sampleLine } from "./evidence.ts";
import type { Handoff } from "./handoff.ts";
import { eventName, handName, lastName, longDate, monthYear, roundName } from "./people.ts";
import type { Candidate, PlayerRef, Rate, Sample, SearchResult } from "./types.ts";

// ---------- the response ----------

export interface RecordSummary {
  matches: number;
  wins: number;
  losses: number;
  win_rate: Rate;
}

export interface PageFilters {
  surface: string | null;
  season: number | null;
}

interface Block {
  tool: string;
  player: PlayerRef;
  filters: PageFilters & Record<string, unknown>;
  sample: Sample;
  excluded: Record<string, number>;
}

export interface SurfaceSplits extends Block {
  overall: RecordSummary;
  surfaces: (RecordSummary & { surface: string })[];
}

export interface StatBlock extends Block {
  stats: Record<string, Rate>;
}

export interface MatchEntry {
  tourney_date: string;
  match_date: string | null;
  tournament: string;
  surface: string | null;
  round: string;
  result: "W" | "L";
  score: string | null;
  rank: number | null;
  opponent: PlayerRef & { rank: number | null };
}

export interface RecentForm extends Block {
  n: number;
  record: RecordSummary;
  matches: MatchEntry[];
}

export interface HeadToHead extends Block {
  opponent: PlayerRef;
  record: RecordSummary;
}

export interface Profile {
  tool: string;
  player: PlayerRef;
  hand: string | null;
  country: string | null;
  height_cm: number | null;
  matches_loaded: number;
  first_tourney_date: string | null;
  last_match: { tourney_date: string } | null;
  latest_rank: { rank: number; tournament: string; tourney_date: string; match_date: string | null } | null;
}

export interface DataWindow {
  first_tourney_date: string | null;
  last_tourney_date: string | null;
  last_match_date: string | null;
}

export interface SeasonEntry {
  season: number;
  overall: RecordSummary;
}

export interface PlayerStats {
  profile: Profile;
  filters: PageFilters;
  data_window: DataWindow;
  seasons: SeasonEntry[];
  by_surface: SurfaceSplits;
  record: SurfaceSplits;
  serve_return: StatBlock;
  pressure: StatBlock;
  recent_form: RecentForm;
  career: { serve_return: StatBlock; pressure: StatBlock };
  head_to_head: HeadToHead | null;
}

// ---------- the URL ----------

/** The page's state, as text from the URL. Nothing is checked here: the API validates every
 * value and its error is what the page shows. */
export interface PageQuery {
  id: string;
  surface: string | null;
  season: string | null;
  against: string | null;
}

/** The page's state from its URL, or null when no player has been chosen yet. */
export function parseQuery(params: { get(name: string): string | null }): PageQuery | null {
  const read = (name: string) => params.get(name)?.trim() || null;
  const id = read("id");
  return id ? { id, surface: read("surface"), season: read("season"), against: read("against") } : null;
}

/** The state after the first player is picked from the empty page. */
export function queryForPlayer(playerId: number): PageQuery {
  return { id: String(playerId), surface: null, season: null, against: null };
}

export function pageHref(query: PageQuery): string {
  const params = new URLSearchParams({ id: query.id });
  if (query.surface) params.set("surface", query.surface);
  if (query.season) params.set("season", query.season);
  if (query.against) params.set("against", query.against);
  return `/players?${params}`;
}

/** The browser's address for this page's data, through the app's /api proxy. */
export function statsUrl(query: PageQuery): string {
  const params = new URLSearchParams();
  if (query.surface) params.set("surface", query.surface);
  if (query.season) params.set("season", query.season);
  if (query.against) params.set("opponent_id", query.against);
  const search = params.toString();
  return `/api/players/${encodeURIComponent(query.id)}/stats${search ? `?${search}` : ""}`;
}

export function withSurface(query: PageQuery, tile: SurfaceTileId): PageQuery {
  return { ...query, surface: tile === "All" ? null : tile };
}

export function withSeason(query: PageQuery, season: number | null): PageQuery {
  return { ...query, season: season === null ? null : String(season) };
}

export function withoutFilters(query: PageQuery): PageQuery {
  return { ...query, surface: null, season: null };
}

/** A new player keeps the filters and the comparison, unless they are the player being compared
 * with: the API refuses a player against themselves. */
export function withPlayer(query: PageQuery, playerId: number): PageQuery {
  const id = String(playerId);
  return { ...query, id, against: query.against === id ? null : query.against };
}

export function withAgainst(query: PageQuery, playerId: number | null): PageQuery {
  return { ...query, against: playerId === null ? null : String(playerId) };
}

/** 404 and 422 answer the link itself, so asking again can't help. Anything else might pass. */
export function isBadLink(status: number): boolean {
  return status === 404 || status === 422;
}

// ---------- words and numbers ----------

function count(n: number): string {
  return formatValue(n, null);
}

function plural(n: number, one: string, many: string): string {
  return `${count(n)} ${n === 1 ? one : many}`;
}

/** The rate as it reads on screen, or null when there was nothing to divide by. Worked out from
 * the counts because the API's value is already rounded to four places, and rounding that again
 * can move the last digit: 37 of 43 is 86.0%, but its 0.8605 would read 86.1%. */
function rateText(rate: Rate | undefined): string | null {
  return rate && rate.value !== null ? formatValue(rate.numerator / rate.denominator, rate) : null;
}

function barWidth(rate: Rate | undefined): number {
  return rate && rate.value !== null ? Math.min(100, Math.max(0, 100 * rate.value)) : 0;
}

export function isFiltered(filters: PageFilters): boolean {
  return Boolean(filters.surface || filters.season);
}

/** "on clay in 2025", or "" with no filters. */
function context(filters: PageFilters): string {
  return [filters.surface && `on ${filters.surface.toLowerCase()}`, filters.season && `in ${filters.season}`].filter(Boolean).join(" ");
}

export function showingText(filters: PageFilters): string {
  const where = filters.surface ? `${filters.surface.toLowerCase()} courts` : "every surface";
  return `Showing ${where}, ${filters.season ?? "every season"}.`;
}

export function coverageLine(window: DataWindow | null): string {
  const first = window?.first_tourney_date?.slice(0, 4);
  const last = window?.last_match_date ?? window?.last_tourney_date;
  const span = first && last ? ` from ${first}, through ${longDate(last)}` : "";
  return `ATP tour-level singles${span}. Every number comes from tested database queries, with no AI model involved.`;
}

/** Country, hand, height and latest ranking, leaving out whatever isn't known. `country` is the
 * country's name when the app has one; otherwise the data's code is shown. */
export function bioLine(profile: Pick<Profile, "country" | "hand" | "height_cm" | "latest_rank">, country: string | null): string {
  const facts = [country ?? profile.country, handName(profile.hand), profile.height_cm === null ? null : `${profile.height_cm} cm`]
    .filter(Boolean)
    .join(", ");
  const about = facts && `${facts.charAt(0).toUpperCase()}${facts.slice(1)}.`;
  const rank = profile.latest_rank;
  const ranked = rank && `Ranked ${rank.rank} at ${eventName(rank.tournament)}, ${monthYear(rank.match_date ?? rank.tourney_date)}.`;
  return [about, ranked].filter(Boolean).join(" ");
}

export interface BoardNumbers {
  matches: string;
  won: string;
  lost: string;
  winRate: string;
  hasWinRate: boolean;
}

/** The four hanging tiles. A true count of 0 is a count; a rate over 0 matches is not a rate. */
export function boardNumbers(record: RecordSummary): BoardNumbers {
  const winRate = rateText(record.win_rate);
  return { matches: count(record.matches), won: count(record.wins), lost: count(record.losses), winRate: winRate ?? "No data", hasWinRate: winRate !== null };
}

export function countedNote(record: Pick<SurfaceSplits, "filters" | "sample" | "excluded">, playerName: string): string {
  const { sample } = record;
  const parts: string[] = [];
  if (!sample.matches_counted) {
    parts.push(isFiltered(record.filters) ? "No matches for this filter." : "No matches in the data.");
  } else {
    const range = sample.first_tourney_date && sample.last_tourney_date
      ? ` in tournaments starting ${longDate(sample.first_tourney_date)} to ${longDate(sample.last_tourney_date)}`
      : "";
    parts.push(`Counts ${plural(sample.matches_counted, "match", "matches")}${range}.`);
  }
  const excluded = describeExcluded(record.excluded);
  if (excluded.length) parts.push(`${excluded.join(", ")} left out.`);
  const { opponent_retired_or_defaulted: byOpponents, player_retired_or_defaulted: byPlayer } = sample;
  if (byOpponents + byPlayer > 0) {
    parts.push(`Retirements and defaults count: ${byOpponents} by opponents, ${byPlayer} by ${lastName(playerName)}.`);
  }
  return parts.join(" ");
}

// ---------- record by surface ----------

export type SurfaceTileId = "All" | "Hard" | "Clay" | "Grass";

export interface SurfaceTile {
  id: SurfaceTileId;
  name: string;
  swatch: string;
  on: boolean;
  rate: string;
  hasRate: boolean;
  record: string;
}

const SURFACE_TILES: SurfaceTileId[] = ["All", "Hard", "Clay", "Grass"];

export function surfaceTiles(splits: Pick<SurfaceSplits, "overall" | "surfaces">, query: PageQuery): SurfaceTile[] {
  const chosen = (query.surface ?? "All").toLowerCase();
  return SURFACE_TILES.map((id) => {
    const record = id === "All" ? splits.overall : splits.surfaces.find((s) => s.surface === id);
    const rate = rateText(record?.win_rate);
    return {
      id,
      name: id === "All" ? "All surfaces" : id,
      swatch: `sw-${id.toLowerCase()}`,
      on: id.toLowerCase() === chosen,
      rate: rate ?? "No matches",
      hasRate: rate !== null,
      record: record && rate !== null ? `${record.wins}-${record.losses}` : "",
    };
  });
}

// ---------- season by season ----------

export interface SeasonRow {
  key: string;
  season: number | null;
  label: string;
  on: boolean;
  width: number;
  record: string;
  rate: string;
}

/** The record over every listed season. The API lists each season a player has a counted match
 * in, so this is the player's whole record under the page's surface filter. */
export function sumRecords(records: RecordSummary[]): RecordSummary {
  const wins = records.reduce((sum, r) => sum + r.wins, 0);
  const matches = records.reduce((sum, r) => sum + r.matches, 0);
  return { matches, wins, losses: matches - wins, win_rate: { value: matches ? wins / matches : null, numerator: wins, denominator: matches, unit: "fraction" } };
}

export function seasonRows(seasons: SeasonEntry[], query: PageQuery): SeasonRow[] {
  const row = (season: number | null, record: RecordSummary, on: boolean): SeasonRow => {
    const rate = rateText(record.win_rate);
    return {
      key: season === null ? "all" : String(season),
      season,
      label: season === null ? "All seasons" : String(season),
      on,
      width: barWidth(record.win_rate),
      record: rate === null ? "" : `${record.wins}-${record.losses}`,
      rate: rate ?? "No matches",
    };
  };
  return [
    row(null, sumRecords(seasons.map((s) => s.overall)), query.season === null),
    ...seasons.map((s) => row(s.season, s.overall, Number(query.season) === s.season)),
  ];
}

export function seasonNote(filters: PageFilters): string {
  return `${filters.surface ? `On ${filters.surface.toLowerCase()}` : "Every surface"}. Choose a year to filter the page.`;
}

// ---------- serve and return ----------

export interface SourceFacts {
  tool: string;
  filters: string;
  sample: string;
  left: string;
}

/** The Source panel: what this block of the response says about itself. */
export function sourceFacts(block: Pick<Block, "tool" | "filters" | "sample" | "excluded">): SourceFacts {
  const filters = describeFilters(block.filters);
  const { sample } = block;
  const line = sample.matches_counted
    ? sampleLine({
        ...sample,
        first_tourney_date: sample.first_tourney_date && longDate(sample.first_tourney_date),
        last_tourney_date: sample.last_tourney_date && longDate(sample.last_tourney_date),
      })
    : null;
  const left = describeExcluded(block.excluded);
  return {
    tool: TOOL_NAMES[block.tool] ?? block.tool,
    filters: filters.length ? `${filters.join(", ")}.` : "None: every surface and season.",
    sample: line ? `${line}.` : "No matches counted.",
    left: left.length ? `${left.join(", ")}.` : "Nothing.",
  };
}

export interface ServeRow {
  key: string;
  title: string;
  value: string;
  counts: string;
  small: boolean;
  hasBar: boolean;
  width: number;
  /** Where the career figure sits on the bar, or null when there is no tick to draw. */
  tick: number | null;
  source: SourceFacts;
}

export interface ServeGroup {
  name: string;
  rows: ServeRow[];
}

type RowDefinition = [key: string, title: string, block: "serve_return" | "pressure", unit: string | null];

const SERVE_GROUPS: [name: string, rows: RowDefinition[]][] = [
  ["On serve", [
    ["first_serve_in", "First serve in", "serve_return", "serve points"],
    ["first_serve_points_won", "First-serve points won", "serve_return", "first-serve points"],
    ["second_serve_points_won", "Second-serve points won", "serve_return", "second-serve points"],
    ["service_points_won", "Service points won", "serve_return", "serve points"],
    ["break_points_saved", "Break points saved", "pressure", "break points faced"],
    ["aces_per_match", "Aces per match", "serve_return", null],
  ]],
  ["On return", [
    ["return_points_won", "Return points won", "serve_return", "return points"],
    ["break_points_converted", "Break points converted", "pressure", "break points earned"],
  ]],
];

const SMALL_SAMPLE = 10;

export function serveGroups(data: Pick<PlayerStats, "filters" | "serve_return" | "pressure" | "career">): ServeGroup[] {
  const filtered = isFiltered(data.filters);
  const row = ([key, title, from, unit]: RowDefinition): ServeRow => {
    const block = data[from];
    const rate: Rate | undefined = block.stats[key];
    const career: Rate | undefined = data.career[from].stats[key];
    const value = rateText(rate);
    const hasBar = unit !== null;
    let counts = filtered ? "No matches with stats for this filter" : "No matches with stats";
    if (rate && value !== null) {
      counts = hasBar
        ? `${count(rate.numerator)} of ${count(rate.denominator)} ${unit}`
        : `${plural(rate.numerator, "ace", "aces")} in ${plural(rate.denominator, "match", "matches")}`;
    }
    return {
      key,
      title,
      value: value ?? "No data",
      counts,
      small: value !== null && block.sample.matches_with_stats < SMALL_SAMPLE,
      hasBar,
      width: hasBar ? barWidth(rate) : 0,
      tick: hasBar && filtered && career && career.value !== null ? barWidth(career) : null,
      source: sourceFacts(block),
    };
  };
  return SERVE_GROUPS.map(([name, rows]) => ({ name, rows: rows.map(row) }));
}

export function serveNote(filters: PageFilters): string {
  return isFiltered(filters)
    ? "Open a number to see its source. The brass tick marks the figure across every surface and season."
    : "Open a number to see its source.";
}

// ---------- against ----------

export interface AgainstView {
  title: string;
  text: string;
  note: string | null;
}

/** The head-to-head in the page's words, from that block's own players, record and filters. */
export function againstView(h2h: HeadToHead): AgainstView {
  const { wins, losses, matches } = h2h.record;
  const where = context(h2h.filters);
  const text = matches
    ? `${lastName(h2h.player.name)} ${wins}, ${lastName(h2h.opponent.name)} ${losses} ${where || "across every meeting in the data"}.`
    : `No meetings ${where || "in the data"}.`;
  const excluded = describeExcluded(h2h.excluded);
  return { title: `Against ${h2h.opponent.name}`, text, note: excluded.length ? `${excluded.join(", ")} left out.` : null };
}

// ---------- last 10 matches ----------

export interface FormRow {
  key: string;
  date: string;
  event: string;
  round: string;
  surface: string;
  swatch: string | null;
  opponent: string;
  rank: string;
  won: boolean;
  score: string;
}

export interface FormView {
  title: string;
  note: string;
  rows: FormRow[];
}

const SWATCHES = new Set(["hard", "clay", "grass"]);

export function formView(form: Pick<RecentForm, "n" | "filters" | "record" | "matches">): FormView {
  const where = context(form.filters);
  const returned = form.matches.length;
  const rows = form.matches.map((m, i): FormRow => {
    const surface = m.surface?.toLowerCase() ?? null;
    return {
      key: `${m.tourney_date}-${m.round}-${m.opponent.player_id}-${i}`,
      date: monthYear(m.match_date ?? m.tourney_date),
      event: eventName(m.tournament),
      round: roundName(m.round),
      surface: surface ?? "unknown surface",
      swatch: surface && SWATCHES.has(surface) ? `sw-${surface}` : null,
      opponent: m.opponent.name,
      rank: m.opponent.rank ? `No. ${m.opponent.rank}` : "No ranking in the data",
      won: m.result === "W",
      score: m.score ?? "No score in the data",
    };
  });
  return {
    title: returned === 1 ? "Last match" : `Last ${returned || form.n} matches`,
    note: returned
      ? `Newest first, ${where || "any surface or season"}. Won ${form.record.wins} of these ${returned}.`
      : `No matches ${where || "in the data"}.`,
    rows,
  };
}

// ---------- handing off to scouting ----------

export function candidateFromProfile(profile: Profile): Candidate {
  return {
    player_id: profile.player.player_id,
    name: profile.player.name,
    country: profile.country,
    hand: profile.hand,
    matches_loaded: profile.matches_loaded,
    last_tourney_date: profile.last_match?.tourney_date ?? null,
  };
}

/** "Scout {name}": the player on this page is the one to be scouted, so the opponent in setup. */
export function scoutHandoff(profile: Profile): Handoff {
  return { opponent: candidateFromProfile(profile) };
}

/** "Scout this match-up": a report for the player being compared with, on how to beat this one. */
export function matchupHandoff(profile: Profile, comparedWith: Candidate): Handoff {
  return { opponent: candidateFromProfile(profile), player: comparedWith };
}

/** The search result for this exact player, since a name alone can match several people. */
export function findCandidate(result: SearchResult, playerId: number): Candidate | null {
  return result.candidates.find((c) => c.player_id === playerId) ?? null;
}
