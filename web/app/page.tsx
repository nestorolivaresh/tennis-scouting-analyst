"use client";

// Match setup, report and chat on one page. The setup reads as a sentence: who is being
// scouted, for whom, on which surface.

import { useEffect, useMemo, useRef, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel.tsx";
import { PlayerPicker } from "@/components/PlayerPicker.tsx";
import { ReportView } from "@/components/ReportView.tsx";
import { ApiFailure, streamReport } from "@/lib/api.ts";
import { progressSteps } from "@/lib/progress.ts";
import type { ChatMessage, PlayerRef, ReportEvent, ReportResponse, Surface } from "@/lib/types.ts";
import { SURFACES } from "@/lib/types.ts";

type ReportState =
  | { state: "idle" }
  | { state: "working"; started: number; events: ReportEvent[]; names: Map<number, string> }
  | { state: "done"; data: ReportResponse }
  | { state: "error"; message: string };

export default function Home() {
  const [player, setPlayer] = useState<PlayerRef | null>(null);
  const [opponent, setOpponent] = useState<PlayerRef | null>(null);
  const [surface, setSurface] = useState<Surface>("Hard");
  const [report, setReport] = useState<ReportState>({ state: "idle" });
  const controller = useRef<AbortController | null>(null);

  const samePlayer = player && opponent && player.player_id === opponent.player_id;
  const ready = player && opponent && !samePlayer && report.state !== "working";

  async function writeReport() {
    if (!player || !opponent) return;
    controller.current?.abort();
    controller.current = new AbortController();
    const names = new Map([[player.player_id, player.name], [opponent.player_id, opponent.name]]);
    setReport({ state: "working", started: Date.now(), events: [], names });
    try {
      const data = await streamReport(
        { player_id: player.player_id, opponent_id: opponent.player_id, surface },
        (event) => setReport((r) => (r.state === "working" ? { ...r, events: [...r.events, event] } : r)),
        controller.current.signal,
      );
      setReport({ state: "done", data });
    } catch (error) {
      if (controller.current.signal.aborted) return;
      setReport({ state: "error", message: error instanceof ApiFailure ? error.message : "The report request failed." });
    }
  }

  const context = useMemo(() => (report.state === "done" ? reportContext(report.data) : []), [report]);

  return (
    <main className="page">
      <header className="masthead">
        <strong>Tennis Scouting Analyst</strong>
        <span>ATP tour-level singles, 2015 on. Numbers come from tested stats tools, not the model’s memory.</span>
      </header>

      <div className="workspace">
        <div>
          <section className="setup" aria-label="Match setup">
            <div className="setup-sentence">
              <span className="setup-word">Scout</span>
              <PlayerPicker side="opponent" label="Opponent to scout" placeholder="an opponent" value={opponent} onChange={setOpponent} />
              <span className="setup-word">for</span>
              <PlayerPicker side="player" label="Your player" placeholder="your player" value={player} onChange={setPlayer} />
              <span className="setup-word">on</span>
              <fieldset className="surfaces">
                <legend className="visually-hidden">Surface</legend>
                {SURFACES.map((s) => (
                  <label key={s}>
                    <input type="radio" name="surface" value={s} checked={surface === s} onChange={() => setSurface(s)} />
                    {s.toLowerCase()}
                  </label>
                ))}
              </fieldset>
            </div>
            <div className="setup-actions">
              <button type="button" className="primary" disabled={!ready} onClick={writeReport}>
                Write the report
              </button>
              <span className="hint">
                {samePlayer ? "Pick two different players." : "Uses the two years up to the newest tournament in the data."}
              </span>
            </div>
          </section>

          {report.state === "working" && <Working started={report.started} events={report.events} names={report.names} />}
          {report.state === "error" && (
            <div className="status" data-kind="error" role="alert">
              <strong>The report couldn't be written.</strong> {report.message}
            </div>
          )}
          {report.state === "done" && <ReportView data={report.data} />}
          {report.state === "idle" && (
            <p className="hint">Pick an opponent and your player to write a scouting report. It takes 15 to 40 seconds.</p>
          )}
        </div>

        <ChatPanel key={report.state === "done" ? report.data.request_id : "no-report"} context={context} />
      </div>
    </main>
  );
}

function Working({ started, events, names }: { started: number; events: ReportEvent[]; names: Map<number, string> }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const steps = progressSteps(events, names);
  return (
    <div className="working">
      <p role="status">
        <strong>Writing the report.</strong> {Math.round((now - started) / 1000)} seconds so far. The report appears once
        every key number has been checked against the data.
      </p>
      <ol className="progress" aria-label="Progress">
        {steps.map((step) => (
          <li key={step.key} data-state={step.state}>{step.text}</li>
        ))}
      </ol>
    </div>
  );
}

/** The report as a first exchange, so follow-up questions have context. */
function reportContext(data: ReportResponse): ChatMessage[] {
  if (!data.report) return [];
  const { player, opponent, surface } = data.request;
  const r = data.report;
  const text = [
    r.summary,
    `${opponent.name}'s strengths: ${r.strengths.join(" ")}`,
    `${opponent.name}'s weaknesses: ${r.weaknesses.join(" ")}`,
    `Game plan for ${player.name}: ${r.game_plan.join(" ")}`,
  ].join("\n\n").slice(0, 3_900);
  return [
    { role: "user", content: `Write a scouting report on ${opponent.name} for ${player.name}, on ${surface.toLowerCase()}.` },
    { role: "assistant", content: text },
  ];
}
