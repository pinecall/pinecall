/** A simulation the gateway plays with the agent on other voices and models, and a comparison of several, followed through their logs. */

import { z } from "zod";

import type { Entry } from "../../api/calls.js";
import * as calls from "../../api/calls.js";
import type { Persona } from "../../api/cases.js";
import * as api from "../../api/evals.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { playedBy, ranOn, scoreOf, type Simulated, type SimulateInput, type SimulationListeners } from "./simulation.js";
import { mediansOf } from "./suite.js";

/** The knobs `--against` takes, the test room's: each stage as vendor/model, a voice, a language, a temperature, who ends the turn. */
export const AGAINST_KNOBS = ["stt", "llm", "tts", "voice", "language", "temperature", "end_of_turn"] as const;

export const AgentValuesInput = z.strictObject({
  stt: z.string().min(1).optional(),
  llm: z.string().min(1).optional(),
  tts: z.string().min(1).optional(),
  voice: z.string().min(1).optional(),
  language: z.string().min(1).optional(),
  temperature: z.number().optional(),
  end_of_turn: z.enum(["stt", "livekit", "smart-turn"]).optional(),
});
export type AgentValuesInput = z.infer<typeof AgentValuesInput>;

const A_PAIR = `--against takes knob=value pairs joined by commas — ${AGAINST_KNOBS.join(", ")} — as in llm=groq/openai/gpt-oss-120b,tts=deepgram`;
// How long the table is asked for after every call ended: the judges answer after the hang-up.
const JUDGED_WITHIN_MS = 90_000;
const ASKED_EVERY_MS = 1500;
// A call that waits its turn waits for another to end: the table is asked this often meanwhile.
const WAITING_ASKED_EVERY_MS = 5000;

/** `llm=groq/openai/gpt-oss-120b,tts=deepgram` as the gateway takes it; a knob it does not know is refused. */
export function parseAgainst(word: string): AgentValuesInput {
  const values: Record<string, string | number> = {};
  for (const pair of word.split(",")) {
    const at = pair.indexOf("=");
    const knob = pair.slice(0, at).trim();
    const value = pair.slice(at + 1).trim();
    if (at < 0 || !(AGAINST_KNOBS as readonly string[]).includes(knob) || value === "") throw new UsageError(A_PAIR);
    values[knob] = knob === "temperature" ? Number(value) : value;
  }
  const parsed = AgentValuesInput.safeParse(values);
  if (!parsed.success) throw new UsageError(A_PAIR);
  return parsed.data;
}

/** What a comparison came to: its id, what the gateway refused, and its table as it stood when every call was judged or the wait ran out. */
export interface Compared {
  comparison: string;
  refused: { against: api.AgentValues; why: string }[];
  table: api.Comparison;
}

/** The request one simulation the gateway plays takes, from the input: the line and who plays the caller. */
function wanted(agent: string, persona: Persona, input: SimulateInput): Omit<api.SimulationRequest, "against"> {
  const degraded =
    input.backgroundNoise === undefined && input.packetLoss === undefined && input.ambience === undefined
      ? {}
      : { interferer_db: input.backgroundNoise ?? 0, packet_loss: input.packetLoss ?? 0, ...(input.ambience === undefined ? {} : { ambience: input.ambience }) };
  const played = ranOn(input);
  // The gateway plays and briefs the caller; a goal given is the scenario it phones about instead.
  const scenario = input.goal === undefined ? {} : { scenario: { goal: input.goal } };
  return { agent, persona: persona.name, voice: input.voice, turns: input.turns, ...degraded, ...(played === undefined ? {} : { played_by: played }), ...scenario };
}

/**
 * One simulation the gateway plays — written or spoken — with the agent on the values named, followed
 * through the call's log until it ends; scored once the judges answered, when asked.
 */
