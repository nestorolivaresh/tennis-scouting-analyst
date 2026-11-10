"use client";

// The evidence view (spec): each key number, read from the tool result it cites, opens to show
// the tool call, its filters, the sample and what was left out. The value, sample and title
// all come from that result; the model's figure is shown only when it differs, as a warning.

import { useState } from "react";
import { checkStat, describeStat, formatValue, groupKeyStats, isSmallKeyStat, matchCount, sourcePanel } from "@/lib/evidence.ts";
import type { Evidence, KeyStat } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

export function KeyNumbers({ stats, evidence }: { stats: KeyStat[]; evidence: Evidence[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <>
      {groupKeyStats(stats, evidence).map((group) => (
        <div className={styles.knGroup} key={group.name}>
          <h3 className={`h3 ${styles.knTitle}`}>{group.name}</h3>
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
  const check = checkStat(stat, evidence);
  const { title } = describeStat(stat, check.evidence);
  const panel = sourcePanel(stat, check);
  const panelId = `evidence-${index}`;
  return (
    <div>
      <button type="button" className={styles.numRow} aria-expanded={isOpen} aria-controls={isOpen ? panelId : undefined} onClick={onToggle}>
        <span className={styles.numMain}>
          <span className={styles.numTitle}>{title}</span>
          {check.status !== "matched" && (
            <span className={styles.numWarning}>
              {check.status === "missing" ? "Not found in the data: this number can't be shown." : `Didn't match the data: the report said ${stat.value}.`}
            </span>
          )}
          <span className={styles.numToggle}>{isOpen ? "Hide the source" : "Show where this comes from"}</span>
        </span>
        {isSmallKeyStat(stat, check) && <span className={`tag ${styles.numTag}`}>Small sample</span>}
        {check.sample !== null && <span className={styles.numSample}>{matchCount(check.sample)}</span>}
        {check.value !== null
          ? <span className={styles.numValue}>{formatValue(check.value, check.rate)}</span>
          : <span className={`${styles.numValue} ${styles.numValueWord}`}>Not available</span>}
      </button>
      {isOpen && (
        <div id={panelId} className={styles.card}>
          {panel ? (
            <dl>
              <dt>Source</dt>
              <dd>{panel.source}</dd>
              <dt>Filters</dt>
              <dd>{panel.filters}</dd>
              <dt>Sample</dt>
              <dd>{panel.sample}</dd>
              <dt>Left out</dt>
              <dd>{panel.leftOut}</dd>
              <dt>Value</dt>
              <dd>{panel.value}<code className={styles.field}>{panel.field}</code></dd>
            </dl>
          ) : (
            <p className={styles.cardMissing}>Tool call {stat.tool_call_id} isn&apos;t in this report&apos;s results.</p>
          )}
        </div>
      )}
    </div>
  );
}
