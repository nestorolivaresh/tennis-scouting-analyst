"use client";

// The evidence view (spec): each key number opens to show the tool call behind it, its
// filters, the sample size and what was left out. The number itself is the one the grounding
// check matched against that tool result (D-018).

import { useState } from "react";
import {
  TOOL_NAMES, describeExcluded, describeFilters, findEvidence, formatStat, rateFor, sampleLine,
} from "@/lib/evidence.ts";
import type { Evidence, KeyStat } from "@/lib/types.ts";

export function KeyNumbers({ stats, evidence }: { stats: KeyStat[]; evidence: Evidence[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="numbers">
      {stats.map((stat, i) => {
        const source = findEvidence(evidence, stat.tool_call_id);
        const rate = rateFor(stat, source);
        const isOpen = open === i;
        const panelId = `evidence-${i}`;
        return (
          <div className="number-row" data-open={isOpen} key={`${stat.tool_call_id}-${stat.field}`}>
            <button
              type="button"
              className="number-toggle"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => setOpen(isOpen ? null : i)}
            >
              <span>
                <span>{stat.label}</span>
                <br />
                <span className="number-source">{isOpen ? "Hide the source" : "Show where this comes from"}</span>
              </span>
              <span className="number-n">{stat.sample_matches} {stat.sample_matches === 1 ? "match" : "matches"}</span>
              <span className="number-value">{formatStat(stat, rate)}</span>
            </button>
            {isOpen && (
              <div className="evidence" id={panelId}>
                {source ? <EvidenceDetails stat={stat} source={source} rate={rate} /> : (
                  <p className="error-text">Tool call {stat.tool_call_id} isn't in this report's results.</p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function EvidenceDetails({ stat, source, rate }: { stat: KeyStat; source: Evidence; rate: ReturnType<typeof rateFor> }) {
  const result = source.result;
  const filters = describeFilters(source.input.filters);
  const excluded = describeExcluded(result?.excluded);
  const who = [result?.player?.name, result?.opponent?.name].filter(Boolean).join(" against ");
  return (
    <dl>
      <dt>Tool</dt>
      <dd>
        {TOOL_NAMES[source.tool] ?? source.tool}
        {who ? ` for ${who}` : ""} (call {source.tool_call_id})
      </dd>
      <dt>Filters</dt>
      <dd>{filters.length ? filters.join("; ") : "None: every match in the data"}</dd>
      <dt>Sample</dt>
      <dd>{sampleLine(result?.sample) ?? "Not reported"}</dd>
      <dt>Left out</dt>
      <dd>{excluded.length ? excluded.join(", ") : "Nothing"}</dd>
      <dt>Value</dt>
      <dd>
        <code>{stat.field}</code> = {stat.value}
        {rate && rate.unit === "fraction" && ` (${rate.numerator.toLocaleString("en-US")} of ${rate.denominator.toLocaleString("en-US")})`}
        {rate && rate.unit === "per_match" && ` (${rate.numerator.toLocaleString("en-US")} over ${rate.denominator.toLocaleString("en-US")} matches)`}
      </dd>
    </dl>
  );
}
