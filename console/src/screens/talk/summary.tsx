/** The call once it is over, at the foot of the conversation: how long, how fast, what it ran and cost, how the judges found it, and its page. */

import { type CallScore } from "@pinecall/core/wire/events-call";
import { type State } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { elapsed } from "@pinecall/core/calls";
import { usd } from "../../lib/format";
import { answerOf } from "../../lib/judgment";
import { Pill } from "../../ui";
import { VERDICT_TONE } from "../call/over";
import "./summary.css";

/** What the log has said of the call so far: the folded state, and the judges once `call.score` seals it. */
export interface Followed {
  call: string;
  state: State;
  score: CallScore | null;
}

/** How fast the agent answered, measured the way this call could measure it, in ms per reply. */
interface Latency {
  /** `e2e` a spoken call (the caller stopped → the voice started); `ttft` a written one (to the model's first token). */
  measure: "e2e" | "ttft";
  ms: number[];
  p50: number;
  p95: number;
  worst: number;
}

const MEASURED = { e2e: "you stopped → it answered", ttft: "to the model's first token" } as const;

/**
 * Everything is the log's own: the turns' measurements, the price `call.summary` writes and the
 * verdicts `call.score` seals the log with. What has not arrived yet — the price and the judges come
 * a few seconds after the hang-up — is drawn as the shape it will fill, shimmering.
 */
export function CallSummary({ call, log }: { call: string; log: Followed | null }): ReactNode {
  const state = log?.state ?? null;
  const length = state !== null && state.started_at !== null && state.ended_at !== null ? elapsed(state.started_at, state.ended_at) : null;
  const latency = state === null ? null : latencyOf(state);
  const failed = state?.tools.filter((run) => run.status === "failed").length ?? 0;
  return (
    <section className="tsum" aria-label="The call, in numbers">
      <header className="tsum-head">
        <span className="tsum-title">The call, in numbers</span>
        <Link to={`/calls/${call}`} className="tsum-open">
          Open the conversation ↗
        </Link>
      </header>
      <dl className="tsum-tiles">
        <Tile name="Length" value={length} />
        <Tile name="Turns" value={state === null ? null : String(state.turns.length)} />
        <Tile name="Tools" value={state === null ? null : String(state.tools.length)} aside={failed > 0 ? `${failed} failed` : undefined} />
        <Tile name="Cost" value={state?.cost == null ? null : usd(state.cost.usd)} />
      </dl>
      {latency !== null && <Speed latency={latency} />}
      <Judges score={log?.score ?? null} />
    </section>
  );
}

/** One number of the call; a value still coming is its shape, shimmering. */
function Tile({ name, value, aside }: { name: string; value: string | null; aside?: string | undefined }): ReactNode {
  return (
    <div className="tsum-tile">
      <dt>{name}</dt>
      <dd>{value === null ? <span className="tsum-wait" aria-label="still coming" /> : value}</dd>
      {aside !== undefined && <small>{aside}</small>}
    </div>
  );
}

/** How fast it answered: the typical reply, large, and every reply a column against it. */
function Speed({ latency }: { latency: Latency }): ReactNode {
  const top = Math.max(...latency.ms, 1);
  return (
    <div className="tsum-speed">
      <div className="tsum-typical">
        <span className="tsum-label">Typical reply</span>
        <b>
          {latency.p50}
          <small>ms</small>
        </b>
        <span className="tsum-how">{MEASURED[latency.measure]}</span>
      </div>
      <div className="tsum-bars" aria-label={`every reply: ${latency.ms.join(", ")} ms`}>
        <span className="tsum-p50" style={{ bottom: `${(latency.p50 / top) * 100}%` }} aria-hidden />
        {latency.ms.map((ms, at) => (
          <span key={at} className={ms === latency.worst && latency.ms.length > 1 ? "tsum-bar tsum-bar-worst" : "tsum-bar"} style={{ height: `${(ms / top) * 100}%`, animationDelay: `${at * 30}ms` }} title={`reply ${at + 1} · ${ms} ms`} />
        ))}
      </div>
      <p className="tsum-pcts">
        p50 <b>{latency.p50}</b> · p95 <b>{latency.p95}</b> · worst <b>{latency.worst}</b> ms · {latency.ms.length} {latency.ms.length === 1 ? "reply" : "replies"}
      </p>
    </div>
  );
}

/** The judges' verdicts once the log is sealed; until then, that they are being asked. */
function Judges({ score }: { score: CallScore | null }): ReactNode {
  if (score === null) {
    return (
      <div className="tsum-judges">
        <span className="tsum-label">Being scored…</span>
        <span className="tsum-wait tsum-wait-wide" aria-hidden />
      </div>
    );
  }
  const answered = score.judges.filter((judge) => judge.verdict !== "deferred" && judge.verdict !== "skipped");
  return (
    <div className="tsum-judges">
      <span className="tsum-label">{answered.length === 0 ? "Not judged" : score.passed === false ? "Scored · something broke" : "Scored at hang-up"}</span>
      {answered.length === 0 ? (
        <p className="tsum-none">{score.not_judged ?? "No judge was given to this session."}</p>
      ) : (
        answered.map((judge) => (
          <div key={judge.name} className="tsum-verdict">
            <span className="tsum-verdict-head">
              <Pill tone={VERDICT_TONE[judge.verdict] ?? "muted"} small>
                {answerOf(judge)}
              </Pill>
              <b>{judge.name}</b>
            </span>
            {judge.reason !== "" && <span className="tsum-why">{judge.reason}</span>}
          </div>
        ))
      )}
    </div>
  );
}

// The agent's replies, measured end to end on a voice call; a written one has no voice, so to its first token.
function latencyOf(state: State): Latency | null {
  const replies = state.turns.flatMap((turn) => (turn.role === "agent" ? [turn.metrics] : []));
  const e2e = replies.flatMap((metrics) => (typeof metrics.e2e_latency === "number" && metrics.e2e_latency >= 0 ? [metrics.e2e_latency] : []));
  const ttft = replies.flatMap((metrics) => (typeof metrics.llm_node_ttft === "number" && metrics.llm_node_ttft >= 0 ? [metrics.llm_node_ttft] : []));
  const [measure, seconds] = e2e.length > 0 ? (["e2e", e2e] as const) : (["ttft", ttft] as const);
  if (seconds.length === 0) return null;
  const ms = seconds.map((value) => Math.round(value * 1000));
  const sorted = [...ms].sort((a, b) => a - b);
  return { measure, ms, p50: rank(sorted, 0.5), p95: rank(sorted, 0.95), worst: sorted.at(-1) ?? 0 };
}

// The value at a share of a sorted list, by nearest rank.
function rank(sorted: readonly number[], share: number): number {
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(share * sorted.length) - 1))] ?? 0;
}
