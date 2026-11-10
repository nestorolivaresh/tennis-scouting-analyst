// The chat history the API accepts (api/chat.py): plain text turns that alternate from the user
// and end with the user, at most 21 messages, 4,000 characters each and 30,000 in all.

import { TOOL_NAMES, describeFilters } from "./evidence.ts";
import type { ChatEvent, ChatMessage, ReportResponse } from "./types.ts";

export const MAX_PAIRS = 8; // context (2) + 8 pairs (16) + the question = 19 messages
export const MAX_CHARS = 3_900;
export const MAX_TOTAL = 29_000;

export type Turn = {
  role: "user" | "assistant";
  content: string;
  /** True only for an answer that finished normally; a stopped or failed answer is shown but
   * never sent back to the model as if it were complete. */
  complete: boolean;
};

/** The report context, then the last complete question-and-answer pairs, then the question,
 * trimmed to the API's limits. */
export function buildHistory(context: ChatMessage[], turns: Turn[], question: string): ChatMessage[] {
  const pairs: ChatMessage[][] = [];
  for (let i = 0; i + 1 < turns.length; i += 1) {
    const [user, assistant] = [turns[i], turns[i + 1]];
    if (user.role === "user" && assistant.role === "assistant" && assistant.complete && assistant.content.trim()) {
      pairs.push([
        { role: "user", content: user.content.slice(0, MAX_CHARS) },
        { role: "assistant", content: assistant.content.slice(0, MAX_CHARS) },
      ]);
    }
  }
  let kept = pairs.slice(-MAX_PAIRS);
  const size = (messages: ChatMessage[]) => messages.reduce((n, m) => n + m.content.length, 0);
  while (kept.length && size([...context, ...kept.flat()]) + question.length > MAX_TOTAL) kept = kept.slice(1);
  return [...context, ...kept.flat(), { role: "user", content: question.slice(0, MAX_CHARS) }];
}

export function contextLabel(data: ReportResponse): string {
  const { player, opponent, surface } = data.request;
  return `${opponent.name} for ${player.name}, ${surface.toLowerCase()}`;
}

/** The report as a first exchange, so follow-up questions have context. */
export function reportContext(data: ReportResponse): ChatMessage[] {
  if (!data.report) return [];
  const { player, opponent, surface } = data.request;
  const r = data.report;
  const text = [
    r.summary,
    `${opponent.name}'s strengths: ${r.strengths.join(" ")}`,
    `${opponent.name}'s weaknesses: ${r.weaknesses.join(" ")}`,
    `Game plan for ${player.name}: ${r.game_plan.join(" ")}`,
  ].join("\n\n").slice(0, MAX_CHARS);
  return [
    { role: "user", content: `Write a scouting report on ${opponent.name} for ${player.name}, on ${surface.toLowerCase()}.` },
    { role: "assistant", content: text },
  ];
}

export type Activity = { id: string; label: string; ok: boolean | null };
export type LiveTurn = Turn & { activity: Activity[]; error?: string; done: boolean };

export const CUT_OFF_MESSAGE = "The answer stopped partway. Try asking again.";

function describeCall(tool: string, input: Record<string, unknown>): string {
  const name = TOOL_NAMES[tool] ?? tool;
  if (tool === "resolve_player" && typeof input.name === "string") return `${name} for “${input.name}”`;
  const filters = describeFilters(input.filters as Record<string, unknown> | undefined);
  return filters.length ? `${name} (${filters.join(", ")})` : name;
}

/** One stream event applied to the answer it belongs to. */
export function applyChatEvent(turn: LiveTurn, event: ChatEvent): LiveTurn {
  switch (event.event) {
    case "tool_call":
      return { ...turn, activity: [...turn.activity, { id: event.data.id, label: describeCall(event.data.tool, event.data.input), ok: null }] };
    case "tool_result":
      return { ...turn, activity: turn.activity.map((a) => (a.id === event.data.id ? { ...a, ok: event.data.ok } : a)) };
    case "text":
      return { ...turn, content: turn.content + event.data.delta };
    case "done": {
      const completed = event.data.outcome === "completed";
      return { ...turn, done: true, complete: completed, error: completed ? undefined : (event.data.message ?? "The answer stopped early.") };
    }
    case "error":
      return { ...turn, done: true, complete: false, error: event.data.message };
    default:
      return turn;
  }
}

/** Ends an answer that never got a final event. It stays on screen, marked, and is not sent back
 * to the model as if complete. An answer that already finished is left alone. */
export function closeTurn(turn: LiveTurn, message: string): LiveTurn {
  return turn.done ? turn : { ...turn, done: true, complete: false, error: message };
}

/** What a screen reader hears, once: the whole answer when it has finished, and nothing before. */
export function finishedAnnouncement(turn: LiveTurn | undefined): string {
  if (!turn?.done) return "";
  return [turn.content.trim(), turn.error].filter(Boolean).join(" ");
}
