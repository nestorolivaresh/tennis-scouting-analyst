"use client";

// The wait for a report, drawn as a game: the board's score, the court and the umpire's card all
// come from the real stream. The only clock here is the "seconds so far" count.

import { useEffect, useState } from "react";
import { Board } from "@/components/ui/Board.tsx";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { surfaceWords } from "@/lib/i18n.ts";
import { ALL_SCORES, type LoaderState, flapPosition, loaderState, loaderStatus } from "@/lib/loader.ts";
import { type Step, progressSteps } from "@/lib/progress.ts";
import type { ReportEvent, ReportResponse, Surface } from "@/lib/types.ts";
import { Court } from "./Court.tsx";
import styles from "./Loader.module.css";

export type LoaderProps = {
  player: string;
  opponent: string;
  surface: Surface;
  /** When the request was sent (ms since the epoch). */
  started: number;
  events: ReportEvent[];
  names: Map<number, string>;
  /** The verified report during its moment on "Game"; null until then. */
  final: ReportResponse | null;
};

const FLAP_CLASS = { now: styles.flapNow, past: styles.flapPast, next: styles.flapNext };

export function Loader({ player, opponent, surface, started, events, names, final }: LoaderProps) {
  const t = useT();
  const [now, setNow] = useState(started);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const state = loaderState(events, final, Math.max(0, Math.round((now - started) / 1000)), t);
  const steps = progressSteps(events, names, t);

  return (
    <main className={styles.main}>
      {/* Screen readers hear each new step once, not the ticking timer. */}
      <p className="vh" role="status">{loaderStatus(state, steps, t)}</p>

      <div className={styles.layout}>
        <div className={styles.boardColumn}>
          <Board aria-label={t.reportProgress}>
            <div className={styles.slats}>
              <div className={`slat ${styles.headerSlat}`}>
                <h1 className={styles.matchTitle}>{t.scoutingTitle(opponent, player)}</h1>
                <span className={styles.surfaceLabel}>
                  <span className={`sw sw-${surface.toLowerCase()} ${styles.chip}`} aria-hidden="true" />
                  {surfaceWords(t, surface).onCap}
                </span>
              </div>

              <div className={`slat ${styles.scoreSlat}`}>
                <ScoreWindow state={state} />
                <div className={styles.stageText}>
                  <h2 className={styles.stageTitle}>{state.title}</h2>
                  <p className={styles.stageNote}>{state.note}</p>
                </div>
              </div>

              <Court surface={surface} stage={state.stage} corrections={state.corrections} />
            </div>
          </Board>
        </div>

        <section className={styles.card} aria-labelledby="umpire-card-title">
          <h2 id="umpire-card-title" className={styles.cardTitle}>{t.umpireCard}</h2>
          <ol className={styles.steps}>
            {steps.map((step) => (
              <StepLine key={step.key} step={step} finished={state.stage === "done"} />
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}

/** All six flaps are always there, so Deuce can turn into the window the moment a check fails. */
function ScoreWindow({ state }: { state: LoaderState }) {
  const t = useT();
  return (
    <div className={styles.window} aria-hidden="true">
      {ALL_SCORES.map((label) => {
        // Sized by the word shown, not the English one: "Ad" is a short score, "Avantage" is not.
        const shown = Object.hasOwn(t.flaps, label) ? t.flaps[label] : label;
        return (
          <div key={label} className={`${styles.flap} ${FLAP_CLASS[flapPosition(label, state)]}${shown.length > 7 ? ` ${styles.flapLong}` : shown.length > 2 ? ` ${styles.flapWord}` : ""}`}>
            {shown}
          </div>
        );
      })}
    </div>
  );
}

function StepLine({ step, finished }: { step: Step; finished: boolean }) {
  const status = finished && step.state === "active" ? "done" : step.state;
  const lineClass = status === "active" ? styles.stepActive : status === "failed" ? styles.stepFailed : "";
  return (
    <li className={`${styles.step} ${lineClass}`}>
      <span className={styles.box} aria-hidden="true">
        {status === "done" && (
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#12372B" strokeWidth="2.4">
            <path d="M2.5 8.4l3.6 3.6 7.4-8.2" />
          </svg>
        )}
        {status === "active" && <span className={styles.live} />}
        {status === "failed" && (
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.4">
            <path d="M2.5 2.5l9 9M11.5 2.5l-9 9" />
          </svg>
        )}
      </span>
      <span>{step.text}</span>
    </li>
  );
}
