/** One simulated call: a model plays the persona against the agent wherever it is held, written or spoken, judged at hang-up. */

import { randomBytes } from "node:crypto";

import type { CallScore } from "@pinecall/agents/wire";
import { z } from "zod";

import type { Entry } from "../../api/calls.js";
import * as calls from "../../api/calls.js";
import type { Persona } from "../../api/cases.js";
import * as api from "../../api/evals.js";
import { Chat } from "../../calls/service/chat.js";
import type { Context } from "../../context.js";
import { UsageError } from "../../errors.js";
import { AMBIENCES, allEntries, mediansOf, type Medians } from "./suite.js";

/** Default caller turns; long enough for a full booking flow, not just the opening. */
export const TURNS = 15;
export const ONLY_ON_A_LINE = "--background-noise, --ambience and --packet-loss are about audio: add --voice";
const A_TURNS = "--turns is how many turns the caller gets, 1 to 40";
const A_LOSS = "--packet-loss is a share of the caller's packets: a number from 0 to 1, such as 0.05";

// Background TV at 15 dB below the caller: measured to leak into `turn.user`.
const DEFAULT_NOISE_DB = 15;
// `call.score` is written after hang-up, so it is waited for up to this long.
const JUDGING_MAY_TAKE_MS = 60_000;
// Quiet period before the caller's next line, and the per-turn timeout.
const SETTLE_MS = 400;
const A_TURN_MAY_TAKE_MS = 30_000;

/** What one simulation takes: the persona, judged or not, written or spoken, its line, how many turns. */
export const SimulateInput = z.object({
  persona: z.string().min(1),
  judge: z.boolean().default(false),
  voice: z.boolean().default(false),
  turns: z.number().int(A_TURNS).min(1, A_TURNS).max(40, A_TURNS).default(TURNS),
  backgroundNoise: z.number().optional(),
  ambience: z.enum(AMBIENCES, { error: `--ambience takes ${AMBIENCES.join(", ")}` }).optional(),
  packetLoss: z.number().min(0, A_LOSS).max(1, A_LOSS).optional(),
  // Who plays the caller this run, over the persona's own: vendor/model, a voice's vendor, a voice id.
  llm: z.string().min(1).optional(),
  tts: z.string().min(1).optional(),
  callerVoice: z.string().min(1).optional(),
});
export type SimulateInput = z.infer<typeof SimulateInput>;

/** What a simulation tells whoever runs it, as it happens. */
export interface SimulationListeners {
  /** Every entry of the call, in order. */
  onEntry?: (entry: Entry) => void;
  /** The call has an id. */
  onOpened?: (call: string) => void;
}

/** A finished simulation: its call, the turns, the latency medians, and the score when judged. */
export interface Simulated {
  persona: string;
  goal: string;
  call: string;
  agentTurns: number;
  callerTurns: number | null;
  /** A spoken call's line as the runtime describes it; null on a written one. */
  line: string | null;
  medians: Medians;
  score: CallScore | null;
  /** Judging was asked and no score came in time. */
  unjudged: boolean;
}

/** Where the agent is: its slug, and the process that serves the call (read on every dial). */
export interface Reached {
  slug: string;
  app?: (() => string | undefined) | undefined;
}

/** Exit code: 1 when a judge answered broken, else 0. */
export function exitCodeOf(said: Simulated): number {
  return said.score === null || said.score.passed !== false ? 0 : 1;
}

/** The persona as this run plays it: the run's model and voice over its own; another voice vendor drops its voice. */
export function playedBy(persona: Persona, input: Pick<SimulateInput, "llm" | "tts" | "callerVoice">): Persona {
  const voice = input.callerVoice ?? (input.tts === undefined ? persona.voice : null);
  return { ...persona, llm: input.llm ?? persona.llm, tts: input.tts ?? persona.tts, voice };
}

/** The persona in the gateway's wire shape; unset optional fields are left out. */
export function callerOf(persona: Persona): api.CallerPersona {
  const set = (value: string | null | undefined): value is string => value !== undefined && value !== null && value !== "";
  return {
    name: persona.name,
    goal: persona.goal,
    style: persona.style,
    ...(Object.keys(persona.facts).length === 0 ? {} : { facts: persona.facts }),
    ...(set(persona.llm) ? { llm: persona.llm } : {}),
    ...(set(persona.tts) ? { tts: persona.tts } : {}),
    ...(set(persona.voice) ? { voice: persona.voice } : {}),
    ...(persona.expects.length === 0 ? {} : { expects: persona.expects }),
    behavior: persona.behavior,
  };
}

/**
 * One call at the agent against a model playing the persona in the gateway. A written call names the
 * app in its socket; a spoken one reaches whoever takes unclaimed calls, held by the runtime.
 */
export async function simulate(ctx: Context, reached: Reached, written: Persona, input: SimulateInput, listeners: SimulationListeners = {}): Promise<Simulated> {
  const persona = playedBy(written, input);
  const spoiled = input.backgroundNoise !== undefined || input.packetLoss !== undefined || input.ambience !== undefined;
  if (!input.voice && spoiled) throw new UsageError(ONLY_ON_A_LINE);
  const heard = new Heard(listeners);
  const placed = input.voice ? await outLoud(ctx, reached.slug, persona, input, heard, listeners) : await inWriting(ctx, reached, persona, input, heard);
  const entries = placed.call === "" ? [] : await allEntries(ctx, placed.call);
  const score = input.judge && placed.call !== "" ? await scoreOf(ctx, placed.call) : null;
  return {
    persona: persona.name,
    goal: persona.goal,
    call: placed.call,
    agentTurns: heard.agentTurns,
    callerTurns: placed.callerTurns,
    line: placed.line,
    medians: mediansOf(entries),
    score,
    unjudged: input.judge && score === null,
  };
}

