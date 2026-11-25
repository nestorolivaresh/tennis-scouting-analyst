"use client";

// Model text as React elements, never as HTML. Numbers the API's check didn't find in the data
// are underlined (D-031), with words for screen readers; numbers the model cited are buttons
// that open their source (D-032).

import { Fragment, type ReactNode } from "react";
import { useT } from "@/components/ui/LanguageProvider.tsx";
import { glued, pieces } from "@/lib/numbers.ts";
import type { Citation, NumberSpan } from "@/lib/types.ts";

type Props = {
  text: string;
  at?: number; // where `text` starts in the text that was checked
  spans: readonly NumberSpan[];
  cites?: readonly Citation[];
  open?: number | null; // the citation whose source is showing
  cardId?: string;
  onCite?: (index: number) => void;
};

export function Marked({ text, at = 0, spans, cites = [], open = null, cardId, onCite }: Props) {
  const t = useT();
  if (!spans.length && !cites.length) return <>{text}</>;
  return (
    <>
      {glued(pieces(text, at, spans, cites)).map((piece, i) => {
        let content: ReactNode = piece.text;
        if (piece.cite !== null && onCite) {
          const index = piece.cite;
          const shown = open === index;
          content = (
            <button type="button" className="cited" aria-expanded={shown} aria-controls={shown ? cardId : undefined} onClick={() => onCite(index)}>
              {piece.text}<span className="vh">{t.sourceOf}</span>
            </button>
          );
          if (piece.lead || piece.tail) content = <span className="nowrap">{piece.lead}{content}{piece.tail}</span>;
        } else if (piece.lead || piece.tail) {
          content = `${piece.lead}${piece.text}${piece.tail}`; // no button here, so nothing to keep together
        }
        return piece.marked
          ? <mark key={i} className="not-found">{content}<span className="vh">{t.notFoundMark}</span></mark>
          : <Fragment key={i}>{content}</Fragment>;
      })}
    </>
  );
}
