"use client";

// Autocomplete over GET /players/search (no model call). It never picks a player by itself:
// the coach chooses from the list, which shows enough to tell namesakes apart.

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { ApiFailure, searchPlayers } from "@/lib/api.ts";
import { handName, longDate } from "@/lib/people.ts";
import type { Candidate } from "@/lib/types.ts";
import { Flag } from "./Flag.tsx";
import { Medal } from "./Medal.tsx";
import styles from "./PlayerSearch.module.css";

export type PlayerSearchProps = {
  inputId: string;
  describedBy?: string;
  value: Candidate | null;
  onChange: (candidate: Candidate | null) => void;
  placeholder: string;
  /** Hides this player from the results, so one player can't be picked twice. */
  excludeId?: number;
  tone: "player" | "opponent";
  showMedal?: boolean;
  changeLabel: string;
};

type Lookup =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "done"; candidates: Candidate[]; more: boolean }
  | { state: "error"; message: string };

export function PlayerSearch({ inputId, describedBy, value, onChange, placeholder, excludeId, tone, showMedal = true, changeLabel }: PlayerSearchProps) {
  // What's being typed. While a player is chosen the input shows their name instead.
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [lookup, setLookup] = useState<Lookup>({ state: "idle" });
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = `${inputId}-list`;
  const picked = value !== null;

  useEffect(() => {
    const query = text.trim();
    if (!open || picked || query.length < 2) {
      setLookup({ state: "idle" });
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLookup({ state: "loading" });
      try {
        const result = await searchPlayers(query, controller.signal);
        if (controller.signal.aborted) return;
        setLookup({ state: "done", candidates: result.candidates, more: result.more_candidates });
        setActive(0);
      } catch (error) {
        if (controller.signal.aborted) return;
        setLookup({ state: "error", message: error instanceof ApiFailure ? error.message : "The player search failed. Try again." });
      }
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, open, picked]);

  const found = lookup.state === "done" ? lookup.candidates : [];
  const candidates = found.filter((c) => c.player_id !== excludeId);
  const current = Math.min(active, candidates.length - 1); // the list shrinks if excludeId changes while it is open

  function choose(candidate: Candidate) {
    onChange(candidate);
    setText("");
    setOpen(false);
  }

  function change() {
    setText("");
    onChange(null);
    input.current?.focus();
  }

  function move(index: number) {
    setActive(index);
    document.getElementById(`${listId}-${index}`)?.scrollIntoView({ block: "nearest" });
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true); // reopens the list after Escape
      else if (candidates.length) move(Math.min(current + 1, candidates.length - 1));
    } else if (event.key === "ArrowUp" && candidates.length) {
      event.preventDefault();
      move(Math.max(current - 1, 0));
    } else if (event.key === "Enter" && open && candidates[current]) {
      event.preventDefault();
      choose(candidates[current]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && lookup.state !== "idle";
  const listOpen = showList && candidates.length > 0;
  const rootClass = [styles.root, showMedal && styles.withMedal, picked && styles.picked].filter(Boolean).join(" ");
  const emptyNote = found.length > 0
    ? "That player is already chosen. Pick someone else."
    : `No ATP player in the data matches “${text.trim()}”. Check the spelling, or try the last name.`;

  return (
    <div className={rootClass}>
      <div className={styles.row}>
        {showMedal && (value
          ? <Medal name={value.name} country={value.country} tone={tone} size="setup" />
          : <span className={styles.medalEmpty} aria-hidden="true" />)}
        <input
          ref={input}
          id={inputId}
          className={`line-input ${styles.input}`}
          type="text"
          role="combobox"
          aria-expanded={listOpen}
          aria-controls={listOpen ? listId : undefined}
          aria-autocomplete="list"
          aria-activedescendant={listOpen ? `${listId}-${current}` : undefined}
          aria-describedby={describedBy}
          autoComplete="off"
          spellCheck={false}
          placeholder={placeholder}
          value={value ? value.name : text}
          onChange={(event) => {
            setText(event.target.value);
            setOpen(true);
            if (value) onChange(null);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
        {value && (
          <button type="button" className={styles.change} aria-label={changeLabel} onClick={change}>
            Change
          </button>
        )}
      </div>
      <span className="vh" role="status">{statusText(lookup, candidates.length, found.length, text)}</span>
      {showList && lookup.state === "loading" && (
        <div className={`${styles.results} ${styles.note}`} aria-hidden="true">Searching…</div>
      )}
      {showList && lookup.state === "error" && (
        <div className={`${styles.results} ${styles.note} ${styles.failed}`} aria-hidden="true">{lookup.message}</div>
      )}
      {showList && lookup.state === "done" && !candidates.length && (
        <div className={`${styles.results} ${styles.note}`} aria-hidden="true">{emptyNote}</div>
      )}
      {listOpen && (
        <ul className={styles.results} id={listId} role="listbox" aria-label="Matching players">
          {candidates.map((c, i) => (
            <li key={c.player_id} role="presentation">
              <button
                type="button"
                id={`${listId}-${i}`}
                className={styles.result}
                role="option"
                aria-selected={i === current}
                tabIndex={-1}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(event) => event.preventDefault()} // keeps focus in the input, or its blur would close the list first
                onClick={() => choose(c)}
              >
                <span className={styles.flag}><Flag country={c.country} /></span>
                <span className={styles.who}>
                  <span className={styles.name}>{c.name}</span>
                  <span className={styles.meta}>{describe(c)}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function describe(c: Candidate): string {
  return [
    c.country,
    handName(c.hand),
    `${c.matches_loaded} ${c.matches_loaded === 1 ? "match" : "matches"}`,
    c.last_tourney_date ? `last played ${longDate(c.last_tourney_date)}` : null,
  ].filter(Boolean).join(", ");
}

/** What a screen reader hears as the search runs: the state, and how many players match. */
function statusText(lookup: Lookup, shown: number, found: number, text: string): string {
  if (lookup.state === "loading") return "Searching";
  if (lookup.state === "error") return lookup.message;
  if (lookup.state !== "done") return "";
  if (!shown) return found ? "That player is already chosen" : `No player matches ${text.trim()}`;
  return `${shown} ${shown === 1 ? "player matches" : "players match"}${lookup.more ? ", and more: type more of the name" : ""}. Use the arrow keys to choose.`;
}
