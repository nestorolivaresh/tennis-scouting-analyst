"use client";

// The match prep page (D-033). Its state is the URL, so a view can be shared and Back works. Each
// URL is one API call; while the next one loads, the last numbers stay on screen, marked busy.
// No model is involved, so the page keeps working when the daily spend cap is reached.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import stats from "@/components/stats/Stats.module.css";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { Medal } from "@/components/ui/Medal.tsx";
import { ApiFailure, fetchMatchup } from "@/lib/api.ts";
import { type T, failureText, surfaceWords } from "@/lib/i18n.ts";
import { isBadLink } from "@/lib/player-stats.ts";
import { type Matchup, type PrepQuery, headerView, matchupUrl, parsePrepQuery, prepHref, withPrepSurface, withScope } from "@/lib/prep.ts";
import { SURFACES } from "@/lib/types.ts";
import styles from "./Prep.module.css";
import { HeadToHeadSection, RecordSection, ServeSection, SetsSection, ShotsSection } from "./Sections.tsx";

type Failure = { message: string; badLink: boolean };

/** What the last finished request gave. `key` says which request that was. */
type Settled = { key: string; data: Matchup | null; failure: Failure | null };

function describeFailure(error: unknown, t: T): Failure {
  if (error instanceof ApiFailure) return { message: failureText(error.kind, error.message, t), badLink: isBadLink(error.status) };
  return { message: t.prepUnreachable, badLink: false };
}

function useMatchup(url: string | null, t: T) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const key = `${attempt} ${url}`;

  useEffect(() => {
    if (url === null) return; // no match-up or no surface yet, so nothing to fetch
    const controller = new AbortController();
    fetchMatchup(url, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setSettled({ key, data, failure: null });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setSettled((last) => ({ key, data: last?.data ?? null, failure: describeFailure(error, t) }));
      },
    );
    return () => controller.abort();
  }, [url, key, t]);

  return {
    data: settled?.data ?? null,
    failure: settled?.failure ?? null,
    busy: settled?.key !== key,
    retry: () => setAttempt((n) => n + 1),
  };
}

function Heading() {
  const t = useT();
  return (
    <div className={stats.head}>
      <div className={stats.headText}>
        <h1 className={stats.title}>{t.prepHeading}</h1>
        <p className={stats.lede}>{t.prepLede}</p>
      </div>
    </div>
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

function Loading() {
  const t = useT();
  return <p className={styles.loading} role="status">{t.prepLoading}</p>;
}

/** Shown until the URL can be read in the browser. */
export function PrepLoading() {
  return (
    <main className={stats.page}>
      <Heading />
      <Loading />
    </main>
  );
}

function Header({ m, onScope }: { m: Matchup; onScope: (scope: "surface" | "all") => void }) {
  const t = useT();
  const view = headerView(m, t);
  return (
    <div className={styles.header}>
      <div className={styles.versus}>
        <div className={styles.side}>
          <Medal name={m.player.player.name} country={m.player.country} tone="player" />
          <div>
            <p className={`${styles.name} ${styles.textPlayer}`}>{m.player.player.name}</p>
            <p className={styles.role}>{t.yourPlayer}</p>
          </div>
        </div>
        <span className={styles.against}>{t.prepAgainst}</span>
        <div className={`${styles.side} ${styles.sideOpponent}`}>
          <div>
            <p className={`${styles.name} ${styles.textOpponent}`}>{m.opponent.player.name}</p>
            <p className={styles.role}>{t.opponent}</p>
          </div>
          <Medal name={m.opponent.player.name} country={m.opponent.country} tone="opponent" />
        </div>
      </div>
      <p className={stats.note}>{view.window}</p>
      <div className={styles.scopes} role="group" aria-label={t.scopeLegend}>
        {view.scopes.map((scope) => (
          <button key={scope.id} type="button" className={styles.scope} aria-pressed={scope.pressed} onClick={() => onScope(scope.id)}>
            {scope.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Content({ m }: { m: Matchup }) {
  const [open, setOpen] = useState<string | null>(null);
  const toggle = (id: string) => setOpen(open === id ? null : id);
  const opening = { open, toggle };
  return (
    <>
      <HeadToHeadSection m={m} />
      <ServeSection m={m} server="player" {...opening} />
      <ServeSection m={m} server="opponent" {...opening} />
      <SetsSection m={m} {...opening} />
      <ShotsSection m={m} {...opening} />
      <RecordSection m={m} {...opening} />
    </>
  );
}

export function PrepView() {
  const t = useT();
  const query = parsePrepQuery(useSearchParams());
  const url = query?.surface ? matchupUrl({ ...query, surface: query.surface }) : null;
  const { data, failure, busy, retry } = useMatchup(url, t);

  // Next keeps useSearchParams in step with pushState, with no server round trip and no jump to
  // the top of the page.
  function go(next: PrepQuery) {
    const href = prepHref(next);
    if (!query || href !== prepHref(query)) window.history.pushState(null, "", href);
  }

  return (
    <main className={stats.page}>
      <Heading />

      {!query && (
        <Panel title={t.prepNoPlayersTitle} text={t.prepNoPlayersHelp}>
          <Link className="btn" href="/">{t.setUpMatch}</Link>
        </Panel>
      )}

      {query && !query.surface && (
        <div className={styles.choose} role="group" aria-labelledby="choose-surface">
          <p id="choose-surface" className={styles.chooseText}>{t.prepChooseSurface}</p>
          <div className={styles.scopes}>
            {SURFACES.map((surface) => (
              <button key={surface} type="button" className={styles.scope} onClick={() => go(withPrepSurface(query, surface))}>
                <span className={`sw sw-${surface.toLowerCase()} ${stats.subSwatch}`} aria-hidden="true" /> {surfaceWords(t, surface).name}
              </button>
            ))}
          </div>
        </div>
      )}

      {url && query && failure && (
        failure.badLink ? (
          <Panel title={t.linkCantShow} text={t.prepLinkHelp}>
            <Link className="btn" href="/">{t.setUpMatch}</Link>
          </Panel>
        ) : (
          <Panel title={t.prepDidntLoad} text={failure.message} busy={busy}>
            <button type="button" className="btn" onClick={retry} disabled={busy}>{busy ? t.tryingAgain : t.tryAgain}</button>
          </Panel>
        )
      )}
      {url && query && !failure && !data && <Loading />}
      {url && query && !failure && data && (
        <div className={styles.content} aria-busy={busy}>
          <Header m={data} onScope={(scope) => go(withScope(query, scope))} />
          <Content key={url} m={data} />
        </div>
      )}
    </main>
  );
}
