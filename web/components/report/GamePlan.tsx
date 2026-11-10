import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type CheckedPercent, matchCount, shortNames } from "@/lib/evidence.ts";
import { capitalized, findFigure, parsePlanItem } from "@/lib/plan.ts";
import type { PlayerRef } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

type Props = { items: string[]; player: PlayerRef; opponent: PlayerRef; checked: CheckedPercent[] };

export function GamePlan({ items, player, opponent, checked }: Props) {
  const t = useT();
  const points = items.filter((item) => item.trim());
  return (
    <section id="plan" className={styles.sec}>
      <h2 className="h2">{t.gamePlanFor(player.name)}</h2>
      <div className="courtline" aria-hidden="true" />
      {points.map((text, i) => <PlanRow key={i} text={text} checked={checked} names={shortNames(player, opponent)} />)}
      {points.length === 0 && <p className={styles.nothing}>{t.noPlanPoints}</p>}
    </section>
  );
}

function PlanRow({ text, checked, names }: { text: string; checked: CheckedPercent[]; names: { player: string; opponent: string } }) {
  const t = useT();
  const { head, body, inference } = parsePlanItem(text);
  const figure = findFigure(text, checked, names, t);
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
        {head && <h3 className={styles.planHead}>{head}</h3>}
        {(body || figure?.small) && (
          <p className={styles.planBody}>{body}{figure?.small && <span className="tag">{t.smallSample}</span>}</p>
        )}
        {inference && (
          <p className={styles.inference}><span className={styles.inferenceLabel}>{t.coachingInference}</span> {capitalized(inference)}</p>
        )}
      </div>
    </article>
  );
}
