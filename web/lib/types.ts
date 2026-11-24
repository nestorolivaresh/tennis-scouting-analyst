// The API's response shapes (docs/decisions.md D-019), as the frontend uses them.

export type Surface = "Hard" | "Clay" | "Grass";
export const SURFACES: Surface[] = ["Hard", "Clay", "Grass"];

export interface PlayerRef {
  player_id: number;
  name: string;
}

export interface Candidate extends PlayerRef {
  country: string | null;
  hand: string | null;
  matches_loaded: number;
  last_tourney_date: string | null;
}

export interface SearchResult {
  query: string;
  candidates: Candidate[];
  more_candidates: boolean;
}

/** A rate as the stats tools return it: always with the counts it was computed from. */
export interface Rate {
  value: number | null;
  numerator: number;
  denominator: number;
  unit: "fraction" | "per_match";
}

export interface Sample {
  matches_counted: number;
  matches_with_stats: number;
  opponent_retired_or_defaulted: number;
  player_retired_or_defaulted: number;
  first_tourney_date: string | null;
  last_tourney_date: string | null;
}

export interface ToolResult {
  tool: string;
  player?: PlayerRef;
  opponent?: PlayerRef;
  filters?: Record<string, unknown>;
  sample?: Sample;
  excluded?: Record<string, number>;
  [key: string]: unknown;
}

export interface Evidence {
  tool_call_id: string;
  tool: string;
  input: { player_id?: number; opponent_id?: number; filters?: Record<string, unknown>; [key: string]: unknown };
  result: ToolResult | null;
  error: string | null;
}

export interface KeyStat {
  label: string;
  value: number;
  tool_call_id: string;
  field: string;
  sample_matches: number;
}

export interface Report {
  summary: string;
  strengths: string[];
  weaknesses: string[];
  game_plan: string[];
  key_stats: KeyStat[];
  data_caveats: string[];
}

/** A number, or a pair such as "10 of 14", in model text that no tool result of the request
 * states (D-031). `start` and `end` are character positions in the text that was checked. */
export interface NumberSpan {
  text: string;
  start: number;
  end: number;
}

/** A number the model cited and the API wrote in (D-032): where it is in the text, and the
 * tool call and field it is, as a key stat names them. */
export interface Citation {
  text: string; // the number as written in, so a position that doesn't line up is dropped
  start: number;
  end: number;
  tool_call_id: string;
  field: string;
}

/** The same in a report, with the text field it's in ("summary", "game_plan.2"). */
export interface ReportCitation extends Citation {
  text_field: string;
}

/** The check on the numbers in a chat answer: how many it read, and the ones not found. */
export interface NumberCheck {
  checked: number;
  not_found: NumberSpan[];
}

/** The same for a report's written text; each span names its field ("summary", "game_plan.2"). */
export interface ReportNumberCheck {
  checked: number;
  not_found: (NumberSpan & { field: string })[];
}

export interface ReportResponse {
  request_id: string;
  status: "verified" | "unverified" | "incomplete";
  message: string | null;
  report: Report | null;
  grounding: { passed: boolean; attempts: number; errors: string[] };
  /** null for an unfinished report or when the check itself failed; absent from a report
   * written before the check existed. */
  numbers?: ReportNumberCheck | null;
  /** Absent from a report written before citations existed. */
  citations?: ReportCitation[];
  request: { player: PlayerRef; opponent: PlayerRef; surface: Surface; date_from: string; date_to: string };
  evidence: Evidence[];
  usage: { cost_usd: number | null; latency_ms: number; tool_calls: number; model: string };
}

export interface ApiError {
  error: { kind: string; message: string };
  request_id?: string;
}

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type ChatEvent =
  | { event: "start"; data: { request_id: string } }
  | { event: "tool_call"; data: { id: string; tool: string; input: Record<string, unknown> } }
  | { event: "tool_result"; data: { id: string; tool: string; ok: boolean; error: string | null } }
  | { event: "text"; data: { delta: string } }
  | {
      event: "done";
      data: { outcome: string; message: string | null; numbers?: NumberCheck | null; citations?: Citation[]; evidence?: Evidence[] };
    }
  | { event: "error"; data: { kind: string; message: string } };

/** Events from POST /report/stream (D-019). The report itself arrives only in the last event,
 * after its numbers have been checked. */
export type ReportEvent =
  | { event: "start"; data: { request_id: string; request: ReportResponse["request"] } }
  | { event: "model_call"; data: { call: number; tool_calls_so_far: number } }
  | { event: "tool_call"; data: { id: string; tool: string; input: Record<string, unknown> } }
  | { event: "tool_result"; data: { id: string; tool: string; ok: boolean; error: string | null } }
  | { event: "checking"; data: { attempt: number; key_stats: number } }
  | { event: "correcting"; data: { errors: number } }
  | { event: "report"; data: ReportResponse }
  | { event: "error"; data: { kind: string; message: string } };
