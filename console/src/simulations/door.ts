/** Simulations' doors: an agent's callers, the simulated calls already made, and the one that places a new one. */

import { z } from "zod";

import { post, read, type Credentials } from "@pinecall/core/api";
import { type AgentValues, type Hearing, type Comparison, type ComparisonRow, ComparisonSchema, type ComparisonStarted, ComparisonStartedSchema, type Persona, PersonaListSchema, type PersonaRun, type PersonaRunList, PersonaRunListSchema } from "@pinecall/core/wire/rest-evals";
import { readReport } from "../configure/door";
import { brandOf } from "../configure/vendors";

export type { AgentValues, Comparison, ComparisonRow, Hearing, Persona, PersonaRun };

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

/** The three stages a setup may change, and what a person calls each. */
export const STAGES = [
  { modality: "llm", name: "Thinks" },
  { modality: "stt", name: "Hears" },
  { modality: "tts", name: "Speaks" },
] as const;

export type Modality = (typeof STAGES)[number]["modality"];

/** One model a comparison may run a stage of the agent on, as a picker lists it. */
export interface Model {
  /** `vendor/model`, what the agent's setting takes. */
  value: string;
  name: string;
  vendor: string;
  /** Whether this org may run it: on its own key, or lent by the platform. */
  available: boolean;
  recommended: boolean;
}

/** What this box offers each stage of the agent, and what the agent runs on now. */
export interface Models {
  own: Record<Modality, string>;
  offered: Record<Modality, Model[]>;
}

export async function readModels(credentials: Credentials, agent: string): Promise<Models> {
  const report = await readReport(credentials, agent);
  const offered = (modality: Modality): Model[] =>
    report.providers
      .filter((one) => one.does.includes(modality))
      .flatMap((one) => (report.choices[`${modality}/${one.name}`] ?? []).map((choice) => ({ value: `${one.name}/${choice.model}`, name: choice.name, vendor: brandOf(one.name), available: choice.available, recommended: choice.recommended })));
  const own = (stage: { vendor: string; model: string | null }): string => (stage.model === null ? brandOf(stage.vendor) : stage.model);
  return { own: { llm: own(report.decides), stt: own(report.hears), tts: own(report.speaks) }, offered: { llm: offered("llm"), stt: offered("stt"), tts: offered("tts") } };
}

const LimitsSchema = z.object({ at_once: z.number(), on_the_line: z.number(), comparison_calls: z.number() });

/** How the org may shape its simulations here: the calls at once, and the calls one comparison places. */
export type Limits = z.infer<typeof LimitsSchema>;

/** The platform's own numbers, for a gateway from before an org had its own. */
export const USUAL_LIMITS: Limits = { at_once: 10, on_the_line: 0, comparison_calls: 10 };

export async function readLimits(credentials: Credentials): Promise<Limits> {
  return LimitsSchema.parse(await read(credentials, "/v1/simulations/limits"));
}

/** What a comparison is placed with: one simulation's wants, more callers beside the first, and the agent's values for each column. */
export interface Compared extends Wanted {
  more_personas: string[];
  against: AgentValues[];
  /** How many times each caller rings under each setup. */
  repeats: number;
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

const modelOf = (word: string): string => word.slice(word.indexOf("/") + 1);

/** A column's name: the model it thinks with, else what else it changes, or that it is the agent as it stands. */
export function setupName(against: AgentValues): string {
  if (against.llm !== undefined) return modelOf(against.llm);
  const named = [against.stt, against.tts].flatMap((word) => (word === undefined ? [] : [modelOf(word)]));
  return named.length === 0 ? "The agent as it is" : named.join(" · ");
}

/** What a column changes beside its name, in a line: `hears nova-3 · speaks sonic-2`; empty when nothing. */
export function setupUnder(against: AgentValues): string {
  const parts = [against.llm === undefined ? null : against.stt === undefined ? null : `hears ${modelOf(against.stt)}`, against.llm === undefined ? null : against.tts === undefined ? null : `speaks ${modelOf(against.tts)}`, against.voice === undefined ? null : `voice ${against.voice}`];
  return parts.filter((part) => part !== null).join(" · ");
}

/** The judge that holds a call to what its caller expected of the agent. */
export const THE_GOAL = "expected-outcome";

/** How one call of a comparison stands: still on, never begun, waiting for its judges, or its task done or failed. */
export type Cell = "live" | "unstarted" | "scoring" | "passed" | "failed" | "unjudged";

// The judges answer a few seconds after the hang-up; past this a call with no score has none coming.
const JUDGES_ANSWER_WITHIN_S = 90;

// A task is its caller's goal: done when the judge of what the caller expected held. A caller that
// expects nothing has no such judge, and its call is done when every judge that answered held.
export function cellOf(row: ComparisonRow, now: number = Date.now() / 1000): Cell {
  if (row.why !== null) return "unstarted";
  if (row.ended_at === null) return "live";
  if (row.score === null) return now - row.ended_at < JUDGES_ANSWER_WITHIN_S ? "scoring" : "unjudged";
  if (row.goal !== null) return row.goal === "held" ? "passed" : "failed";
  if (row.score.judged === 0) return "unjudged";
  return row.score.passed ? "passed" : "failed";
}

/** The judges beside the goal's that gave a verdict on the call: how well it was done, apart from whether it was. */
export function qualityOf(row: ComparisonRow): { held: number; judged: number } {
  const others = row.judges.filter((judge) => judge.name !== THE_GOAL && (judge.verdict === "held" || judge.verdict === "broken"));
  return { held: others.filter((judge) => judge.verdict === "held").length, judged: others.length };
}

/** How fast a call's agent answered, in seconds: end to end when spoken, to the model's first token when written. */
export function replyOf(row: ComparisonRow): number | null {
  return row.latency.e2e_latency ?? row.latency.llm_node_ttft;
}
