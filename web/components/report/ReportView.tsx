"use client";

// The report screen. Everything numeric comes from the run's tool results (lib/evidence.ts); the
// model's prose is shown as prose. The status line says whether every key number passed the
// grounding check (D-018), and says so plainly when one didn't.

import { useMemo } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { checkStat, checkedPercents, hasCareerHeadToHead } from "@/lib/evidence.ts";
import { contextLabel, reportContext } from "@/lib/chat.ts";
import { serverText } from "@/lib/i18n.ts";
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

export function ReportView({ data, countries, onNewReport }: ReportViewProps) {
  const t = useT();
  const { report, request, evidence } = data;
  const { player, opponent, surface } = request;
  const context = useMemo(() => reportContext(data), [data]);
  const checked = useMemo(() => checkedPercents(data), [data]);
  const sections = [
    { href: "#plan", label: t.sectionPlan },
    { href: "#notes", label: t.sectionNotes },
    { href: "#side", label: t.sectionSide },
    { href: "#honours", label: t.sectionHonours },
    { href: "#numbers", label: t.sectionNumbers },
  ];
  const links = [...(report ? sections : []), { href: "#chat", label: t.askFollowUp }];
  return (
    <div className={styles.root}>
      <nav aria-label={t.onThisPage} className={styles.pageNav}>
        {links.map((link) => (
          <a key={link.href} className={styles.navLink} href={link.href}>{link.label}</a>
        ))}
      </nav>

      <main className={styles.main}>
        <Scoreboard data={data} countries={countries} />

        <div className={styles.statusRow}>
          <Status data={data} />
          <button type="button" className={styles.textButton} onClick={onNewReport}>{t.writeAnother}</button>
        </div>

        {report && (
          <>
            <GamePlan items={report.game_plan} player={player} opponent={opponent} checked={checked} />
            <ScoutingNotes summary={report.summary} strengths={report.strengths} weaknesses={report.weaknesses} player={player} opponent={opponent} checked={checked} />
            <SideBySide evidence={evidence} player={player} opponent={opponent} surface={surface} window={request} />
            <HonoursBoard evidence={evidence} player={player} opponent={opponent} />

            <section id="numbers" className={styles.sec}>
              <h2 className="h2">{t.keyNumbersTitle}</h2>
              <div className={`courtline ${styles.lineWide}`} aria-hidden="true" />
              <p className={styles.numbersIntro}>
                {t.numbersIntro(longDate(request.date_from, t), longDate(request.date_to, t), hasCareerHeadToHead(evidence, player, opponent))}
              </p>
              <KeyNumbers stats={report.key_stats} evidence={evidence} />
            </section>

            {report.data_caveats.length > 0 && (
              <section className={styles.sec}>
                <h2 className="h2">{t.aboutData}</h2>
                <div className={`courtline ${styles.lineWide}`} aria-hidden="true" />
                <ul className={styles.caveats}>
                  {report.data_caveats.map((caveat, i) => <li key={i}>{caveat}</li>)}
                </ul>
              </section>
            )}

            <div className={styles.closing}>
              <button type="button" className="btn" onClick={onNewReport}>{t.writeAnother}</button>
            </div>
          </>
        )}

        <RunLine data={data} />

        <ReportChat context={context} contextLabel={report ? contextLabel(data, t) : null} surface={surface} />
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
  const t = useT();
  const total = data.report?.key_stats.length ?? 0;
  if (data.status === "verified") {
    return (
      <div className={styles.status} role="status">
        <Seal kind="verified" />
        <p className={styles.statusText}>
          <strong>{t.allKeyNumbersMatch(total)}</strong> {t.textNotChecked}
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
            <strong>{t.keyNumbersFailed(failing, total)}</strong>
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
        <strong>{t.reportNotFinished}</strong> {data.message === null ? "" : serverText(data.message, t)} {t.reportNotFinishedHelp}
      </p>
    </div>
  );
}

function RunLine({ data }: { data: ReportResponse }) {
  const t = useT();
  const { usage, grounding } = data;
  const cost = usage.cost_usd === null ? null : t.dec(usage.cost_usd.toFixed(3));
  return (
    <p className={styles.runLine}>
      {t.runLine(data.request_id, usage.tool_calls, t.dec((usage.latency_ms / 1000).toFixed(1)), cost, grounding.attempts > 1)}
    </p>
  );
}
