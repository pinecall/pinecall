/** The evals endpoints: a suite run and the runs kept, the simulated caller's next line, a spoken call, a call replayed by code. */

import type { ModelConfig } from "@pinecall/agents/wire";

import type { Behavior } from "./cases.js";

import { seg, type GatewayClient } from "./client.js";

export type { CallScore, ModelConfig } from "@pinecall/agents/wire";

/** One judge's verdict on one golden. */
export interface Score {
  metric: string;
  score: number;
  passed: boolean;
  /** The judge's reasoning: seqs for a code policy, model output otherwise. */
  reason: string;
  /** The question judged, as LiveKit attaches it to each judgment. */
  criteria: string;
  /** Model calls this judgment made; zero for a code policy. */
  judge_calls: number;
}

/** One LLM request as the provider received it. */
export interface AskedRequest {
  /** One string per static system block; empty when the vendor puts system text in `messages`. */
  system: string[];
  tools: Record<string, unknown>[];
  messages: Record<string, unknown>[];
}

/** `call.summary` as written to the log. */
export interface Summary {
  duration_s: number;
  turns: number;
  cost?: { usd: number };
}

/** One matrix cell: a golden under a model, its scores and call summary. */
export interface Cell {
  model: string;
  golden: string;
  scores: Score[];
  summary: Summary | null;
  /** The call's LLM requests, on failing cells only (the prompt is not in the log); null on spoken runs. */
  asked?: AskedRequest[] | null;
}

/** Scores of every golden under every model. */
export interface Matrix {
  models: string[];
  goldens: string[];
  metrics: string[];
  /** Total model calls made by judges across the matrix. */
  judge_calls: number;
  runs: Cell[];
  failures: { model: string; golden: string; metric: string }[];
}

/** The call a golden opened under one model. */
export interface OpenedCall {
  golden: string;
  model: string;
  call: string;
}

/** One stored suite run. */
export interface EvalRun {
  id: string;
  agent: string;
  started_at: number;
  finished_at: number | null;
  status: "running" | "done" | "failed";
  calls: OpenedCall[];
  matrix: Matrix | null;
  error: string | null;
}

/** What a run plays beside its goldens — the org's cases — and the version of the settings it plays on. */
export interface Played {
  cases?: string[];
  dataset?: boolean;
  version?: number;
}

/** Ring 2 fields of a spoken run; a written run sends none of them. */
export interface SpokenLine {
  voice?: boolean;
  interferer_db?: number;
  packet_loss?: number;
  ambience?: string;
}

/** Body of `POST /v1/evals/run`. */
export interface RunRequest extends Played, SpokenLine {
  agent: string;
  goldens: unknown[];
  models?: ModelConfig[];
  app?: string;
}

/** A simulated caller as the gateway plays it. */
export interface CallerPersona {
  name: string;
  goal: string;
  style: string;
  facts?: Record<string, unknown>;
  llm?: string;
  tts?: string;
  voice?: string;
  expects?: string[];
  behavior?: Behavior;
}

/** One turn of a simulated call. */
export interface Spoken {
  who: "agent" | "caller";
  said: string;
}

/** The simulated caller's next line and whether it hangs up. */
export interface NextLine {
  say: string;
  hangup: boolean;
}

/** Body of `POST /v1/evals/voice`: a spoken call the runtime places and holds. */
export interface VoiceCallRequest {
  call: string;
  agent: string;
  persona: CallerPersona;
  turns: number;
  interferer_db?: number;
  packet_loss?: number;
  ambience?: string;
  /** Seconds of silence before each of the caller's lines, over the persona's own; 0 answers at once. */
  pause_s?: number;
  state?: Record<string, unknown>;
}

/** What a spoken call came to. */
export interface VoiceCalled {
  call: string;
  turns: number;
  line: string;
}

/** One check's result of a replay. */
export interface Verdict {
  check: string;
  status: string;
  detail: string;
}

/** `POST /v1/evals/replay/{call}`: the code checks over one finished call. */
export interface Replayed {
  call: string;
  agent: string;
  passed: boolean;
  verdicts: Verdict[];
}

/** Replay policy: banned phrases and latency budgets. */
export interface ReplayPolicy {
  banned?: string[];
  budget?: Record<string, number>;
}

/** The suite run, answered when every golden was played and judged; one per agent at a time (409). */
export function startRun(gw: GatewayClient, body: RunRequest): Promise<EvalRun> {
  return gw.post<EvalRun>("/v1/evals/run", body);
}

/** Recent runs, newest first, optionally for one agent. */
export async function listRuns(gw: GatewayClient, limit: number, agent?: string): Promise<EvalRun[]> {
  return (await gw.get<{ runs: EvalRun[] }>("/v1/evals/runs", { limit, agent })).runs;
}

/** One run with its calls and, once finished, its matrix. */
export function getRun(gw: GatewayClient, id: string): Promise<EvalRun> {
  return gw.get<EvalRun>(`/v1/evals/runs/${seg(id)}`);
}

