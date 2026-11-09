// Calls to the FastAPI service, through this app's /api proxy (next.config.ts). Every failure
// becomes an ApiFailure with a message safe to show; nothing is turned into empty data.

import { SseParser } from "./sse.ts";
import type { ApiError, ChatEvent, ChatMessage, ReportEvent, ReportResponse, SearchResult, Surface } from "./types.ts";

export class ApiFailure extends Error {
  readonly kind: string;
  readonly status: number;
  constructor(kind: string, message: string, status: number) {
    super(message);
    this.kind = kind;
    this.status = status;
  }
}

async function failure(response: Response): Promise<ApiFailure> {
  try {
    const body = (await response.json()) as ApiError;
    if (body?.error?.message) return new ApiFailure(body.error.kind, body.error.message, response.status);
  } catch {
    // not JSON: the proxy couldn't reach the API, for example
  }
  if (response.status >= 500) {
    return new ApiFailure("api_unreachable", "The scouting service isn't responding. Check that the API is running.", response.status);
  }
  return new ApiFailure("http_error", `The request failed (HTTP ${response.status}).`, response.status);
}

export async function searchPlayers(q: string, signal?: AbortSignal): Promise<SearchResult> {
  const response = await fetch(`/api/players/search?q=${encodeURIComponent(q)}`, { signal });
  if (!response.ok) throw await failure(response);
  return response.json();
}

/** Stream a chat answer; calls onEvent for each server-sent event as it arrives. */
export async function streamChat(
  messages: ChatMessage[],
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!response.ok || !response.body) throw await failure(response);
  const parser = new SseParser();
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      for (const event of done ? parser.finish() : parser.feed(value)) onEvent(event);
      if (done) break;
    }
  } finally {
    reader.cancel().catch(() => {}); // releases the connection if we stopped early
  }
  if (parser.incomplete) {
    onEvent({ event: "error", data: { kind: "stream_cut", message: "The answer stopped partway. Try asking again." } });
  }
}

/** The report with progress: calls onEvent for each step, and resolves with the checked
 * report from the last event. Bad input fails before the stream opens, with the API's message. */
export async function streamReport(
  body: { player_id: number; opponent_id: number; surface: Surface },
  onEvent: (event: ReportEvent) => void,
  signal?: AbortSignal,
): Promise<ReportResponse> {
  const response = await fetch("/api/report/stream", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw await failure(response);
  const parser = new SseParser<ReportEvent>();
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let result: ReportResponse | null = null;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      for (const event of done ? parser.finish() : parser.feed(value)) {
        if (event.event === "report") result = event.data;
        else if (event.event === "error") throw new ApiFailure(event.data.kind, event.data.message, 200);
        else onEvent(event);
      }
      if (done) break;
    }
  } finally {
    reader.cancel().catch(() => {}); // releases the connection if we stopped early
  }
  if (!result) throw new ApiFailure("stream_cut", "The report stopped before it finished. Try again.", 200);
  return result;
}
