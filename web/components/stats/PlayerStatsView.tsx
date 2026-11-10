"use client";

// The Player stats page. Its state is the URL, so a view can be shared and Back works. Each URL
// is one API call; while the next one loads, the last numbers stay on screen, marked busy.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Board } from "@/components/ui/Board.tsx";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { PlayerSearch } from "@/components/ui/PlayerSearch.tsx";
import { ApiFailure, fetchPlayerStats } from "@/lib/api.ts";
import { type T, failureText } from "@/lib/i18n.ts";
import {
  type DataWindow,
  type PageQuery,
  type PlayerStats,
  coverageLine,
  isBadLink,
  pageHref,
  parseQuery,
  queryForPlayer,
  statsUrl,
  withAgainst,
  withPlayer,
  withSeason,
  withSurface,
  withoutFilters,
} from "@/lib/player-stats.ts";
import { AgainstBox } from "./AgainstBox.tsx";
import { NoPlayerYet } from "./NoPlayerYet.tsx";
import { PlayerBoard } from "./PlayerBoard.tsx";
import { RecentMatches } from "./RecentMatches.tsx";
import { SeasonBoard } from "./SeasonBoard.tsx";
import { ServeReturn } from "./ServeReturn.tsx";
import styles from "./Stats.module.css";
import { SurfaceRecord } from "./SurfaceRecord.tsx";

type Failure = { message: string; badLink: boolean };

/** What the last finished request gave. `key` says which request that was. */
type Settled = { key: string; data: PlayerStats | null; failure: Failure | null };

function describeFailure(error: unknown, t: T): Failure {
  if (error instanceof ApiFailure) return { message: failureText(error.kind, error.message, t), badLink: isBadLink(error.status) };
  return { message: t.statsUnreachable, badLink: false };
}

function usePlayerStats(url: string | null, t: T) {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled | null>(null);
  const key = `${attempt} ${url}`;

  useEffect(() => {
    if (url === null) return; // no player chosen yet, so nothing to fetch
    const controller = new AbortController();
    fetchPlayerStats(url, controller.signal).then(
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

function Heading({ coverage, children }: { coverage: DataWindow | null; children?: ReactNode }) {
  const t = useT();
  return (
    <div className={styles.head}>
      <div className={styles.headText}>
        <h1 className={styles.title}>{t.statsTitle}</h1>
        <p className={styles.lede}>{coverageLine(coverage, t)}</p>
      </div>
      <div className={styles.lookup}>{children}</div>
    </div>
  );
}

function LoadingBoard() {
  const t = useT();
  return (
    <Board aria-label={t.statsTitle} aria-busy="true" className={styles.loadingBoard}>
      <p className={styles.loadingText} role="status">{t.loadingStats}</p>
    </Board>
  );
}

function FailurePanel({ failure, busy, onRetry }: { failure: Failure; busy: boolean; onRetry: () => void }) {
  const t = useT();
  return (
    <div className={styles.failure} role="alert" aria-busy={busy}>
      <h2 className="h2">{failure.badLink ? t.linkCantShow : t.statsDidntLoad}</h2>
      <p className={styles.failureText}>{failure.badLink ? t.linkHelp : failure.message}</p>
      {failure.badLink
        ? <Link className="btn" href="/players">{t.searchForPlayer}</Link>
        : <button type="button" className="btn" onClick={onRetry} disabled={busy}>{busy ? t.tryingAgain : t.tryAgain}</button>}
    </div>
  );
}

/** Shown until the URL can be read in the browser. */
export function PlayerStatsLoading() {
  return (
    <main className={styles.page}>
      <Heading coverage={null} />
      <LoadingBoard />
    </main>
  );
}

export function PlayerStatsView() {
  const t = useT();
  const query = parseQuery(useSearchParams());
  const url = query ? statsUrl(query) : null;
  const { data, failure, busy, retry } = usePlayerStats(url, t);

  // Next keeps useSearchParams in step with pushState, with no server round trip and no jump to
  // the top of the page.
  function go(next: PageQuery) {
    const href = pageHref(next);
    if (!query || href !== pageHref(query)) window.history.pushState(null, "", href);
  }

  return (
    <main className={styles.page}>
      <Heading coverage={query ? (data?.data_window ?? null) : null}>
        <label htmlFor="who" className={styles.lookupLabel}>{t.lookUpPlayer}</label>
        <PlayerSearch
          inputId="who"
          value={null}
          onChange={(candidate) => {
            if (candidate) go(query ? withPlayer(query, candidate.player_id) : queryForPlayer(candidate.player_id));
          }}
          placeholder={t.searchForPlayer}
          tone="player"
          showMedal={false}
          changeLabel={t.changePlayer}
        />
      </Heading>

      {!query && <NoPlayerYet />}
      {query && failure && <FailurePanel failure={failure} busy={busy} onRetry={retry} />}
      {query && !failure && !data && <LoadingBoard />}
      {query && !failure && data && (
        <div className={styles.stats} aria-busy={busy}>
          <PlayerBoard data={data} onClear={() => go(withoutFilters(query))} />
          <SurfaceRecord data={data} query={query} onPick={(tile) => go(withSurface(query, tile))} />
          <div className={`${styles.sec} ${styles.columns}`}>
            <ServeReturn key={url} data={data} />
            <div className={styles.sideCol}>
              <SeasonBoard data={data} query={query} onPick={(season) => go(withSeason(query, season))} />
              <AgainstBox
                data={data}
                against={query.against}
                onChoose={(playerId) => go(withAgainst(query, playerId))}
                onClear={() => go(withAgainst(query, null))}
              />
            </div>
          </div>
          <RecentMatches form={data.recent_form} />
        </div>
      )}
    </main>
  );
}
