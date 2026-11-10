"use client";

// The report screen. Everything numeric comes from the run's tool results (lib/evidence.ts); the
// model's prose is shown as prose. The status line says whether every key number passed the
// grounding check (D-018), and says so plainly when one didn't.

import { useMemo } from "react";
import { checkStat, checkedPercents, hasCareerHeadToHead } from "@/lib/evidence.ts";
import { contextLabel, reportContext } from "@/lib/chat.ts";
import { longDate } from "@/lib/people.ts";
import type { ReportResponse } from "@/lib/types.ts";
import { GamePlan } from "./GamePlan.tsx";
import { HonoursBoard } from "./HonoursBoard.tsx";
import { KeyNumbers } from "./KeyNumbers.tsx";
import { ReportChat } from "./ReportChat.tsx";
import { Scoreboard } from "./Scoreboard.tsx";
import { ScoutingNotes } from "./ScoutingNotes.tsx";
import { SideBySide } from "./SideBySide.tsx";
import styles from "./ReportView.module.css";

export type ReportViewProps = {
  data: ReportResponse;
  countries: Record<number, string | null>;
  onNewReport: () => void;
};

const SECTIONS = [
  { href: "#plan", label: "Game plan" },
  { href: "#notes", label: "Scouting notes" },
  { href: "#side", label: "Side by side" },
  { href: "#honours", label: "Honours board" },
  { href: "#numbers", label: "Key numbers" },
];

export function ReportView({ data, countries, onNewReport }: ReportViewProps) {
  const { report, request, evidence } = data;
  const { player, opponent, surface } = request;
  const context = useMemo(() => reportContext(data), [data]);
  const checked = useMemo(() => checkedPercents(data), [data]);
  const links = [...(report ? SECTIONS : []), { href: "#chat", label: "Ask a follow-up" }];
  return (
    <div className={styles.root}>
      <nav aria-label="On this page" className={styles.pageNav}>
        {links.map((link) => (
          <a key={link.href} className={styles.navLink} href={link.href}>{link.label}</a>
        ))}
      </nav>

      <main className={styles.main}>
        <Scoreboard data={data} countries={countries} />

        <div className={styles.statusRow}>
          <Status data={data} />
          <button type="button" className={styles.textButton} onClick={onNewReport}>Write another report</button>
        </div>

        {report && (
          <>
            <GamePlan items={report.game_plan} player={player} opponent={opponent} checked={checked} />
            <ScoutingNotes summary={report.summary} strengths={report.strengths} weaknesses={report.weaknesses} player={player} opponent={opponent} checked={checked} />
            <SideBySide evidence={evidence} player={player} opponent={opponent} surface={surface} window={request} />
            <HonoursBoard evidence={evidence} player={player} opponent={opponent} />

            <section id="numbers" className={styles.sec}>
              <h2 className="h2">Key numbers and where they come from</h2>
              <div className={`courtline ${styles.lineWide}`} aria-hidden="true" />
              <p className={styles.numbersIntro}>
                Win rate, serve and pressure figures cover tournaments starting {longDate(request.date_from)} to {longDate(request.date_to)}.
                {hasCareerHeadToHead(evidence, player, opponent) ? " Head-to-head covers every meeting in the data." : ""} Open a number to see its source.
              </p>
              <KeyNumbers stats={report.key_stats} evidence={evidence} />
            </section>

            {report.data_caveats.length > 0 && (
              <section className={styles.sec}>
                <h2 className="h2">About the data</h2>
                <div className={`courtline ${styles.lineWide}`} aria-hidden="true" />
                <ul className={styles.caveats}>
                  {report.data_caveats.map((caveat, i) => <li key={i}>{caveat}</li>)}
                </ul>
              </section>
            )}

            <div className={styles.closing}>
              <button type="button" className="btn" onClick={onNewReport}>Write another report</button>
            </div>
          </>
        )}

        <RunLine data={data} />

        <ReportChat context={context} contextLabel={report ? contextLabel(data) : null} surface={surface} />
      </main>
    </div>
  );
}

function Seal({ kind }: { kind: "verified" | "warning" }) {
  return (
    <svg className={styles.seal} viewBox="0 0 42 42" aria-hidden="true" fill="none">
      <circle className={styles.sealOuter} cx="21" cy="21" r="19.5" stroke="#7A5C24" />
      <circle className={styles.sealInner} cx="21" cy="21" r="15.5" stroke="#7A5C24" />
      {kind === "verified"
        ? <path className={styles.sealMark} d="M13.5 21.5l5.2 5.2 10-11" stroke="#12372B" />
        : <path className={styles.sealMark} d="M21 12.5v11M21 28v2.5" stroke="#B85A32" strokeLinecap="round" />}
    </svg>
  );
}

function Status({ data }: { data: ReportResponse }) {
  const total = data.report?.key_stats.length ?? 0;
  if (data.status === "verified") {
    return (
      <div className={styles.status} role="status">
        <Seal kind="verified" />
        <p className={styles.statusText}>
          <strong>All {total} key numbers match the stats data.</strong> The written text around them isn&apos;t checked the same way.
        </p>
      </div>
    );
  }
  if (data.status === "unverified") {
    const failing = (data.report?.key_stats ?? []).filter((stat) => checkStat(stat, data.evidence).status !== "matched").length;
    return (
      <div className={`${styles.status} ${styles.statusWarning}`} role="alert">
        <Seal kind="warning" />
        <div className={styles.statusBody}>
          <p className={styles.statusText}>
            <strong>
              {failing} of {total} key numbers didn&apos;t match the stats data. They&apos;re marked below, and the report&apos;s text may repeat them, so treat it with care.
            </strong>
          </p>
          <ul className={styles.statusErrors}>{data.grounding.errors.map((error, i) => <li key={i}>{error}</li>)}</ul>
        </div>
      </div>
    );
  }
  return (
    <div className={`${styles.status} ${styles.statusWarning}`} role="alert">
      <Seal kind="warning" />
      <p className={styles.statusText}>
        <strong>The report couldn&apos;t be finished.</strong> {data.message ?? ""} Try again, or ask about the matchup in the chat.
      </p>
    </div>
  );
}

function RunLine({ data }: { data: ReportResponse }) {
  const { usage, grounding } = data;
  return (
    <p className={styles.runLine}>
      Request {data.request_id}. {usage.tool_calls} tool calls, {(usage.latency_ms / 1000).toFixed(1)} seconds
      {usage.cost_usd !== null ? `, about $${usage.cost_usd.toFixed(3)}` : ""}.{grounding.attempts > 1 ? " The report was corrected once after the check." : ""}
    </p>
  );
}
