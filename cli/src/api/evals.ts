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
