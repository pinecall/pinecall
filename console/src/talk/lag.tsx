/** How long the agent took to answer, under each reply: the wait from its first word on, and where that time went once the session has measured it. */

import { type ReactNode } from "react";

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { type Line } from "./transcript";

type Stage = "hears" | "thinks" | "speaks" | "rest";

/** One reply's wait, in milliseconds, and the stages it is made of. */
export interface Lag {
  /** `e2e` a spoken reply (the caller stopped → the voice started); `ttft` a written one (to the model's first token). */
  measure: "e2e" | "ttft";
  ms: number;
  /** Empty while the reply is still being given: the session measures its stages when it ends. */
  parts: readonly { stage: Stage; ms: number }[];
}

/** The reply the caller is waiting for, or hearing, that the log has not closed yet. */
export interface Begun {
  measure: Lag["measure"];
  /** Epoch seconds: when the caller stopped speaking, or the written line landed. */
  from: number;
  /** To the reply's first word, by the log's own clock; null while the caller still waits. */
  ms: number | null;
}

const NAMED: Record<Stage, string> = { hears: "Hears", thinks: "Thinks", speaks: "Speaks", rest: "Rest" };
const MEANT: Record<Stage, string> = {
  hears: "Waiting to be sure you had stopped",
  thinks: "The model, to its first word",
  speaks: "The voice, to its first sound",
  rest: "Tools, and the line in between",
};
// Under the first a reply feels instant; over the second a caller notices the wait.
const FAST_MS = { e2e: 1000, ttft: 600 } as const;
const SLOW_MS = { e2e: 1800, ttft: 1200 } as const;
// A remainder under this is rounding, not a stage.
const WORTH_MS = 30;

const ms = (seconds: number | null | undefined): number | null => (typeof seconds === "number" && seconds >= 0 ? Math.round(seconds * 1000) : null);

/** The reply in the air after one more entry of the log: a caller's turn opens the wait, the reply's first word ends it, the reply's own turn closes it. */
export function begunAfter(was: Begun | null, entry: Entry): Begun | null {
  const data = entry.data as Record<string, unknown>;
  switch (entry.type) {
    case "turn.user": {
      const stopped = (data["metrics"] as Record<string, unknown> | undefined)?.["stopped_speaking_at"];
      return typeof stopped === "number" ? { measure: "e2e", from: stopped, ms: null } : { measure: "ttft", from: entry.ts, ms: null };
    }
    case "agent.transcript":
      if (was === null || was.ms !== null || String(data["text"] ?? "").trim() === "") return was;
      return { ...was, ms: Math.max(0, Math.round((entry.ts - was.from) * 1000)) };
    case "turn.agent":
    case "call.ended":
      return null;
    default:
      return was;
  }
}

/** Each agent reply's wait, by the id of the last line it was said in. A reply the session did not time has none. */
export function lagsOf(state: State, lines: readonly Line[], begun: Begun | null): Map<string, Lag> {
  const found = new Map<string, Lag>();
  let from = 0;
  state.turns.forEach((turn, at) => {
    if (turn.role !== "agent") return;
    // The reply is on screen as one line per sentence: the last of them carries its time.
    const whole = turn.text.replace(/\s+/g, " ");
    let last: string | null = null;
    for (let index = from; index < lines.length; index += 1) {
      const line = lines[index] as Line;
      if (line.kind !== "said") continue;
      if (line.speaker !== "agent" || line.text.trim() === "" || !whole.includes(line.text.replace(/\s+/g, " ").trim())) {
        if (last !== null) break;
        continue;
      }
      last = line.id;
      from = index + 1;
    }
    const before = state.turns[at - 1];
    const lag = lagOf(turn.metrics, before?.role === "user" ? before.metrics.end_of_turn_delay : null);
    if (last !== null && lag !== null) found.set(last, lag);
  });
  // The reply in the air has no turn yet: it is the agent's lines since the caller's last turn, and
  // the last of them carries the wait to its first word until the turn lands with the session's own.
  if (begun !== null && begun.ms !== null) {
    let last: string | null = null;
    for (let index = lines.length - 1; index >= from && last === null; index -= 1) {
      const line = lines[index] as Line;
      if (line.kind !== "said") continue;
      if (line.speaker === "user" && line.landed === true) break;
      if (line.speaker === "agent" && line.text.trim() !== "") last = line.id;
    }
    if (last !== null) found.set(last, { measure: begun.measure, ms: begun.ms, parts: [] });
  }
  return found;
}

function lagOf(metrics: { e2e_latency?: number | null | undefined; llm_node_ttft?: number | null | undefined; tts_node_ttfb?: number | null | undefined }, heardIn: number | null | undefined): Lag | null {
  const thinks = ms(metrics.llm_node_ttft);
  const total = ms(metrics.e2e_latency);
  if (total === null) return thinks === null ? null : { measure: "ttft", ms: thinks, parts: [{ stage: "thinks", ms: thinks }] };
  const known = [
    { stage: "hears" as const, ms: ms(heardIn) },
    { stage: "thinks" as const, ms: thinks },
    { stage: "speaks" as const, ms: ms(metrics.tts_node_ttfb) },
  ].flatMap((part) => (part.ms === null ? [] : [{ stage: part.stage, ms: part.ms }]));
  // With no stage timed there is nothing to cut the wait into: the total stands alone.
  if (known.length === 0) return { measure: "e2e", ms: total, parts: [] };
  const rest = total - known.reduce((sum, part) => sum + part.ms, 0);
  return { measure: "e2e", ms: total, parts: rest > WORTH_MS ? [...known, { stage: "rest", ms: rest }] : known };
}

const paceOf = (lag: Lag): "fast" | "fair" | "slow" => (lag.ms <= FAST_MS[lag.measure] ? "fast" : lag.ms <= SLOW_MS[lag.measure] ? "fair" : "slow");

/** Under a reply: its wait, and once its stages are measured, one thin bar cut into them, each with its milliseconds. */
export function LagBar({ lag }: { lag: Lag }): ReactNode {
  const whole = Math.max(
    lag.parts.reduce((sum, part) => sum + part.ms, 0),
    1,
  );
  return (
    <div className={`talk-lagbar talk-lag-${paceOf(lag)}`} aria-label={[`This reply took ${lag.ms} milliseconds`, ...lag.parts.map((part) => `${NAMED[part.stage]} ${part.ms}`)].join(", ")}>
      <span className="talk-lagbar-total">
        <b>{lag.ms}</b> ms
      </span>
      {lag.parts.length > 0 && (
        <>
          <span className="talk-lagbar-track" aria-hidden>
            {lag.parts.map((part) => (
              <i key={part.stage} className={`talk-lagbar-${part.stage}`} style={{ flexGrow: part.ms / whole }} />
            ))}
          </span>
          <span className="talk-lagbar-parts">
            {lag.parts.map((part) => (
              <span key={part.stage} title={MEANT[part.stage]}>
                <i className={`talk-lagbar-${part.stage}`} aria-hidden />
                {NAMED[part.stage]} <b>{part.ms}</b>
              </span>
            ))}
          </span>
        </>
      )}
    </div>
  );
}
