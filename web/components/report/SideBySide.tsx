// Both comparisons are drawn in plain HTML and CSS, from this run's tool results. A gap is a gap,
// with a note saying why (no matches, not looked up, or no matches with stats); never a zero.

import { type Lead, type SurfaceRow, type Window, isSmallSample, leadOf, scalePosition, serveChart, serveSampleLine, serveScale, shortNames, surfaceChart } from "@/lib/evidence.ts";
import { longDate } from "@/lib/people.ts";
import type { Evidence, PlayerRef, Surface } from "@/lib/types.ts";
import styles from "./ReportView.module.css";

type Names = { player: string; opponent: string };
type Props = { evidence: Evidence[]; player: PlayerRef; opponent: PlayerRef; surface: Surface; window: Window };

const MISSING = "No data";
const percent = (value: number | null) => (value === null ? MISSING : `${value.toFixed(1)}%`);

function Ahead({ lead, names }: { lead: Lead; names: Names }) {
  if (lead.side === null) return <>{MISSING}</>;
  if (lead.side === "level") return <>Level</>;
  return <><span className={lead.side === "player" ? styles.whoS : styles.whoA}>{names[lead.side]}</span> by {lead.gap}</>;
}

export function SideBySide({ evidence, player, opponent, surface, window }: Props) {
  const serve = serveChart(evidence, player, opponent, surface, window);
  const surfaces = surfaceChart(evidence, player, opponent, window);
  const names = shortNames(player, opponent);
  const scale = serveScale(serve.rows);
  const word = surface.toLowerCase();
  const onSurface = serve.scope === word || serve.sources.length === 0;
  const place = onSurface ? `on ${word}` : serve.scope === "all surfaces" ? "on all surfaces" : "on mixed surfaces";
  const sampleLine = serveSampleLine(serve, player, opponent, surface);
  const small = [...serve.matchesWithStats.player, ...serve.matchesWithStats.opponent].some(isSmallSample);
  const notes = sampleLine ? serve.caveats : serve.notes;
  const surfaceRows = [...surfaces.rows].sort((a, b) => Number(b.surface === surface) - Number(a.surface === surface));
  return (
    <section id="side" className={styles.sec}>
      <h2 className="h2">Side by side</h2>
      <div className={`courtline ${styles.lineSide}`} aria-hidden="true" />
      <div className={styles.sideWrap}>
        <div className={styles.sideTable}>
          <h3 className={`h3 ${styles.bottleHead}`}>Serve, return and break points {place}</h3>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <caption className="vh">Figures {place} for {player.name} and {opponent.name}, with who is ahead and by how many percentage points</caption>
              <thead>
                <tr>
                  <th scope="col" className={`${styles.td} ${styles.headMuted}`}>Figure</th>
                  <th scope="col" className={`${styles.td} ${styles.whoS} ${styles.headNum}`}><span className={`${styles.dotS} ${styles.dotKey}`} aria-hidden="true" />{names.player}</th>
                  <th scope="col" className={`${styles.td} ${styles.dumbCol}`}><span className="vh">Gap on a scale of {scale.min}% to {scale.max}%</span></th>
                  <th scope="col" className={`${styles.td} ${styles.whoA} ${styles.headNum}`}><span className={`${styles.dotA} ${styles.dotKey}`} aria-hidden="true" />{names.opponent}</th>
                  <th scope="col" className={`${styles.td} ${styles.headMuted}`}>Ahead</th>
                </tr>
              </thead>
              <tbody>
                {serve.rows.map((row) => {
                  const lead = leadOf(row.player, row.opponent);
                  const ends = [row.player, row.opponent].filter((v): v is number => v !== null);
                  const [from, to] = [Math.min(...ends), Math.max(...ends)];
                  return (
                    <tr key={row.metric}>
                      <th scope="row" className={styles.td}>{row.metric}</th>
                      <td className={`${styles.td} ${styles.num} ${lead.side === "player" ? styles.lead : ""}`}>{percent(row.player)}</td>
                      <td className={`${styles.td} ${styles.dumbCol}`}>
                        <div className={styles.dumb} aria-hidden="true">
                          {ends.length === 2 && <span className={styles.dumbLine} style={{ left: `${scalePosition(from, scale)}%`, width: `${scalePosition(to, scale) - scalePosition(from, scale)}%` }} />}
                          {row.player !== null && <span className={styles.dotS} style={{ left: `${scalePosition(row.player, scale)}%` }} />}
                          {row.opponent !== null && <span className={styles.dotA} style={{ left: `${scalePosition(row.opponent, scale)}%` }} />}
                        </div>
                      </td>
                      <td className={`${styles.td} ${styles.num} ${lead.side === "opponent" ? styles.lead : ""}`}>{percent(row.opponent)}</td>
                      <td className={styles.td}><Ahead lead={lead} names={names} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className={styles.sideNote}>
            Gaps are in percentage points<span className={styles.dumbNote}>, drawn on a shared scale from {scale.min}% to {scale.max}%</span>.
            {sampleLine ? ` ${sampleLine}` : ""}{small && <span className="tag">Small sample</span>}
          </p>
          <Notes notes={notes} />
        </div>

        <div className={styles.sideSurface}>
          <h3 className={`h3 ${styles.bottleHead}`}>Win rate by surface</h3>
          <div className={styles.surfGrid}>
            {surfaceRows.map((row) => <SurfaceCard key={row.surface} row={row} isThisMatch={row.surface === surface} names={names} />)}
          </div>
          <p className={styles.sideNote}>Tournaments starting {longDate(window.date_from)} to {longDate(window.date_to)}.</p>
          <Notes notes={surfaces.notes} />
        </div>
      </div>
    </section>
  );
}

function Notes({ notes }: { notes: string[] }) {
  if (!notes.length) return null;
  return <ul className={styles.sideNotes}>{notes.map((note, i) => <li key={i}>{note}</li>)}</ul>;
}

const CELL_WORDS = { no_matches: "No matches", not_looked_up: "Not looked up" } as const;

function cellText(cell: SurfaceRow["playerCell"]): string {
  return cell.status === "ok" ? percent(cell.winRate) : CELL_WORDS[cell.status];
}

function SurfaceCard({ row, isThisMatch, names }: { row: SurfaceRow; isThisMatch: boolean; names: Names }) {
  const lead = leadOf(row.player, row.opponent);
  const records = [
    row.playerCell.record && `${names.player} ${row.playerCell.record}`,
    row.opponentCell.record && `${names.opponent} ${row.opponentCell.record}`,
  ].filter(Boolean);
  const ahead = lead.side === null ? null : lead.side === "level" ? "Level" : `${names[lead.side]} by ${lead.gap}`;
  return (
    <div className={`${styles.surf} sw-${row.surface.toLowerCase()}`}>
      <div className={styles.surfTop}>
        <span className={styles.surfName}>{row.surface}</span>
        {isThisMatch && <span className={styles.surfThis}>This match</span>}
      </div>
      <div className={styles.surfRates}>
        <span>{names.player} {cellText(row.playerCell)}</span>
        <span>{names.opponent} {cellText(row.opponentCell)}</span>
      </div>
      {ahead && <div className={styles.surfAhead}>{ahead}</div>}
      {records.length > 0 && <div className={styles.surfRecord}>Won-lost: {records.join(", ")}</div>}
    </div>
  );
}
