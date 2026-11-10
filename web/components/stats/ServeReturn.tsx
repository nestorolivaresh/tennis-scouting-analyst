"use client";

import { useState } from "react";
import { type PlayerStats, type ServeRow, serveGroups, serveNote } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

function Row({ row, open, onToggle }: { row: ServeRow; open: boolean; onToggle: () => void }) {
  const panelId = `src-${row.key}`;
  return (
    <div>
      <button type="button" className={styles.numrow} aria-expanded={open} aria-controls={open ? panelId : undefined} onClick={onToggle}>
        <span className={styles.numLeft}>
          <span className={styles.numTitle}>
            {row.title}
            {row.small && <span className="tag">Small sample</span>}
          </span>
          {row.hasBar && (
            <span className={styles.track} aria-hidden="true">
              <span className={styles.fill} style={{ width: `${row.width}%` }} />
              {row.tick !== null && <span className={styles.tick} style={{ left: `${row.tick}%` }} />}
            </span>
          )}
          <span className={styles.numCount}>{row.counts}</span>
        </span>
        <span className={styles.numValue}>{row.value}</span>
      </button>
      {open && (
        <div id={panelId} className={styles.card}>
          <dl>
            <dt>Source</dt>
            <dd>{row.source.tool}</dd>
            <dt>Filters</dt>
            <dd>{row.source.filters}</dd>
            <dt>Sample</dt>
            <dd>{row.source.sample}</dd>
            <dt>Left out</dt>
            <dd>{row.source.left}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}

export function ServeReturn({ data }: { data: PlayerStats }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className={styles.serveCol} aria-labelledby="serve-return">
      <h2 id="serve-return" className="h2">Serve and return</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={styles.note}>{serveNote(data.filters)}</p>
      {serveGroups(data).map((group) => (
        <div key={group.name}>
          <h3 className="h3">{group.name}</h3>
          {group.rows.map((row) => (
            <Row key={row.key} row={row} open={open === row.key} onToggle={() => setOpen(open === row.key ? null : row.key)} />
          ))}
        </div>
      ))}
    </section>
  );
}
