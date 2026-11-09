// Server-sent events from POST /chat and POST /report/stream. EventSource only does GET, so
// the stream is read with fetch and parsed here. Chunks can split an event anywhere, so the
// parser buffers.

import type { ChatEvent } from "./types.ts";

export class SseParser<E extends { event: string; data: unknown } = ChatEvent> {
  private buffer = "";

  /** Add a chunk of text; returns the events it completed. */
  feed(chunk: string): E[] {
    // Normalize CRLF and bare CR line endings; a CR at the end may be half of a CRLF split
    // across chunks, so it waits for the next chunk.
    this.buffer += chunk;
    const holdCr = this.buffer.endsWith("\r");
    const text = (holdCr ? this.buffer.slice(0, -1) : this.buffer).replace(/\r\n?/g, "\n");
    this.buffer = holdCr ? `${text}\r` : text;
    const events: E[] = [];
    let end: number;
    while ((end = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      const event = parseBlock<E>(block);
      if (event) events.push(event);
    }
    return events;
  }

  /** Call when the stream ends: a CR held back in case an LF followed is a line ending after all. */
  finish(): E[] {
    if (this.buffer.endsWith("\r")) this.buffer = `${this.buffer.slice(0, -1)}\n`;
    return this.feed("");
  }

  /** True if the stream ended partway through an event. */
  get incomplete(): boolean {
    return this.buffer.trim().length > 0;
  }
}

function parseBlock<E>(block: string): E | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!data.length) return null;
  try {
    return { event: name, data: JSON.parse(data.join("\n")) } as E;
  } catch {
    return { event: "error", data: { kind: "bad_stream", message: "The server sent a message the page couldn't read." } } as E;
  }
}
