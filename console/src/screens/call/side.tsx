/** The pane beside a call, read at a glance: what it came to, each judge in a line, four tiles — how fast, what it cost, how many turns, who ended it — and what is put under them. */

import { type Judgment } from "@pinecall/core/wire/events";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { type State } from "@pinecall/core/wire/state";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { seconds, type Median } from "@pinecall/core/metrics";
import { duration, usd } from "../../lib/format";
import { answerOf } from "../../lib/judgment";
import { Icon, type IconName } from "../../ui";
import "./side.css";

export function Side({ state, score, latencies, children }: { state: State; score: CallScore | null; latencies: Median[]; children?: ReactNode }): ReactNode {
  const over = state.status === "ended";
  return (
    <div className="call-side">
      {over && (
        <section className="call-side-part">
          <h3 className="call-side-head">Outcome</h3>
          <p className="call-side-outcome">{state.outcome ?? "The call left no outcome sentence."}</p>
        </section>
      )}
      {over && <Judges score={score} />}
      <div className="call-side-tiles">
        <Response latencies={latencies} />
        {state.cost !== null && state.cost.rows.length > 0 && <Tile label="Cost" value={usd(state.cost.usd)} sub={sharesOf(state.cost.rows)} />}
        <Tile
          label="Turns"
          value={String(state.turns.length)}
          sub={`caller ${state.turns.filter((turn) => turn.role === "user").length} · agent ${state.turns.filter((turn) => turn.role === "agent").length}`}
        />
        {over && state.end_reason !== null && <Ended state={state} reason={state.end_reason} />}
      </div>
      {/* What follows the tiles in the same column, at its margins: the models on the line. */}
      {children}
    </div>
  );
}

// ── the judges ────────────────────────────────────────────────────────────────

/** How a verdict is drawn: its icon, its tint, and the word it is said in when not the answer's own. */
interface Look {
  icon: IconName;
  tone: "red" | "green" | "indigo" | "muted";
  said?: string;
}

const VERDICT: Record<string, Look> = {
  broken: { icon: "cross", tone: "red", said: "broke" },
  held: { icon: "check", tone: "green" },
  classified: { icon: "check", tone: "indigo" },
};
const QUIET: Look = { icon: "dash", tone: "muted" };

