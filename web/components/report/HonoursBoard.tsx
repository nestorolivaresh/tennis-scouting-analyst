import { Board } from "@/components/ui/Board.tsx";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type HonoursRow, honoursBoard, shortNames } from "@/lib/evidence.ts";
import { surfaceWords } from "@/lib/i18n.ts";
import type { Evidence, PlayerRef } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

type Names = { player: string; opponent: string };
type Props = { evidence: Evidence[]; player: PlayerRef; opponent: PlayerRef };

const SWATCHES = new Set(["clay", "grass", "hard"]);

export function HonoursBoard({ evidence, player, opponent }: Props) {
  const t = useT();
  const board = honoursBoard(evidence, player, opponent, t);
  const names = shortNames(player, opponent);
  let line: string;
  if (board.status === "not_looked_up") line = t.honoursMissing;
  else if (board.status === "no_meetings") line = t.neverMet(player.name, opponent.name);
  else line = t.honoursLine(board.rows.length, names.player, board.wins.player, names.opponent, board.wins.opponent);
  const rows = board.status === "ok" ? board.rows : [];
  const split = Math.ceil(rows.length / 2);
  return (
    <Board id="honours" aria-labelledby="honours-title" className={styles.sec}>
      <div className={styles.honoursFrame}>
        <h2 id="honours-title" className={styles.honoursTitle}>{t.sectionHonours}</h2>
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
  const t = useT();
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
                {m.surface ? t.roundOn(m.round, surfaceWords(t, m.surface).lower) : m.round}
              </span>
            </span>
            <span className={styles.giltResult}>
              <span className={`${styles.giltDisplay} ${styles.giltBlock}`}>{m.winner ? names[m.winner] : t.resultNotRecorded}</span>
              {m.score && <span className={styles.giltScore}>{m.score}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
