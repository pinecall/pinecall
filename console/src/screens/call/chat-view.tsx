/** A call read as a chat: the caller's words on the right, the agent's on the left, each tool one quiet line, the line's moves between them. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { BrokenBy } from "./broken-by";
import { brokenAt } from "./broken";
import { heardSoFar } from "./heard";
import { scoreIn } from "./over";
import { rowsOf } from "./timeline-rows";

// How close to the end counts as "reading the end": a person who scrolled up to read is left alone.
const NEAR_THE_END_PX = 80;

/** The conversation only — what was said and done — with the words being said as its last bubbles. */
export function ChatView({ entries, state, after }: { entries: Entry[]; state: State; after?: ReactNode }): ReactNode {
  const list = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const saying = state.live.agent;
  const heard = useMemo(() => heardSoFar(entries, state.live.user), [entries, state.live.user]);
  const rows = useMemo(() => rowsOf(entries, state), [entries, state]);
  const broken = useMemo(() => brokenAt(scoreIn(entries), rows), [entries, rows]);

  useEffect(() => {
    const box = list.current;
    if (box !== null && following.current) box.scrollTop = box.scrollHeight;
  }, [entries, heard, saying]);

  return (
    <div
      className="call-chat"
      ref={list}
      onScroll={(event) => {
        const box = event.currentTarget;
        following.current = box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_THE_END_PX;
      }}
    >
      <div className="call-chat-column">
        {rows.map((row) => {
          const broke = broken.get(row.seq);
          switch (row.kind) {
            case "turn":
              return (
                <div key={`t-${row.seq}`} className={broke === undefined ? "call-chat-said" : "call-chat-said call-chat-broken"}>
                  <Bubble who={row.turn.role === "agent" ? "agent" : "caller"} text={row.turn.text} />
                  {broke !== undefined && <BrokenBy broke={broke} />}
                </div>
              );
            case "tool":
              return (
                <div key={`x-${row.seq}`} className={broke === undefined ? "call-chat-said" : "call-chat-said call-chat-broken"}>
                  <div className="call-chat-tool">
                    <span className="call-chat-tool-name">{row.run.name}</span>
                    <span className={row.run.status === "failed" ? "call-chat-tool-bad" : row.run.status === "running" ? "call-chat-tool-running" : "call-chat-tool-ok"}>
                      {row.run.status === "failed" ? "✗ failed" : row.run.status === "running" ? "running…" : "✓"}
                    </span>
                  </div>
                  {broke !== undefined && <BrokenBy broke={broke} />}
                </div>
              );
            case "supervisor":
            case "line":
              return (
                <div key={`m-${row.seq}`} className="call-chat-note">
                  {row.mark.said}
                </div>
              );
            default:
              return null;
          }
        })}
        {heard !== null && <Bubble who="caller" text={heard} unsettled />}
        {saying !== null && <Bubble who="agent" text={saying} unsettled />}
        {after}
      </div>
    </div>
  );
}

function Bubble({ who, text, unsettled = false }: { who: "caller" | "agent"; text: string; unsettled?: boolean }): ReactNode {
  const classes = ["call-chat-bubble", who === "caller" ? "call-chat-caller" : "call-chat-agent"];
  if (unsettled) classes.push("call-chat-unsettled");
  return (
    <div className={who === "caller" ? "call-chat-line call-chat-line-caller" : "call-chat-line"}>
      <p className={classes.join(" ")}>{text}</p>
    </div>
  );
}
