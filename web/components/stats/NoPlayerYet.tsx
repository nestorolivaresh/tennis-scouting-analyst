import { Board } from "@/components/ui/Board.tsx";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import styles from "./Stats.module.css";

const TILES = [
  { label: "tileMatches", tilt: "t-a", delay: "0.05s" },
  { label: "tileWon", tilt: "t-b", delay: "0.14s" },
  { label: "tileLost", tilt: "t-c", delay: "0.23s" },
  { label: "tileWinRate", tilt: "t-a", delay: "0.32s" },
] as const;

/** The scoreboard before anyone has been looked up: the same board, with its tiles still blank. */
export function NoPlayerYet() {
  const t = useT();
  return (
    <Board aria-labelledby="no-player" className={styles.noPlayer}>
      <div className={styles.slats}>
        <div className={`slat ${styles.who}`}>
          <div className={styles.whoLeft}>
            <span className={styles.noPlayerMedal} aria-hidden="true" />
            <div className={styles.whoText}>
              <h2 id="no-player" className={styles.noPlayerTitle}>{t.noPlayerTitle}</h2>
              <p className={styles.bio}>{t.noPlayerHelp}</p>
            </div>
          </div>
        </div>

        <div className={`slat ${styles.tiles}`} aria-hidden="true">
          {TILES.map(({ label, tilt, delay }) => (
            <div className="tile-cell" key={label}>
              <span className="tile-label">{t[label]}</span>
              <span className={`tile ${tilt}`} style={{ animationDelay: delay }} />
            </div>
          ))}
        </div>
      </div>
    </Board>
  );
}
