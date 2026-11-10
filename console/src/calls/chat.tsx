/** A call read as a chat: the caller's words on the right, the agent's on the left, each tool one line, the words in progress last; a line's time plays the recording from there. */

import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { elapsed } from "@pinecall/core/calls";
import { seconds } from "@pinecall/core/metrics";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { type State, type ToolRun, type Turn } from "@pinecall/core/wire/state";
import { Icon } from "../shell/icons";
import { type Broke, brokenAt } from "./broken";
import { sentence } from "./format";
import { heardSoFar } from "./heard";
import { rowsOf } from "./timeline-rows";

// How close to the end counts as reading the end: a person who scrolled up to read is left alone.
const NEAR_THE_END_PX = 80;

// A median of one or two replies says nothing about what is usual.
const FEWEST_REPLIES_TO_COMPARE = 3;
// Slow means twice the usual reply and a full second over it: on a fast agent, twice is still nothing a caller notices.
const SLOW_TIMES = 2;
const SLOW_OVER_S = 1;

/** The middle of this call's reply times, or null when too few were timed to call one slow. */
function usualReply(turns: readonly Turn[]): number | null {
  const timed = turns
    .flatMap((turn) => (turn.role === "agent" && typeof turn.metrics.e2e_latency === "number" && turn.metrics.e2e_latency >= 0 ? [turn.metrics.e2e_latency] : []))
    .sort((one, other) => one - other);
  if (timed.length < FEWEST_REPLIES_TO_COMPARE) return null;
  const half = Math.floor(timed.length / 2);
  const above = timed[half] ?? 0;
  return timed.length % 2 === 1 ? above : ((timed[half - 1] ?? 0) + above) / 2;
}

