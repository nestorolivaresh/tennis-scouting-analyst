// The Calendar page (D-036): every tournament of a season with its final, from GET /calendar, and
// one tournament's history across seasons. The data holds only tournaments already played; the
// page links to the ATP's own calendar for upcoming ones.

import { EN, type T, surfaceWords } from "./i18n.ts";
import { eventName, longDate } from "./people.ts";
import { type DataWindow, pageHref } from "./player-stats.ts";
import type { PlayerRef } from "./types.ts";

// ---------- the response ----------

export type FinalStatus = "final" | "team" | "no_final" | "unclear";

export interface Tournament {
  event_code: number;
  season: number;
  tournament: string;
  level: string;
  surface: string | null;
  tourney_date: string;
  last_match_date: string | null;
  is_exhibition: boolean;
  status: FinalStatus;
  final: { winner: PlayerRef; runner_up: PlayerRef; score: string | null; result_type: string } | null;
}

export interface SeasonCalendar {
  tool: string;
  filters: { season: number } & Record<string, unknown>;
  data_window: DataWindow;
  count: number;
  tournaments: Tournament[];
}

export interface TournamentHistory {
  tool: string;
  event_code: number;
  count: number;
  editions: Tournament[];
}

export interface CalendarResponse {
  calendar: SeasonCalendar;
  history: TournamentHistory | null;
}

/** The ATP's own calendar, for upcoming tournaments: their terms allow a link, not a copy. */
export const ATP_CALENDAR_URL = "https://www.atptour.com/en/tournaments";

// ---------- the URL ----------

/** The page's state, as text from the URL. The API validates every value. */
export interface CalendarQuery {
  season: string | null;
  event: string | null;
}

export function parseCalendarQuery(params: { get(name: string): string | null }): CalendarQuery {
  const read = (name: string) => params.get(name)?.trim() || null;
  return { season: read("season"), event: read("event") };
}

export function calendarHref(query: CalendarQuery): string {
  const params = new URLSearchParams();
  if (query.season) params.set("season", query.season);
  if (query.event) params.set("event", query.event);
  const search = params.toString();
  return `/calendar${search ? `?${search}` : ""}`;
}

export function calendarUrl(query: CalendarQuery): string {
  const params = new URLSearchParams();
  if (query.season) params.set("season", query.season);
  if (query.event) params.set("event", query.event);
  const search = params.toString();
  return `/api/calendar${search ? `?${search}` : ""}`;
}

/** Choosing a season closes any open history; opening a tournament keeps the season. */
export const withSeason = (query: CalendarQuery, season: number): CalendarQuery => ({ season: String(season), event: null });
export const withEvent = (query: CalendarQuery, code: number | null): CalendarQuery => ({ ...query, event: code === null ? null : String(code) });

// ---------- the view ----------

export interface FinalView {
  /** Set when one player won: the winner and runner-up with links to their Player stats. */
  winner: { name: string; href: string } | null;
  runnerUp: { name: string; href: string } | null;
  text: string;
  score: string | null;
}

export interface TournamentRow {
  key: string;
  code: number;
  date: string;
  event: string;
  level: string;
  surface: string;
  swatch: string | null;
  final: FinalView;
}

export interface MonthGroup {
  key: string;
  title: string;
  rows: TournamentRow[];
}

const SWATCHES = new Set(["hard", "clay", "grass"]);
const playerHref = (p: PlayerRef) => pageHref({ id: String(p.player_id), surface: null, season: null, against: null });

/** How the final reads: "Sinner beat Medvedev" with the score, or why no one player won it. */
export function finalView(t: Tournament, tr: T = EN): FinalView {
  if (t.status === "final" && t.final) {
    const { winner, runner_up: runnerUp } = t.final;
    return {
      winner: { name: winner.name, href: playerHref(winner) },
      runnerUp: { name: runnerUp.name, href: playerHref(runnerUp) },
      text: tr.calBeat(winner.name, runnerUp.name),
      score: t.final.score,
    };
  }
  const text = t.status === "team" ? tr.calTeam : t.status === "unclear" ? tr.calUnclear : tr.calNoFinal;
  return { winner: null, runnerUp: null, text, score: null };
}

function row(t: Tournament, tr: T): TournamentRow {
  const swatch = t.surface?.toLowerCase() ?? null;
  return {
    key: `${t.tourney_date}-${t.event_code}`,
    code: t.event_code,
    date: longDate(t.tourney_date, tr),
    event: eventName(t.tournament),
    level: Object.hasOwn(tr.calLevels, t.level) ? tr.calLevels[t.level] : t.level,
    surface: t.surface ? surfaceWords(tr, t.surface).name : tr.unknownSurface,
    swatch: swatch && SWATCHES.has(swatch) ? `sw-${swatch}` : null,
    final: finalView(t, tr),
  };
}

/** The season's tournaments by the month they start in, in date order. */
export function monthGroups(calendar: SeasonCalendar, tr: T = EN): MonthGroup[] {
  const groups: MonthGroup[] = [];
  for (const t of calendar.tournaments) {
    const [year, month] = t.tourney_date.split("-").map(Number);
    const key = `${year}-${month}`;
    if (groups[groups.length - 1]?.key !== key) groups.push({ key, title: tr.calMonth(month - 1, year), rows: [] });
    groups[groups.length - 1].rows.push(row(t, tr));
  }
  return groups;
}

/** The seasons to choose from: every season the data window covers, newest first. */
export function seasonChoices(window: DataWindow): number[] {
  const first = Number(window.first_tourney_date?.slice(0, 4));
  const last = Number(window.last_tourney_date?.slice(0, 4));
  if (!first || !last) return [];
  return Array.from({ length: last - first + 1 }, (_, i) => last - i);
}

export interface HistoryRow {
  key: string;
  year: number;
  /** The edition's own name, shown when it differs from the newest one (the tournament moved). */
  name: string | null;
  surface: string;
  final: FinalView;
}

export interface HistoryView {
  title: string;
  note: string;
  rows: HistoryRow[];
}

export function historyView(history: TournamentHistory, tr: T = EN): HistoryView {
  const newest = eventName(history.editions[0]?.tournament ?? "");
  return {
    title: tr.calHistory(newest),
    note: tr.calHistoryNote,
    rows: history.editions.map((e) => {
      const name = eventName(e.tournament);
      return {
        key: `${e.season}-${e.tourney_date}`,
        year: e.season,
        name: name === newest ? null : name,
        surface: e.surface ? surfaceWords(tr, e.surface).name : tr.unknownSurface,
        final: finalView(e, tr),
      };
    }),
  };
}
