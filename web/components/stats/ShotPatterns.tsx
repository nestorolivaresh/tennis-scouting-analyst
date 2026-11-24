"use client";

// Serve direction, points won by rally length and net points from the Match Charting Project's
// charted matches (D-030). Every figure says how many charted matches it rests on.

import { useState } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type DirectionRow, shotView } from "@/lib/patterns.ts";
import type { PlayerStats } from "@/lib/player-stats.ts";
import { NumberRow, SourceCard } from "./NumberRow.tsx";
import styles from "./Stats.module.css";

export function Directions({ id, title, rows }: { id: string; title: string; rows: DirectionRow[] }) {
  const t = useT();
  const sides = rows[0]?.cells.map((cell) => cell.side) ?? [];
  return (
    <div className={styles.sheet}>
      <h3 id={id} className="h3">{title}</h3>
      <div className={styles.matches} role="table" aria-labelledby={id}>
        <div role="rowgroup">
          <div className={`${styles.drow} ${styles.phead}`} role="row">
            <span role="columnheader">{t.colCourt}</span>
            {sides.map((side) => <span key={side} role="columnheader">{side}</span>)}
          </div>
        </div>
        <div className={styles.mbody} role="rowgroup">
          {rows.map((row) => (
            <div key={row.court} className={styles.drow} role="row">
              <span role="cell">{row.court}</span>
              {row.cells.map((cell) => (
                <span key={cell.side} className={styles.num} role="cell">
                  {cell.value} <span className={styles.oppRank}>{cell.counts}</span>
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ShotPatterns({ data }: { data: PlayerStats }) {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  const view = shotView(data.shots, t);
  const toggle = (key: string) => setOpen(open === key ? null : key);
  return (
    <section className={styles.sec} aria-labelledby="shots">
      <h2 id="shots" className="h2">{t.shotsTitle}</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={styles.note}>{view.note}</p>
      {view.charted > 0 && (
        <div className={styles.columns}>
          <div className={styles.serveCol}>
            <Directions id="dir-first" title={t.firstServesIn} rows={view.first} />
            <Directions id="dir-second" title={t.secondServes} rows={view.second} />
            <details className={styles.sourceDetails}>
              <summary>{t.showSource}</summary>
              <SourceCard source={view.source} />
            </details>
          </div>
          <div className={styles.sideCol}>
            <div>
              <h3 className="h3">{t.ralliesTitle}</h3>
              {view.rallies.map((row) => (
                <NumberRow key={row.key} row={row} idPrefix="rally" open={open === `r${row.key}`} onToggle={() => toggle(`r${row.key}`)} />
              ))}
            </div>
            <div>
              <h3 className="h3">{t.netTitle}</h3>
              {view.net.map((row) => (
                <NumberRow key={row.key} row={row} idPrefix="net" open={open === `n${row.key}`} onToggle={() => toggle(`n${row.key}`)} />
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
