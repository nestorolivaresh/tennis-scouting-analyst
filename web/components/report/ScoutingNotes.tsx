import { type CheckedPercent, matchCount, shortNames } from "@/lib/evidence.ts";
import { findFigure } from "@/lib/plan.ts";
import type { PlayerRef } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

type Names = { player: string; opponent: string };
type Props = { summary: string; strengths: string[]; weaknesses: string[]; player: PlayerRef; opponent: PlayerRef; checked: CheckedPercent[] };

export function ScoutingNotes({ summary, strengths, weaknesses, player, opponent, checked }: Props) {
  const names = shortNames(player, opponent);
  return (
    <section id="notes" className={styles.sec}>
      <h2 className="h2">Scouting notes on {opponent.name}</h2>
      <div className={`courtline ${styles.lineNotes}`} aria-hidden="true" />
      {summary.trim() && <p className={styles.summary}>{summary}</p>}
      <div className={styles.two}>
        <NoteColumn title={`What ${opponent.name} does well`} notes={strengths} checked={checked} names={names} />
        <NoteColumn title={`Where ${opponent.name} is open`} notes={weaknesses} checked={checked} names={names} />
      </div>
    </section>
  );
}

function NoteColumn({ title, notes, checked, names }: { title: string; notes: string[]; checked: CheckedPercent[]; names: Names }) {
  const shown = notes.filter((note) => note.trim());
  return (
    <div>
      <h3 className={`h3 ${styles.notesHead}`}>{title}</h3>
      {shown.map((text, i) => {
        const figure = findFigure(text, checked, names);
        return (
          <div className={`${styles.pt}${figure ? "" : ` ${styles.ptBare}`}`} key={i}>
            {figure && (
              <div>
                <div className={styles.ptFig}>{figure.text}</div>
                {figure.sample !== null && <div className={styles.ptSample}>{matchCount(figure.sample)}</div>}
              </div>
            )}
            <p className={styles.ptText}>{text}{figure?.small && <span className="tag">Small sample</span>}</p>
          </div>
        );
      })}
      {shown.length === 0 && <p className={styles.nothing}>Nothing listed in this report.</p>}
    </div>
  );
}
