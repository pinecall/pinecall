/** One call: who is on it, the log as it arrives, and beside them the desk on a live call or the reading of a finished one. */

import { type Entry } from "@pinecall/core/wire/envelope";
import { type State } from "@pinecall/core/wire/state";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { elapsed, isSpoken, prettyNumber } from "@pinecall/core/calls";
import { medians } from "@pinecall/core/metrics";
import { keepCallView, keptCallView, type CallView } from "../../lib/preferences";
import { useScopes } from "../../lib/whoami";
import { visitorOf } from "../../lib/format";
import { Avatar, ButtonLink, Pill, usePane } from "../../ui";
import { Desk } from "./desk";
import { Actions, CostCard, Details, LatencyCard, Outcome, Player, recordingIn, ScoreCard, scoreIn, timeSpentIn } from "./over";
import { ChatView } from "./chat-view";
import { Timeline } from "./timeline";
import { traceOf } from "./trace-bars";
import { TraceStep } from "./trace-step";
import { TraceView } from "./trace-view";
import { useWatchedCall } from "./use-watched-call";
import "./call.css";

// Everything on screen comes out of this one hook, so two calls side by side are two streams, two
// states and two timelines. The log is read from its first entry and followed to its last, live or
// not: a call that ends is the same page, with nothing more arriving.
/** A whole call, live or over. Mounting it opens the stream; leaving closes it. */
export function Call({
  call,
  agent,
  supervised = true,
  name,
  beside,
  foot,
  aside,
}: {
  call: string;
  agent?: string | undefined;
  /** Whether the supervisor's desk may be drawn here. A simulation is stopped, not whispered to. */
  supervised?: boolean;
  /** Who is on the call as the screen mounting it knows them — a name somebody wrote down — over what its log says. */
  name?: string | undefined;
  /** One more control in the call's head, told whether the call is over. */
  beside?: ((over: boolean) => ReactNode) | undefined;
  /** Under the log: the screen that mounts the call may put a composer there. */
  foot?: ReactNode | undefined;
  /** After the call's own panels in the pane: what the screen that mounts the call knows besides. */
  aside?: ReactNode | undefined;
}): ReactNode {
  const watched = useWatchedCall(call);
  const state = watched.state;
  const scopes = useScopes();
  const over = state.status === "ended";
  const recorded = recordingIn(summaryOf(watched.entries));
  // A thread — the widget's chat, WhatsApp — is not spoken, and the desk over it neither listens
  // nor opens a microphone. The widget's chat has a room too, so core's rule reads the caller's seat.
  const spoken = isSpoken(state);
  // A key that does not open `supervise` is refused every move: the desk is not drawn for it.
  const supervises = supervised && (scopes === null || scopes.includes("supervise"));
  const read = useMemo(
    () => ({ latencies: medians(watched.entries), score: scoreIn(watched.entries), spent: timeSpentIn(watched.entries, state) }),
    [watched.entries, state],
  );

  const pane = usePane({ name: "call.pane", initial: 360, min: 280, max: 640, side: "right" });
  // Four ways to read the same call: as a chat — the bubbles, the tools as one line each — as the
  // transcript, as the whole log with every number, or as a trace of its stages on a time axis. The
  // one a person picked is the one the next call opens in; the chat is where a person who never picked starts.
  const [view, setView] = useState<CallView>(() => keptCallView() ?? "chat");
  const pick = (chosen: CallView): void => {
    setView(chosen);
    keepCallView(chosen);
  };
  // The trace is folded only while it is read, and the bar picked in it is shown in the pane by id,
  // so a live call's next update shows the same bar with what has come in since.
  const trace = useMemo(() => (view === "trace" ? traceOf(watched.entries, state) : null), [view, watched.entries, state]);
  const [picked, setPicked] = useState<string | null>(null);
  const step = trace?.rows.flatMap((row) => row.bars).find((bar) => bar.id === picked);
  // Everything the call holds is a page of its own, outside the shell, so the pane keeps what is read at a glance.
  const page = `/calls/${encodeURIComponent(call)}/show`;

  // What closes the conversation, however it is read: the recording, and on a call that is over its details.
  const theEnd = (
    <>
      {recorded !== null && <Recorded call={call} />}
      {over && (
        <div className="call-foot">
          <Details state={state} entries={watched.entries} beside={<Actions agent={state.agent || agent || ""} call={call} number={(state.direction === "outbound" ? state.to : state.from) ?? null} />} />
        </div>
      )}
    </>
  );

  return (
    <div className="call" style={pane.style}>
      {pane.handle}
      <div className="call-middle">
        <Head call={call} agent={agent} name={name} state={state} connection={watched.connection} failed={watched.error}>
          <span className="call-view" role="group" aria-label="how the call is read">
            {(["chat", "transcript", "log", "trace"] as const).map((one) => (
              <button key={one} type="button" className={view === one ? "call-view-one call-view-on" : "call-view-one"} onClick={() => pick(one)}>
                {VIEW_NAMES[one]}
              </button>
            ))}
          </span>
          {beside?.(over)}
          <ButtonLink to={page} kind="primary" size="md">
            Open the call ↗
          </ButtonLink>
        </Head>
        {view === "chat" ? (
          <ChatView entries={watched.entries} state={state} after={theEnd} />
        ) : trace !== null ? (
          <TraceView trace={trace} picked={picked} onPick={setPicked} after={theEnd} />
        ) : (
          <Timeline entries={watched.entries} state={state} terse={view === "transcript"} after={theEnd} />
        )}
        {foot}
      </div>
      <aside className="call-pane" aria-label="what the call holds">
        {/* A bar picked in the trace is what the reader is looking at: it comes before the rest. */}
        {step !== undefined && <TraceStep bar={step} onClose={() => setPicked(null)} />}
        {/* The desk is the live call's first thing: a supervisor opens the page to act on it. */}
        {!over && supervises && <Desk call={call} live spoken={spoken} asked={state.attention ?? null} />}
        {/* What the call came to, how fast it answered, how it was judged and what it cost: the rest is a page of its own. */}
        <div className="call-over">
          {over && <Outcome state={state} />}
          <LatencyCard rows={read.latencies} />
          {over && <ScoreCard call={call} base={`/calls/${call}`} score={read.score} turns={state.turns.length} ended compact />}
          {state.cost !== null && state.cost.rows.length > 0 && <CostCard cost={state.cost} />}
          <ButtonLink to={page} kind="primary">
            Open the call's page
          </ButtonLink>
        </div>
        {aside}
      </aside>
    </div>
  );
}

