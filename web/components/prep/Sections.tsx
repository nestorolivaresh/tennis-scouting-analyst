"use client";

// The match prep page's sections (D-033). Every figure comes from lib/prep.ts, which reads it from
// the response's blocks; one source card is open at a time, under the row it belongs to.

import Link from "next/link";
import { SourceCard } from "@/components/stats/NumberRow.tsx";
import { Directions, ShotDirectionTables } from "@/components/stats/ShotPatterns.tsx";
import stats from "@/components/stats/Stats.module.css";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import type { PatternRow } from "@/lib/patterns.ts";
import { lastName } from "@/lib/people.ts";
import { type Matchup, type TwoRow, headToHeadView, recordView, serveView, setsView, shotsView } from "@/lib/prep.ts";
import { Figure, type Tone } from "./Figure.tsx";
import styles from "./Prep.module.css";

export type Opening = { open: string | null; toggle: (id: string) => void };

const OTHER: Record<Tone, Tone> = { player: "opponent", opponent: "player" };

/** The source card for whichever of these figures is open, if any. */
function OpenCard({ open, figures }: { open: string | null; figures: [id: string, row: PatternRow | null][] }) {
  const shown = figures.find(([id, row]) => row && id === open);
  return shown ? <SourceCard id={shown[0]} source={shown[1]!.source} /> : null;
}

function Heading({ id, title, note }: { id: string; title: string; note: string }) {
  return (
    <>
      <h2 id={id} className="h2">{title}</h2>
      <div className="courtline" aria-hidden="true" />
      <p className={stats.note}>{note}</p>
    </>
  );
}

function names(m: Matchup) {
  return { player: lastName(m.player.player.name), opponent: lastName(m.opponent.player.name) };
}

// ---------- head-to-head ----------

