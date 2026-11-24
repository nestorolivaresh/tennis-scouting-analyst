"use client";

// One figure on the match prep page: a button showing the value, the counts behind it and a bar,
// which opens its source card. `who` names the player for screen readers when the title doesn't.

import { useT } from "@/components/ui/LanguageProvider.tsx";
import type { PatternRow } from "@/lib/patterns.ts";
import stats from "@/components/stats/Stats.module.css";
import styles from "./Prep.module.css";

export type Tone = "player" | "opponent";

export function Figure({ id, row, title, who, tone, open, onToggle }: {
  id: string;
  row: PatternRow;
  title: string;
  who?: string;
  tone: Tone;
  open: boolean;
  onToggle: () => void;
}) {
  const t = useT();
  return (
    <button
      type="button"
      className={`${styles.fig} ${tone === "opponent" ? styles.figOpponent : styles.figPlayer}`}
      aria-expanded={open}
      aria-controls={open ? id : undefined}
      onClick={onToggle}
    >
      <span className={styles.figTitle}>
        {who && <span className="vh">{who} </span>}
        {title}
        {row.small && <span className="tag">{t.smallSample}</span>}
      </span>
      <span className={styles.figValue}>{row.value}</span>
      {row.hasBar && (
        <span className={stats.track} aria-hidden="true">
          <span className={`${stats.fill} ${styles.fill}`} style={{ width: `${row.width}%` }} />
        </span>
      )}
      <span className={styles.figCount}>{row.counts}</span>
    </button>
  );
}
