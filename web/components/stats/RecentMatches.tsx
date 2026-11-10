import { type RecentForm, formView } from "@/lib/player-stats.ts";
import styles from "./Stats.module.css";

export function RecentMatches({ form }: { form: RecentForm }) {
  const view = formView(form);
  return (
    <section className={`${styles.sec} ${styles.recent}`} aria-labelledby="recent">
      <h2 id="recent" className="h2">{view.title}</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={styles.note}>{view.note}</p>
      {view.rows.length > 0 && (
        <div className={styles.sheet}>
          <div className={styles.matches} role="table" aria-labelledby="recent">
            <div role="rowgroup">
              <div className={`${styles.mrow} ${styles.mhead}`} role="row">
                <span role="columnheader">Date</span>
                <span role="columnheader">Tournament</span>
                <span role="columnheader">Opponent</span>
                <span role="columnheader">Result</span>
                <span role="columnheader">Score</span>
              </div>
            </div>
            <div className={styles.mbody} role="rowgroup">
              {view.rows.map((m) => (
                <div key={m.key} className={styles.mrow} role="row">
                  <span className={`${styles.cDate} ${styles.num}`} role="cell">{m.date}</span>
                  <span className={styles.cEvent} role="cell">
                    <span className={styles.event}>{m.event}</span>
                    <span className={styles.sub}>
                      {m.swatch && <span className={`sw ${m.swatch} ${styles.subSwatch}`} aria-hidden="true" />}
                      {m.round} on {m.surface}
                    </span>
                  </span>
                  <span className={styles.cOpp} role="cell">{m.opponent} <span className={styles.oppRank}>{m.rank}</span></span>
                  <span className={`${styles.cRes} ${m.won ? styles.won : styles.lost}`} role="cell">{m.won ? "Won" : "Lost"}</span>
                  <span className={`${styles.cScore} ${styles.num}`} role="cell">{m.score}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
