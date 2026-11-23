"use client";

import { useState } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type PlayerStats, serveGroups, serveNote } from "@/lib/player-stats.ts";
import { NumberRow } from "./NumberRow.tsx";
import styles from "./Stats.module.css";

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
            <NumberRow key={row.key} row={row} idPrefix="src" open={open === row.key} onToggle={() => setOpen(open === row.key ? null : row.key)} />
          ))}
        </div>
      ))}
    </section>
  );
}
