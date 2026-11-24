"use client";

// A number's source, read from the tool result it comes from: the card a key number opens
// (D-018), and the one a number cited in the text opens (D-032). The title, value and sample
// all come from the result; nothing here is the model's text.

import { useT } from "@/components/ui/LanguageProvider.tsx";
import { checkStat, describeStat, sourcePanel } from "@/lib/evidence.ts";
import { citedStat } from "@/lib/numbers.ts";
import type { Citation, Evidence, KeyStat } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

export function SourceCard({ stat, evidence, id, titled = false }: { stat: KeyStat; evidence: Evidence[]; id: string; titled?: boolean }) {
  const t = useT();
  const check = checkStat(stat, evidence);
  const panel = sourcePanel(stat, check, t);
  return (
    <div id={id} className={styles.card}>
      {titled && check.evidence?.result && <p className={styles.cardTitle}>{describeStat(stat, check.evidence, t).title}</p>}
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
  );
}

/** The card for a number cited in the text, with what the number is as its title. */
export function CitedSource({ cite, evidence, id }: { cite: Citation; evidence: Evidence[]; id: string }) {
  return <SourceCard stat={citedStat(cite)} evidence={evidence} id={id} titled />;
}
