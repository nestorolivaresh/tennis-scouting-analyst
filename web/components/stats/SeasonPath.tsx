"use client";

// A player's season path (D-035): each tournament of the page's season, how it ended and its
// matches, which open under the row. Walkovers are listed and tagged not counted.

import { useT } from "@/components/ui/LanguageProvider.tsx";
import { type SeasonPath as SeasonPathBlock, pathView } from "@/lib/season-path.ts";
import { SourceCard } from "./NumberRow.tsx";
import styles from "./Stats.module.css";

/** Nothing is shown for a response cached before the season path existed, or with no season. */
export function SeasonPath({ path }: { path: SeasonPathBlock | null | undefined }) {
  const t = useT();
  if (!path) return null;
  const view = pathView(path, t);
  return (
    <section className={`${styles.sec} ${styles.recent}`} aria-labelledby="season-path">
      <h2 id="season-path" className="h2">{view.title}</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={styles.note}>{view.note}</p>
      {view.summary && <p className={styles.pathSummary}>{view.summary}</p>}
      {view.empty && <p className={styles.note}>{view.empty}</p>}
      {view.rows.length > 0 && (
        <div className={styles.sheet}>
          <div className={`${styles.pathRow} ${styles.mhead}`} aria-hidden="true">
            <span>{t.colDate}</span>
            <span>{t.colTournament}</span>
            <span>{t.colEnded}</span>
            <span className={styles.pathRecord}>{t.colWinLoss}</span>
          </div>
          <ol className={styles.pathList}>
            {view.rows.map((row) => (
              <li key={row.key} className={styles.pathItem}>
                <details>
                  <summary className={styles.pathRow}>
                    <span className={`${styles.pathDate} ${styles.num}`}>{row.date}</span>
                    <span className={styles.pathEvent}>
                      <span className={styles.event}>{row.event}</span>
                      <span className={styles.sub}>
                        {row.swatch && <span className={`sw ${row.swatch} ${styles.subSwatch}`} aria-hidden="true" />}
                        {row.surface}
                      </span>
                    </span>
                    <span className={styles.pathEnded}>
                      <span className={row.title ? styles.won : undefined}>{row.ended}</span>
                      <span className={styles.sub}>{row.last}</span>
                    </span>
                    <span className={styles.pathRecord}>
                      <span className={styles.num}>{row.record}</span>
                      <span className={styles.sub}>{row.matchCount}</span>
                    </span>
                  </summary>
                  <ul className={styles.pathMatches}>
                    {row.matches.map((m) => (
                      <li key={m.key} className={styles.pathMatch}>
                        <span className={styles.pathRound}>{m.round}</span>
                        <span>{m.opponent} <span className={styles.oppRank}>{m.rank}</span></span>
                        <span className={m.won ? styles.won : styles.lost}>{m.won ? t.won : t.lost}</span>
                        <span className={styles.num}>
                          {m.score}
                          {!m.counted && <span className={`tag ${styles.pathTag}`}>{t.notCounted}</span>}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              </li>
            ))}
          </ol>
        </div>
      )}
      <details className={styles.sourceDetails}>
        <summary>{t.showSource}</summary>
        <SourceCard source={view.source} />
      </details>
    </section>
  );
}
