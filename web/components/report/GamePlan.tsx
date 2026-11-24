import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type CheckedPercent, matchCount, shortNames } from "@/lib/evidence.ts";
import { fieldCitations, fieldSpans } from "@/lib/numbers.ts";
import { findFigure, placedParts } from "@/lib/plan.ts";
import type { Evidence, NumberSpan, PlayerRef, ReportCitation, ReportNumberCheck } from "@/lib/types.ts";
import { CitedText } from "./CitedText.tsx";
import styles from "./ReportView.module.css";

type Props = {
  items: string[];
  player: PlayerRef;
  opponent: PlayerRef;
  checked: CheckedPercent[];
  numbers: ReportNumberCheck | null | undefined;
  citations: ReportCitation[] | undefined;
  evidence: Evidence[];
};

export function GamePlan({ items, player, opponent, checked, numbers, citations, evidence }: Props) {
  const t = useT();
  // The check and the citations name a point by its place in the report's list, empty points included.
  const points = items
    .map((text, index) => ({ text, spans: fieldSpans(numbers, `game_plan.${index}`, text), cites: fieldCitations(citations, `game_plan.${index}`, text) }))
    .filter((p) => p.text.trim());
  return (
    <section id="plan" className={styles.sec}>
      <h2 className="h2">{t.gamePlanFor(player.name)}</h2>
      <div className="courtline" aria-hidden="true" />
      {points.map(({ text, spans, cites }, i) => (
        <PlanRow key={i} text={text} spans={spans} cites={cites} evidence={evidence} checked={checked} names={shortNames(player, opponent)} />
      ))}
      {points.length === 0 && <p className={styles.nothing}>{t.noPlanPoints}</p>}
    </section>
  );
}

type RowProps = {
  text: string;
  spans: NumberSpan[];
  cites: ReportCitation[];
  evidence: Evidence[];
  checked: CheckedPercent[];
  names: { player: string; opponent: string };
};

function PlanRow({ text, spans, cites, evidence, checked, names }: RowProps) {
  const t = useT();
  const { head, body, inference } = placedParts(text);
  const figure = findFigure(text, checked, names, t);
  // A part that isn't where the check says (at -1) is shown plain.
  const marks = (at: number) => (at >= 0 ? spans : []);
  const cited = (at: number) => (at >= 0 ? cites : []);
  return (
    <article className={`${styles.planRow}${figure ? "" : ` ${styles.planRowBare}`}`}>
      {figure && (
        <div className={styles.figBlock}>
          <div className={styles.fig}>{figure.text}</div>
          {figure.sub && <div className={styles.figSub}>{figure.sub}</div>}
          {figure.sample !== null && <div className={styles.figSub}>{matchCount(figure.sample, t)}</div>}
        </div>
      )}
      <div className={styles.planText}>
        {head.text && (
          <CitedText as="h3" className={styles.planHead} text={head.text} at={head.at} spans={marks(head.at)} cites={cited(head.at)} evidence={evidence} />
        )}
        {(body.text || figure?.small) && (
          <CitedText
            className={styles.planBody} text={body.text} at={body.at} spans={marks(body.at)} cites={cited(body.at)} evidence={evidence}
            after={figure?.small && <span className="tag">{t.smallSample}</span>}
          />
        )}
        {inference && (
          <CitedText
            className={styles.inference} text={inference.text} at={inference.at} spans={marks(inference.at)} cites={cited(inference.at)} evidence={evidence}
            before={<><span className={styles.inferenceLabel}>{t.coachingInference}</span>{" "}</>}
          />
        )}
      </div>
    </article>
  );
}
