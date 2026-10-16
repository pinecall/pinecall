/** Inspector: live metrics, turns, tools and state of one call, read from its log. */

import { type State, type Turn } from "@pinecall/core/wire/state";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { usd } from "../../lib/format";
import { medians, seconds } from "@pinecall/core/metrics";
import type { Connection } from "@pinecall/core/stream";
import { useOrg } from "../../lib/org";
import { Pill, SectionLabel, Tabs } from "../../ui";
import { useWatchedCall } from "../call/use-watched-call";
import "./inspector.css";

/** Side pane for Talk and Chat: this tab's call, or the agent's last call before one starts. */
export function Inspector({ agent, call }: { agent: string; call: string | null }): ReactNode {
  const { lines } = useOrg();
  const last = lines.find((line) => line.agent === agent)?.call ?? null;
  const shown = call ?? last;
  return (
    <aside className="inspector" aria-label="Inspector">
      {shown === null ? (
        <>
          <InspectorHead connection={null} />
          <p className="inspector-quiet">Nothing to read yet: the first call this agent takes is read here as it happens.</p>
        </>
      ) : (
        <Reading key={shown} call={shown} yours={call !== null} />
      )}
    </aside>
  );
}

function InspectorHead({ connection }: { connection: Connection | null }): ReactNode {
  return (
    <div className="inspector-head">
      <span className="inspector-title">Inspector</span>
      <span className="inspector-standing">{standing(connection)}</span>
    </div>
  );
}

function standing(connection: Connection | null): ReactNode {
  switch (connection) {
    case "live":
      return <Pill tone="green">reading the log</Pill>;
    case "connecting":
      return <Pill tone="muted">opening the log</Pill>;
    case "reconnecting":
      return <Pill tone="amber">reconnecting</Pill>;
    case "ended":
      return <Pill tone="muted">call ended</Pill>;
    default:
      return <Pill tone="muted">no call yet</Pill>;
  }
}

type Tab = "call" | "turns" | "tools" | "state";

function Reading({ call, yours }: { call: string; yours: boolean }): ReactNode {
  const [tab, setTab] = useState<Tab>("call");
  const watched = useWatchedCall(call);
  const { state } = watched;
  const seen = new Set<number>();
  // Dedupe by seq: a log re-read from the start repeats entries.
  const measured = medians(watched.entries.filter((entry) => (seen.has(entry.seq) ? false : (seen.add(entry.seq), true))));
  const median = (name: string): string => {
    const found = measured.find((one) => one.name === name);
    return found === undefined ? "—" : seconds(found.seconds);
  };
  const tokens = tokensOf(state);
  // Latencies are medians, labelled as on the call's latency card.
  const figures: [string, string][] = [
    ["Turns", String(state.turns.length)],
    ["Cost", usd(state.cost?.usd)],
    ["First token", median("llm_node_ttft")],
    ["End to end", median("e2e_latency")],
    ["Tokens in", grouped(tokens.in)],
    ["Tokens out", grouped(tokens.out)],
  ];
  const fields = Object.keys(state.app_state).sort();

  const tabs = [
    { tab: "call" as const, name: "Call" },
    { tab: "turns" as const, name: "Turns", mark: <span className="inspector-count">{state.turns.length}</span> },
    { tab: "tools" as const, name: "Tools", mark: <span className="inspector-count">{state.tools.length}</span> },
    { tab: "state" as const, name: "State" },
  ];

  return (
    <>
      <InspectorHead connection={watched.connection} />
      <div className="inspector-tabs">
        <Tabs label="Inspector" tabs={tabs} on={tab} onPick={setTab} />
      </div>

      {tab === "call" && (
        <>
          <SectionLabel>{yours ? "This session" : "Last session"}</SectionLabel>
          <div className="inspector-figures">
            {figures.map(([label, value]) => (
              <div key={label} className="inspector-tile">
                <div className="inspector-figure-label">{label}</div>
                <div className="inspector-figure">{value}</div>
              </div>
            ))}
          </div>
          {!yours && (
            <Link to={`/calls/${call}`} className="inspector-call" title={call}>
              <span className="inspector-call-id ui-fixed ui-clip">{call}</span>
              <span className="inspector-call-open">Open call →</span>
            </Link>
          )}
        </>
      )}

      {tab === "turns" && (
        <div className="inspector-turns">
          {state.turns.length === 0 && <p className="inspector-none">No turn yet.</p>}
          {state.turns.map((turn, index) => (
            <div className="inspector-turn" key={`${turn.speech_id}-${index}`}>
              <span className={turn.role === "agent" ? "inspector-who inspector-who-agent" : "inspector-who"}>{turn.role === "agent" ? "agent" : "caller"}</span>
              <span className="inspector-turn-body">
                <span className="inspector-turn-text">{turn.text}</span>
                <span className="inspector-turn-meta">{metaOf(turn)}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {tab === "tools" && (
        <div className="inspector-tools">
          {state.tools.length === 0 && <p className="inspector-none">No tool has run.</p>}
          {state.tools.map((run) => (
            <div className="inspector-tool" key={run.call_id}>
              <div className="inspector-tool-name">{run.name}</div>
              <div className="inspector-tool-args">{argumentsOf(run.arguments)}</div>
              <div className={run.status === "failed" ? "inspector-tool-result inspector-tool-failed" : run.status === "running" ? "inspector-tool-result inspector-tool-running" : "inspector-tool-result"}>
                {run.status === "failed" ? (run.error ?? "failed") : run.status === "running" ? "running…" : `ok${run.summary ? ` · ${run.summary}` : ""}`}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "state" && (
        <div className="inspector-state">
          {fields.length === 0 && <p className="inspector-none">The app has declared no state yet.</p>}
          {fields.map((name) => (
            <div className="inspector-field" key={name}>
              <span className="inspector-field-key">{name}</span>
              <span className="inspector-field-value">{said(state.app_state[name])}</span>
            </div>
          ))}
        </div>
      )}
      {watched.error !== null && <p className="inspector-refused">{watched.error}</p>}
    </>
  );
}

// Per-turn latencies: agent ("ttft · e2e") and caller ("stt · speech id").
function metaOf(turn: Turn): string {
  if (turn.role === "agent") {
    const parts: string[] = [];
    if (typeof turn.metrics.llm_node_ttft === "number") parts.push(`ttft ${seconds(turn.metrics.llm_node_ttft)}`);
    if (typeof turn.metrics.e2e_latency === "number") parts.push(`e2e ${seconds(turn.metrics.e2e_latency)}`);
    if (turn.interrupted) parts.push("interrupted");
    return parts.join(" · ");
  }
  const parts: string[] = [];
  if (typeof turn.metrics.transcription_delay === "number") parts.push(`stt ${seconds(turn.metrics.transcription_delay)}`);
  parts.push(turn.speech_id);
  return parts.join(" · ");
}

// Input tokens include cached ones (still context); output tokens separately.
function tokensOf(state: State): { in: number; out: number } {
  let read = 0;
  let wrote = 0;
  for (const row of state.usage) {
    if (row.type !== "llm_usage") continue;
    read += (row.input_tokens ?? 0) + (row.input_cached_tokens ?? 0);
    wrote += row.output_tokens ?? 0;
  }
  return { in: read, out: wrote };
}

function grouped(count: number): string {
  return count.toLocaleString("en-US").replace(/,/g, " ");
}

function argumentsOf(values: Record<string, unknown>): string {
  const pairs = Object.entries(values).map(([key, value]) => `${key}=${said(value)}`);
  return pairs.length === 0 ? "no arguments" : pairs.join(" · ");
}

function said(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}
