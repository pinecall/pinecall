/** One call open: its four readings, the recording under them, and its details docked beside it. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { isSpoken } from "@pinecall/core/calls";
import { medians } from "@pinecall/core/metrics";
import { type CallScore } from "@pinecall/core/wire/events-call";
import { useOrg } from "../lib/org";
import { spotlight } from "./broken";
import { ChatView } from "./chat";
import { useLine } from "./desk";
import { DetailsPanel } from "./details";
import { Timeline } from "./log";
import { Recording, type TapeControl } from "./recording";
import { type Thread } from "./threads";
import { TraceView } from "./trace";
import { traceOf } from "./trace-bars";
import { recordingIn, scoreIn, useWatchedCall } from "./use-watched-call";
import { VIEWS, type CallView } from "./view";

export function OpenCall({ call, person, search, details, onDetails }: { call: string; /** The thread the call belongs to, when the list holds it. */ person: Thread | undefined; search: string; details: boolean; onDetails: (open: boolean) => void }): ReactNode {
  const watched = useWatchedCall(call);
  const { state, entries } = watched;
  const { whose } = useOrg();
  const scopes = whose?.scopes ?? null;
  const over = state.status === "ended";
  const live = !over && state.status !== "idle";
  const spoken = isSpoken(state);
  // A key that does not open `supervise` is refused every move: the desk is not drawn for it.
  const supervises = scopes === null || scopes.includes("supervise");
  // Held here, not in the panel: folding the details must not drop a line somebody has taken.
  const line = useLine(call, spoken, live && spoken && supervises);
  const sealed = useMemo(() => scoreIn(entries), [entries]);
  const latencies = useMemo(() => medians(entries), [entries]);
  const recorded = useMemo(() => recordingIn(entries), [entries]);
  // A verdict asked for here is the one shown, over the one the log was sealed with.
  const [judged, setJudged] = useState<CallScore | null>(null);
  const score = judged ?? sealed;

  // Every call opens on its chat: the other readings are a click away, and none is remembered.
  const [view, setView] = useState<CallView>("chat");

  // Folded only while it is read; the bar picked is kept by id, so a live call's next update shows the same bar with what has come in since.
  const trace = useMemo(() => (view === "trace" ? traceOf(entries, state) : null), [view, entries, state]);
  const [picked, setPicked] = useState<string | null>(null);
  const step = trace?.rows.flatMap((row) => row.bars).find((bar) => bar.id === picked);
  const pickBar = (bar: string | null): void => {
    setPicked(bar);
    if (bar !== null) onDetails(true);
  };

  const tape = useRef<TapeControl | null>(null);
  const [canSeek, setCanSeek] = useState(false);

  // On an address opened directly the page is drawn in the same pass as the frame, whose column does not exist yet: the panel waits for it, before anything is painted.
  const [framed, setFramed] = useState(false);
  useLayoutEffect(() => setFramed(true), []);

  // A citation lands on a row, and the trace has none: it goes to the chat first.
  const body = useRef<HTMLDivElement>(null);
  const [cited, setCited] = useState<{ seq: number; asked: number } | null>(null);
  useEffect(() => {
    if (cited !== null) spotlight(body.current, cited.seq);
  }, [cited]);
  const cite = (seq: number): void => {
    if (view === "trace") setView("chat");
    setCited({ seq, asked: Date.now() });
  };

  return (
    <div className="calls-watch">
      <nav className="app-tabs calls-views" aria-label="How the call is read">
        {VIEWS.map((one) => (
          <button key={one.view} type="button" className={view === one.view ? "app-tab app-tab-on calls-tab" : "app-tab calls-tab"} aria-pressed={view === one.view} onClick={() => setView(one.view)}>
            {one.name}
          </button>
        ))}
      </nav>
      <div className="calls-body" ref={body}>
        {view === "chat" ? (
          <ChatView entries={entries} state={state} score={score} onSeek={canSeek ? (at) => tape.current?.seek(at) : undefined} />
        ) : trace !== null ? (
          <TraceView trace={trace} picked={picked} onPick={pickBar} />
        ) : (
          <Timeline entries={entries} state={state} score={score} terse={view === "transcript"} />
        )}
      </div>
      {recorded !== null && <Recording call={call} control={tape} onReady={setCanSeek} />}
      {details && framed && (
        <DetailsPanel call={call} watched={watched} score={score} latencies={latencies} step={step} onLetGo={() => setPicked(null)} line={line} live={live} spoken={spoken} supervises={supervises} person={person} search={search} onCite={cite} onJudged={setJudged} onClose={() => onDetails(false)} />
      )}
    </div>
  );
}