export function HeadToHeadSection({ m }: { m: Matchup }) {
  const t = useT();
  const view = headToHeadView(m, t);
  return (
    <section className={stats.sec} aria-labelledby="h2h">
      <Heading id="h2h" title={t.tools.head_to_head} note={t.h2hNote} />
      <div className={styles.h2hLines}>
        <p className={styles.h2hLine}>{view.career}</p>
        <p className={styles.h2hLine}>
          {view.onSurface}
          {view.small && <span className="tag">{t.smallSample}</span>}
        </p>
      </div>
      {view.note && <p className={stats.note}>{view.note}</p>}
      {view.rows.length > 0 && (
        <div className={stats.sheet}>
          <div className={stats.matches} role="table" aria-labelledby="h2h">
            <div role="rowgroup">
              <div className={`${stats.mrow} ${styles.meetRow} ${stats.mhead}`} role="row">
                <span role="columnheader">{t.colDate}</span>
                <span role="columnheader">{t.colTournament}</span>
                <span role="columnheader">{t.colWinner}</span>
                <span role="columnheader">{view.scoreHeader}</span>
              </div>
            </div>
            <div className={stats.mbody} role="rowgroup">
              {view.rows.map((row) => (
                <div key={row.key} className={`${stats.mrow} ${styles.meetRow}`} role="row">
                  <span className={`${stats.cDate} ${stats.num}`} role="cell">{row.date}</span>
                  <span className={stats.cEvent} role="cell">
                    <span className={stats.event}>{row.event}</span>
                    <span className={stats.sub}>
                      {row.swatch && <span className={`sw ${row.swatch} ${stats.subSwatch}`} aria-hidden="true" />}
                      {t.roundOn(row.round, row.surface)}
                    </span>
                  </span>
                  <span className={`${stats.cOpp} ${row.playerWon ? styles.textPlayer : styles.textOpponent}`} role="cell">{row.winner}</span>
                  <span className={`${stats.cScore} ${stats.num}`} role="cell">{row.score}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------- each serve against the other's return ----------

export function ServeSection({ m, server, open, toggle }: { m: Matchup; server: Tone } & Opening) {
  const t = useT();
  const view = serveView(m, server, t);
  const who = names(m);
  const returner = OTHER[server];
  const id = `serves-${server}`;
  return (
    <section className={stats.sec} aria-labelledby={id}>
      <Heading id={id} title={view.title} note={view.note} />
      <div className={styles.pairHead} aria-hidden="true">
        <span className={styles[`text${server === "player" ? "Player" : "Opponent"}`]}>{view.serving}</span>
        <span />
        <span className={`${styles.right} ${styles[`text${returner === "player" ? "Player" : "Opponent"}`]}`}>{view.returning}</span>
      </div>
      {view.rows.map((row) => {
        const serveId = `${id}-${row.key}-serve`;
        const retId = `${id}-${row.key}-return`;
        return (
          <div key={row.key} className={styles.block}>
            <div className={styles.pair}>
              <Figure
                id={serveId} row={row.serve} title={row.serve.title} who={who[server]} tone={server}
                open={open === serveId} onToggle={() => toggle(serveId)}
              />
              <span className={styles.vs} aria-hidden="true">{row.ret ? t.versus : ""}</span>
              {row.ret ? (
                <Figure
                  id={retId} row={row.ret} title={row.ret.title} who={who[returner]} tone={returner}
                  open={open === retId} onToggle={() => toggle(retId)}
                />
              ) : <span className={styles.empty} />}
            </div>
            <OpenCard open={open} figures={[[serveId, row.serve], [retId, row.ret]]} />
          </div>
        );
      })}
    </section>
  );
}

// ---------- the same figure for both players ----------

function TwoRows({ prefix, rows, m, open, toggle }: { prefix: string; rows: TwoRow[]; m: Matchup } & Opening) {
  const who = names(m);
  return (
    <>
      <div className={`${styles.two} ${styles.twoHead}`} aria-hidden="true">
        <span />
        <span className={styles.textPlayer}>{who.player}</span>
        <span className={styles.textOpponent}>{who.opponent}</span>
      </div>
      {rows.map((row) => {
        const ids = { player: `${prefix}-${row.key}-player`, opponent: `${prefix}-${row.key}-opponent` };
        return (
          <div key={row.key} className={styles.block}>
            <div className={styles.two}>
              <span className={styles.twoTitle}>{row.title}</span>
              {(["player", "opponent"] as const).map((side) => (
                <Figure
                  key={side} id={ids[side]} row={row[side]} title={who[side]} tone={side}
                  open={open === ids[side]} onToggle={() => toggle(ids[side])}
                />
              ))}
            </div>
            <OpenCard open={open} figures={[[ids.player, row.player], [ids.opponent, row.opponent]]} />
          </div>
        );
      })}
    </>
  );
}

export function SetsSection({ m, open, toggle }: { m: Matchup } & Opening) {
  const t = useT();
  const view = setsView(m, t);
  return (
    <section className={stats.sec} aria-labelledby="prep-sets">
      <Heading id="prep-sets" title={t.setsTitle} note={view.note} />
      <TwoRows prefix="sets" rows={view.rows} m={m} open={open} toggle={toggle} />
    </section>
  );
}

export function ShotsSection({ m, open, toggle }: { m: Matchup } & Opening) {
  const t = useT();
  const view = shotsView(m, t);
  const anyDirection = view.sides.some((side) => side.direction !== null);
  return (
    <section className={stats.sec} aria-labelledby="prep-shots">
      <Heading id="prep-shots" title={t.shotsTitle} note={view.note} />
      <div className={styles.courts}>
        {view.sides.map((side) => (
          <div key={side.who} className={styles.court}>
            {side.none ? (
              <p className={stats.note}>{side.none}</p>
            ) : (
              <>
                <Directions id={`dir-first-${side.who}`} title={side.title} rows={side.view.first} />
                <Directions id={`dir-second-${side.who}`} title={side.secondTitle} rows={side.view.second} />
                <details className={stats.sourceDetails}>
                  <summary>{t.showSource}</summary>
                  <SourceCard source={side.view.source} />
                </details>
              </>
            )}
          </div>
        ))}
      </div>
      {anyDirection && (
        <div className={styles.courts}>
          {view.sides.map((side) => (
            <div key={side.who} className={styles.court}>
              {side.direction && <ShotDirectionTables view={side.direction} id={`prep-shot-${side.who}`} title={side.directionTitle} />}
            </div>
          ))}
        </div>
      )}
      <h3 className="h3">{t.ralliesTitle}</h3>
      <TwoRows prefix="rally" rows={view.rallies} m={m} open={open} toggle={toggle} />
      <h3 className="h3">{t.netTitle}</h3>
      <TwoRows prefix="net" rows={view.net} m={m} open={open} toggle={toggle} />
    </section>
  );
}

// ---------- records ----------

export function RecordSection({ m, open, toggle }: { m: Matchup } & Opening) {
  const t = useT();
  const cards = recordView(m, t);
  return (
    <section className={stats.sec} aria-labelledby="prep-record">
      <h2 id="prep-record" className="h2">{t.recordTitle}</h2>
      <div className="courtline" aria-hidden="true" />
      <div className={styles.records}>
        {cards.map((card) => {
          const id = `record-${card.who}`;
          return (
            <div key={card.who} className={styles.record}>
              <h3 className={`h3 ${card.who === "player" ? styles.textPlayer : styles.textOpponent}`}>{card.name}</h3>
              <Figure id={id} row={card.figure} title={card.figure.title} tone={card.who} open={open === id} onToggle={() => toggle(id)} />
              <OpenCard open={open} figures={[[id, card.figure]]} />
              <p className={styles.recordLine}>{card.line}</p>
              <Link href={card.href}>{card.linkText}</Link>
            </div>
          );
        })}
      </div>
    </section>
  );
}
