// What the report is doing right now, from the events of POST /report/stream: each lookup as
// it happens, then writing, then checking the key numbers. Only real events become steps;
// nothing is estimated.

import { EN, type T, surfaceWords } from "./i18n.ts";
import type { ReportEvent } from "./types.ts";

export type Step = { key: string; text: string; state: "active" | "done" | "failed" };

export function progressSteps(events: ReportEvent[], names: Map<number, string>, t: T = EN): Step[] {
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
      const text = e.data.call === 1 ? t.stepChoosing
        : looksUpMore ? t.stepChoosingMore
        : corrected ? t.stepRewriting : t.stepWriting;
      steps.push({ key: `model-${e.data.call}`, text, state: "done" });
    } else if (e.event === "tool_call") {
      const ok = results.get(e.data.id);
      steps.push({
        key: e.data.id,
        text: describeLookup(e.data.tool, e.data.input, names, t) + (ok === false ? t.stepFailed : ""),
        state: ok === false ? "failed" : ok === true ? "done" : "active",
      });
    } else if (e.event === "checking") {
      steps.push({ key: `check-${e.data.attempt}`, text: t.stepChecking(e.data.key_stats), state: "done" });
    } else if (e.event === "correcting") {
      corrected = true;
      const n = e.data.errors;
      steps.push({ key: "correct", text: t.stepCorrecting(n), state: "done" });
    }
  });
  // The newest step is the one in progress, unless it's a lookup that has already returned.
  const last = steps[steps.length - 1];
  if (last && !results.has(last.key)) last.state = "active";
  return steps;
}

function describeLookup(tool: string, input: Record<string, unknown>, names: Map<number, string>, t: T): string {
  const name = (Object.hasOwn(t.tools, tool) ? t.tools[tool] : undefined) ?? tool;
  const who = (id: unknown) => names.get(Number(id)) ?? t.playerNumber(String(id));
  const filters = (input.filters ?? {}) as Record<string, unknown>;
  if (tool === "head_to_head") return t.lookupPair(name, who(input.player_id), who(input.opponent_id));
  if (tool === "recent_form") return t.lookupRecent(name, who(input.player_id), String(input.n ?? 5));
  if (tool === "resolve_player") return t.lookupName(name, String(input.name ?? ""));
  const where = filters.surface ? surfaceWords(t, String(filters.surface)).courts : tool === "surface_splits" ? t.everySurface : t.allSurfaces;
  return t.lookupWhere(name, who(input.player_id), where);
}
