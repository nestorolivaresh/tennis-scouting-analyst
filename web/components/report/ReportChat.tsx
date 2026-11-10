"use client";

// Follow-up questions over POST /chat (server-sent events). The API is stateless, so the
// conversation is sent each time as plain text (D-019), with the report first as context.
// Above phone width the chat is a section of the page; at phone width the design's bottom bar
// opens it as a sheet. The conversation lives here, above both, so rotating a phone mid-answer
// neither loses it nor stops the stream.

import { type FormEvent, type RefObject, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { ApiFailure, streamChat } from "@/lib/api.ts";
import { CUT_OFF_MESSAGE, type LiveTurn, MAX_CHARS, applyChatEvent, buildHistory, closeTurn, finishedAnnouncement } from "@/lib/chat.ts";
import type { ChatMessage, Surface } from "@/lib/types.ts";
import { ChatAnswer } from "./ChatAnswer.tsx";
import styles from "./ReportChat.module.css";

type Entry = { kind: "turn"; turn: LiveTurn } | { kind: "note"; text: string };

const PHONE = "(max-width: 520px)";

function subscribeToWidth(onChange: () => void) {
  const query = window.matchMedia(PHONE);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function useChat(context: ChatMessage[], contextLabel: string | null) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const sending = useRef(false); // state lags a double press, and each send costs money
  const shownLabel = useRef<string | null>(null);

  useEffect(() => {
    if (contextLabel && contextLabel !== shownLabel.current) {
      if (shownLabel.current !== null || entries.length) setEntries((all) => [...all, { kind: "note", text: `Now discussing: ${contextLabel}` }]);
      shownLabel.current = contextLabel;
    }
  }, [contextLabel, entries.length]);

  useEffect(() => () => controller.current?.abort(), []);

  function updateAnswer(change: (turn: LiveTurn) => LiveTurn) {
    setEntries((all) => {
      let i = all.length - 1;
      while (i >= 0 && all[i].kind !== "turn") i -= 1;
      const entry = all[i];
      if (entry?.kind !== "turn") return all;
      return [...all.slice(0, i), { kind: "turn", turn: change(entry.turn) }, ...all.slice(i + 1)];
    });
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || sending.current) return;
    sending.current = true;
    const turns = entries.flatMap((e) => (e.kind === "turn" ? [e.turn] : []));
    const history = buildHistory(context, turns, text);
    setQuestion("");
    setEntries((all) => [
      ...all,
      { kind: "turn", turn: { role: "user", content: text, complete: true, activity: [], done: true } },
      { kind: "turn", turn: { role: "assistant", content: "", complete: false, activity: [], done: false } },
    ]);
    setBusy(true);
    const abort = new AbortController();
    controller.current = abort;
    try {
      await streamChat(history, (e) => updateAnswer((turn) => applyChatEvent(turn, e)), abort.signal);
      updateAnswer((turn) => closeTurn(turn, CUT_OFF_MESSAGE)); // a stream that ended without saying how
    } catch (error) {
      const message = abort.signal.aborted ? "Stopped." : error instanceof ApiFailure ? error.message : "The chat request failed.";
      updateAnswer((turn) => closeTurn(turn, message));
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  return { entries, question, setQuestion, busy, ask, stop: () => controller.current?.abort() };
}

type Chat = ReturnType<typeof useChat>;

/** Keeps the newest text in view while it streams, until the reader scrolls up to read. */
function useFollow(scroller: RefObject<HTMLDivElement | null>, entries: Entry[]) {
  const following = useRef(true);
  const count = useRef(0);
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (entries.length !== count.current) following.current = true;
    count.current = entries.length;
    if (following.current) el.scrollTop = el.scrollHeight;
  }, [entries, scroller]);
  return () => {
    const el = scroller.current;
    if (el) following.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };
}

function Chips({ chat, chips }: { chat: Chat; chips: string[] }) {
  if (!chips.length) return null;
  return (
    <div className={styles.chips}>
      {chips.map((chip) => {
        const on = chat.question === chip;
        return (
          // Only fills the box: a send is always the person's own action, because each one costs money.
          <button key={chip} type="button" className={`${styles.chip}${on ? ` ${styles.chipOn}` : ""}`} aria-pressed={on} onClick={() => chat.setQuestion(on ? "" : chip)}>
            {chip}
          </button>
        );
      })}
    </div>
  );
}

function Conversation({ chat }: { chat: Chat }) {
  const lastAnswer = [...chat.entries].reverse().find((e) => e.kind === "turn" && e.turn.role === "assistant");
  return (
    <>
      {chat.entries.map((entry, i) => {
        if (entry.kind === "note") return <p className={styles.note} key={i}>{entry.text}</p>;
        const { turn } = entry;
        if (turn.role === "user") return <p className={styles.asked} key={i}>{turn.content}</p>;
        return (
          <div className={styles.answer} key={i}>
            {turn.activity.length > 0 && (
              <ul className={styles.activity}>
                {turn.activity.map((a) => (
                  <li key={a.id} data-ok={a.ok !== false}>
                    {a.ok === null ? "Looking up" : a.ok ? "Looked up" : "Couldn't look up"}: {a.label}
                  </li>
                ))}
              </ul>
            )}
            <ChatAnswer text={turn.content} />
            {!turn.done && !turn.content && !turn.activity.length && <p className={styles.thinking}>Thinking…</p>}
            {turn.error && <p className={styles.error}>{turn.error}</p>}
          </div>
        );
      })}
      {/* The text above streams in pieces, so only this is live: each answer is heard once, when it has finished. */}
      <div className="vh" role="status">{finishedAnnouncement(lastAnswer?.kind === "turn" ? lastAnswer.turn : undefined)}</div>
    </>
  );
}

