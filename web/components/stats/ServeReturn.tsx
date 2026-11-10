"use client";

import { useState } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type PlayerStats, type ServeRow, serveGroups, serveNote } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

function Row({ row, open, onToggle }: { row: ServeRow; open: boolean; onToggle: () => void }) {
  const t = useT();
  const panelId = `src-${row.key}`;
  return (
    <div>
      <button type="button" className={styles.numrow} aria-expanded={open} aria-controls={open ? panelId : undefined} onClick={onToggle}>
        <span className={styles.numLeft}>
          <span className={styles.numTitle}>
            {row.title}
            {row.small && <span className="tag">{t.smallSample}</span>}
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
            <dt>{t.source}</dt>
            <dd>{row.source.tool}</dd>
            <dt>{t.filters}</dt>
            <dd>{row.source.filters}</dd>
            <dt>{t.sample}</dt>
            <dd>{row.source.sample}</dd>
            <dt>{t.leftOut}</dt>
            <dd>{row.source.left}</dd>
          </dl>
        </div>
      )}
    </div>
  );
}

export function ServeReturn({ data }: { data: PlayerStats }) {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className={styles.serveCol} aria-labelledby="serve-return">
      <h2 id="serve-return" className="h2">{t.serveAndReturn}</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={styles.note}>{serveNote(data.filters, t)}</p>
      {serveGroups(data, t).map((group) => (
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
