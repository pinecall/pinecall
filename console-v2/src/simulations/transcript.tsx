/** A simulated call as it is read: who said what, each of the agent's replies with how long it took, each tool as one line that unfolds. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { type Entry } from "@pinecall/core/wire/envelope";
import { Icon } from "../shell/icons";

/** One thing the log said that this page draws. */
export type Line =
  | { kind: "said"; id: string; who: "caller" | "agent"; text: string; seconds: number | null; cut: boolean }
  | { kind: "tool"; id: string; name: string; args: Record<string, unknown>; status: "running" | "ok" | "failed"; result: string | null; seconds: number | null }
  | { kind: "note"; id: string; text: string };

// How close to the end counts as reading the end: a person who scrolled up to read is left alone.
const NEAR_THE_END_PX = 80;
// An answer longer than this is drawn as its size, never as a page of text.
const A_LONG_ANSWER = 4000;

function written(value: unknown): string {
  return typeof value === "string" ? value : (JSON.stringify(value, null, 2) ?? String(value));
}

/** The line one entry of the log is worth here, or null when it is worth none. */
export function lineOf(entry: Entry): Line | null {
  const data = entry.data as Record<string, unknown>;
  switch (entry.type) {
    case "turn.user":
    case "turn.agent": {
      const text = typeof data["text"] === "string" ? data["text"].trim() : "";
      if (text === "") return null;
      const metrics = (data["metrics"] ?? {}) as Record<string, unknown>;
      const took = metrics["e2e_latency"] ?? metrics["llm_node_ttft"];
      return { kind: "said", id: `turn-${entry.seq}`, who: entry.type === "turn.user" ? "caller" : "agent", text, seconds: typeof took === "number" && took >= 0 ? took : null, cut: data["interrupted"] === true };
    }
    case "tool.call":
      return { kind: "tool", id: `tool-${String(data["call_id"])}`, name: String(data["name"]), args: (data["arguments"] as Record<string, unknown> | undefined) ?? {}, status: "running", result: null, seconds: null };
    case "tool.result": {
      const failed = data["error"] !== undefined && data["error"] !== null;
      const answer = failed ? data["error"] : (data["output"] ?? data["summary"] ?? "nothing");
      return { kind: "tool", id: `tool-${String(data["call_id"])}`, name: String(data["name"]), args: {}, status: failed ? "failed" : "ok", result: written(answer), seconds: typeof data["duration_s"] === "number" ? data["duration_s"] : null };
    }
    case "error":
      return { kind: "note", id: `note-${entry.seq}`, text: String(data["message"]) };
    default:
      return null;
  }
}

/** The lines with one more: a tool's result joins the line of its call, keeping what it was asked. */
export function withLine(lines: Line[], line: Line): Line[] {
  const at = lines.findIndex((one) => one.id === line.id);
  if (at === -1) return [...lines, line];
  return lines.map((was, index) => (index !== at ? was : was.kind === "tool" && line.kind === "tool" ? { ...line, args: was.args } : line));
}

function seconds(value: number): string {
  return value < 10 ? `${value.toFixed(1)} s` : `${Math.round(value)} s`;
}

function Tool({ line }: { line: Extract<Line, { kind: "tool" }> }): ReactNode {
  const [open, setOpen] = useState(false);
  const asked = Object.entries(line.args)
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(", ");
  const answer = line.result ?? "";
  return (
    <div className={`sim-tool sim-tool-${line.status}`}>
      <button type="button" className="sim-tool-head" aria-expanded={open} disabled={line.result === null} onClick={() => setOpen(!open)}>
        <Icon name="tools" size={13} />
        <span className="sim-tool-name">{line.name}</span>
        <span className="sim-tool-asked dash-clip">{asked}</span>
        <span className="sim-tool-went">{line.status === "running" ? "running…" : line.status === "failed" ? "failed" : line.seconds === null ? "done" : seconds(line.seconds)}</span>
      </button>
      {open && <pre className="sim-tool-answer">{answer.length > A_LONG_ANSWER ? `${answer.slice(0, A_LONG_ANSWER)}\n… ${answer.length - A_LONG_ANSWER} more characters` : answer}</pre>}
    </div>
  );
}

export function Transcript({ lines, agent, caller, after }: { lines: Line[]; agent: string; caller: string; after?: ReactNode }): ReactNode {
  const stream = useRef<HTMLDivElement>(null);
  const following = useRef(true);

  useEffect(() => {
    const box = stream.current;
    if (box && following.current) box.scrollTop = box.scrollHeight;
  }, [lines, after]);

  return (
    <div
      className="sim-stream"
      ref={stream}
      onScroll={(event) => {
        const box = event.currentTarget;
        following.current = box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_THE_END_PX;
      }}
    >
      <div className="sim-lines">
        {lines.map((line, index) => {
          if (line.kind === "tool") return <Tool key={line.id} line={line} />;
          if (line.kind === "note") {
            return (
              <p key={line.id} className="sim-note">
                {line.text}
              </p>
            );
          }
          // The speaker is named where it changes hands, not on every line.
          const before = lines.slice(0, index).filter((one) => one.kind === "said").at(-1);
          const named = before === undefined || before.kind !== "said" || before.who !== line.who;
          return (
            <div key={line.id} className={line.who === "caller" ? "sim-said sim-said-caller" : "sim-said"}>
              {named && <span className="sim-who">{line.who === "caller" ? caller : agent}</span>}
              <p className="sim-text">{line.text}</p>
              {line.who === "agent" && (line.seconds !== null || line.cut) && (
                <span className="sim-took">
                  {line.seconds !== null && `answered in ${seconds(line.seconds)}`}
                  {line.cut && <span className="sim-cut">cut off by the caller</span>}
                </span>
              )}
            </div>
          );
        })}
        {after}
      </div>
    </div>
  );
}
