// The Player stats page's scouting patterns (D-029) and charted shot patterns (D-030). Every
// figure is read from a block of the API's response; a rate with nothing to divide by stays
// missing, never 0.

import { ratePercent } from "./evidence.ts";
import { EN, type T } from "./i18n.ts";
import { type SourceFacts, type StatBlock, sourceFacts } from "./player-stats.ts";
import type { Rate } from "./types.ts";

// ---------- the response ----------

export interface SetPatterns extends StatBlock {
  scores_read: { completed_matches: number; ended_early: number; unreadable_scores: number };
}

export interface TourLine {
  value: Rate;
  rank: number | null;
  players_ranked: number;
  tour_median: number | null;
}

export interface TourComparison extends Omit<StatBlock, "stats"> {
  tour: { min_matches: number; qualifying_players: number; player_qualifies: boolean };
  stats: Record<string, TourLine>;
}

export type Court = Record<"wide" | "body" | "t", Rate>;

export interface ShotPatterns extends Omit<StatBlock, "stats"> {
  charting: { charted_matches: number; points_charted: number; player_charts_not_linked_all_dates: Record<string, number> };
  serve_direction: { matches: number; first_serves_in: Record<"deuce" | "ad", Court>; second_serves: Record<"deuce" | "ad", Court> };
  rally_length: { matches: number; points_won: Record<string, Rate> };
  net_points: { matches: number; net_points_won: Rate; share_of_points_at_net: Rate };
}

// ---------- shared ----------

export interface PatternRow {
  key: string;
  title: string;
  value: string;
  counts: string;
  small: boolean;
  hasBar: boolean;
  width: number;
  tick: null;
  source: SourceFacts;
}

const SMALL_SAMPLE = 10;

function percentText(rate: Rate | undefined, t: T): string | null {
  const pct = rate ? ratePercent(rate) : null;
  return pct === null ? null : t.pct(pct.toFixed(1));
}

function rateRow(key: string, title: string, rate: Rate | undefined, noun: string, source: SourceFacts, t: T): PatternRow {
  const value = percentText(rate, t);
  const pct = rate ? ratePercent(rate) : null;
  return {
    key,
    title,
    value: value ?? t.noData,
    counts: rate && value !== null ? `${t.countOf(rate.numerator, rate.denominator)} ${noun}` : t.noneToCount,
    small: rate !== undefined && value !== null && rate.denominator < SMALL_SAMPLE,
    hasBar: pct !== null,
    width: pct ?? 0,
    tick: null,
    source,
  };
}

// ---------- sets ----------

const SET_ROWS = ["tiebreaks_won", "deciding_sets_won", "won_after_winning_first_set", "won_after_losing_first_set"];

/** Tiebreaks, deciding sets and what happened after the first set, with what each counts. */
export function setRows(block: SetPatterns, t: T = EN): PatternRow[] {
  const source = sourceFacts(block, t, { n: block.scores_read.completed_matches, part: "completed" });
  return SET_ROWS.map((key) => rateRow(key, t.stats[key], block.stats[key], t.setUnits[key], source, t));
}

export function setNote(block: SetPatterns, t: T = EN): string {
  return t.setNote(block.scores_read.completed_matches, block.scores_read.ended_early);
}

// ---------- against the tour ----------

const TOUR_ROWS = [
  "service_points_won", "first_serve_points_won", "second_serve_points_won", "first_serve_in",
  "return_points_won", "break_points_saved", "break_points_converted",
];

export interface TourRow {
  key: string;
  title: string;
  value: string;
  rank: string;
  median: string;
}

/** The player's figure, rank and the median, for each rate. A player below the threshold
 * keeps their figures, with no rank. */
export function tourView(block: TourComparison, t: T = EN): { note: string; rows: TourRow[]; source: SourceFacts } {
  const { min_matches: min, qualifying_players: players, player_qualifies: qualifies } = block.tour;
  const rows = TOUR_ROWS.filter((key) => block.stats[key]).map((key): TourRow => {
    const line = block.stats[key];
    return {
      key,
      title: t.stats[key],
      value: percentText(line.value, t) ?? t.noData,
      rank: line.rank === null ? t.notRanked : t.rankOf(line.rank, line.players_ranked),
      median: line.tour_median === null ? t.noData : t.pct((Math.round(line.tour_median * 1000) / 10).toFixed(1)),
    };
  });
  return { note: qualifies ? t.tourNote(min, players) : t.tourNoteBelow(min, players), rows, source: sourceFacts(block, t) };
}

// ---------- charted shots ----------

const SIDES = ["wide", "body", "t"] as const;
const BANDS = ["1_3", "4_6", "7_9", "10_plus"];

export interface DirectionRow {
  court: string;
  cells: { side: string; value: string; counts: string }[];
}

export interface ShotView {
  charted: number;
  note: string;
  first: DirectionRow[];
  second: DirectionRow[];
  rallies: PatternRow[];
  net: PatternRow[];
  source: SourceFacts;
}

function directions(courts: Record<"deuce" | "ad", Court>, t: T): DirectionRow[] {
  return (["deuce", "ad"] as const).map((court) => ({
    court: t.courts[court],
    cells: SIDES.map((side) => {
      const rate = courts[court][side];
      return { side: t.directions[side], value: percentText(rate, t) ?? t.noData, counts: rate.denominator ? t.countOf(rate.numerator, rate.denominator) : "" };
    }),
  }));
}

/** Serve direction, points won by rally length and net points from the charted matches. */
export function shotView(block: ShotPatterns, t: T = EN): ShotView {
  const { charted_matches: charted, points_charted: points } = block.charting;
  const source = (n: number) => sourceFacts(block, t, { n, part: "charted" });
  const net = block.net_points;
  const rallySource = source(block.rally_length.matches);
  const netSource = source(net.matches);
  return {
    charted,
    note: charted ? t.chartedNote(charted, points) : t.noChartedMatches,
    first: directions(block.serve_direction.first_serves_in, t),
    second: directions(block.serve_direction.second_serves, t),
    rallies: BANDS.map((band) => rateRow(band, t.rallyBands[band], block.rally_length.points_won[band], t.pointsWord, rallySource, t)),
    net: [
      rateRow("net_points_won", t.stats.net_points_won, net.net_points_won, t.netPointsWord, netSource, t),
      rateRow("share_of_points_at_net", t.stats.share_of_points_at_net, net.share_of_points_at_net, t.pointsWord, netSource, t),
    ],
    source: source(charted),
  };
}
