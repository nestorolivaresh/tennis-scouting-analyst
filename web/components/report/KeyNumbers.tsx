"use client";

// The evidence view (spec): each key number, read from the tool result it cites, opens to show
// the tool call, its filters, the sample and what was left out. The value, sample and title
// all come from that result; the model's figure is shown only when it differs, as a warning.

import { useState } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { checkStat, describeStat, formatValue, groupKeyStats, isSmallKeyStat, matchCount, sourcePanel } from "@/lib/evidence.ts";
import type { Evidence, KeyStat } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

export function KeyNumbers({ stats, evidence }: { stats: KeyStat[]; evidence: Evidence[] }) {
  const t = useT();
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      {groupKeyStats(stats, evidence).map((group) => (
        <div className={styles.knGroup} key={group.name}>
          <h3 className={`h3 ${styles.knTitle}`}>{Object.hasOwn(t.groups, group.name) ? t.groups[group.name] : group.name}</h3>
          <div className={styles.knRows}>
            {group.rows.map(({ stat, index }) => (
              <NumberRow key={index} stat={stat} evidence={evidence} index={index} isOpen={open === index} onToggle={() => setOpen(open === index ? null : index)} />
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

type RowProps = { stat: KeyStat; evidence: Evidence[]; index: number; isOpen: boolean; onToggle: () => void };

function NumberRow({ stat, evidence, index, isOpen, onToggle }: RowProps) {
  const t = useT();
  const check = checkStat(stat, evidence);
  const { title } = describeStat(stat, check.evidence, t);
  const panel = sourcePanel(stat, check, t);
  const panelId = `evidence-${index}`;
  return (
    <div>
      <button type="button" className={styles.numRow} aria-expanded={isOpen} aria-controls={isOpen ? panelId : undefined} onClick={onToggle}>
        <span className={styles.numMain}>
          <span className={styles.numTitle}>{title}</span>
          {check.status !== "matched" && (
            <span className={styles.numWarning}>
              {check.status === "missing" ? t.notInData : t.didntMatch(String(stat.value))}
            </span>
          )}
          <span className={styles.numToggle}>{isOpen ? t.hideSource : t.showSource}</span>
        </span>
        {isSmallKeyStat(stat, check) && <span className={`tag ${styles.numTag}`}>{t.smallSample}</span>}
        {check.sample !== null && <span className={styles.numSample}>{matchCount(check.sample, t)}</span>}
        {check.value !== null
          ? <span className={styles.numValue}>{formatValue(check.value, check.rate, t)}</span>
          : <span className={`${styles.numValue} ${styles.numValueWord}`}>{t.notAvailable}</span>}
      </button>
      {isOpen && (
        <div id={panelId} className={styles.card}>
          {panel ? (
            <dl>
              <dt>{t.source}</dt>
              <dd>{panel.source}</dd>
              <dt>{t.filters}</dt>
              <dd>{panel.filters}</dd>
              <dt>{t.sample}</dt>
              <dd>{panel.sample}</dd>
              <dt>{t.leftOut}</dt>
              <dd>{panel.leftOut}</dd>
              <dt>{t.value}</dt>
              <dd>{panel.value}<code className={styles.field}>{panel.field}</code></dd>
            </dl>
          ) : (
            <p className={styles.cardMissing}>{t.callMissing(stat.tool_call_id)}</p>
          )}
        </div>
      )}
    </div>
  );
}
