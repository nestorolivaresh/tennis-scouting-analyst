// A player's season path on the Player stats page (D-035): each tournament they played in one
// season, how it ended and their matches there, read from the season_path block of the response.
// Walkovers are listed and marked not counted; they never enter a win-loss.

import { EN, type T, surfaceWords } from "./i18n.ts";
import { eventName, lastName, longDate, roundName } from "./people.ts";
import { type MatchEntry, type SourceFacts, type StatBlock, sourceFacts } from "./player-stats.ts";

// ---------- the response ----------

export type Outcome = "title" | "lost" | "withdrew" | "round_robin" | "team" | "tie" | "bronze" | "fourth" | "no_later_match";

export interface PathMatch extends MatchEntry {
  result_type: string;
  counted: boolean;
}

interface Tally {
  matches: number;
  wins: number;
  losses: number;
}

export interface PathEvent {
  tournament: string;
  level: string;
  surface: string | null;
  tourney_date: string;
  record: Tally;
  walkovers: number;
  outcome: Outcome;
  round: string;
  last_match: PathMatch;
  matches: PathMatch[];
}

export interface SeasonPath extends Omit<StatBlock, "stats"> {
  summary: { events: number; titles: number; record: Tally; walkovers_shown: number };
  events: PathEvent[];
}

// ---------- the view ----------

export interface PathMatchView {
  key: string;
  round: string;
  opponent: string;
  rank: string;
  won: boolean;
  score: string;
  counted: boolean;
}

export interface PathRow {
  key: string;
  date: string;
  event: string;
  surface: string;
  swatch: string | null;
  record: string;
  ended: string;
  last: string;
  title: boolean;
  matchCount: string;
  matches: PathMatchView[];
}

export interface PathView {
  title: string;
  note: string;
  summary: string | null;
  empty: string | null;
  rows: PathRow[];
  source: SourceFacts;
}

const SWATCHES = new Set(["hard", "clay", "grass"]);

/** "in 2025", or "on clay in 2025" under a surface filter. */
function where(path: SeasonPath, t: T): string {
  const season = t.inSeason(String(path.filters.season));
  return path.filters.surface ? `${surfaceWords(t, path.filters.surface).on} ${season}` : season;
}

/** How the tournament ended, in words. The round comes from the player's last match there. */
export function endedText(event: Pick<PathEvent, "outcome" | "round">, t: T = EN): string {
  switch (event.outcome) {
    case "lost": return t.pathLost(event.round);
    case "withdrew": return t.pathWithdrew(event.round);
    case "team": return t.pathTeam(event.round);
    default: return Object.hasOwn(t.pathOutcome, event.outcome) ? t.pathOutcome[event.outcome] : event.outcome;
  }
}

function lastText(match: PathMatch, t: T): string {
  const name = lastName(match.opponent.name);
  if (match.result_type === "walkover") return t.pathLastWalkover(match.result === "W", name);
  return t.pathLast(match.result === "W", name, match.player_score ?? match.score ?? t.noScore);
}

export function pathView(path: SeasonPath, t: T = EN): PathView {
  const { events, summary } = path;
  const here = where(path, t);
  const rows = events.map((event, i): PathRow => {
    const swatch = event.surface?.toLowerCase() ?? null;
    return {
      key: `${event.tourney_date}-${i}`,
      date: longDate(event.tourney_date, t),
      event: eventName(event.tournament),
      surface: event.surface ? surfaceWords(t, event.surface).name : t.unknownSurface,
      swatch: swatch && SWATCHES.has(swatch) ? `sw-${swatch}` : null,
      record: `${t.int(event.record.wins)}-${t.int(event.record.losses)}`,
      ended: endedText(event, t),
      last: lastText(event.last_match, t),
      title: event.outcome === "title",
      matchCount: t.matchCount(event.matches.length),
      matches: event.matches.map((m, j) => ({
        key: `${j}-${m.round}-${m.opponent.player_id}`,
        round: roundName(m.round, t),
        opponent: m.opponent.name,
        rank: m.opponent.rank ? t.rankNumber(m.opponent.rank) : t.noRanking,
        won: m.result === "W",
        score: m.player_score ?? m.score ?? t.noScore,
        counted: m.counted,
      })),
    };
  });
  return {
    title: t.pathTitle(path.filters.season ?? 0),
    note: t.pathNote(here),
    summary: events.length ? t.pathSummary(summary.events, summary.titles, summary.record.wins, summary.record.losses) : null,
    empty: events.length ? null : t.pathEmpty(here),
    rows,
    source: sourceFacts(path, t),
  };
}
