/** A call read as a chat: the caller's words on the right, the agent's on the left, each under its seq and moment, each tool one card, the call's start and end as rules. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State, type ToolRun, type Turn } from "@pinecall/core/wire/state";
import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { elapsed } from "@pinecall/core/calls";
import { seconds } from "@pinecall/core/metrics";
import { Icon } from "../../ui";
import { type Broke, brokenAt } from "./broken";
import { heardSoFar } from "./heard";
import { scoreIn } from "./over";
import { rowsOf } from "./timeline-rows";
import "./chat.css";

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
  const loggedAt = useMemo(() => new Map(entries.map((entry) => [entry.seq, entry.ts])), [entries]);
  // A moment of the call, as the minutes and seconds since it started.
  const since = (at: number | undefined | null): string | null => (at === undefined || at === null || state.started_at === null ? null : elapsed(state.started_at, at));

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
        {state.started_at !== null && <Rule>Call started{state.channel === null ? "" : ` · ${state.channel}`}</Rule>}
        {rows.map((row) => {
          const broke = broken.get(row.seq);
          switch (row.kind) {
            case "turn":
              return (
                <Said key={`t-${row.seq}`} turn={row.turn} seq={row.seq} at={since(row.turn.metrics.started_speaking_at ?? loggedAt.get(row.seq))} broke={broke} />
              );
            case "tool":
              return <ToolCard key={`x-${row.seq}`} run={row.run} broke={broke} />;
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
        {state.status === "ended" && state.end_reason !== null && (
          <Rule>
            {sentence(state.end_reason)}
            {state.started_at !== null && state.ended_at !== null ? ` · ${elapsed(state.started_at, state.ended_at)}` : ""}
          </Rule>
        )}
        {after}
      </div>
    </div>
  );
}

/** One turn: the bubble, and under it its seq, its moment, how long the agent took to answer, and the judges that cite it. */
function Said({ turn, seq, at, broke }: { turn: Turn; seq: number; at: string | null; broke: readonly Broke[] | undefined }): ReactNode {
  const who = turn.role === "agent" ? "agent" : "caller";
  const answer = turn.role === "agent" ? turn.metrics.e2e_latency : null;
  return (
    <div className={who === "caller" ? "call-chat-said call-chat-said-caller" : "call-chat-said"}>
      <Bubble who={who} text={turn.text} broken={broke !== undefined} />
      <div className="call-chat-meta">
        <span>
          #{seq}
          {at !== null && ` · ${at}`}
        </span>
        {turn.role === "agent" && <span>{answer === null || answer === undefined ? "—" : seconds(answer)}</span>}
        {broke !== undefined && <Cited broke={broke} />}
      </div>
    </div>
  );
}

/** A tool the agent ran, as a card: its name, what it came back with, and how long it took. */
function ToolCard({ run, broke }: { run: ToolRun; broke: readonly Broke[] | undefined }): ReactNode {
  const outcome = run.status === "running" ? "running…" : (run.error ?? run.summary ?? (run.status === "failed" ? "failed" : "done"));
  return (
    <div className="call-chat-said">
      <div className={broke === undefined ? "call-chat-tool" : "call-chat-tool call-chat-tool-broken"}>
        <span className="call-chat-tool-icon" aria-hidden>
          <Icon name={run.name.startsWith("memory.") ? "memory" : "plug"} size={15} />
        </span>
        <span className="call-chat-tool-name">{run.name}</span>
        <span className={run.status === "failed" ? "call-chat-tool-said call-chat-tool-bad" : run.status === "running" ? "call-chat-tool-said call-chat-tool-running" : "call-chat-tool-said"}>
          {outcome}
        </span>
        {run.duration_s !== undefined && run.duration_s !== null && <span className="call-chat-tool-took">{seconds(run.duration_s)}</span>}
      </div>
      {broke !== undefined && (
        <div className="call-chat-meta">
          <Cited broke={broke} />
        </div>
      )}
    </div>
  );
}

/** The judges that broke on a line, by name; why each did is what the name says on hover. */
function Cited({ broke }: { broke: readonly Broke[] }): ReactNode {
  return (
    <span className="call-chat-cited" title={broke.map((one) => `${one.judge}: ${one.reason}`).join("\n")}>
      cited by {broke.map((one) => one.judge).join(", ")}
    </span>
  );
}

function Bubble({ who, text, unsettled = false, broken = false }: { who: "caller" | "agent"; text: string; unsettled?: boolean; broken?: boolean }): ReactNode {
  const classes = ["call-chat-bubble", who === "caller" ? "call-chat-caller" : "call-chat-agent"];
  if (unsettled) classes.push("call-chat-unsettled");
  if (broken) classes.push("call-chat-bubble-broken");
  return (
    <div className={who === "caller" ? "call-chat-line call-chat-line-caller" : "call-chat-line"}>
      <p className={classes.join(" ")}>{text}</p>
    </div>
  );
}

/** A moment of the call between two rules: where it started, how it ended. */
function Rule({ children }: { children: ReactNode }): ReactNode {
  return <div className="call-chat-rule">{children}</div>;
}

// `caller_hung_up` → `Caller hung up`.
function sentence(reason: string): string {
  const words = reason.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
