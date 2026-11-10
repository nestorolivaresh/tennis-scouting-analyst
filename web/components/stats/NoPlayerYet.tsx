import { Board } from "@/components/ui/Board.tsx";
import styles from "./Stats.module.css";

const TILES = [
  { label: "Matches", tilt: "t-a", delay: "0.05s" },
  { label: "Won", tilt: "t-b", delay: "0.14s" },
  { label: "Lost", tilt: "t-c", delay: "0.23s" },
  { label: "Win rate", tilt: "t-a", delay: "0.32s" },
];

/** The scoreboard before anyone has been looked up: the same board, with its tiles still blank. */
export function NoPlayerYet() {
  return (
    <Board aria-labelledby="no-player" className={styles.noPlayer}>
      <div className={styles.slats}>
        <div className={`slat ${styles.who}`}>
          <div className={styles.whoLeft}>
            <span className={styles.noPlayerMedal} aria-hidden="true" />
            <div className={styles.whoText}>
              <h2 id="no-player" className={styles.noPlayerTitle}>No player chosen yet</h2>
              <p className={styles.bio}>Search for a player to see their record, serve and return numbers, seasons and recent matches.</p>
            </div>
          </div>
        </div>

        <div className={`slat ${styles.tiles}`} aria-hidden="true">
          {TILES.map(({ label, tilt, delay }) => (
            <div className="tile-cell" key={label}>
              <span className="tile-label">{label}</span>
              <span className={`tile ${tilt}`} style={{ animationDelay: delay }} />
            </div>
          ))}
        </div>
      </div>
    </Board>
  );
}
