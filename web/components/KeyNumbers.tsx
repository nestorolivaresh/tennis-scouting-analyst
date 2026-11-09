"use client";

// The evidence view (spec): each key number, read from the tool result it cites, opens to show
// the tool call, its filters, the sample and what was left out. The value, sample and title
// all come from that result; the model's figure is shown only when it differs, as a warning.

import { useState } from "react";
import { TOOL_NAMES, checkStat, describeExcluded, describeStat, formatValue, sampleLine } from "@/lib/evidence.ts";
import type { Evidence, KeyStat } from "@/lib/types.ts";

export function KeyNumbers({ stats, evidence }: { stats: KeyStat[]; evidence: Evidence[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div className="numbers">
      {stats.map((stat, i) => {
        const check = checkStat(stat, evidence);
        const { title, filters } = describeStat(stat, check.evidence);
        const isOpen = open === i;
        const panelId = `evidence-${i}`;
        return (
          <div className="number-row" data-open={isOpen} data-status={check.status} key={i}>
            <button
              type="button"
              className="number-toggle"
              aria-expanded={isOpen}
              aria-controls={isOpen ? panelId : undefined}
              onClick={() => setOpen(isOpen ? null : i)}
            >
              <span>
                <span>{title}</span>
                {filters.length > 0 && <span className="number-filters">{filters.join("; ")}</span>}
                {check.status !== "matched" && (
                  <span className="number-warning">
                    {check.status === "missing"
                      ? "Not found in the data: this number can't be shown."
                      : `Didn't match the data: the report said ${stat.value}.`}
                  </span>
                )}
                <span className="number-source">{isOpen ? "Hide the source" : "Show where this comes from"}</span>
              </span>
              <span className="number-n">
                {check.sample !== null ? `${check.sample} ${check.sample === 1 ? "match" : "matches"}` : ""}
              </span>
              <span className="number-value">{check.value !== null ? formatValue(check.value, check.rate) : "Not available"}</span>
            </button>
            {isOpen && (
              <div className="evidence" id={panelId}>
                {check.evidence?.result ? (
                  <EvidenceDetails stat={stat} check={check} />
                ) : (
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

function EvidenceDetails({ stat, check }: { stat: KeyStat; check: ReturnType<typeof checkStat> }) {
  const source = check.evidence!;
  const result = source.result!;
  const excluded = describeExcluded(result.excluded);
  const { rate } = check;
  return (
    <dl>
      <dt>Tool</dt>
      <dd>{TOOL_NAMES[source.tool] ?? source.tool} (call {source.tool_call_id})</dd>
      <dt>Filters</dt>
      <dd>{describeStat(stat, source).filters.join("; ") || "None: every match in the data"}</dd>
      <dt>Sample</dt>
      <dd>{sampleLine(result.sample) ?? "Not reported"}</dd>
      <dt>Left out</dt>
      <dd>{excluded.length ? excluded.join(", ") : "Nothing"}</dd>
      <dt>Value</dt>
      <dd>
        <code>{stat.field}</code> = {check.value ?? "not found"}
        {rate && rate.unit === "fraction" && ` (${rate.numerator.toLocaleString("en-US")} of ${rate.denominator.toLocaleString("en-US")})`}
        {rate && rate.unit === "per_match" && ` (${rate.numerator.toLocaleString("en-US")} over ${rate.denominator.toLocaleString("en-US")} matches)`}
      </dd>
    </dl>
  );
}
