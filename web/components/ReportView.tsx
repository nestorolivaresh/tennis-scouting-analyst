"use client";

// The report screen (spec): summary, the opponent's strengths and weaknesses, the game plan,
// two charts, and the key numbers with their evidence. The status line says whether every
// key number passed the grounding check (D-018), and says so plainly when one didn't.

import { Charts } from "./Charts.tsx";
import { KeyNumbers } from "./KeyNumbers.tsx";
import { checkStat } from "@/lib/evidence.ts";
import type { ReportResponse } from "@/lib/types.ts";

export function ReportView({ data }: { data: ReportResponse }) {
  const { report, request, grounding, evidence, usage } = data;
  const { player, opponent, surface } = request;
  return (
    <article aria-labelledby="report-title">
      <h2 id="report-title" className="visually-hidden">
        Scouting report: {opponent.name}, for {player.name}, on {surface.toLowerCase()}
      </h2>
      <Status data={data} />
      {report && (
        <>
          <p className="prose summary">{report.summary}</p>

          <div className="matchup">
            <section>
              <h3 className="who-opponent">What {opponent.name} does well</h3>
              <ul className="prose">{report.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </section>
            <section>
              <h3 className="who-opponent">Where {opponent.name} is open</h3>
              <ul className="prose">{report.weaknesses.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </section>
          </div>

          <section className="section plan">
            <h3 className="who-player">Game plan for {player.name}</h3>
            <ul className="prose">{report.game_plan.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </section>

          <section className="section">
            <Charts evidence={evidence} player={player} opponent={opponent} surface={surface} window={request} />
          </section>

          <section className="section">
            <h2>Key numbers</h2>
            <p className="hint">Each number is read from the tool result it cites. Open one to see the tool, filters and sample behind it.</p>
            <KeyNumbers stats={report.key_stats} evidence={evidence} />
          </section>

          {report.data_caveats.length > 0 && (
            <section className="section caveats">
              <h3>About the data</h3>
              <ul>{report.data_caveats.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </section>
          )}
        </>
      )}
      <p className="hint">
        Request {data.request_id}. {usage.tool_calls} tool calls, {(usage.latency_ms / 1000).toFixed(1)} seconds
        {usage.cost_usd !== null ? `, about $${usage.cost_usd.toFixed(3)}` : ""}.{grounding.attempts > 1 ? " The report was corrected once after the check." : ""}
      </p>
    </article>
  );
}

function Status({ data }: { data: ReportResponse }) {
  if (data.status === "verified") {
    const n = data.report?.key_stats.length ?? 0;
    return (
      <div className="status" data-kind="verified" role="status">
        <strong>All {n} key numbers match the stats data.</strong> The written text around them isn't checked the same way.
      </div>
    );
  }
  if (data.status === "unverified") {
    return (
      <div className="status" data-kind="unverified" role="alert">
        <strong>
          {failing(data)} of {data.report?.key_stats.length ?? 0} key numbers didn't match the stats data. They're marked
          below, and the report's text may repeat them, so treat it with care.
        </strong>
        <ul>{data.grounding.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
      </div>
    );
  }
  return (
    <div className="status" data-kind="incomplete" role="alert">
      <strong>The report couldn't be finished.</strong> {data.message ?? ""} Try again, or ask about the matchup in the chat.
    </div>
  );
}

function failing(data: ReportResponse): number {
  return (data.report?.key_stats ?? []).filter((stat) => checkStat(stat, data.evidence).status !== "matched").length;
}
