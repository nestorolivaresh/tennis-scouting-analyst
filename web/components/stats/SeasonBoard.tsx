import { Board } from "@/components/ui/Board.tsx";
import { type PageQuery, type PlayerStats, seasonNote, seasonRows } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

export function SeasonBoard({ data, query, onPick }: { data: PlayerStats; query: PageQuery; onPick: (season: number | null) => void }) {
  return (
    <Board aria-labelledby="by-season" className={styles.sideBoard}>
      <div className={styles.giltFrame}>
        <h2 id="by-season" className={styles.giltTitle}>Season by season</h2>
        <p className={styles.giltNote}>{seasonNote(data.filters)}</p>
        <div className={styles.giltRule} aria-hidden="true" />
        <ul className={styles.seasons}>
          {seasonRows(data.seasons, query).map((row) => (
            <li key={row.key}>
              <button type="button" className={`${styles.season}${row.on ? ` ${styles.seasonOn}` : ""}`} aria-pressed={row.on} onClick={() => onPick(row.season)}>
                <span className={styles.yr}>
                  {row.on && <span className="serve" aria-hidden="true" />}
                  {row.label}
                </span>
                <span className={styles.gbar} aria-hidden="true"><span style={{ width: `${row.width}%` }} /></span>
                <span className={styles.fig}>{row.record}</span>
                <span className={styles.fig}>{row.rate}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </Board>
  );
}
