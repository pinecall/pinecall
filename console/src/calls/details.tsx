/** The panel docked beside a call: the desk while it is live; then what it came to, each judge, how fast, what it cost, the models, the person's other calls, and what to do with it. */

import type { ReactNode } from "react";
import { Link } from "react-router";

import { seconds, type Median } from "@pinecall/core/metrics";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { type State } from "@pinecall/core/wire/state";
import { lengthOf } from "../lib/format";
import { SidePanel } from "../ui/side-panel";
import { Actions } from "./actions";
import { Desk, type OnTheLine } from "./desk";
import { dayOf, usd } from "./format";
import { Judges } from "./judges";
import { Models } from "./models";
import { Proofs } from "./proofs";
import type { Thread } from "./threads";
import { TraceStep } from "./trace";
import type { TraceBar } from "./trace-bars";
import type { WatchedCall } from "./use-watched-call";

function Tile({ label, value, sub }: { label: string; value: string; sub: string }): ReactNode {
  return (
    <div className="calls-tile">
      <span className="dash-quiet">{label}</span>
      <span className="calls-tile-value dash-clip">{value}</span>
      <span className="calls-tile-sub dash-clip" title={sub}>
        {sub}
      </span>
    </div>
  );
}

/** How fast the agent answered, end to end, and under it how long it took to hear, to think and to start speaking. */
function Response({ latencies }: { latencies: readonly Median[] }): ReactNode {
  const median = (name: string): number | undefined => latencies.find((one) => one.name === name)?.seconds;
  const e2e = median("e2e_latency");
  const hears = median("transcription_delay");
  const thinks = median("llm_node_ttft");
  const speaks = median("tts_node_ttfb");
  const parts = [hears === undefined ? null : `hears ${seconds(hears)}`, thinks === undefined ? null : `thinks ${seconds(thinks)}`, speaks === undefined ? null : `speaks ${seconds(speaks)}`].filter((part) => part !== null);
  return <Tile label="Response" value={e2e === undefined ? "—" : seconds(e2e)} sub={e2e === undefined ? "No turn was timed" : parts.join(", ") || "Median end to end"} />;
}

// What the bill went on, by the unit it was billed in: tokens are the model, characters the voice, audio seconds the transcription, the line's own minutes the rest.
const PART_OF: Record<string, string> = { input_tokens: "LLM", cached_input_tokens: "LLM", cache_creation_tokens: "LLM", output_tokens: "LLM", characters: "voice", audio_seconds: "STT" };

/** The bill's three largest parts, as shares of it: `LLM 64%, voice 17%, STT 14%`. */
function sharesOf(rows: readonly { unit: string; usd: number }[]): string {
  const total = rows.reduce((all, row) => all + row.usd, 0);
  if (total <= 0) return "Nothing billed";
  const parts = new Map<string, number>();
  for (const row of rows) {
    const part = PART_OF[row.unit] ?? "line";
    parts.set(part, (parts.get(part) ?? 0) + row.usd);
  }
  return [...parts.entries()]
    .sort((one, other) => other[1] - one[1])
    .slice(0, 3)
    .map(([part, spent]) => `${part} ${Math.round((spent / total) * 100)}%`)
    .join(", ");
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

function Tiles({ state, latencies }: { state: State; latencies: readonly Median[] }): ReactNode {
  const over = state.status === "ended";
  const [who, did] = ENDED_BY[state.end_reason ?? ""] ?? ["—", (state.end_reason ?? "").replace(/_/g, " ")];
  return (
    <section className="calls-tiles" aria-label="The call, in numbers">
      <Response latencies={latencies} />
      {state.cost !== null && state.cost.rows.length > 0 && <Tile label="Cost" value={usd(state.cost.usd)} sub={sharesOf(state.cost.rows)} />}
      <Tile label="Turns" value={String(state.turns.length)} sub={`Caller ${state.turns.filter((turn) => turn.role === "user").length}, agent ${state.turns.filter((turn) => turn.role === "agent").length}`} />
      {over && state.end_reason !== null && <Tile label="Ended by" value={who} sub={`${did}, after ${lengthOf(state.started_at, state.ended_at)}`} />}
    </section>
  );
}

function OtherCalls({ person, shown, search }: { person: Thread; shown: string; search: string }): ReactNode {
  const others = person.lines.filter((line) => line.call !== shown);
  if (others.length === 0) return null;
  return (
    <section className="calls-part" aria-label="Their other conversations">
      <span className="dash-eyebrow">Their other conversations</span>
      <div className="calls-others">
        {others.map((line) => (
          <Link key={line.call} to={`/calls/${encodeURIComponent(line.call)}${search}`} className="calls-other">
            <span className="calls-other-top">
              <span>{line.started_at === null ? line.call : dayOf(line.started_at)}</span>
              <span className="dash-quiet dash-clip">
                {line.agent}, {line.channel ?? "—"}, {line.status === "ended" ? lengthOf(line.started_at, line.ended_at) : "on the line now"}
              </span>
            </span>
            {line.outcome !== null && line.outcome !== "" && <span className="dash-quiet dash-clip">{line.outcome}</span>}
          </Link>
        ))}
      </div>
    </section>
  );
}

export function DetailsPanel({
  call,
  watched,
  score,
  latencies,
  step,
  onLetGo,
  line,
  live,
  spoken,
  supervises,
  person,
  search,
  onCite,
  onJudged,
  onClose,
}: {
  call: string;
  watched: WatchedCall;
  score: CallScore | null;
  latencies: readonly Median[];
  /** A bar picked in the trace: what the reader is looking at, so it comes first. */
  step: TraceBar | undefined;
  onLetGo: () => void;
  line: OnTheLine;
  live: boolean;
  spoken: boolean;
  supervises: boolean;
  person: Thread | undefined;
  search: string;
  onCite: (seq: number) => void;
  onJudged: (score: CallScore) => void;
  onClose: () => void;
}): ReactNode {
  const { state, entries } = watched;
  const over = state.status === "ended";
  const number = (state.direction === "outbound" ? state.to : state.from) ?? null;
  return (
    // Escape belongs to the desk's fields here, and a stray one must not fold a call being worked.
    <SidePanel title="Details" icon="quality" width={420} closesOnEscape={false} onClose={onClose}>
      {step !== undefined && <TraceStep bar={step} onClose={onLetGo} />}
      {live && supervises && <Desk line={line} spoken={spoken} asked={state.attention ?? null} />}
      {over && (
        <section className="calls-part" aria-label="What it came to">
          <span className="dash-eyebrow">Outcome</span>
          <p className="calls-outcome">{state.outcome ?? "The call left no outcome sentence."}</p>
        </section>
      )}
      {over && <Judges score={score} onCite={onCite} />}
      <Tiles state={state} latencies={latencies} />
      <Models call={call} state={state} entries={entries} />
      {person !== undefined && <OtherCalls person={person} shown={call} search={search} />}
      {over && <Proofs state={state} entries={entries} />}
      {over && <Actions agent={state.agent || person?.latest.agent || ""} call={call} number={number} onJudged={onJudged} />}
    </SidePanel>
  );
}
