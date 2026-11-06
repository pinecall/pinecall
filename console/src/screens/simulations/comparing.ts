/** Start a comparison — a persona or more against the agent under several voices and models, placed together — and read its table. */

import { post, read, type Credentials } from "@pinecall/core/api";
import { type AgentValues, type Comparison, type ComparisonRow, ComparisonSchema, type ComparisonStarted, ComparisonStartedSchema } from "@pinecall/core/wire/rest-evals";

import type { Wanted } from "./simulating";

export type { AgentValues, Comparison, ComparisonRow, ComparisonStarted };

/** What a comparison is started with: one simulation's wants, more callers beside its persona, and the agent's values for each call (runtime evals/schemas.py ComparisonRequest). */
export interface Compared extends Omit<Wanted, "against"> {
  against: AgentValues[];
  /** More callers, each against every configuration as `persona` is: one call per pair. */
  more_personas?: string[];
}

/** The gateway holds an org to this many calls in one comparison, callers times configurations. */
export const COMPARED_AT_MOST = 10;

/**
 * POST /v1/simulations/compare answers at once with the comparison's id, the calls placed and what
 * was refused; the calls go on in the gateway and the table is read as they end.
 */
export async function startComparison(credentials: Credentials, wanted: Compared): Promise<ComparisonStarted> {
  return ComparisonStartedSchema.parse(await post(credentials, "/v1/simulations/compare", wanted));
}

/** GET /v1/simulations/compare/{id}: caller by caller, each one's rows best first — every judge held, then the fastest, then the cheapest. */
export async function readComparison(credentials: Credentials, comparison: string): Promise<Comparison> {
  return ComparisonSchema.parse(await read(credentials, `/v1/simulations/compare/${encodeURIComponent(comparison)}`));
}

/** A configuration in a few words: `thinks groq/openai/gpt-oss-120b · speaks deepgram`; the agent's own when nothing is named. */
export function said(values: AgentValues): string {
  const parts: [string, string | number | undefined][] = [
    ["hears", values.stt],
    ["thinks", values.llm],
    ["speaks", values.tts],
    ["voice", values.voice],
    ["language", values.language],
    ["temperature", values.temperature],
    ["end of turn", values.end_of_turn],
  ];
  const named = parts.flatMap(([name, value]) => (value === undefined ? [] : [`${name} ${String(value)}`]));
  return named.length === 0 ? "the agent's own settings" : named.join(" · ");
}

/** Only what a row names: an empty word is the agent's own, and is left out. */
export function trimmed(values: AgentValues): AgentValues {
  const kept: AgentValues = {};
  if (values.stt) kept.stt = values.stt;
  if (values.llm) kept.llm = values.llm;
  if (values.tts) kept.tts = values.tts;
  if (values.voice) kept.voice = values.voice;
  if (values.language) kept.language = values.language;
  if (values.temperature !== undefined) kept.temperature = values.temperature;
  if (values.end_of_turn) kept.end_of_turn = values.end_of_turn;
  return kept;
}
