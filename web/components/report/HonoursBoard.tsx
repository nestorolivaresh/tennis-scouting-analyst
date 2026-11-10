import { Board } from "@/components/ui/Board.tsx";
import { type HonoursRow, honoursBoard, shortNames } from "@/lib/evidence.ts";
import type { Evidence, PlayerRef } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

type Names = { player: string; opponent: string };
type Props = { evidence: Evidence[]; player: PlayerRef; opponent: PlayerRef };

const SWATCHES = new Set(["clay", "grass", "hard"]);

export function HonoursBoard({ evidence, player, opponent }: Props) {
  const board = honoursBoard(evidence, player, opponent);
  const names = shortNames(player, opponent);
  let line: string;
  if (board.status === "not_looked_up") line = "This report's results don't include the two players' full head-to-head, so their meetings can't be listed.";
  else if (board.status === "no_meetings") line = `${player.name} and ${opponent.name} have not met in the data.`;
  else line = `${board.rows.length === 1 ? "Their only meeting" : `All ${board.rows.length} meetings, newest first`}. ${names.player} ${board.wins.player}, ${names.opponent} ${board.wins.opponent}.`;
  const rows = board.status === "ok" ? board.rows : [];
  const split = Math.ceil(rows.length / 2);
  return (
    <Board id="honours" aria-labelledby="honours-title" className={styles.sec}>
      <div className={styles.honoursFrame}>
        <h2 id="honours-title" className={styles.honoursTitle}>Honours board</h2>
        <p className={styles.honoursLine}>{line}</p>
        {rows.length > 0 && (
          <>
            <div className={styles.honoursRule} aria-hidden="true" />
            <div className={styles.honoursCols}>
              <Column rows={rows.slice(0, split)} names={names} />
              <Column rows={rows.slice(split)} names={names} />
            </div>
          </>
        )}
      </div>
    </Board>
  );
}

function Column({ rows, names }: { rows: HonoursRow[]; names: Names }) {
  if (!rows.length) return null;
  return (
    <ul className={styles.honoursCol}>
      {rows.map((m) => {
        const surface = m.surface?.toLowerCase();
        return (
          <li className={styles.giltRow} key={`${m.date}-${m.event}-${m.round}`}>
            <span className={styles.giltDisplay}>{m.year}</span>
            <span className={styles.giltEvent}>
              <span className={`${styles.giltDisplay} ${styles.giltBlock}`}>{m.event}</span>
              <span className={styles.giltRound}>
                <span className={`sw sw-${surface && SWATCHES.has(surface) ? surface : "all"} ${styles.giltSwatch}`} aria-hidden="true" />
                {m.round}{surface ? ` on ${surface}` : ""}
              </span>
            </span>
            <span className={styles.giltResult}>
              <span className={`${styles.giltDisplay} ${styles.giltBlock}`}>{m.winner ? names[m.winner] : "Result not recorded"}</span>
              {m.score && <span className={styles.giltScore}>{m.score}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
