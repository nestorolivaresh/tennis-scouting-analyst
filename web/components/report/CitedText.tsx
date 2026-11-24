"use client";

// One piece of the report's text with its marks and cited numbers; the source of a cited number
// opens just below it (D-031, D-032).

import { type ReactNode, useId, useState } from "react";
import type { Citation, Evidence, NumberSpan } from "@/lib/types.ts";
import { Marked } from "./Marked.tsx";
import { CitedSource } from "./SourceCard.tsx";

type Props = {
  as?: "p" | "h3" | "span";
  className?: string;
  text: string;
  at?: number;
  spans: readonly NumberSpan[];
  cites?: readonly Citation[];
  evidence?: Evidence[];
  before?: ReactNode;
  after?: ReactNode;
};

export function CitedText({ as: Tag = "p", className, text, at = 0, spans, cites = [], evidence = [], before, after }: Props) {
  const [open, setOpen] = useState<number | null>(null);
  const cardId = useId();
  const cite = open === null ? undefined : cites[open];
  return (
    <>
      <Tag className={className}>
        {before}
        <Marked text={text} at={at} spans={spans} cites={cites} open={open} cardId={cardId} onCite={(i) => setOpen(open === i ? null : i)} />
        {after}
      </Tag>
      {cite && <CitedSource cite={cite} evidence={evidence} id={cardId} />}
    </>
  );
}
