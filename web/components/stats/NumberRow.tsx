"use client";

// One figure on the Player stats page: its title, a bar for a share, the counts behind it, the
// value, and a source panel that opens on click.

import { useT } from "@/components/ui/LanguageProvider.tsx";
import type { SourceFacts } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

export interface NumberRowData {
  key: string;
  title: string;
  value: string;
  counts: string;
  small: boolean;
  hasBar: boolean;
  width: number;
  tick: number | null;
  source: SourceFacts;
}

export function NumberRow({ row, idPrefix, open, onToggle }: { row: NumberRowData; idPrefix: string; open: boolean; onToggle: () => void }) {
  const t = useT();
  const panelId = `${idPrefix}-${row.key}`;
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
      {open && <SourceCard id={panelId} source={row.source} />}
    </div>
  );
}

export function SourceCard({ id, source }: { id?: string; source: SourceFacts }) {
  const t = useT();
  return (
    <div id={id} className={styles.card}>
      <dl>
        <dt>{t.source}</dt>
        <dd>{source.tool}</dd>
        <dt>{t.filters}</dt>
        <dd>{source.filters}</dd>
        <dt>{t.sample}</dt>
        <dd>{source.sample}</dd>
        <dt>{t.leftOut}</dt>
        <dd>{source.left}</dd>
      </dl>
    </div>
  );
}
