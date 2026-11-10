// What the loader shows, worked out only from the events of POST /report/stream. Nothing here
// runs on a timer or estimates progress, so every rule can be tested with a list of events.

import { EN, type T } from "./i18n.ts";
import { progressSteps, type Step } from "./progress.ts";
import type { ReportEvent, ReportResponse } from "./types.ts";

export type Stage = "look" | "write" | "check" | "deuce" | "adv" | "done";
export type Shot = "rally" | "clip" | "finish";
export type FlapPosition = "now" | "past" | "next";

export interface LoaderState {
  stage: Stage;
  /** The label on the flap showing now. */
  score: string;
  /** The flaps in play, in the order they turn. */
  scores: string[];
  title: string;
  note: string;
  /** How many times the check has failed so far; the net clip plays once for each. */
  corrections: number;
}

/** Every flap on the board. Deuce and Ad stay out of sight until a correction needs them. */
export const ALL_SCORES = ["15", "30", "40", "Deuce", "Ad", "Game"];
const CLEAN_SCORES = ["15", "30", "40", "Game"];

const SCORE: Record<Stage, string> = { look: "15", write: "30", check: "40", deuce: "Deuce", adv: "Ad", done: "Game" };

/** How long "Game" stays up before a verified report is shown. */
export const GAME_HOLD_MS = 1_200;

export function loaderState(events: ReportEvent[], final: ReportResponse | null, seconds: number, t: T = EN): LoaderState {
  const { running, corrections } = readEvents(events);
  // Only a report that passed the check may claim that its numbers match.
  const verified = final?.status === "verified" ? final.report : null;
  const stage = verified ? "done" : running;
  return {
    stage,
    score: SCORE[stage],
    scores: corrections > 0 || running === "adv" ? ALL_SCORES : CLEAN_SCORES,
    title: stage === "deuce" ? deuceTitle(events, t) : t.loaderTitles[stage],
    note: verified ? t.allKeyNumbersMatch(verified.key_stats.length) : t.secondsSoFar(seconds),
    corrections,
  };
}

function readEvents(events: ReportEvent[]): { running: Stage; corrections: number } {
  let running: Stage = "look";
  let corrections = 0;
  for (const e of events) {
    if (e.event === "correcting") {
      running = "deuce";
      corrections += 1;
    } else if (e.event === "checking") {
      running = e.data.attempt === 1 ? "check" : "adv";
    } else if (running === "deuce") {
      // Everything between a failed check and the next check is the rewrite.
    } else if (e.event === "tool_call") {
      running = "look";
    } else if (e.event === "model_call") {
      // What a call is doing shows only in what follows it, and the stream sends no text while
      // the report is written. So a later call reads as writing unless a tool_call comes next.
      running = e.data.call > 1 ? "write" : "look";
    }
  }
  return { running, corrections };
}

/** Deuce is the one stage titled by what is happening: the check that failed, then the rewrite. */
function deuceTitle(events: ReportEvent[], t: T): string {
  const steps = progressSteps(events, new Map(), t).filter((s) => s.key === "correct" || s.key.startsWith("model-"));
  return steps[steps.length - 1].text;
}

/** Where a flap sits. A flap not in play stays waiting, so it never sweeps past the window. */
export function flapPosition(label: string, state: Pick<LoaderState, "score" | "scores">): FlapPosition {
  const at = state.scores.indexOf(state.score);
  const n = state.scores.indexOf(label);
  if (n === -1 || n > at) return "next";
  return n === at ? "now" : "past";
}

/** The next shot, asked for only while the ball is out of view. `clipped` is how many corrections
 * have already had their net clip. */
export function nextShot(stage: Stage, corrections: number, clipped: number): { shot: Shot; clipped: number } {
  if (stage === "done") return { shot: "finish", clipped };
  if (stage === "deuce" && clipped < corrections) return { shot: "clip", clipped: corrections };
  return { shot: "rally", clipped };
}

/** The one line a screen reader hears. It depends on the steps alone, never on the timer. */
export function loaderStatus(state: LoaderState, steps: Step[], t: T = EN): string {
  if (state.stage === "done") return state.title;
  return steps[steps.length - 1]?.text ?? t.starting;
}

/** Milliseconds to hold on "Game" before showing this report. */
export function reportHold(report: ReportResponse, reducedMotion: boolean): number {
  return report.status === "verified" && report.report && !reducedMotion ? GAME_HOLD_MS : 0;
}
