// The chat history the API accepts (api/chat.py): plain text turns that alternate from the user
// and end with the user, at most 21 messages, 4,000 characters each and 30,000 in all.

import type { ChatMessage } from "./types.ts";

export const MAX_PAIRS = 8; // context (2) + 8 pairs (16) + the question = 19 messages
export const MAX_CHARS = 3_900;
export const MAX_TOTAL = 29_000;

export type Turn = {
  role: "user" | "assistant";
  content: string;
  /** True only for an answer that finished normally; a stopped or failed answer is shown but
   * never sent back to the model as if it were complete. */
  complete: boolean;
};

/** The report context, then the last complete question-and-answer pairs, then the question,
 * trimmed to the API's limits. */
export function buildHistory(context: ChatMessage[], turns: Turn[], question: string): ChatMessage[] {
  const pairs: ChatMessage[][] = [];
  for (let i = 0; i + 1 < turns.length; i += 1) {
    const [user, assistant] = [turns[i], turns[i + 1]];
    if (user.role === "user" && assistant.role === "assistant" && assistant.complete && assistant.content.trim()) {
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
