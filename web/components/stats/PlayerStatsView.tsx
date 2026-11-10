"use client";

// The Player stats page. Its state is the URL, so a view can be shared and Back works. Each URL
// is one API call; while the next one loads, the last numbers stay on screen, marked busy.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Board } from "@/components/ui/Board.tsx";
import { PlayerSearch } from "@/components/ui/PlayerSearch.tsx";
import { ApiFailure, fetchPlayerStats } from "@/lib/api.ts";
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

function describeFailure(error: unknown): Failure {
  if (error instanceof ApiFailure) return { message: error.message, badLink: isBadLink(error.status) };
  return { message: "The player stats couldn't be reached. Check your connection and try again.", badLink: false };
}

function usePlayerStats(url: string | null) {
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
        if (!controller.signal.aborted) setSettled((last) => ({ key, data: last?.data ?? null, failure: describeFailure(error) }));
      },
    );
    return () => controller.abort();
  }, [url, key]);

  return {
    data: settled?.data ?? null,
    failure: settled?.failure ?? null,
    busy: settled?.key !== key,
    retry: () => setAttempt((n) => n + 1),
  };
}

function Heading({ coverage, children }: { coverage: DataWindow | null; children?: ReactNode }) {
  return (
    <div className={styles.head}>
      <div className={styles.headText}>
        <h1 className={styles.title}>Player stats</h1>
        <p className={styles.lede}>{coverageLine(coverage)}</p>
      </div>
      <div className={styles.lookup}>{children}</div>
    </div>
  );
}

function LoadingBoard() {
  return (
    <Board aria-label="Player stats" aria-busy="true" className={styles.loadingBoard}>
      <p className={styles.loadingText} role="status">Loading player stats…</p>
    </Board>
  );
}

function FailurePanel({ failure, busy, onRetry }: { failure: Failure; busy: boolean; onRetry: () => void }) {
  return (
    <div className={styles.failure} role="alert" aria-busy={busy}>
      <h2 className="h2">{failure.badLink ? "This link can't be shown" : "The player stats didn't load"}</h2>
      <p className={styles.failureText}>{failure.badLink ? "It doesn't point to a player in the data. Try searching for the player instead." : failure.message}</p>
      {failure.badLink
        ? <Link className="btn" href="/players">Search for a player</Link>
        : <button type="button" className="btn" onClick={onRetry} disabled={busy}>{busy ? "Trying again…" : "Try again"}</button>}
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
  const query = parseQuery(useSearchParams());
  const url = query ? statsUrl(query) : null;
  const { data, failure, busy, retry } = usePlayerStats(url);

  // Next keeps useSearchParams in step with pushState, with no server round trip and no jump to
  // the top of the page.
  function go(next: PageQuery) {
    const href = pageHref(next);
    if (!query || href !== pageHref(query)) window.history.pushState(null, "", href);
  }

  return (
    <main className={styles.page}>
      <Heading coverage={query ? (data?.data_window ?? null) : null}>
        <label htmlFor="who" className={styles.lookupLabel}>Look up a player</label>
        <PlayerSearch
          inputId="who"
          value={null}
          onChange={(candidate) => {
            if (candidate) go(query ? withPlayer(query, candidate.player_id) : queryForPlayer(candidate.player_id));
          }}
          placeholder="Search for a player"
          tone="player"
          showMedal={false}
          changeLabel="Change player"
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
