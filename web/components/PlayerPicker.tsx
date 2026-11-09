"use client";

// Autocomplete over GET /players/search (no model call). It never picks a player by itself:
// the coach chooses from the list, which shows enough to tell namesakes apart.

import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { ApiFailure, searchPlayers } from "@/lib/api.ts";
import type { Candidate, PlayerRef } from "@/lib/types.ts";

type Props = {
  side: "player" | "opponent";
  label: string;
  placeholder: string;
  value: PlayerRef | null;
  onChange: (player: PlayerRef | null) => void;
};

type Lookup =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "done"; candidates: Candidate[]; more: boolean }
  | { state: "error"; message: string };

export function PlayerPicker({ side, label, placeholder, value, onChange }: Props) {
  const [text, setText] = useState(value?.name ?? "");
  const [open, setOpen] = useState(false);
  const [lookup, setLookup] = useState<Lookup>({ state: "idle" });
  const [active, setActive] = useState(0);
  const listId = useId();
  const box = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (value) setText(value.name); // a choice made elsewhere; typing clears value but keeps the text
  }, [value]);

  useEffect(() => {
    const query = text.trim();
    if (!open || query.length < 2 || query === value?.name) {
      setLookup({ state: "idle" });
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLookup({ state: "loading" });
      try {
        const result = await searchPlayers(query, controller.signal);
        setLookup({ state: "done", candidates: result.candidates, more: result.more_candidates });
        setActive(0);
      } catch (error) {
        if (controller.signal.aborted) return;
        setLookup({ state: "error", message: error instanceof ApiFailure ? error.message : "The player search failed." });
      }
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, open, value]);

  useEffect(() => {
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const candidates = lookup.state === "done" ? lookup.candidates : [];

  function choose(candidate: Candidate) {
    onChange({ player_id: candidate.player_id, name: candidate.name });
    setText(candidate.name);
    setOpen(false);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true); // reopens the list after Escape
      else if (candidates.length) setActive((i) => Math.min(i + 1, candidates.length - 1));
    } else if (event.key === "ArrowUp" && candidates.length) {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && open && candidates[active]) {
      event.preventDefault();
      choose(candidates[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && lookup.state !== "idle";
  return (
    <span className="picker" data-side={side} ref={box}>
      <label className="visually-hidden" htmlFor={`${listId}-input`}>
        {label}
      </label>
      <input
        id={`${listId}-input`}
        role="combobox"
        aria-expanded={showList && candidates.length > 0}
        aria-controls={showList && candidates.length > 0 ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={showList && candidates[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        value={text}
        style={{ width: `${Math.max(text.length, placeholder.length) + 1.5}ch` }}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      <span className="visually-hidden" role="status">{statusText(lookup, text)}</span>
      {showList && lookup.state !== "done" && (
        <div className={`picker-list picker-note${lookup.state === "error" ? " error-text" : ""}`} aria-hidden="true">
          {lookup.state === "error" ? lookup.message : "Searching…"}
        </div>
      )}
      {showList && lookup.state === "done" && !candidates.length && (
        <div className="picker-list picker-note" aria-hidden="true">
          No ATP player in the data matches “{text.trim()}”. Check the spelling, or try the last name.
        </div>
      )}
      {showList && candidates.length > 0 && (
        <ul className="picker-list" id={listId} role="listbox" aria-label={`${label} matches`}>
          {candidates.map((c, i) => (
            <li
              key={c.player_id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(event) => {
                event.preventDefault();
                choose(c);
              }}
            >
              <div className="who">{c.name}</div>
              <div className="meta">
                {[c.country, c.hand === "L" ? "left-handed" : c.hand === "R" ? "right-handed" : null,
                  `${c.matches_loaded} matches`, c.last_tourney_date ? `last played ${c.last_tourney_date.slice(0, 7)}` : null]
                  .filter(Boolean)
                  .join(", ")}
              </div>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}

/** What a screen reader hears as the search runs: the state, and how many players match. */
function statusText(lookup: Lookup, text: string): string {
  if (lookup.state === "loading") return "Searching";
  if (lookup.state === "error") return lookup.message;
  if (lookup.state !== "done") return "";
  if (!lookup.candidates.length) return `No player matches ${text.trim()}`;
  const n = lookup.candidates.length;
  return `${n} ${n === 1 ? "player matches" : "players match"}${lookup.more ? ", and more: type more of the name" : ""}. Use the arrow keys to choose.`;
}
