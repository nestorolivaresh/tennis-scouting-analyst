"use client";

// Follow-up questions over POST /chat (server-sent events). The API is stateless, so the
// conversation is sent each time as plain text (D-019). When a report is open, it goes first
// as context; the agent recomputes any number it uses with its tools (CHAT_RULES).

import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiFailure, streamChat } from "@/lib/api.ts";
import { TOOL_NAMES, describeFilters } from "@/lib/evidence.ts";
import { PlainMarkdown } from "./PlainMarkdown.tsx";
import type { ChatMessage } from "@/lib/types.ts";

// The API's limits (api/chat.py): 21 messages, 4,000 characters each, 30,000 in all.
const MAX_PAIRS = 8;
const MAX_CHARS = 3_900;
const MAX_TOTAL = 29_000;

type Activity = { id: string; label: string; ok: boolean | null };
type Turn = { role: "user" | "assistant"; content: string; activity: Activity[]; error?: string; done: boolean };

export function ChatPanel({ context }: { context: ChatMessage[] }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [turns]);

  useEffect(() => () => controller.current?.abort(), []);

  function update(fn: (last: Turn) => Turn) {
    setTurns((all) => [...all.slice(0, -1), fn(all[all.length - 1])]);
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    const history = buildHistory(context, turns, text);
    setQuestion("");
    setTurns((all) => [
      ...all,
      { role: "user", content: text, activity: [], done: true },
      { role: "assistant", content: "", activity: [], done: false },
    ]);
    setBusy(true);
    controller.current = new AbortController();
    try {
      await streamChat(history, (e) => {
        if (e.event === "tool_call") {
          update((t) => ({ ...t, activity: [...t.activity, { id: e.data.id, label: describeCall(e.data.tool, e.data.input), ok: null }] }));
        } else if (e.event === "tool_result") {
          update((t) => ({ ...t, activity: t.activity.map((a) => (a.id === e.data.id ? { ...a, ok: e.data.ok } : a)) }));
        } else if (e.event === "text") {
          update((t) => ({ ...t, content: t.content + e.data.delta }));
        } else if (e.event === "done") {
          update((t) => ({ ...t, done: true, error: e.data.outcome === "completed" ? undefined : (e.data.message ?? "The answer stopped early.") }));
        } else if (e.event === "error") {
          update((t) => ({ ...t, done: true, error: e.data.message }));
        }
      }, controller.current.signal);
    } catch (error) {
      if (!controller.current.signal.aborted) {
        update((t) => ({ ...t, done: true, error: error instanceof ApiFailure ? error.message : "The chat request failed." }));
      } else {
        update((t) => ({ ...t, done: true, error: "Stopped." }));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="chat" aria-label="Follow-up questions">
      <header>
        <h2 style={{ marginBottom: 0 }}>Ask a follow-up</h2>
        <p>
          {context.length
            ? "Questions about this matchup or anything else in the data. Every number is looked up again."
            : "Ask about any ATP player from 2015 on, for example “How did Alcaraz serve on clay in 2025?”"}
        </p>
      </header>
      <div className="chat-log" ref={log} aria-live="polite">
        {turns.map((turn, i) => (
          <div className="turn" data-role={turn.role} key={i}>
            {turn.activity.length > 0 && (
              <ul className="activity">
                {turn.activity.map((a) => (
                  <li key={a.id} data-ok={a.ok !== false}>
                    {a.ok === null ? "Looking up" : a.ok ? "Looked up" : "Couldn't look up"}: {a.label}
                  </li>
                ))}
              </ul>
            )}
            {turn.role === "assistant" ? <PlainMarkdown text={turn.content} /> : turn.content}
            {!turn.done && !turn.content && !turn.activity.length && <span className="hint">Thinking…</span>}
            {turn.error && <div className="error-text">{turn.error}</div>}
          </div>
        ))}
      </div>
      <form onSubmit={ask}>
        <label className="visually-hidden" htmlFor="chat-question">Your question</label>
        <input
          id="chat-question"
          value={question}
          maxLength={MAX_CHARS}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question"
          autoComplete="off"
        />
        {busy ? (
          <button type="button" className="secondary" onClick={() => controller.current?.abort()}>Stop</button>
        ) : (
          <button type="submit" className="primary" disabled={!question.trim()}>Ask</button>
        )}
      </form>
    </aside>
  );
}

/** Text-only history the API accepts: the report context, then the last complete question and
 * answer pairs, then the new question, trimmed to the API's limits. */
export function buildHistory(context: ChatMessage[], turns: Turn[], question: string): ChatMessage[] {
  const pairs: ChatMessage[][] = [];
  for (let i = 0; i + 1 < turns.length; i += 2) {
    const [user, assistant] = [turns[i], turns[i + 1]];
    if (user.role === "user" && assistant.role === "assistant" && assistant.done && assistant.content.trim()) {
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

function describeCall(tool: string, input: Record<string, unknown>): string {
  const name = TOOL_NAMES[tool] ?? tool;
  if (tool === "resolve_player" && typeof input.name === "string") return `${name} for “${input.name}”`;
  const filters = describeFilters(input.filters as Record<string, unknown> | undefined);
  return filters.length ? `${name} (${filters.join(", ")})` : name;
}