/** Each judge in a line — what it answered, and why when it broke, with the turns it cites. */
function Judges({ score }: { score: CallScore | null }): ReactNode {
  const judges = score?.judges ?? [];
  const broke = judges.filter((judge) => judge.verdict === "broken").length;
  const settled = judges.filter((judge) => judge.verdict === "held" || judge.verdict === "broken").length;
  // Judges on the panel that answered nothing are listed too, dim, so coverage is never overstated.
  const silent = (score?.panel ?? []).filter((name) => !judges.some((judge) => judge.name === name));
  return (
    <section className="call-side-part">
      <div className="call-side-head-line">
        <h3 className="call-side-head">Judges</h3>
        {settled > 0 && <span className="call-side-head-meta">{broke > 0 ? `${broke} of ${settled} broke` : `${settled} of ${settled} held`}</span>}
      </div>
      {score === null ? (
        <p className="call-side-quiet">Not judged yet.</p>
      ) : judges.length === 0 && silent.length === 0 ? (
        <p className="call-side-quiet">No judge was given to this call.</p>
      ) : (
        <div className="call-side-judges">
          {judges.map((judge) => (
            <JudgeLine key={judge.name} judge={judge} />
          ))}
          {silent.map((name) => (
            <div key={name} className="call-side-judge" title="Was run over this call and answered nothing.">
              <span className="call-side-judge-icon call-side-tone-muted">
                <Icon name="dash" size={15} />
              </span>
              <span className="call-side-judge-name">{name}</span>
              <span className="call-side-judge-said call-side-tone-muted">no answer</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function JudgeLine({ judge }: { judge: Judgment }): ReactNode {
  const look = VERDICT[judge.verdict] ?? QUIET;
  const broke = judge.verdict === "broken";
  return (
    <div className="call-side-judge" title={broke ? undefined : judge.reason}>
      <span className={`call-side-judge-icon call-side-tone-${look.tone}`}>
        <Icon name={look.icon} size={15} />
      </span>
      <span className="call-side-judge-name">{judge.name}</span>
      <span className={`call-side-judge-said call-side-tone-${look.tone}`}>{look.said ?? answerOf(judge)}</span>
      {broke && (
        <p className="call-side-judge-why">
          {judge.reason}
          {judge.evidence.seqs.map((seq) => (
            <Link key={seq} className="call-side-judge-seq" to={{ hash: `#seq-${seq}` }}>
              #{seq}
            </Link>
          ))}
        </p>
      )}
    </div>
  );
}

// ── the tiles ─────────────────────────────────────────────────────────────────

function Tile({ label, value, sub }: { label: string; value: string; sub: string }): ReactNode {
  return (
    <div className="call-side-tile">
      <span className="call-side-tile-label">{label}</span>
      <span className="call-side-tile-value">{value}</span>
      <span className="call-side-tile-sub" title={sub}>
        {sub}
      </span>
    </div>
  );
}

/** How fast the agent answered, end to end, and under it how long it took to hear, to think and to start speaking. */
function Response({ latencies }: { latencies: Median[] }): ReactNode {
  const median = (name: string): number | undefined => latencies.find((one) => one.name === name)?.seconds;
  const e2e = median("e2e_latency");
  const hears = median("transcription_delay");
  const thinks = median("llm_node_ttft");
  const speaks = median("tts_node_ttfb");
  const parts = [
    hears === undefined ? null : `hears ${seconds(hears)}`,
    thinks === undefined ? null : `thinks ${seconds(thinks)}`,
    speaks === undefined ? null : `speaks ${seconds(speaks)}`,
  ].filter((part) => part !== null);
  return <Tile label="Response" value={e2e === undefined ? "—" : seconds(e2e)} sub={e2e === undefined ? "no turn was timed" : parts.join(" · ") || "median end to end"} />;
}

// Who ended the call, in a word, and what they did.
const ENDED_BY: Record<string, [string, string]> = {
  caller_hung_up: ["Caller", "hung up"],
  agent_hung_up: ["Agent", "hung up"],
  supervisor_ended: ["Supervisor", "ended it"],
  transferred: ["Transfer", "handed on"],
  no_answer: ["Nobody", "no answer"],
  busy: ["The line", "busy"],
  dial_failed: ["The dial", "failed"],
  timeout: ["Platform", "timed out"],
  drained: ["Platform", "drained"],
  app_detached: ["The app", "detached"],
  error: ["Platform", "an error"],
};

function Ended({ state, reason }: { state: State; reason: string }): ReactNode {
  const [who, did] = ENDED_BY[reason] ?? ["—", reason.replace(/_/g, " ")];
  return <Tile label="Ended by" value={who} sub={`${did} after ${duration(state)}`} />;
}

// What the bill went on, by the unit it was billed in: tokens are the model, characters the voice,
// audio seconds the transcription, and the line's own minutes the rest.
const PART_OF: Record<string, string> = {
  input_tokens: "LLM",
  cached_input_tokens: "LLM",
  cache_creation_tokens: "LLM",
  output_tokens: "LLM",
  characters: "voice",
  audio_seconds: "STT",
};

/** The bill's three largest parts, as shares of it: `LLM 64% · voice 17% · STT 14%`. */
function sharesOf(rows: readonly { unit: string; usd: number }[]): string {
  const total = rows.reduce((all, row) => all + row.usd, 0);
  if (total <= 0) return "nothing billed";
  const parts = new Map<string, number>();
  for (const row of rows) {
    const part = PART_OF[row.unit] ?? "line";
    parts.set(part, (parts.get(part) ?? 0) + row.usd);
  }
  return [...parts.entries()]
    .sort((one, other) => other[1] - one[1])
    .slice(0, 3)
    .map(([part, spent]) => `${part} ${Math.round((spent / total) * 100)}%`)
    .join(" · ");
}
