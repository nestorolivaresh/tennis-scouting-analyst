"use client";

// A chat answer, laid out by answerBlocks (lib/numbers.ts): **bold** and "- " bullet lists only,
// as React elements (never as HTML), everything else as plain text. Numbers the API's check
// didn't find in the data are underlined (D-031); cited numbers open their source below the
// paragraph or list item they're in (D-032).

import { Fragment, useId, useState } from "react";
import { type Run, answerBlocks } from "@/lib/numbers.ts";
import type { Citation, Evidence, NumberSpan } from "@/lib/types.ts";
import { Marked } from "./Marked.tsx";
import { CitedSource } from "./SourceCard.tsx";

type Props = { text: string; notFound?: readonly NumberSpan[]; cites?: readonly Citation[]; evidence?: Evidence[] };

export function ChatAnswer({ text, notFound = [], cites = [], evidence = [] }: Props) {
  const [open, setOpen] = useState<number | null>(null);
  const cardId = useId();
  const toggle = (i: number) => setOpen(open === i ? null : i);
  const cite = open === null ? undefined : cites[open];
  // The open source shows below the paragraph or list item that holds its number.
  const holds = (runs: Run[]) => cite !== undefined && runs.some((r) => cite.start >= r.at && r.at + r.text.length >= cite.end);
  const card = (runs: Run[]) =>
    cite && holds(runs)
      ? <CitedSource cite={cite} evidence={evidence} id={cardId} />
      : null;
  const line = (runs: Run[]) =>
    runs.map((run, i) => {
      const marked = <Marked text={run.text} at={run.at} spans={notFound} cites={cites} open={open} cardId={cardId} onCite={toggle} />;
      return run.bold ? <strong key={i}>{marked}</strong> : <Fragment key={i}>{marked}</Fragment>;
    });
  return answerBlocks(text).map((block, i) =>
    block.kind === "p"
      ? <Fragment key={i}><p>{line(block.runs)}</p>{card(block.runs)}</Fragment>
      : <ul key={i}>{block.items.map((runs, j) => <li key={j}>{line(runs)}{card(runs)}</li>)}</ul>,
  );
}