const VIEW_NAMES: Record<CallView, string> = { chat: "Chat", transcript: "Transcript", log: "Log", trace: "Trace" };

/**
 * The call's head, person first: who is on it and how the call stands, then where they came from
 * and which agent took it — the call's id is the name's title, and the stream is mentioned only
 * when it is not following the log. On the right, how the call is read and the screen's own moves.
 */
function Head({
  call,
  agent,
  name,
  state,
  connection,
  failed,
  children,
}: {
  call: string;
  agent: string | undefined;
  name: string | undefined;
  state: State;
  connection: string;
  failed: string | null;
  children: ReactNode;
}): ReactNode {
  const now = useNow(state.status !== "ended");
  const over = state.status === "ended";
  const address = state.direction === "outbound" ? state.to : state.from;
  const who = name ?? state.caller?.name ?? visitorOf(address) ?? (address === null ? "A caller" : prettyOrAsIs(address));
  const asking = !over && state.attention?.status === "open";
  return (
    <div className="call-head">
      <Avatar name={who} size={36} round tint={asking ? "amber" : over ? undefined : "green"} />
      <div className="call-who">
        <div className="call-who-line">
          <span className="call-who-name" title={call}>
            {who}
          </span>
          {asking ? (
            <Pill tone="amber" small>
              wants a person · {elapsed(state.started_at, now)}
            </Pill>
          ) : over ? (
            <Pill tone="gray" small>
              {(state.end_reason ?? "ended").replace(/_/g, " ")}
            </Pill>
          ) : (
            <Pill tone="green" small>
              {state.status === "active" ? `on a call · ${elapsed(state.started_at, now)}` : state.status}
            </Pill>
          )}
        </div>
        <div className="call-who-sub">
          {[address !== null && visitorOf(address) === null && prettyOrAsIs(address) !== who ? prettyOrAsIs(address) : null, state.channel, state.direction === "outbound" ? "outbound" : null, state.agent || agent || null]
            .filter((part): part is string => part !== null && part !== "")
            .join(" · ")}
          {failed !== null ? (
            <span className="call-connection-bad"> · {failed}</span>
          ) : (
            !over && connection !== "live" && <span className="call-connection"> · {connection}</span>
          )}
        </div>
      </div>
      <div className="call-head-moves">{children}</div>
    </div>
  );
}

function prettyOrAsIs(number: string): string {
  return number.startsWith("+") ? prettyNumber(number) : number;
}

// A live call's clock is the one thing here that moves without the log moving.
function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!ticking) return;
    const tick = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(tick);
  }, [ticking]);
  return now;
}

// The pointer to the audio rides the summary, near the end of a finished call's log.
function summaryOf(entries: Entry[]): Record<string, unknown> | undefined {
  return [...entries].reverse().find((entry) => entry.type === "call.summary")?.data;
}

// The call's audio at the foot of its log — and nothing at all when the gateway has none to play.
function Recorded({ call }: { call: string }): ReactNode {
  const [nothing, setNothing] = useState(false);
  const noAudio = useCallback(() => setNothing(true), []);
  if (nothing) return null;
  return (
    <div className="call-recording">
      <Player call={call} onNothing={noAudio} />
    </div>
  );
}