export function ChatView({ entries, state, score, onSeek }: { entries: Entry[]; state: State; score: CallScore | null; /** Plays the recording from a moment of the call, once there is one to play. */ onSeek: ((at: number) => void) | undefined }): ReactNode {
  const list = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const saying = state.live.agent;
  const heard = useMemo(() => heardSoFar(entries, state.live.user), [entries, state.live.user]);
  const rows = useMemo(() => rowsOf(entries, state), [entries, state]);
  const broken = useMemo(() => brokenAt(score, rows), [score, rows]);
  const loggedAt = useMemo(() => new Map(entries.map((entry) => [entry.seq, entry.ts])), [entries]);
  const usual = useMemo(() => usualReply(state.turns), [state.turns, state.seq]);
  const began = state.started_at;

  useEffect(() => {
    const box = list.current;
    if (box !== null && following.current) box.scrollTop = box.scrollHeight;
  }, [entries, heard, saying]);

  const nothing = rows.every((row) => row.kind !== "turn" && row.kind !== "tool") && heard === null && saying === null;

  return (
    <div
      className="calls-scroll"
      ref={list}
      onScroll={(event) => {
        const box = event.currentTarget;
        following.current = box.scrollHeight - box.scrollTop - box.clientHeight < NEAR_THE_END_PX;
      }}
    >
      <div className="calls-chat">
        {began !== null && <div className="calls-rule">Call started{state.channel === null ? "" : `, ${state.channel}`}</div>}
        {nothing && state.status !== "idle" && <p className="dash-quiet calls-chat-nothing">{state.status === "ended" ? "Nothing was said on this call." : "Nothing said yet. The words show up here the moment somebody speaks."}</p>}
        {rows.map((row) => {
          const broke = broken.get(row.seq);
          switch (row.kind) {
            case "turn": {
              const spokeAt = row.turn.metrics.started_speaking_at;
              const logged = spokeAt ?? loggedAt.get(row.seq);
              return <Said key={`t-${row.seq}`} turn={row.turn} seq={row.seq} at={logged === undefined || began === null ? null : elapsed(began, logged)} seek={typeof spokeAt === "number" && began !== null && onSeek !== undefined ? () => onSeek(Math.max(0, spokeAt - began)) : undefined} usual={usual} broke={broke} />;
            }
            case "tool":
              return <ToolLine key={`x-${row.seq}`} run={row.run} seq={row.seq} broke={broke} />;
            case "supervisor":
            case "line":
              return (
                <div key={`m-${row.seq}`} className="calls-chat-note">
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
          <div className="calls-rule">
            {sentence(state.end_reason)}
            {began !== null && state.ended_at !== null ? `, ${elapsed(began, state.ended_at)}` : ""}
          </div>
        )}
      </div>
    </div>
  );
}

/** One turn: the bubble, and under it its seq, its moment, how long the agent took to answer, and the judges that cite it. */
function Said({ turn, seq, at, seek, usual, broke }: { turn: Turn; seq: number; at: string | null; seek: (() => void) | undefined; usual: number | null; broke: readonly Broke[] | undefined }): ReactNode {
  const who = turn.role === "agent" ? "agent" : "caller";
  const answer = turn.role === "agent" ? turn.metrics.e2e_latency : null;
  const timed = typeof answer === "number" && answer >= 0;
  const slow = timed && usual !== null && answer >= usual * SLOW_TIMES && answer - usual >= SLOW_OVER_S;
  return (
    <div className={who === "caller" ? "calls-said calls-said-caller" : "calls-said"} data-seq={seq}>
      <Bubble who={who} text={turn.text} broken={broke !== undefined} />
      <div className="calls-meta">
        <span>#{seq}</span>
        {at !== null &&
          (seek !== undefined ? (
            <button type="button" className="calls-seek" title="Play the recording from here" onClick={seek}>
              {at}
            </button>
          ) : (
            <span>{at}</span>
          ))}
        {turn.role === "agent" && (
          <span className={slow ? "dash-mood-warn" : undefined} title={slow && usual !== null ? `Much slower than this call's usual reply, ${seconds(usual)}` : undefined}>
            {timed ? seconds(answer) : "—"}
          </span>
        )}
        {turn.role === "agent" && turn.interrupted && <span className="dash-mood-warn">Cut off by the caller</span>}
        {broke !== undefined && <Cited broke={broke} />}
      </div>
    </div>
  );
}

/** A tool the agent ran: its name, what it came back with, how long it took. */
function ToolLine({ run, seq, broke }: { run: ToolRun; seq: number; broke: readonly Broke[] | undefined }): ReactNode {
  const outcome = run.status === "running" ? "Running…" : (run.error ?? run.summary ?? (run.status === "failed" ? "Failed" : "Done"));
  return (
    <div className="calls-said calls-said-tool" data-seq={seq}>
      <div className={broke === undefined ? "calls-tool" : "calls-tool calls-tool-broken"}>
        <Icon name={run.name.startsWith("memory.") ? "brain" : "tools"} size={13} />
        <span className="calls-tool-name">{run.name}</span>
        <span className={run.status === "failed" ? "calls-tool-said dash-clip dash-mood-bad" : run.status === "running" ? "calls-tool-said dash-clip dash-mood-warn" : "calls-tool-said dash-clip"} title={outcome}>
          {outcome}
        </span>
        {run.duration_s !== undefined && run.duration_s !== null && <span className="calls-tool-took">{seconds(run.duration_s)}</span>}
      </div>
      {broke !== undefined && (
        <div className="calls-meta">
          <Cited broke={broke} />
        </div>
      )}
    </div>
  );
}

/** The judges that broke on a line, by name; why each did is what the name says on hover. */
function Cited({ broke }: { broke: readonly Broke[] }): ReactNode {
  return (
    <span className="dash-mood-bad" title={broke.map((one) => `${one.judge}: ${one.reason}`).join("\n")}>
      Cited by {broke.map((one) => one.judge).join(", ")}
    </span>
  );
}

function Bubble({ who, text, unsettled = false, broken = false }: { who: "caller" | "agent"; text: string; unsettled?: boolean; broken?: boolean }): ReactNode {
  const classes = ["calls-bubble", who === "caller" ? "calls-bubble-caller" : "", unsettled ? "calls-bubble-unsettled" : "", broken ? "calls-bubble-broken" : ""].join(" ");
  return (
    <div className={who === "caller" ? "calls-line calls-line-caller" : "calls-line"}>
      <p className={classes}>
        {text}
        {unsettled && <span className="calls-caret" aria-hidden="true" />}
      </p>
    </div>
  );
}
