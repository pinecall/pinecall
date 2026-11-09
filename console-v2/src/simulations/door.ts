/** Simulations' doors: an agent's callers, the simulated calls already made, and the one that places a new one. */

import { z } from "zod";

import { post, read, type Credentials } from "@pinecall/core/api";
import { type AgentValues, type Comparison, type ComparisonRow, ComparisonSchema, type ComparisonStarted, ComparisonStartedSchema, type Persona, PersonaListSchema, type PersonaRun, type PersonaRunList, PersonaRunListSchema } from "@pinecall/core/wire/rest-evals";
import { readReport } from "../configure/door";
import { brandOf } from "../configure/vendors";

export type { AgentValues, Comparison, ComparisonRow, Persona, PersonaRun };

/** What plays behind a caller on a noisy line. */
export type Ambience = "television" | "cafe" | "office" | "street";

/** How a caller reaches the agent: typed, spoken on a clear line, or spoken with a room behind it. */
export type Line = "chat" | "call" | "noisy";

/** What a simulation is placed with (the runtime's SimulationRequest). */
export interface Wanted {
  agent: string;
  persona: string;
  voice: boolean;
  turns: number;
  /** Spoken alone: dB under the caller of what plays behind it, the whole call. */
  interferer_db?: number;
  /** Spoken alone: the share of the line's packets lost, 0 to 1. */
  packet_loss?: number;
  /** Spoken alone: what plays behind the caller; the persona's own when left out. */
  ambience?: Ambience;
}

const StartedSchema = z.strictObject({ call: z.string(), voice: z.boolean() });

/** Whether a caller is one of Pinecall's library: switched on or off, never written here. */
export const isPinecalls = (persona: Persona): boolean => persona.owner === "pinecall";

/** What a caller wants, in a line. */
export function aboutOf(persona: Persona): string {
  if (isPinecalls(persona)) return persona.summary ?? persona.goal;
  return persona.about !== "" ? persona.about : persona.goal;
}

/** The agent's own callers first, then Pinecall's switched on, then the rest; the red team last of each. */
export function inOrder(personas: readonly Persona[]): Persona[] {
  const rank = (one: Persona): number => (isPinecalls(one) ? (one.on ? 1 : 2) : 0) * 2 + Number(one.tags.includes("red-team"));
  return [...personas].sort((one, other) => rank(one) - rank(other) || one.name.localeCompare(other.name));
}

export async function readCallers(credentials: Credentials, agent: string): Promise<Persona[]> {
  return PersonaListSchema.parse(await read(credentials, `/v1/agents/${encodeURIComponent(agent)}/personas`)).personas;
}

/** One page of the simulated calls to the agents named, newest first; `before` is the page before's `next`. */
export async function readRuns(credentials: Credentials, agents: readonly string[], before?: string): Promise<PersonaRunList> {
  return PersonaRunListSchema.parse(await read(credentials, "/v1/simulations", { agent: [...agents], ...(before === undefined ? {} : { before }) }));
}

/** The gateway answers the call's id at once and plays the caller itself: the page watches it as any call. */
export async function startSimulation(credentials: Credentials, wanted: Wanted): Promise<string> {
  return StartedSchema.parse(await post(credentials, "/v1/simulations", wanted)).call;
}

/** How a run stands: on the line, held by every judge, broken by one, or ended with nobody judging it. */
export type Standing = "live" | "held" | "broke" | "unjudged";

export function standingOf(run: PersonaRun): Standing {
  if (run.ended_at === null) return "live";
  if (run.score === null || run.score.judged === 0) return "unjudged";
  return run.score.passed ? "held" : "broke";
}

// ── a comparison: the same callers against the agent on several models ──

/** The gateway places this many calls in one comparison at most: callers times models. */
export const COMPARED_AT_MOST = 10;

/** One model a comparison may run the agent on, as a picker lists it. */
export interface Model {
  /** `vendor/model`, what the agent's `llm` takes. */
  value: string;
  name: string;
  vendor: string;
  /** Whether this org may run it: on its own key, or lent by the platform. */
  available: boolean;
  recommended: boolean;
}

/** The models this box offers the agent, and the one it runs on now. */
export interface Models {
  own: string;
  offered: Model[];
}

export async function readModels(credentials: Credentials, agent: string): Promise<Models> {
  const report = await readReport(credentials, agent);
  const offered = report.providers
    .filter((one) => one.does.includes("llm"))
    .flatMap((one) => (report.choices[`llm/${one.name}`] ?? []).map((choice) => ({ value: `${one.name}/${choice.model}`, name: choice.name, vendor: brandOf(one.name), available: choice.available, recommended: choice.recommended })));
  const { vendor, model } = report.decides;
  return { own: model === null ? brandOf(vendor) : model, offered };
}

/** What a comparison is placed with: one simulation's wants, more callers beside the first, and the agent's values for each column. */
export interface Compared extends Wanted {
  more_personas: string[];
  against: AgentValues[];
}

/** Answered at once with the comparison's id; its calls go on in the gateway, and its board is read as they end. */
export async function startComparison(credentials: Credentials, wanted: Compared): Promise<ComparisonStarted> {
  return ComparisonStartedSchema.parse(await post(credentials, "/v1/simulations/compare", wanted));
}

export async function readComparison(credentials: Credentials, comparison: string): Promise<Comparison> {
  return ComparisonSchema.parse(await read(credentials, `/v1/simulations/compare/${encodeURIComponent(comparison)}`));
}

/** What tells one column of a comparison from another: the values it ran the agent on, as one word. */
export function setupKey(against: AgentValues): string {
  return JSON.stringify(Object.entries(against).sort(([one], [other]) => one.localeCompare(other)));
}

/** A column's name: the model it thinks with, or that it is the agent as it stands. */
export function setupName(against: AgentValues): string {
  if (against.llm !== undefined) return against.llm.slice(against.llm.indexOf("/") + 1);
  const named = Object.values(against).filter((value) => value !== undefined);
  return named.length === 0 ? "The agent as it is" : named.join(" · ");
}

/** How one call of a comparison stands: still on, never begun, waiting for its judges, or its task done or failed. */
export type Cell = "live" | "unstarted" | "scoring" | "passed" | "failed" | "unjudged";

// The judges answer a few seconds after the hang-up; past this a call with no score has none coming.
const JUDGES_ANSWER_WITHIN_S = 90;

export function cellOf(row: ComparisonRow, now: number = Date.now() / 1000): Cell {
  if (row.why !== null) return "unstarted";
  if (row.ended_at === null) return "live";
  if (row.score === null) return now - row.ended_at < JUDGES_ANSWER_WITHIN_S ? "scoring" : "unjudged";
  if (row.score.judged === 0) return "unjudged";
  return row.score.passed ? "passed" : "failed";
}

/** How fast a call's agent answered, in seconds: end to end when spoken, to the model's first token when written. */
export function replyOf(row: ComparisonRow): number | null {
  return row.latency.e2e_latency ?? row.latency.llm_node_ttft;
}
