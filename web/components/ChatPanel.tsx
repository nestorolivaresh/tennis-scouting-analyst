"use client";

// Follow-up questions over POST /chat (server-sent events). The API is stateless, so the
// conversation is sent each time as plain text (D-019). When a report is open, it goes first
// as context. A new report doesn't clear the conversation: a note marks the change, and later
// questions get the new report as context.

import { type FormEvent, useEffect, useRef, useState } from "react";
import { ApiFailure, streamChat } from "@/lib/api.ts";
import { MAX_CHARS, type Turn as HistoryTurn, buildHistory } from "@/lib/chat.ts";
import { TOOL_NAMES, describeFilters } from "@/lib/evidence.ts";
import type { ChatMessage } from "@/lib/types.ts";
import { PlainMarkdown } from "./PlainMarkdown.tsx";

type Activity = { id: string; label: string; ok: boolean | null };
type Turn = HistoryTurn & { activity: Activity[]; error?: string; done: boolean };
type Entry = { kind: "turn"; turn: Turn } | { kind: "note"; text: string };

export function ChatPanel({ context, contextLabel }: { context: ChatMessage[]; contextLabel: string | null }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const shownLabel = useRef<string | null>(null);

  useEffect(() => {
    if (contextLabel && contextLabel !== shownLabel.current) {
      if (shownLabel.current !== null || entries.length) setEntries((all) => [...all, { kind: "note", text: `Now discussing: ${contextLabel}` }]);
      shownLabel.current = contextLabel;
    }
  }, [contextLabel, entries.length]);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [entries]);

  useEffect(() => () => controller.current?.abort(), []);

  function updateLast(fn: (last: Turn) => Turn) {
    setEntries((all) => {
      const i = all.length - 1;
      const last = all[i];
      return last?.kind === "turn" ? [...all.slice(0, i), { kind: "turn", turn: fn(last.turn) }] : all;
    });
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    const turns = entries.flatMap((e) => (e.kind === "turn" ? [e.turn] : []));
    const history = buildHistory(context, turns, text);
    setQuestion("");
    setEntries((all) => [
      ...all,
      { kind: "turn", turn: { role: "user", content: text, complete: true, activity: [], done: true } },
      { kind: "turn", turn: { role: "assistant", content: "", complete: false, activity: [], done: false } },
    ]);
    setBusy(true);
    controller.current = new AbortController();
    try {
      await streamChat(history, (e) => {
        if (e.event === "tool_call") {
          updateLast((t) => ({ ...t, activity: [...t.activity, { id: e.data.id, label: describeCall(e.data.tool, e.data.input), ok: null }] }));
        } else if (e.event === "tool_result") {
          updateLast((t) => ({ ...t, activity: t.activity.map((a) => (a.id === e.data.id ? { ...a, ok: e.data.ok } : a)) }));
        } else if (e.event === "text") {
          updateLast((t) => ({ ...t, content: t.content + e.data.delta }));
        } else if (e.event === "done") {
          const completed = e.data.outcome === "completed";
          updateLast((t) => ({ ...t, done: true, complete: completed, error: completed ? undefined : (e.data.message ?? "The answer stopped early.") }));
        } else if (e.event === "error") {
          updateLast((t) => ({ ...t, done: true, complete: false, error: e.data.message }));
        }
      }, controller.current.signal);
    } catch (error) {
      const message = controller.current.signal.aborted ? "Stopped." : error instanceof ApiFailure ? error.message : "The chat request failed.";
      updateLast((t) => ({ ...t, done: true, complete: false, error: message }));
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
            ? "Ask about this matchup or anything else in the data. Answers use the stats tools, but their numbers aren't checked the way the report's key numbers are."
            : "Ask about any ATP player from 2015 on, for example “How did Alcaraz serve on clay in 2025?” Answers use the stats tools, but their numbers aren't checked the way a report's key numbers are."}
        </p>
      </header>
      <div className="chat-log" ref={log} aria-live="polite" aria-busy={busy}>
        {entries.map((entry, i) =>
          entry.kind === "note" ? (
            <p className="chat-note" key={i}>{entry.text}</p>
          ) : (
            <div className="turn" data-role={entry.turn.role} key={i}>
              {entry.turn.activity.length > 0 && (
                <ul className="activity">
                  {entry.turn.activity.map((a) => (
                    <li key={a.id} data-ok={a.ok !== false}>
                      {a.ok === null ? "Looking up" : a.ok ? "Looked up" : "Couldn't look up"}: {a.label}
                    </li>
                  ))}
                </ul>
              )}
              {entry.turn.role === "assistant" ? <PlainMarkdown text={entry.turn.content} /> : entry.turn.content}
              {!entry.turn.done && !entry.turn.content && !entry.turn.activity.length && <span className="hint">Thinking…</span>}
              {entry.turn.error && <div className="error-text">{entry.turn.error}</div>}
            </div>
          ),
        )}
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

function describeCall(tool: string, input: Record<string, unknown>): string {
  const name = TOOL_NAMES[tool] ?? tool;
  if (tool === "resolve_player" && typeof input.name === "string") return `${name} for “${input.name}”`;
  const filters = describeFilters(input.filters as Record<string, unknown> | undefined);
  return filters.length ? `${name} (${filters.join(", ")})` : name;
}
