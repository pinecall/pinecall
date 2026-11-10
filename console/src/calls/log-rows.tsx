/** The rows of the Transcript and the Log: a turn, a tool, a state change, a confirmation, a fact from outside, what a supervisor did, the entries nobody reads folded. */

import type { ReactNode } from "react";

import { blocksFor, headline, seconds, type Reading } from "@pinecall/core/metrics";
import { type EventSource } from "@pinecall/core/wire/defs";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type DocsSources, type MemoryOps, type StateCause } from "@pinecall/core/wire/events";
import { type CollectedMetrics, type Confirm, type ToolRun, type Turn } from "@pinecall/core/wire/state";

/** What sets the colour of a row's kind. */
export type Tone = "turn" | "tool" | "state" | "confirm" | "event" | "supervisor" | "handing" | "quiet" | "lookup";

// Units not drawn: the value itself says what it is.
const NOT_A_UNIT = new Set(["tag", "name", "id", "flag"]);

// Floats round to 3 decimals; the full value is in the hover title.
function rounded(value: string): string {
  return /^-?\d+\.\d{4,}$/.test(value) ? Number(value).toFixed(3) : value;
}

/** A metrics block field by field, under LiveKit's own names. */
export function Readings({ rows }: { rows: readonly Reading[] }): ReactNode {
  return (
    <div className="calls-readings">
      {rows.map((reading) => (
        <div key={reading.field} className="calls-reading">
          <span className="calls-reading-name dash-clip">{reading.field}</span>
          <span className="calls-reading-value" title={String(reading.value)}>
            {rounded(String(reading.value))}
            {reading.unit !== null && !NOT_A_UNIT.has(reading.unit) && <span className="dash-quiet"> {reading.unit}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

/** A row with children unfolds, the line being its summary. */
export function LogRow({ seq, kind, tone, who, said, note = [], children }: { seq: number | undefined; kind: string; tone: Tone; who?: "caller" | "agent" | undefined; said: ReactNode; note?: readonly ReactNode[]; children?: ReactNode }): ReactNode {
  const shown = note.filter((one) => one !== null && one !== undefined && one !== "");
  const line = (
    <>
      <span className="calls-log-seq">{seq}</span>
      <span className={`calls-kind calls-kind-${tone}`}>{kind}</span>
      <span className={tone === "turn" ? "calls-log-text calls-log-turn" : tone === "quiet" ? "calls-log-text dash-quiet" : "calls-log-text"}>
        {who !== undefined && <span className={who === "agent" ? "calls-log-who calls-log-who-agent" : "calls-log-who"}>{who === "agent" ? "Agent" : "Caller"}</span>}
        {said}
        {shown.length > 0 && (
          <span className="calls-log-note">
            {shown.map((one, index) => (
              <span key={index}>
                {index > 0 && " · "}
                {one}
              </span>
            ))}
          </span>
        )}
      </span>
    </>
  );
  if (children === undefined || children === null || children === false) {
    return (
      <div className="calls-log-row">
        <div className="calls-log-line">{line}</div>
      </div>
    );
  }
  return (
    <details className="calls-log-row">
      <summary className="calls-log-line">{line}</summary>
      <div className="calls-log-more">{children}</div>
    </details>
  );
}

const SHORT: Record<string, string> = { transcription_delay: "stt", end_of_turn_delay: "eot", llm_node_ttft: "ttft", tts_node_ttfb: "ttfb", e2e_latency: "e2e" };

/** Speaker, words, headline measures, and the full blocks joined to the turn; terse is the words alone. */
export function TurnRow({ turn, seq, metrics, terse }: { turn: Turn; seq: number; metrics: CollectedMetrics; terse: boolean }): ReactNode {
  const blocks = blocksFor(metrics, turn.speech_id);
  const measured = headline(turn).map((reading) => `${SHORT[reading.field] ?? reading.field} ${reading.value}`);
  const interrupted = turn.role === "agent" && turn.interrupted ? ["interrupted"] : [];
  const language = turn.role === "user" && turn.language !== undefined && turn.language !== null ? [turn.language] : [];
  const note = terse ? interrupted : turn.role === "user" ? [...measured, turn.speech_id, ...language] : [...measured, ...interrupted];
  return (
    <LogRow seq={seq} kind="turn" tone="turn" who={turn.role === "agent" ? "agent" : "caller"} said={turn.text} note={note}>
      {terse || blocks.length === 0
        ? null
        : blocks.map((block, index) => (
            <section key={`${block.kind}-${String(index)}`}>
              <h4 className="calls-block-name">metrics.{block.kind}</h4>
              <Readings rows={block.readings} />
            </section>
          ))}
    </LogRow>
  );
}

// Optional fields may be absent or null.
function there<T>(value: T): value is NonNullable<T> {
  return value !== undefined && value !== null;
}

function short(value: unknown): string {
  const said = typeof value === "string" ? value : JSON.stringify(value);
  return said === undefined ? "" : said.slice(0, 60);
}

/** A tool's arguments, and once it answered its output or error and how long it took. */
export function toolReadings(run: ToolRun): Reading[] {
  return [
    { field: "arguments", value: JSON.stringify(run.arguments, null, 2), unit: null },
    ...(there(run.output) ? [{ field: "output", value: JSON.stringify(run.output, null, 2), unit: null }] : []),
    ...(there(run.error) ? [{ field: "error", value: run.error, unit: null }] : []),
    ...(there(run.duration_s) ? [{ field: "duration_s", value: seconds(run.duration_s), unit: null }] : []),
  ];
}

/** Running until the result arrives, then the result or the error. */
export function ToolRow({ run, seq }: { run: ToolRun; seq: number }): ReactNode {
  const args = Object.entries(run.arguments)
    .map(([name, value]) => `${name}=${short(value)}`)
    .join(", ");
  const outcome = run.status === "running" ? "…" : (run.error ?? run.summary ?? short(run.output));
  return (
    <LogRow seq={seq} kind="tool" tone="tool" said={`${run.name}(${args})`} note={[<span className={run.status === "failed" ? "dash-mood-bad" : undefined}>{outcome}</span>]}>
      <Readings rows={toolReadings(run)} />
    </LogRow>
  );
}

function causeOf(cause: StateCause | null): string {
  if (cause === null) return "the app";
  if (cause.kind === "tool") return cause.tool;
  if (cause.kind === "event") return `${cause.name} (seq ${String(cause.seq)})`;
  return cause.hook === "on_call" ? "the start of the call" : "memory";
}

export function StateRow({ changed, cause, seq }: { changed: readonly string[]; cause: StateCause | null; seq: number }): ReactNode {
  return <LogRow seq={seq} kind="state" tone="state" said={`${changed.join(", ")} ← ${causeOf(cause)}`} />;
}

/** A confirmation asked of the caller, pending until granted or declined. */
export function ConfirmRow({ confirm, seq }: { confirm: Confirm; seq: number }): ReactNode {
  const rows: Reading[] = [
    { field: "tool", value: confirm.tool, unit: null },
    { field: "audience", value: confirm.audience, unit: null },
    ...(confirm.said == null ? [] : [{ field: "said", value: confirm.said, unit: null }]),
    ...(confirm.reason == null ? [] : [{ field: "reason", value: confirm.reason, unit: null }]),
  ];
  return (
    <LogRow seq={seq} kind="confirm" tone="confirm" said={confirm.phrase} note={[confirm.status]}>
      <Readings rows={rows} />
    </LogRow>
  );
}

/** A fact that reached the agent from outside the conversation. */
export function EventRow({ name, source, data, seq }: { name: string; source: EventSource; data: Record<string, unknown>; seq: number }): ReactNode {
  return (
    <LogRow seq={seq} kind="event" tone="event" said={name} note={[source]}>
      <pre className="calls-data">{JSON.stringify(data, null, 2)}</pre>
    </LogRow>
  );
}

/** A run of entries that are not the conversation, folded into one row. */
export function QuietRow({ entries }: { entries: readonly Entry[] }): ReactNode {
  return (
    <LogRow seq={entries[0]?.seq} kind="quiet" tone="quiet" said={entries.length === 1 ? "1 entry" : `${entries.length} entries`}>
      <ul className="calls-list">
        {entries.map((entry) => (
          <li key={`${String(entry.seq)}-${entry.type}`}>
            {entry.seq} {entry.type}
          </li>
        ))}
      </ul>
    </LogRow>
  );
}

function LookupRow({ kind, said, lines, seq }: { kind: string; said: string; lines: readonly string[]; seq: number }): ReactNode {
  return (
    <LogRow seq={seq} kind={kind} tone="lookup" said={said}>
      <ul className="calls-list">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </LogRow>
  );
}

function took(ms: number): string {
  return `${Math.round(ms)} ms`;
}

/** Facts recalled from memory, with how long the lookup took. */
export function MemoryRow({ ops, seq }: { ops: MemoryOps; seq: number }): ReactNode {
  const said = ops.ops.map((op) => `${op.op}, ${op.facts.length} facts, ${took(op.took_ms)}`).join("; ");
  const lines = ops.ops.flatMap((op) => op.facts.map((fact) => (fact.category ? `${fact.text} (${fact.category})` : fact.text)));
  return <LookupRow kind="memory" said={said} lines={lines} seq={seq} />;
}

/** Chunks retrieved from knowledge, with how long the lookup took. */
export function SourcesRow({ sources, seq }: { sources: DocsSources; seq: number }): ReactNode {
  const lines = sources.sources.map((source) => `${source.heading ? `${source.path} › ${source.heading}` : source.path}, ${source.score.toFixed(3)}`);
  return <LookupRow kind="sources" said={`${sources.sources.length} sources, ${took(sources.took_ms)}`} lines={lines} seq={seq} />;
}
