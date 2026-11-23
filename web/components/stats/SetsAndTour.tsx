"use client";

// Set patterns and the tour comparison (D-029), under the page's filters.

import { useState } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { setNote, setRows, tourView } from "@/lib/patterns.ts";
import type { PlayerStats } from "@/lib/player-stats.ts";
import { NumberRow, SourceCard } from "./NumberRow.tsx";
import styles from "./Stats.module.css";

export function SetsAndTour({ data }: { data: PlayerStats }) {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  const tour = tourView(data.tour, t);
  return (
    <div className={`${styles.sec} ${styles.columns}`}>
      <section className={styles.serveCol} aria-labelledby="sets">
        <h2 id="sets" className="h2">{t.setsTitle}</h2>
        <div className="courtline" aria-hidden="true" />
        <p className={styles.note}>{setNote(data.set_patterns, t)}</p>
        {setRows(data.set_patterns, t).map((row) => (
          <NumberRow key={row.key} row={row} idPrefix="sets" open={open === row.key} onToggle={() => setOpen(open === row.key ? null : row.key)} />
        ))}
      </section>
      <section className={styles.sideCol} aria-labelledby="tour">
        <div>
          <h2 id="tour" className="h2">{t.tourTitle}</h2>
          <div className="courtline" aria-hidden="true" />
          <p className={styles.note}>{tour.note}</p>
        </div>
        <div className={styles.sheet}>
          <div className={styles.matches} role="table" aria-labelledby="tour">
            <div role="rowgroup">
              <div className={`${styles.prow} ${styles.phead} ${styles.pheadTour}`} role="row">
                <span role="columnheader">{t.colStat}</span>
                <span role="columnheader">{t.colFigure}</span>
                <span role="columnheader">{t.colRank}</span>
                <span role="columnheader">{t.colMedian}</span>
              </div>
            </div>
            <div className={styles.mbody} role="rowgroup">
              {tour.rows.map((row) => (
                <div key={row.key} className={styles.prow} role="row">
                  <span role="cell">{row.title}</span>
                  <span className={styles.num} role="cell" data-label={t.colFigure}>{row.value}</span>
                  <span className={`${styles.num} ${styles.won}`} role="cell" data-label={t.colRank}>{row.rank}</span>
                  <span className={styles.num} role="cell" data-label={t.colMedian}>{row.median}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
        <details className={styles.sourceDetails}>
          <summary>{t.showSource}</summary>
          <SourceCard source={tour.source} />
        </details>
      </section>
    </div>
  );
}