/** The simulated caller's next line, asked of the runtime, which holds the provider keys. */
/** `POST /v1/agents/{slug}/personas/{name}/brief`: the persona as a simulation plays it — Pinecall's briefed on this agent, the agent's own as written. */
export function briefPersona(gw: GatewayClient, agent: string, name: string): Promise<CallerPersona> {
  return gw.post<CallerPersona>(`/v1/agents/${seg(agent)}/personas/${seg(name)}/brief`, {});
}

export function nextCallerLine(gw: GatewayClient, body: { persona: CallerPersona; heard: Spoken[]; turns_left: number }): Promise<NextLine> {
  return gw.post<NextLine>("/v1/evals/caller", body);
}

/** A spoken call the runtime places, holds and hangs up; answers when it is over. */
export function startVoiceCall(gw: GatewayClient, body: VoiceCallRequest): Promise<VoiceCalled> {
  return gw.post<VoiceCalled>("/v1/evals/voice", body);
}

/** One finished call rebuilt from its log and answered by the runtime's code checks. */
export function replayCall(gw: GatewayClient, call: string, policy: ReplayPolicy): Promise<Replayed> {
  return gw.post<Replayed>(`/v1/evals/replay/${seg(call)}`, policy);
}

/**
 * The voice and models a run puts the agent on over its settings, as a test room asks them: each
 * stage as `vendor/model`, a voice of the voice vendor's, a language, a temperature; nothing named
 * is the agent's own. The sandbox's alone, with a key that edits the pipeline.
 */
export interface AgentValues {
  stt?: string | undefined;
  llm?: string | undefined;
  tts?: string | undefined;
  voice?: string | undefined;
  language?: string | undefined;
  temperature?: number | undefined;
  end_of_turn?: "stt" | "livekit" | "smart-turn" | undefined;
}

/** `POST /v1/simulations`: a persona put on the agent, the gateway playing the caller; written or spoken. */
export interface SimulationRequest {
  agent: string;
  persona: string;
  voice: boolean;
  turns: number;
  interferer_db?: number;
  packet_loss?: number;
  ambience?: string;
  pause_s?: number;
  played_by?: { llm?: string; tts?: string; voice?: string };
  /** What the caller phones about this run, over the persona's goal; given, a caller of the library is not briefed. */
  scenario?: { goal: string; facts?: Record<string, string> };
  against?: AgentValues;
}

/** The call a simulation plays on, watched like any call. */
export interface SimulationStarted {
  call: string;
  voice: boolean;
}

/** `POST /v1/simulations/compare`: a persona or more against the agent under each of these, one call per pair, placed together. */
export interface ComparisonRequest extends Omit<SimulationRequest, "against"> {
  against: AgentValues[];
  /** More callers beside `persona`, each against every configuration as it is. */
  more_personas?: string[];
}

/** What a comparison placed, and what it could not. */
export interface ComparisonStarted {
  comparison: string;
  voice: boolean;
  calls: { persona: string; against: AgentValues; call: string }[];
  refused: { persona: string; against: AgentValues; why: string }[];
}

/** A turn's measures over one call, each its median in seconds; one no turn reported is null. */
export interface Latency {
  e2e_latency: number | null;
  llm_node_ttft: number | null;
  tts_node_ttfb: number | null;
  transcription_delay: number | null;
  end_of_turn_delay: number | null;
}

/** One call of a comparison: the caller, what the agent ran on, how it went, what it cost, how fast it was. */
export interface ComparisonRow {
  call: string;
  persona: string;
  against: AgentValues;
  started_at: number;
  ended_at: number | null;
  turns: number;
  end_reason: string | null;
  score: { held: number; judged: number; passed: boolean; reason: string | null } | null;
  cost_usd: number | null;
  latency: Latency;
  why: string | null;
}

/** `GET /v1/simulations/compare/{id}`: the comparison's calls, caller by caller, each one's best first. */
export interface Comparison {
  comparison: string;
  agent: string;
  /** The first caller; `personas` is every one, in the order placed. */
  persona: string;
  personas: string[];
  voice: boolean;
  rows: ComparisonRow[];
}

/** A simulation the gateway plays and answers at once with its call; followed through the call's log. */
export function startSimulation(gw: GatewayClient, body: SimulationRequest): Promise<SimulationStarted> {
  return gw.post<SimulationStarted>("/v1/simulations", body);
}

/** A comparison placed at once: its id, the calls that started, and what was refused. */
export function startComparison(gw: GatewayClient, body: ComparisonRequest): Promise<ComparisonStarted> {
  return gw.post<ComparisonStarted>("/v1/simulations/compare", body);
}

/** The comparison's table as it stands: the rows best first, a call still on the line last. */
export function getComparison(gw: GatewayClient, comparison: string): Promise<Comparison> {
  return gw.get<Comparison>(`/v1/simulations/compare/${seg(comparison)}`);
}
