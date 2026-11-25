"use client";

// Serve direction, points won by rally length and net points from the Match Charting Project's
// charted matches (D-030). Every figure says how many charted matches it rests on.

import { useState } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type DirectionRow, type ShotDirectionView, shotDirectionView, shotView } from "@/lib/patterns.ts";
import type { PlayerStats } from "@/lib/player-stats.ts";
import { NumberRow, SourceCard } from "./NumberRow.tsx";
import styles from "./Stats.module.css";

export function Directions({ id, title, rows, firstColumn }: { id: string; title: string; rows: DirectionRow[]; firstColumn?: string }) {
  const t = useT();
  const sides = rows[0]?.cells.map((cell) => cell.side) ?? [];
  const rowClass = sides.length > 3 ? `${styles.drow} ${styles.drowWide}` : styles.drow;
  return (
    <div className={styles.sheet}>
      <h3 id={id} className="h3">{title}</h3>
      <div className={styles.matches} role="table" aria-labelledby={id}>
        <div role="rowgroup">
          <div className={`${rowClass} ${styles.phead}`} role="row">
            <span role="columnheader">{firstColumn ?? t.colCourt}</span>
            {sides.map((side) => <span key={side} role="columnheader">{side}</span>)}
          </div>
        </div>
        <div className={styles.mbody} role="rowgroup">
          {rows.map((row) => (
            <div key={row.court} className={rowClass} role="row">
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

/** Where each shot went and what it produced (D-038): one player's two tables and their source. */
export function ShotDirectionTables({ view, id, title }: { view: ShotDirectionView; id: string; title: string }) {
  const t = useT();
  return (
    <div className={styles.shotDirection}>
      <h3 className="h3">{title}</h3>
      <p className={styles.note}>{view.note}</p>
      <Directions id={`${id}-where`} title={t.shotDirWhere} rows={view.grid} firstColumn={t.colShot} />
      <div className={styles.sheet}>
        <h4 id={`${id}-produced`} className={styles.sheetTitle}>{t.shotDirProduced}</h4>
        <div className={styles.matches} role="table" aria-labelledby={`${id}-produced`}>
          <div role="rowgroup">
            <div className={`${styles.orow} ${styles.phead}`} role="row">
              <span role="columnheader">{t.colShot}</span>
              <span role="columnheader">{t.colHit}</span>
              <span role="columnheader">{t.colWinners}</span>
              <span role="columnheader">{t.colForcedDrawn}</span>
              <span role="columnheader">{t.colUnforced}</span>
              <span role="columnheader">{t.colPointsWon}</span>
            </div>
          </div>
          <div className={styles.mbody} role="rowgroup">
            {view.outcomes.map((row) => (
              <div key={row.key} className={styles.orow} role="row">
                <span role="cell" className={styles.oshot}>
                  {row.shot}
                  {row.small && <span className="tag">{t.smallSample}</span>}
                </span>
                <span className={styles.num} role="cell" data-label={t.colHit}>{row.hit}</span>
                <span className={styles.num} role="cell" data-label={t.colWinners}>{row.winners}</span>
                <span className={styles.num} role="cell" data-label={t.colForcedDrawn}>{row.forcedDrawn}</span>
                <span className={styles.num} role="cell" data-label={t.colUnforced}>{row.unforced}</span>
                <span className={styles.num} role="cell" data-label={t.colPointsWon}>{row.pointsWon}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <details className={styles.sourceDetails}>
        <summary>{t.showSource}</summary>
        <SourceCard source={view.source} />
      </details>
    </div>
  );
}

export function ShotPatterns({ data }: { data: PlayerStats }) {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  const view = shotView(data.shots, t);
  const direction = shotDirectionView(data.shots, t);
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
      {direction && <ShotDirectionTables view={direction} id="shot-direction" title={t.shotDirTitle} />}
    </section>
  );
}
