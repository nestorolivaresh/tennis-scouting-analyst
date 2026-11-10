"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Board } from "@/components/ui/Board.tsx";
import { PlayerSearch } from "@/components/ui/PlayerSearch.tsx";
import { searchPlayers } from "@/lib/api.ts";
import { saveHandoff } from "@/lib/handoff.ts";
import { type HeadToHead, type PlayerStats, againstView, findCandidate, matchupHandoff } from "@/lib/player-stats.ts";
import { lastName } from "@/lib/people.ts";
import type { Candidate } from "@/lib/types.ts";
import styles from "./Stats.module.css";

const SEARCH_ID = "compare-with";

type Props = {
  data: PlayerStats;
  /** The URL's opponent, which decides at once whether the search or the record is shown. */
  against: string | null;
  onChoose: (playerId: number) => void;
  onClear: () => void;
};

type HandoffState = { state: "idle" } | { state: "working" } | { state: "failed"; playerId: number };

export function AgainstBox({ data, against, onChoose, onClear }: Props) {
  const router = useRouter();
  const [picked, setPicked] = useState<Candidate | null>(null);
  const [handoff, setHandoff] = useState<HandoffState>({ state: "idle" });
  const heading = useRef<HTMLHeadingElement>(null);
  const focusNext = useRef<"heading" | "search" | null>(null);
  const lookup = useRef<AbortController | null>(null);

  useEffect(() => () => lookup.current?.abort(), []);

  // Picking and changing each remove the control that had focus.
  useEffect(() => {
    if (focusNext.current === "heading") heading.current?.focus();
    if (focusNext.current === "search") document.getElementById(SEARCH_ID)?.focus();
    focusNext.current = null;
  }, [against]);

  function choose(candidate: Candidate | null) {
    if (!candidate) return;
    setPicked(candidate);
    focusNext.current = "heading";
    onChoose(candidate.player_id);
  }

  function change() {
    focusNext.current = "search";
    onClear();
  }

  /** The API's head-to-head only names the other player, and setup needs their full details:
   * they come from the search that picked them or, on a shared link, from a new search. */
  async function scoutMatchup(h2h: HeadToHead) {
    const { player_id: playerId, name } = h2h.opponent;
    let comparedWith = picked?.player_id === playerId ? picked : null;
    if (!comparedWith) {
      const controller = new AbortController();
      lookup.current = controller;
      setHandoff({ state: "working" });
      try {
        comparedWith = findCandidate(await searchPlayers(name, controller.signal), playerId);
      } catch {
        comparedWith = null;
      }
      if (controller.signal.aborted) return;
    }
    if (!comparedWith) {
      setHandoff({ state: "failed", playerId });
      return;
    }
    setHandoff({ state: "idle" });
    saveHandoff(matchupHandoff(data.profile, comparedWith));
    router.push("/");
  }

  const h2h = against === null ? null : data.head_to_head;
  const view = h2h ? againstView(h2h) : null;
  const failed = h2h !== null && handoff.state === "failed" && handoff.playerId === h2h.opponent.player_id;

  return (
    <Board aria-labelledby="against" className={styles.sideBoard}>
      <div className={styles.againstFrame}>
        <div className={styles.againstHead}>
          <h2 id="against" ref={heading} tabIndex={-1} className={styles.againstTitle}>{view?.title ?? "Against another player"}</h2>
          {against !== null && (
            <button type="button" className={styles.changeOpponent} aria-label="Change the player to compare with" onClick={change}>Change</button>
          )}
        </div>

        {against === null && (
          <>
            <p className={styles.againstText}>Choose a player to see the record between them.</p>
            <label htmlFor={SEARCH_ID} className={styles.compareLabel}>Compare with</label>
            <div className={styles.compare}>
              <PlayerSearch
                inputId={SEARCH_ID}
                value={null}
                onChange={choose}
                placeholder="Search for a player"
                excludeId={data.profile.player.player_id}
                tone="opponent"
                showMedal={false}
                changeLabel="Change the player to compare with"
              />
            </div>
          </>
        )}

        {against !== null && !view && <p className={styles.againstText}>Loading the record…</p>}

        {view && h2h && (
          <>
            <p className={styles.againstText}>{view.text}</p>
            {view.note && <p className={styles.againstNote}>{view.note}</p>}
            <button
              type="button"
              className={`btn-chalk ${styles.fullButton}`}
              disabled={handoff.state === "working"}
              onClick={() => scoutMatchup(h2h)}
            >
              Scout this match-up
            </button>
            {failed && (
              <p className={styles.againstFailure} role="alert">
                {lastName(h2h.opponent.name)}&rsquo;s details couldn&rsquo;t be loaded for the report. Try again.
              </p>
            )}
          </>
        )}
      </div>
    </Board>
  );
}
