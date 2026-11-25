"use client";

// The Calendar page (D-036). Its state is the URL (season, and an open tournament), so a view can
// be shared and Back works. Each URL is one API call; while the next one loads, the last numbers
// stay on screen, marked busy. No model is involved.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import stats from "@/components/stats/Stats.module.css";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { ApiFailure, fetchCalendar } from "@/lib/api.ts";
import {
  ATP_CALENDAR_URL,
  type CalendarQuery,
  type CalendarResponse,
  type FinalView,
  calendarHref,
  calendarUrl,
  historyView,
  monthGroups,
  parseCalendarQuery,
  seasonChoices,
  withEvent,
  withSeason,
} from "@/lib/calendar.ts";
import { type T, failureText } from "@/lib/i18n.ts";
import { isBadLink } from "@/lib/player-stats.ts";
import styles from "./Calendar.module.css";

type Failure = { message: string; badLink: boolean };
type Settled = { key: string; data: CalendarResponse | null; failure: Failure | null };

function describeFailure(error: unknown, t: T): Failure {
  if (error instanceof ApiFailure) return { message: failureText(error.kind, error.message, t), badLink: isBadLink(error.status) };
  return { message: t.calUnreachable, badLink: false };
}

function useCalendar(url: string, t: T) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const key = `${attempt} ${url}`;
  useEffect(() => {
    const controller = new AbortController();
    fetchCalendar(url, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setSettled({ key, data, failure: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setSettled((last) => ({ key, data: last?.data ?? null, failure: describeFailure(error, t) }));
      },
    );
    return () => controller.abort();
  }, [url, key, t]);
  return { data: settled?.data ?? null, failure: settled?.failure ?? null, busy: settled?.key !== key, retry: () => setAttempt((n) => n + 1) };
}

function Heading() {
  const t = useT();
  const [before, link, after] = t.calUpcoming;
  return (
    <div className={stats.head}>
      <div className={stats.headText}>
        <h1 className={stats.title}>{t.calHeading}</h1>
        <p className={stats.lede}>{t.calLede}</p>
        <p className={styles.upcoming}>
          {before}
          <a href={ATP_CALENDAR_URL} target="_blank" rel="noreferrer">{link}</a>
          {after}
        </p>
      </div>
    </div>
  );
}

function Loading() {
  const t = useT();
  return <p className={styles.loading} role="status">{t.calLoading}</p>;
}

export function CalendarLoading() {
  return (
    <main className={stats.page}>
      <Heading />
      <Loading />
    </main>
  );
}

/** The winner, linked to their Player stats, then who they beat and the score. */
function Final({ final }: { final: FinalView }) {
  const t = useT();
  if (!final.winner || !final.runnerUp) return <span className={styles.noWinner}>{final.text}</span>;
  return (
    <>
      <Link className={styles.winner} href={final.winner.href}>{final.winner.name}</Link>
      <span className={stats.sub}>{t.calBeatOpponent(final.runnerUp.name, final.score)}</span>
    </>
  );
}

function History({ data, onClose }: { data: NonNullable<CalendarResponse["history"]>; onClose: () => void }) {
  const t = useT();
  const view = historyView(data, t);
  return (
    <section className={`${stats.sheet} ${styles.history}`} aria-labelledby="history-title">
      <div className={styles.historyHead}>
        <h2 id="history-title" className="h2">{view.title}</h2>
        <button type="button" className={styles.close} onClick={onClose}>{t.calClose}</button>
      </div>
      <p className={stats.note}>{view.note}</p>
      <div className={stats.matches} role="table" aria-labelledby="history-title">
        <div role="rowgroup">
          <div className={`${styles.historyRow} ${stats.phead}`} role="row">
            <span role="columnheader">{t.calColYear}</span>
            <span role="columnheader">{t.calColFinal}</span>
          </div>
        </div>
        <div className={stats.mbody} role="rowgroup">
          {view.rows.map((row) => (
            <div key={row.key} className={styles.historyRow} role="row">
              <span className={stats.num} role="cell">
                {row.year}
                {row.name && <span className={stats.sub}>{row.name}</span>}
              </span>
              <span className={styles.finalCell} role="cell">
                <Final final={row.final} />
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Panel({ title, text, children, busy }: { title: string; text: string; children?: ReactNode; busy?: boolean }) {
  return (
    <div className={stats.failure} role="alert" aria-busy={busy}>
      <h2 className="h2">{title}</h2>
      <p className={stats.failureText}>{text}</p>
      {children}
    </div>
  );
}

export function CalendarView() {
  const t = useT();
  const query = parseCalendarQuery(useSearchParams());
  const url = calendarUrl(query);
  const { data, failure, busy, retry } = useCalendar(url, t);

  function go(next: CalendarQuery) {
    const href = calendarHref(next);
    if (href !== calendarHref(query)) window.history.pushState(null, "", href);
  }

  const calendar = data?.calendar ?? null;
  const season = calendar?.filters.season ?? null;
  // A tournament's history opens under its row; a shared link to one not in this season opens on top.
  const history = data?.history ?? null;
  const inSeason = Boolean(history && calendar?.tournaments.some((t) => t.event_code === history.event_code));
  const close = () => go(withEvent(query, null));
  return (
    <main className={stats.page}>
      <Heading />
      {failure && (
        failure.badLink ? (
          <Panel title={t.linkCantShow} text={t.calLinkHelp}>
            <Link className="btn" href="/calendar">{t.calShowSeason}</Link>
          </Panel>
        ) : (
          <Panel title={t.calDidntLoad} text={failure.message} busy={busy}>
            <button type="button" className="btn" onClick={retry} disabled={busy}>{busy ? t.tryingAgain : t.tryAgain}</button>
          </Panel>
        )
      )}
      {!failure && !calendar && <Loading />}
      {!failure && calendar && season !== null && (
        <div className={styles.content} aria-busy={busy}>
          <div className={styles.seasons} role="group" aria-label={t.calSeasonLegend}>
            {seasonChoices(calendar.data_window).map((s) => (
              <button key={s} type="button" className={styles.season} aria-pressed={s === season} onClick={() => go(withSeason(query, s))}>
                {s}
              </button>
            ))}
          </div>
          <p className={stats.note}>{t.calCount(calendar.count, season)}</p>
          {history && !inSeason && <History data={history} onClose={close} />}
          {monthGroups(calendar, t).map((group) => (
            <section key={group.key} className={styles.month} aria-labelledby={`month-${group.key}`}>
              <h2 id={`month-${group.key}`} className="h3">{group.title}</h2>
              <ul className={styles.list}>
                {group.rows.map((row) => (
                  <li key={row.key} className={styles.row}>
                    <span className={`${styles.date} ${stats.num}`}>{row.date}</span>
                    <span className={styles.event}>
                      <button
                        type="button"
                        className={styles.eventButton}
                        aria-pressed={query.event === String(row.code)}
                        onClick={() => go(withEvent(query, row.code))}
                      >
                        {row.event}
                      </button>
                      <span className={`${stats.sub} ${styles.meta}`}>
                        <span className={styles.metaItem}>
                          {row.swatch && <span className={`sw ${row.swatch} ${stats.subSwatch}`} aria-hidden="true" />}
                          {row.surface}
                        </span>
                        <span className={styles.metaItem}>{row.level}</span>
                      </span>
                    </span>
                    <span className={styles.finalCell}>
                      <Final final={row.final} />
                    </span>
                    {history?.event_code === row.code && <History data={history} onClose={close} />}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
