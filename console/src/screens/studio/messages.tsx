/** The conversation of the Try-it chat as bubbles: the caller's on the right, the agent's on the left, a tool as a card between them — whether a person wrote it in the room or a model played it in a call. */

import { useEffect, useRef, type ReactNode } from "react";

import { Icon } from "../../ui";
import type { Row } from "../call";
import type { Line } from "../talk";

/** One thing on screen: what was said, a tool the agent ran, or a word of the log's. */
export type Message =
  | { kind: "said"; id: string; who: "caller" | "agent"; text: string; unsettled: boolean }
  | { kind: "tool"; id: string; name: string; says: string; bad: boolean; seconds: number | null }
  | { kind: "note"; id: string; text: string };

/** The room's lines: a written one waits dimmed until the log carries it, a spoken one until the ear settles it. */
export function fromRoom(lines: readonly Line[]): Message[] {
  return lines.map((line): Message => {
    if (line.kind === "said") return { kind: "said", id: line.id, who: line.speaker === "user" ? "caller" : "agent", text: line.text, unsettled: !line.final || line.pending === true };
    if (line.kind === "tool") return { kind: "tool", id: line.id, name: line.name, says: line.status === "running" ? "running…" : (line.result ?? (line.status === "failed" ? "failed" : "done")), bad: line.status === "failed", seconds: line.seconds };
    return { kind: "note", id: line.id, text: line.text };
  });
}

/** A call's rows, as a model played it: the turns, the tools, and what a person did on the line. */
export function fromCall(rows: readonly Row[]): Message[] {
  return rows.flatMap((row): Message[] => {
    if (row.kind === "turn") return [{ kind: "said", id: `t-${String(row.seq)}`, who: row.turn.role === "agent" ? "agent" : "caller", text: row.turn.text, unsettled: false }];
    if (row.kind === "tool") {
      const run = row.run;
      return [{ kind: "tool", id: `x-${String(row.seq)}`, name: run.name, says: run.status === "running" ? "running…" : (run.error ?? run.summary ?? (run.status === "failed" ? "failed" : "done")), bad: run.status === "failed", seconds: run.duration_s ?? null }];
    }
    if (row.kind === "supervisor" || row.kind === "line") return [{ kind: "note", id: `m-${String(row.seq)}`, text: row.mark.said }];
    return [];
  });
}

export function Messages({ messages, empty }: { messages: readonly Message[]; empty: ReactNode }): ReactNode {
  const list = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = list.current;
    if (box !== null) box.scrollTop = box.scrollHeight;
  }, [messages]);
  return (
    <div className="sto-msgs" ref={list}>
      {messages.length === 0 ? (
        empty
      ) : (
        messages.map((one) => {
          if (one.kind === "note") return <div key={one.id} className="sto-msg-note">{one.text}</div>;
          if (one.kind === "tool") {
            return (
              <div key={one.id} className={one.bad ? "sto-msg-tool sto-msg-tool-bad" : "sto-msg-tool"}>
                <span className="sto-msg-tool-icon" aria-hidden>
                  <Icon name={one.name.startsWith("memory.") ? "memory" : "plug"} size={14} />
                </span>
                <span className="sto-msg-tool-name">{one.name}</span>
                <span className="sto-msg-tool-says">{one.says}</span>
                {one.seconds !== null && <span className="sto-msg-tool-took">{Math.round(one.seconds * 1000)} ms</span>}
              </div>
            );
          }
          return (
            <div key={one.id} className={one.who === "caller" ? "sto-msg sto-msg-caller" : "sto-msg"}>
              <p className={one.unsettled ? "sto-bubble sto-bubble-unsettled" : "sto-bubble"}>{one.text}</p>
            </div>
          );
        })
      )}
    </div>
  );
}
