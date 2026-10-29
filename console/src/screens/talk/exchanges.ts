/** The call as a trace: every reply taken apart into hearing, thinking, tools and speaking, from the log alone. */
//
// One exchange is one thing the caller said and everything the agent did about it. The wire ties
// them with one id: the caller's turn, every model request, every tool and every reply it caused
// carry the same `speech_id`. So nothing here guesses at an order: each bar is an entry's own
// timestamps, laid out from the moment the caller stopped speaking, which is when a caller starts
// to wait. A reply still happening is drawn from the states the log has said so far, open-ended,
// and closes as its measurements land. The call page's Trace view (`../call/trace-bars.ts`) lays a
// finished call on one axis; this one follows a reply as it happens.

import { type Entry } from "@pinecall/core/wire/envelope";

export type Lane = "hears" | "thinks" | "tools" | "speaks";

/** One span of one exchange, in seconds from the moment the caller stopped speaking. */
export interface Bar {
  lane: Lane;
  label: string;
  from: number;
  /** Null while it is still happening. */
  to: number | null;
  /** A model's first token, inside its bar. */
  first?: number;
  failed?: boolean;
}

/** What the caller waited for, taken apart; seconds, null where the log did not measure it. */
export interface Stages {
  hears: number;
  thinks: number | null;
  speaks: number | null;
  /** What the three do not account for: the network, a queue, a tool before the first word. */
  other: number | null;
}

export interface Exchange {
  id: string;
  /** Epoch seconds: when the caller stopped speaking, the zero of every bar. */
  zero: number;
  said: string;
  /** Seconds from the caller's last word to the agent's first sound, as the wire measured it. */
  e2e: number | null;
  /** When the agent was first heard, from zero; null until it has been. */
  firstSound: number | null;
  stages: Stages | null;
  bars: Bar[];
  /** The caller spoke again, or the call ended: nothing more lands on it. */
  done: boolean;
}

export interface Models {
  hears: string | null;
  thinks: string | null;
  speaks: string | null;
}

export interface Counts {
  tokensIn: number;
  tokensCached: number;
  tokensOut: number;
  /** The model's last generation speed, tokens a second. */
  tokensPerSecond: number | null;
  /** Seconds of voice synthesised, and the characters it read. */
  voiced: number;
  characters: number;
  tools: number;
  toolsFailed: number;
  /** Replies the caller cut short. */
  cut: number;
}

export interface Trace {
  exchanges: Exchange[];
  models: Models;
  counts: Counts;
  /** Epoch seconds of the caller's last word while the agent has not answered it yet, else null. */
  waitingSince: number | null;
  /** What the agent is doing this instant, by the log: the lane to light. */
  now: Lane | "you" | null;
}

type Data = Record<string, unknown>;

const num = (value: unknown): number | undefined => (typeof value === "number" && Number.isFinite(value) ? value : undefined);
const str = (value: unknown): string | undefined => (typeof value === "string" && value !== "" ? value : undefined);
const obj = (value: unknown): Data | undefined => (value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Data) : undefined);

/** "Deepgram · flux-general-multi", from a metadata block, or null when it names nothing. */
function modelOf(metadata: unknown): string | null {
  const m = obj(metadata);
  const name = str(m?.["model_name"]);
  if (!name) return null;
  const provider = str(m?.["model_provider"]);
  return provider ? `${provider} · ${name}` : name;
}

/** The value at the given share of a sorted list, by nearest rank. */
export function rank(sorted: readonly number[], share: number): number {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(share * sorted.length) - 1))] ?? 0;
}