function QuestionForm({ chat }: { chat: Chat }) {
  const inputId = useId();
  return (
    <form className={styles.form} onSubmit={chat.ask}>
      <div className={styles.field}>
        <label htmlFor={inputId} className={styles.label}>Your question</label>
        <input id={inputId} className="line-input" type="text" value={chat.question} maxLength={MAX_CHARS} autoComplete="off" onChange={(e) => chat.setQuestion(e.target.value)} placeholder="How did Alcaraz serve on clay in 2025?" />
      </div>
      {chat.busy
        ? <button type="button" className="btn" onClick={chat.stop}>Stop</button>
        : <button type="submit" className="btn" disabled={!chat.question.trim()}>Ask</button>}
    </form>
  );
}

function InlineChat({ chat, chips }: { chat: Chat; chips: string[] }) {
  const log = useRef<HTMLDivElement>(null);
  const onScroll = useFollow(log, chat.entries);
  return (
    <section id="chat" aria-labelledby="chat-title" className={styles.section}>
      <h2 id="chat-title" className="h2">Ask a follow-up</h2>
      <div className={`courtline ${styles.line}`} aria-hidden="true" />
      <div className={styles.two}>
        <div>
          <p className={styles.intro}>
            Ask about any ATP player from 2015 on, for example “How did Alcaraz serve on clay in 2025?” Answers use the stats tools, but their numbers aren&apos;t checked the way a report&apos;s key numbers are.
          </p>
          <Chips chat={chat} chips={chips} />
        </div>
        <div>
          <div ref={log} className={chat.entries.length ? styles.log : undefined} onScroll={onScroll} tabIndex={chat.entries.length ? 0 : undefined} role={chat.entries.length ? "group" : undefined} aria-label={chat.entries.length ? "Conversation" : undefined}>
            <Conversation chat={chat} />
          </div>
          <QuestionForm chat={chat} />
        </div>
      </div>
    </section>
  );
}

function PhoneChat({ chat, chips }: { chat: Chat; chips: string[] }) {
  const [open, setOpen] = useState(false);
  const sheet = useRef<HTMLDialogElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const onScroll = useFollow(scroller, chat.entries);

  useEffect(() => {
    const dialog = sheet.current;
    if (!open || !dialog) return;
    // A modal dialog holds focus inside it, closes on Escape and hands focus back to the bar.
    dialog.showModal();
    title.current?.focus();
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;

    const page = document.documentElement;
    const overflow = page.style.overflow;
    page.style.overflow = "hidden";

    // A phone keyboard shrinks only the visual viewport, so the sheet has to move above it itself.
    const viewport = window.visualViewport;
    const fit = () => {
      if (!viewport) return;
      dialog.style.setProperty("--keyboard", `${Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)}px`);
      dialog.style.setProperty("--sheet-max", `${Math.round(viewport.height * 0.9)}px`);
    };
    fit();
    viewport?.addEventListener("resize", fit);
    viewport?.addEventListener("scroll", fit);
    return () => {
      viewport?.removeEventListener("resize", fit);
      viewport?.removeEventListener("scroll", fit);
      page.style.overflow = overflow;
      if (dialog.open) dialog.close();
    };
  }, [open]);

  return (
    <>
      <div className={`on-green ${styles.bar}`}>
        <button type="button" className={styles.barButton} aria-expanded={open} aria-controls="chat-sheet" onClick={() => setOpen(true)}>
          <svg width="22" height="22" viewBox="0 0 44 44" aria-hidden="true" fill="none">
            <circle cx="22" cy="22" r="20.5" fill="#D9DD3C" stroke="#17231E" strokeWidth="2" />
            <path d="M8 8c9 8 9 20 0 28" stroke="#17231E" strokeWidth="2" />
            <path d="M36 8c-9 8-9 20 0 28" stroke="#17231E" strokeWidth="2" />
          </svg>
          Ask a follow-up
        </button>
      </div>
      <dialog
        ref={sheet}
        id="chat-sheet"
        aria-labelledby="chat-title"
        className={styles.sheet}
        onClose={() => setOpen(false)}
        onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
      >
        <div className={styles.sheetInner}>
          <div className={styles.sheetHead}>
            <h2 id="chat-title" ref={title} tabIndex={-1} className={styles.sheetTitle}>Ask a follow-up</h2>
            <button type="button" className={styles.close} onClick={() => setOpen(false)}>Close</button>
          </div>
          <div ref={scroller} className={styles.sheetScroll} onScroll={onScroll}>
            <p className={styles.sheetIntro}>Answers use the stats tools, but their numbers aren&apos;t checked the way a report&apos;s key numbers are.</p>
            <Chips chat={chat} chips={chips} />
            {chat.entries.length > 0 && <div className={styles.sheetLog}><Conversation chat={chat} /></div>}
          </div>
          <QuestionForm chat={chat} />
        </div>
      </dialog>
    </>
  );
}

type Props = { context: ChatMessage[]; contextLabel: string | null; surface: Surface };

export function ReportChat({ context, contextLabel, surface }: Props) {
  const chat = useChat(context, contextLabel);
  const isPhone = useSyncExternalStore(subscribeToWidth, () => window.matchMedia(PHONE).matches, () => false);
  const word = surface.toLowerCase();
  // These speak of "each player", which means nothing to the model without the report as context.
  const chips = context.length
    ? [`How does each player serve on ${word}?`, "Who is better on break points?", `How have their ${word} meetings gone?`]
    : [];
  return isPhone ? <PhoneChat chat={chat} chips={chips} /> : <InlineChat chat={chat} chips={chips} />;
}