export async function simulateAgainst(ctx: Context, agent: string, written: Persona, input: SimulateInput, against: api.AgentValues, listeners: SimulationListeners = {}): Promise<Simulated> {
  const persona = playedBy(written, input);
  const started = await api.startSimulation(ctx.gateway(), { ...wanted(agent, persona, input), against });
  listeners.onOpened?.(started.call);
  const entries = await followUntilEnded(ctx, started.call, listeners);
  const score = input.judge ? await scoreOf(ctx, started.call) : null;
  return {
    persona: persona.name,
    goal: persona.goal,
    call: started.call,
    agentTurns: entries.filter((entry) => entry.type === "turn.agent").length,
    callerTurns: entries.filter((entry) => entry.type === "turn.user").length,
    line: started.voice ? "spoken" : null,
    medians: mediansOf(entries),
    score,
    unjudged: input.judge && score === null,
  };
}

/**
 * The persona against the agent under each of the values, placed together; every call followed to its
 * end, then the table read until every call is judged or the judges' time is up.
 */
export async function compare(ctx: Context, agent: string, written: Persona, input: SimulateInput, against: readonly api.AgentValues[], onPlaced?: (started: api.ComparisonStarted) => void): Promise<Compared> {
  const persona = playedBy(written, input);
  const repeated = input.repeats > 1 ? { repeats: input.repeats } : {};
  const started = await api.startComparison(ctx.gateway(), { ...wanted(agent, persona, input), against: [...against], ...repeated });
  onPlaced?.(started);
  // Nothing placed and nothing waiting, there is no table to read: the gateway's reasons are the answer.
  if (started.calls.length === 0 && (started.waiting ?? 0) === 0) throw new UsageError(nonePlaced(started.refused));
  await Promise.all(started.calls.map((one) => followUntilEnded(ctx, one.call)));
  const readTable = (): Promise<api.Comparison> => api.getComparison(ctx.gateway(), started.comparison);
  const again = (): Promise<void> => new Promise((wake) => setTimeout(wake, WAITING_ASKED_EVERY_MS));
  let table = await readTable();
  // The calls past the org's calls at once wait their turn in the gateway, which places each as the
  // ones before it end: the table says how many still wait, and whether their gateway left them.
  while (stillPlacing(table) || ((table.waiting ?? 0) === 0 && (started.waiting ?? 0) > 0 && table.rows.some((row) => row.ended_at === null))) {
    await again();
    table = await readTable();
  }
  const deadline = Date.now() + JUDGED_WITHIN_MS;
  while (Date.now() < deadline && table.rows.some((row) => row.ended_at === null || row.score === null)) {
    await new Promise((wake) => setTimeout(wake, ASKED_EVERY_MS));
    table = await readTable();
  }
  return { comparison: started.comparison, refused: table.refused ?? started.refused, table };
}

/** Whether calls of the comparison still wait for a place on the line, with a gateway placing them. */
function stillPlacing(table: api.Comparison): boolean {
  return (table.waiting ?? 0) > 0 && table.abandoned !== true;
}

// One reason said once, with how many rows it refused, so nine rows refused alike read as one line.
function nonePlaced(refused: readonly { why: string }[]): string {
  const reasons = [...new Set(refused.map((one) => one.why))];
  const rows = refused.length === 1 ? "the one row was" : `all ${String(refused.length)} rows were`;
  return `no call was placed: ${rows} refused — ${reasons.join("; ")}`;
}

// Follow the call's log from its first entry to call.ended; what the log holds past the cursor then is read once.
async function followUntilEnded(ctx: Context, call: string, listeners: SimulationListeners = {}): Promise<Entry[]> {
  const entries: Entry[] = [];
  const stop = new AbortController();
  let cursor = 0;
  try {
    for await (const entry of calls.followEntries(ctx.gateway(), { call }, { signal: stop.signal })) {
      cursor = entry.seq;
      entries.push(entry);
      listeners.onEntry?.(entry);
      if (entry.type === "call.ended") break;
    }
  } finally {
    stop.abort();
  }
  for (const entry of (await calls.listCallEntries(ctx.gateway(), call, { after: cursor })).entries) {
    entries.push(entry);
    listeners.onEntry?.(entry);
  }
  return entries;
}