/** The trace of a call, as far as its entries go; `live` keeps the last exchange open. */
export function traceOf(entries: readonly Entry[], live: boolean): Trace {
  const exchanges: Exchange[] = [];
  const byId = new Map<string, Exchange>();
  const models: Models = { hears: null, thinks: null, speaks: null };
  const counts: Counts = { tokensIn: 0, tokensCached: 0, tokensOut: 0, tokensPerSecond: null, voiced: 0, characters: 0, tools: 0, toolsFailed: 0, cut: 0 };
  const calls = new Map<string, { exchange: Exchange; name: string; at: number }>();

  // The live edges: when the caller last stopped, and what the agent's state has said since.
  let userState: string | null = null;
  let stoppedAt: number | null = null;
  let agentState: { state: string; at: number } | null = null;
  let toolsRunning = 0;
  let ended = false;

  const current = (): Exchange | undefined => exchanges.at(-1);
  const open = (lane: Lane, label: string, at: number): void => {
    const ex = current();
    if (!ex || ex.done) return;
    ex.bars.push({ lane, label, from: at - ex.zero, to: null });
  };
  const close = (lane: Lane, at: number): void => {
    const ex = current();
    if (!ex) return;
    for (const bar of ex.bars) if (bar.lane === lane && bar.to === null) bar.to = Math.max(bar.from, at - ex.zero);
  };

  for (const entry of entries) {
    const d = entry.data;
    switch (entry.type) {
      case "user.state": {
        const state = str(d["state"]) ?? null;
        if (state === "listening" && userState === "speaking") stoppedAt = entry.ts;
        if (state === "speaking") stoppedAt = null;
        userState = state;
        break;
      }
      case "agent.state": {
        const state = str(d["state"]) ?? "";
        const before = agentState?.state;
        if (before === "thinking" && state !== "thinking") close("thinks", entry.ts);
        if (before === "speaking" && state !== "speaking") close("speaks", entry.ts);
        agentState = { state, at: entry.ts };
        if (state === "thinking") open("thinks", models.thinks ?? "thinking", entry.ts);
        if (state === "speaking") {
          open("speaks", "speaking", entry.ts);
          const ex = current();
          if (ex && !ex.done && ex.firstSound === null) ex.firstSound = entry.ts - ex.zero;
          stoppedAt = null;
        }
        break;
      }
      case "turn.user": {
        const metrics = obj(d["metrics"]) ?? {};
        models.hears = modelOf(metrics["stt_metadata"]) ?? models.hears;
        const last = current();
        if (last) last.done = true;
        const id = str(d["speech_id"]) ?? `turn-${entry.seq}`;
        const zero = num(metrics["stopped_speaking_at"]) ?? stoppedAt ?? entry.ts;
        const hears = Math.max(num(metrics["end_of_turn_delay"]) ?? 0, num(metrics["transcription_delay"]) ?? 0);
        const ex: Exchange = {
          id,
          zero,
          said: str(d["text"]) ?? "",
          e2e: null,
          firstSound: null,
          stages: null,
          bars: hears > 0 ? [{ lane: "hears", label: models.hears ?? "end of turn", from: 0, to: hears }] : [],
          done: false,
        };
        exchanges.push(ex);
        byId.set(id, ex);
        break;
      }
      case "metrics.llm": {
        const at = num(d["timestamp"]);
        const duration = num(d["duration"]) ?? 0;
        const ttft = num(d["ttft"]);
        models.thinks = modelOf(d["metadata"]) ?? models.thinks;
        counts.tokensIn += num(d["prompt_tokens"]) ?? 0;
        counts.tokensCached += num(d["prompt_cached_tokens"]) ?? 0;
        counts.tokensOut += num(d["completion_tokens"]) ?? 0;
        counts.tokensPerSecond = num(d["tokens_per_second"]) ?? counts.tokensPerSecond;
        const ex = byId.get(str(d["speech_id"]) ?? "") ?? current();
        if (!ex || at === undefined) break;
        const from = at - duration - ex.zero;
        // The open bar the state drew is replaced by the request's own measurement.
        ex.bars = ex.bars.filter((bar) => !(bar.lane === "thinks" && bar.to === null));
        ex.bars.push({ lane: "thinks", label: models.thinks ?? "model", from, to: at - ex.zero, ...(ttft !== undefined ? { first: from + ttft } : {}) });
        if (agentState?.state === "thinking" && agentState.at > at) open("thinks", models.thinks ?? "thinking", agentState.at);
        break;
      }
      case "metrics.tts": {
        models.speaks = modelOf(d["metadata"]) ?? models.speaks;
        counts.voiced += num(d["audio_duration"]) ?? 0;
        counts.characters += num(d["characters_count"]) ?? 0;
        break;
      }
      case "metrics.stt": {
        models.hears = modelOf(d["metadata"]) ?? models.hears;
        break;
      }
      case "turn.agent": {
        const metrics = obj(d["metrics"]) ?? {};
        models.thinks = modelOf(metrics["llm_metadata"]) ?? models.thinks;
        models.speaks = modelOf(metrics["tts_metadata"]) ?? models.speaks;
        if (d["interrupted"] === true) counts.cut += 1;
        const ex = byId.get(str(d["speech_id"]) ?? "") ?? current();
        const e2e = num(metrics["e2e_latency"]);
        if (!ex || e2e === undefined || ex.e2e !== null) break;
        ex.e2e = e2e;
        const started = num(metrics["started_speaking_at"]);
        if (started !== undefined) ex.firstSound = started - ex.zero;
        const hears = ex.bars.find((bar) => bar.lane === "hears")?.to ?? 0;
        const thinks = num(metrics["llm_node_ttft"]) ?? null;
        const speaks = num(metrics["tts_node_ttfb"]) ?? null;
        const other = e2e - hears - (thinks ?? 0) - (speaks ?? 0);
        ex.stages = { hears, thinks, speaks, other: other > 0.005 ? other : null };
        break;
      }
      case "tool.call": {
        const callId = str(d["call_id"]);
        const ex = byId.get(str(d["speech_id"]) ?? "") ?? current();
        const name = str(d["name"]) ?? "tool";
        counts.tools += 1;
        toolsRunning += 1;
        if (!ex || !callId) break;
        calls.set(callId, { exchange: ex, name, at: entry.ts });
        ex.bars.push({ lane: "tools", label: name, from: entry.ts - ex.zero, to: null });
        break;
      }
      case "tool.result": {
        toolsRunning = Math.max(0, toolsRunning - 1);
        const failed = str(d["error"]) !== undefined;
        if (failed) counts.toolsFailed += 1;
        const ran = calls.get(str(d["call_id"]) ?? "");
        if (!ran) break;
        const ex = ran.exchange;
        const bar = ex.bars.find((one) => one.lane === "tools" && one.to === null && one.label === ran.name);
        if (bar) {
          bar.to = Math.max(bar.from, entry.ts - ex.zero);
          if (failed) bar.failed = true;
        }
        break;
      }
      case "call.ended": {
        ended = true;
        for (const lane of ["hears", "thinks", "tools", "speaks"] as const) close(lane, entry.ts);
        const last = current();
        if (last) last.done = true;
        break;
      }
    }
  }

  const waiting = live && !ended && stoppedAt !== null ? stoppedAt : null;
  let now: Trace["now"] = null;
  if (live && !ended) {
    if (userState === "speaking") now = "you";
    else if (toolsRunning > 0) now = "tools";
    else if (agentState?.state === "speaking") now = "speaks";
    else if (agentState?.state === "thinking") now = "thinks";
    else if (waiting !== null) now = "hears";
  }
  if (!live) for (const ex of exchanges) ex.done = true;
  return { exchanges, models, counts, waitingSince: waiting, now };
}

/** The measured replies' e2e in ms: what the caller felt, one per exchange that has one. */
export function feltOf(trace: Trace): number[] {
  return trace.exchanges.flatMap((ex) => (ex.e2e === null ? [] : [Math.round(ex.e2e * 1000)]));
}
