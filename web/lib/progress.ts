// What the report is doing right now, from the events of POST /report/stream: each lookup as
// it happens, then writing, then checking the key numbers. Only real events become steps;
// nothing is estimated.

import { TOOL_NAMES } from "./evidence.ts";
import type { ReportEvent } from "./types.ts";

export type Step = { key: string; text: string; state: "active" | "done" | "failed" };

export function progressSteps(events: ReportEvent[], names: Map<number, string>): Step[] {
  const steps: Step[] = [];
  const results = new Map<string, boolean>();
  let corrected = false;
  for (const e of events) {
    if (e.event === "tool_result") results.set(e.data.id, e.data.ok);
  }
  events.forEach((e, i) => {
    if (e.event === "model_call") {
      // What this call did shows in what follows it: more lookups, or the report.
      const next = events[i + 1];
      const looksUpMore = next?.event === "tool_call";
      const text = e.data.call === 1 ? "Choosing which stats to look up"
        : looksUpMore ? "Choosing more stats to look up"
        : corrected ? "Rewriting the report with the corrections" : "Writing the report";
      steps.push({ key: `model-${e.data.call}`, text, state: "done" });
    } else if (e.event === "tool_call") {
      const ok = results.get(e.data.id);
      steps.push({
        key: e.data.id,
        text: describeLookup(e.data.tool, e.data.input, names) + (ok === false ? " (failed)" : ""),
        state: ok === false ? "failed" : ok === true ? "done" : "active",
      });
    } else if (e.event === "checking") {
      steps.push({ key: `check-${e.data.attempt}`, text: `Checking ${e.data.key_stats} key numbers against the data`, state: "done" });
    } else if (e.event === "correcting") {
      corrected = true;
      const n = e.data.errors;
      steps.push({ key: "correct", text: `${n} ${n === 1 ? "number didn't" : "numbers didn't"} match; asking for a corrected report`, state: "done" });
    }
  });
  // The newest step is the one in progress, unless it's a lookup that has already returned.
  const last = steps[steps.length - 1];
  if (last && !results.has(last.key)) last.state = "active";
  return steps;
}

function describeLookup(tool: string, input: Record<string, unknown>, names: Map<number, string>): string {
  const name = TOOL_NAMES[tool] ?? tool;
  const who = (id: unknown) => names.get(Number(id)) ?? `player ${id}`;
  const filters = (input.filters ?? {}) as Record<string, unknown>;
  if (tool === "head_to_head") return `${name}: ${who(input.player_id)} and ${who(input.opponent_id)}`;
  if (tool === "recent_form") return `${name}: ${who(input.player_id)}, last ${input.n ?? 5} matches`;
  if (tool === "resolve_player") return `${name}: “${String(input.name ?? "")}”`;
  const where = filters.surface ? `${String(filters.surface).toLowerCase()} courts` : tool === "surface_splits" ? "every surface" : "all surfaces";
  return `${name}: ${who(input.player_id)}, ${where}`;
}
