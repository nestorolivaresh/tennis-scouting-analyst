"use client";

import Link from "next/link";
import { Board } from "@/components/ui/Board.tsx";
import { countryName } from "@/components/ui/Flag.tsx";
import { Medal } from "@/components/ui/Medal.tsx";
import { saveHandoff } from "@/lib/handoff.ts";
import { type PlayerStats, bioLine, boardNumbers, isFiltered, scoutHandoff, showingText } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

export function PlayerBoard({ data, onClear }: { data: PlayerStats; onClear: () => void }) {
  const { profile, filters } = data;
  const { name } = profile.player;
  const bio = bioLine(profile, countryName(profile.country));
  const numbers = boardNumbers(data.record.overall);

  return (
    <Board aria-labelledby="who-name">
      <div className={styles.slats}>
        <div className={`slat ${styles.who}`}>
          <div className={styles.whoLeft}>
            <Medal name={name} country={profile.country} tone="opponent" />
            <div className={styles.whoText}>
              <h2 id="who-name" className={styles.whoName}>{name}</h2>
              {bio && <p className={styles.bio}>{bio}</p>}
            </div>
          </div>
          <Link className="btn-chalk" href="/" onClick={() => saveHandoff(scoutHandoff(profile))}>Scout {name}</Link>
        </div>

        <div className={`slat ${styles.tiles}`}>
          <div className="tile-cell"><span className="tile-label">Matches</span><span className="tile t-a" style={{ animationDelay: "0.05s" }}>{numbers.matches}</span></div>
          <div className="tile-cell"><span className="tile-label">Won</span><span className="tile t-b" style={{ animationDelay: "0.14s" }}>{numbers.won}</span></div>
          <div className="tile-cell"><span className="tile-label">Lost</span><span className="tile t-c" style={{ animationDelay: "0.23s" }}>{numbers.lost}</span></div>
          <div className="tile-cell"><span className="tile-label">Win rate</span><span className={`tile t-a${numbers.hasWinRate ? "" : ` ${styles.tileWord}`}`} style={{ animationDelay: "0.32s" }}>{numbers.winRate}</span></div>
        </div>

        <div className={`slat ${styles.showing}`}>
          <p className={styles.showingText} role="status">{showingText(filters)}</p>
          {isFiltered(filters) && <button type="button" className={styles.clear} onClick={onClear}>Show every surface and season</button>}
        </div>
      </div>
    </Board>
  );
}
