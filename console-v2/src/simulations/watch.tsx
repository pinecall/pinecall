/** One simulated call, watched: the conversation as the log writes it, the header's buttons (results, the live ear, stop), and its numbers and judges in a panel beside it. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { elapsed, isSpoken } from "@pinecall/core/calls";
import { useCall } from "@pinecall/core/use-call";
import { useListen } from "@pinecall/core/use-listen";
import { useRoomOpen } from "@pinecall/core/use-room-open";
import { useSupervise } from "@pinecall/core/use-supervise";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type CallScore, CallScoreSchema } from "@pinecall/core/wire/events-call";
import { type State } from "@pinecall/core/wire/state";
import { Icon } from "../shell/icons";
import { CallSummary } from "../talk/summary";
import { SidePanel } from "../ui/side-panel";
import type { PersonaRun } from "./door";
import { lineOf, Transcript, withLine, type Line } from "./transcript";
import "../talk/talk.css";

const SCORED = "call.score";

/** What the page knows of the call it watches. */
export interface Watched {
  call: string;
  lines: Line[];
  state: State;
  score: CallScore | null;
  error: string | null;
  over: boolean;
  spoken: boolean;
}

export function useWatched(call: string): Watched {
  const [lines, setLines] = useState<Line[]>([]);
  const [score, setScore] = useState<CallScore | null>(null);
  const onEntry = useCallback((entry: Entry): void => {
    if (entry.type === SCORED) {
      const read = CallScoreSchema.safeParse(entry.data);
      if (read.success) setScore(read.data);
      return;
    }
    const line = lineOf(entry);
    if (line !== null) setLines((was) => withLine(was, line));
  }, []);
  const log = useCall(call, { onEntry });
  return { call, lines, state: log.state, score, error: log.error, over: log.state.status === "ended", spoken: isSpoken(log.state) };
}

function useNow(ticking: boolean): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!ticking) return;
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, [ticking]);
  return now;
}

/** The header's buttons, as Agents has its own: the results panel shown or folded, and while the call is on, the ear and the stop. */
export function WatchActions({ watched, results, onResults }: { watched: Watched; results: boolean; onResults: () => void }): ReactNode {
  return (
    <div className="app-actions">
      {watched.spoken && !watched.over && <Ear call={watched.call} />}
      <button type="button" className={results ? "app-button talk-button talk-button-on" : "app-button talk-button"} aria-pressed={results} onClick={onResults}>
        <Icon name="quality" size={14} />
        Results
      </button>
      {!watched.over && <Stop call={watched.call} spoken={watched.spoken} />}
    </div>
  );
}

/** The conversation, under a line that says how the call stands. */
export function WatchBody({ watched, run }: { watched: Watched; run: PersonaRun | undefined }): ReactNode {
  const { state, over, lines } = watched;
  const now = useNow(!over);
  const caller = run?.persona ?? "Caller";
  const agent = run?.agent ?? state.agent ?? "Agent";
  const standing = over ? "The call is over" : state.agent_state === "speaking" ? `${agent} is speaking` : state.agent_state === "thinking" ? `${agent} is thinking` : "On the line";
  return (
    <section className="sim-watch" aria-label="The simulated call">
      <div className={over ? "sim-standing" : "sim-standing sim-standing-live"}>
        <span className="sim-standing-dot" aria-hidden />
        {standing}
        {!over && state.started_at !== null && <span className="sim-clock">{elapsed(state.started_at, now)}</span>}
        <span className="sim-standing-how">
          <Icon name={watched.spoken ? "numbers" : "chat"} size={13} />
          {watched.spoken ? "Phone call" : "Chat"}
        </span>
      </div>
      {watched.error !== null && <p className="app-refused app-open-note">{watched.error}</p>}
      {lines.length === 0 && !over ? (
        <div className="sim-ringing">
          <span className="sim-ringing-title">Ringing {agent}…</span>
          <span>The call shows up here line by line, the moment somebody speaks.</span>
        </div>
      ) : (
        <Transcript lines={lines} agent={agent} caller={caller} />
      )}
    </section>
  );
}

/** The call's numbers and what the judges said, docked beside the conversation. */
export function ResultsPanel({ watched, onClose }: { watched: Watched; onClose: () => void }): ReactNode {
  return (
    <SidePanel title="Results" icon="quality" width={440} onClose={onClose}>
      {watched.over ? <CallSummary log={{ call: watched.call, state: watched.state, score: watched.score }} /> : <p className="ui-panel-about">The numbers and the judges' verdicts land here when the call ends. Each judge reads the whole conversation at hang-up.</p>}
    </SidePanel>
  );
}

// The room opens a moment after the call has its id: the log says when, and the ear joins once then.
function Ear({ call }: { call: string }): ReactNode {
  const ear = useListen(call);
  const room = useRoomOpen(call);
  const knocked = useRef(false);
  const inside = useRef(false);

  useEffect(() => {
    if (room === "open" && ear.listening === "off" && !knocked.current) {
      knocked.current = true;
      void ear.join();
    }
    // This page is for listening: heard at once, not after a second click.
    if (ear.listening === "muted" && !inside.current) {
      inside.current = true;
      ear.hear(true);
    }
  }, [ear, room]);

  if (ear.listening === "failed") return <span className="sim-ear sim-ear-failed">Could not listen in</span>;
  if (ear.listening !== "on" && ear.listening !== "muted") return <span className="sim-ear">Joining…</span>;
  const on = ear.listening === "on";
  return (
    <button type="button" className={on ? "app-button talk-button sim-ear-on" : "app-button talk-button"} aria-pressed={on} onClick={() => ear.hear(!on)}>
      <Icon name="speaker" size={14} />
      {on ? "Listening" : "Muted"}
    </button>
  );
}

// Stopping a simulation is hanging its call up: the caller is played off the call's own log, and its end is where it stops.
function Stop({ call, spoken }: { call: string; spoken: boolean }): ReactNode {
  const desk = useSupervise(call, spoken);
  const [stopping, setStopping] = useState(false);
  // A refusal puts the button back: the call is still on, and may be stopped again.
  const sent = stopping && desk.error === null;
  return (
    <>
      {desk.error !== null && <span className="app-refused">{desk.error}</span>}
      <button
        type="button"
        className="app-button"
        disabled={sent}
        onClick={() => {
          setStopping(true);
          void desk.end();
        }}
      >
        {sent ? "Stopping…" : "Stop"}
      </button>
    </>
  );
}
