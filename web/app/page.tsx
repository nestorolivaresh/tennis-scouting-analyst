"use client";

// The scouting flow on one route: match setup, the loader while the report is written, then the
// report. A failed report comes back to setup with the choices kept.

import { useEffect, useRef, useState } from "react";
import { Loader } from "@/components/loader/Loader.tsx";
import { ReportView } from "@/components/report/ReportView.tsx";
import { MatchSetup } from "@/components/setup/MatchSetup.tsx";
import { ApiFailure, streamReport } from "@/lib/api.ts";
import { BACK_TO_SETUP, takeHandoff } from "@/lib/handoff.ts";
import { reportHold } from "@/lib/loader.ts";
import type { Candidate, ReportEvent, ReportResponse, Surface } from "@/lib/types.ts";

type Phase =
  | { phase: "idle" }
  | {
      phase: "working";
      player: Candidate;
      opponent: Candidate;
      surface: Surface;
      started: number;
      events: ReportEvent[];
      names: Map<number, string>;
      final: ReportResponse | null;
    }
  | { phase: "done"; data: ReportResponse }
  | { phase: "error"; message: string };

export default function Home() {
  const [player, setPlayer] = useState<Candidate | null>(null);
  const [opponent, setOpponent] = useState<Candidate | null>(null);
  const [surface, setSurface] = useState<Surface>("Clay");
  const [phase, setPhase] = useState<Phase>({ phase: "idle" });
  const controller = useRef<AbortController | null>(null);
  const hold = useRef<ReturnType<typeof setTimeout> | null>(null);
  const view = useRef<HTMLDivElement>(null);
  const shownPhase = useRef(phase.phase);

  useEffect(() => {
    const handoff = takeHandoff();
    if (!handoff) return; // also StrictMode's second run, which finds it already taken
    if (handoff.player) setPlayer(handoff.player);
    if (handoff.opponent) setOpponent(handoff.opponent);
  }, []);

  // Leaving the page stops the work, and the model calls behind it.
  useEffect(
    () => () => {
      controller.current?.abort();
      if (hold.current) clearTimeout(hold.current);
    },
    [],
  );

  // The nav's Scouting link, used from the loader or a report. Stopping the stream stops the
  // model calls behind it; the chosen players stay.
  useEffect(() => {
    const backToSetup = () => {
      controller.current?.abort();
      if (hold.current) clearTimeout(hold.current);
      setPhase({ phase: "idle" });
    };
    window.addEventListener(BACK_TO_SETUP, backToSetup);
    return () => window.removeEventListener(BACK_TO_SETUP, backToSetup);
  }, []);

  useEffect(() => {
    if (shownPhase.current === phase.phase) return;
    shownPhase.current = phase.phase;
    window.scrollTo(0, 0);
    // The control that was in use has gone with the last view, so focus moves to the new one.
    const heading = view.current?.querySelector("h1");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }, [phase.phase]);

  async function writeReport() {
    if (!player || !opponent || player.player_id === opponent.player_id) return;
    controller.current?.abort();
    const run = new AbortController();
    controller.current = run;
    const names = new Map([[player.player_id, player.name], [opponent.player_id, opponent.name]]);
    setPhase({ phase: "working", player, opponent, surface, started: Date.now(), events: [], names, final: null });
    try {
      const data = await streamReport(
        { player_id: player.player_id, opponent_id: opponent.player_id, surface },
        (event) => setPhase((p) => (p.phase === "working" ? { ...p, events: [...p.events, event] } : p)),
        run.signal,
      );
      if (run.signal.aborted) return;
      showReport(data);
    } catch (error) {
      if (run.signal.aborted) return;
      setPhase({ phase: "error", message: error instanceof ApiFailure ? error.message : "The report request failed. Try again." });
    }
  }

  function showReport(data: ReportResponse) {
    const wait = reportHold(data, window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    if (wait === 0) {
      setPhase({ phase: "done", data });
      return;
    }
    setPhase((p) => (p.phase === "working" ? { ...p, final: data } : p));
    hold.current = setTimeout(() => setPhase({ phase: "done", data }), wait);
  }

  return (
    <div ref={view}>
      {(phase.phase === "idle" || phase.phase === "error") && (
        <MatchSetup
          player={player}
          opponent={opponent}
          surface={surface}
          onPlayer={setPlayer}
          onOpponent={setOpponent}
          onSurface={setSurface}
          onStart={writeReport}
          error={phase.phase === "error" ? phase.message : null}
        />
      )}
      {phase.phase === "working" && (
        <Loader
          player={phase.player.name}
          opponent={phase.opponent.name}
          surface={phase.surface}
          started={phase.started}
          events={phase.events}
          names={phase.names}
          final={phase.final}
        />
      )}
      {phase.phase === "done" && (
        <ReportView data={phase.data} countries={countriesOf(player, opponent)} onNewReport={() => setPhase({ phase: "idle" })} />
      )}
    </div>
  );
}

function countriesOf(...players: (Candidate | null)[]): Record<number, string | null> {
  const countries: Record<number, string | null> = {};
  for (const p of players) {
    if (p) countries[p.player_id] = p.country;
  }
  return countries;
}
