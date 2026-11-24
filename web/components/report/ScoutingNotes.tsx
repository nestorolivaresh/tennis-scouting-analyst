import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type CheckedPercent, matchCount, shortNames } from "@/lib/evidence.ts";
import { fieldCitations, fieldSpans } from "@/lib/numbers.ts";
import { findFigure } from "@/lib/plan.ts";
import type { Evidence, PlayerRef, ReportCitation, ReportNumberCheck } from "@/lib/types.ts";
import { CitedText } from "./CitedText.tsx";
import styles from "./ReportView.module.css";

type Names = { player: string; opponent: string };
type Props = {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  player: PlayerRef;
  opponent: PlayerRef;
  checked: CheckedPercent[];
  numbers: ReportNumberCheck | null | undefined;
  citations: ReportCitation[] | undefined;
  evidence: Evidence[];
};

export function ScoutingNotes({ summary, strengths, weaknesses, player, opponent, checked, numbers, citations, evidence }: Props) {
  const t = useT();
  const names = shortNames(player, opponent);
  return (
    <section id="notes" className={styles.sec}>
      <h2 className="h2">{t.notesOn(opponent.name)}</h2>
      <div className={`courtline ${styles.lineNotes}`} aria-hidden="true" />
      {summary.trim() && (
        <CitedText
          className={styles.summary} text={summary} spans={fieldSpans(numbers, "summary", summary)}
          cites={fieldCitations(citations, "summary", summary)} evidence={evidence}
        />
      )}
      <div className={styles.two}>
        <NoteColumn title={t.doesWell(opponent.name)} field="strengths" notes={strengths} {...{ checked, names, numbers, citations, evidence }} />
        <NoteColumn title={t.isOpen(opponent.name)} field="weaknesses" notes={weaknesses} {...{ checked, names, numbers, citations, evidence }} />
      </div>
    </section>
  );
}

type ColumnProps = {
  title: string;
  field: "strengths" | "weaknesses";
  notes: string[];
  checked: CheckedPercent[];
  names: Names;
  numbers: ReportNumberCheck | null | undefined;
  citations: ReportCitation[] | undefined;
  evidence: Evidence[];
};

function NoteColumn({ title, field, notes, checked, names, numbers, citations, evidence }: ColumnProps) {
  const t = useT();
  // The check names a note by its place in the report's list, empty notes included.
  const shown = notes.map((text, index) => ({ text, index })).filter((note) => note.text.trim());
  return (
    <div>
      <h3 className={`h3 ${styles.notesHead}`}>{title}</h3>
      {shown.map(({ text, index }, i) => {
        const figure = findFigure(text, checked, names, t);
        return (
          <div className={`${styles.pt}${figure ? "" : ` ${styles.ptBare}`}`} key={i}>
            {figure && (
              <div>
                <div className={styles.ptFig}>{figure.text}</div>
                {figure.sample !== null && <div className={styles.ptSample}>{matchCount(figure.sample, t)}</div>}
              </div>
            )}
            <div>
              <CitedText
                className={styles.ptText} text={text} spans={fieldSpans(numbers, `${field}.${index}`, text)}
                cites={fieldCitations(citations, `${field}.${index}`, text)} evidence={evidence}
                after={figure?.small && <span className="tag">{t.smallSample}</span>}
              />
            </div>
          </div>
        );
      })}
      {shown.length === 0 && <p className={styles.nothing}>{t.nothingListed}</p>}
    </div>
  );
}