// Written call over one socket; ending it hangs up, which triggers scoring.
async function inWriting(ctx: Context, reached: Reached, persona: Persona, input: SimulateInput, heard: Heard): Promise<{ call: string; callerTurns: number | null; line: null }> {
  const chat = await Chat.open(ctx, { agent: reached.slug, app: reached.app, persona: persona.name, state: Object.keys(persona.state).length === 0 ? undefined : persona.state }, { onEntry: (entry) => heard.absorb(entry) });
  await heard.quiet();
  for (let turn = 0; turn < input.turns; turn += 1) {
    // Hung up elsewhere (console, app, agent): stop, as the spoken path does.
    if (heard.over || chat.ended) break;
    const next = await api.nextCallerLine(ctx.gateway(), { persona: callerOf(persona), heard: heard.said, turns_left: input.turns - turn });
    if (next.say === "" || heard.over) break;
    const before = heard.agentTurns;
    chat.say(next.say);
    await heard.answered(before);
    if (next.hangup) break;
  }
  await chat.end();
  return { call: chat.call ?? "", callerTurns: null, line: null };
}

// Spoken call run entirely by the runtime; this side mints the id and follows the log.
async function outLoud(ctx: Context, agent: string, persona: Persona, input: SimulateInput, heard: Heard, listeners: SimulationListeners): Promise<{ call: string; callerTurns: number; line: string }> {
  // Minted here: the room name is the call id, so the log can be followed at once.
  const call = `call_${randomBytes(12).toString("hex")}`;
  const degraded =
    input.backgroundNoise === undefined && input.packetLoss === undefined && input.ambience === undefined
      ? {}
      : { interferer_db: input.backgroundNoise ?? DEFAULT_NOISE_DB, packet_loss: input.packetLoss ?? 0, ...(input.ambience === undefined ? {} : { ambience: input.ambience }) };
  const held = api.startVoiceCall(ctx.gateway(), {
    call,
    agent,
    persona: callerOf(persona),
    turns: input.turns,
    ...degraded,
    ...(Object.keys(persona.state).length === 0 ? {} : { state: persona.state }),
  });
  // The id is said only after the first entry, so a refused call is never announced.
  let told = false;
  await followUntilScored(ctx, call, held, (entry) => {
    if (!told) {
      told = true;
      listeners.onOpened?.(call);
    }
    heard.absorb(entry);
  });
  const called = await held;
  return { call, callerTurns: called.turns, line: called.line };
}

/**
 * Follow the call's log from its first entry until it is scored or `over` settles; what the log
 * holds past the cursor then is read once, as the closing turns may land after the last one.
 */
async function followUntilScored(ctx: Context, call: string, over: Promise<unknown>, absorb: (entry: Entry) => void): Promise<void> {
  const stop = new AbortController();
  void over.catch(() => undefined).finally(() => stop.abort());
  let cursor = 0;
  try {
    for await (const entry of calls.followEntries(ctx.gateway(), { call }, { signal: stop.signal })) {
      cursor = entry.seq;
      absorb(entry);
      if (entry.type === "call.score") return;
    }
  } finally {
    stop.abort();
  }
  for (const entry of (await calls.listCallEntries(ctx.gateway(), call, { after: cursor })).entries) absorb(entry);
}

// `call.score` is written after hang-up, once the judges answered: asked for again until it is, up to the judging's time.
async function scoreOf(ctx: Context, call: string): Promise<CallScore | null> {
  const deadline = Date.now() + JUDGING_MAY_TAKE_MS;
  while (Date.now() < deadline) {
    const sealed = (await calls.listCallEntries(ctx.gateway(), call, { types: ["call.score"] })).entries.find((entry) => entry.type === "call.score");
    if (sealed !== undefined) return sealed.data as unknown as CallScore;
    await after(SETTLE_MS);
  }
  return null;
}

/** The simulation's only view of the call: the caller model's transcript is built from these entries. */
class Heard {
  agentTurns = 0;
  over = false;
  readonly said: api.Spoken[] = [];
  private last = Date.now();

  constructor(private readonly listeners: SimulationListeners) {}

  absorb(entry: Entry): void {
    this.last = Date.now();
    if (entry.type === "turn.agent") this.agentTurns += 1;
    // Stop sending turns after call.ended, or each one waits out the full turn timeout.
    if (entry.type === "call.ended") this.over = true;
    if (entry.type === "turn.user" || entry.type === "turn.agent") this.said.push({ who: entry.type === "turn.agent" ? "agent" : "caller", said: String(entry.data["text"] ?? "") });
    if (typeof entry.call === "string") this.listeners.onOpened?.(entry.call);
    this.listeners.onEntry?.(entry);
  }

  /** Wait for the next agent turn, then for the log to go quiet. */
  async answered(said: number): Promise<void> {
    const deadline = Date.now() + A_TURN_MAY_TAKE_MS;
    while (this.agentTurns === said && !this.over && Date.now() < deadline) await after(SETTLE_MS / 4);
    await this.quiet();
  }

  /** Wait until no entry has arrived for SETTLE_MS. */
  async quiet(): Promise<void> {
    const deadline = Date.now() + A_TURN_MAY_TAKE_MS;
    while (Date.now() - this.last < SETTLE_MS && Date.now() < deadline) await after(SETTLE_MS / 4);
  }
}

function after(ms: number): Promise<void> {
  return new Promise((wake) => setTimeout(wake, ms));
}
