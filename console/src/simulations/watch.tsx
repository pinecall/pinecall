/** One simulated call, watched: the conversation as the log writes it and, on a spoken one, each line word by word as the room says it; the header's buttons (results, the live ear, stop), and its numbers and judges in a panel beside it. */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { elapsed, isSpoken } from "@pinecall/core/calls";
import { useCall } from "@pinecall/core/use-call";
import type { Said } from "@pinecall/core/transcripts";
import { useListen, type Ear } from "@pinecall/core/use-listen";
import { useRoomOpen } from "@pinecall/core/use-room-open";
import { useSupervise } from "@pinecall/core/use-supervise";
import { type Entry } from "@pinecall/core/wire/envelope";
import { type CallScore, CallScoreSchema } from "@pinecall/core/wire/events-call";
import { type State } from "@pinecall/core/wire/state";
import { Recording, type TapeControl } from "../calls/recording";
import { Icon } from "../shell/icons";
import { CallSummary } from "../talk/summary";
import { SidePanel } from "../ui/side-panel";
import type { Hearing, PersonaRun } from "./door";
import { BeingSaid, lineOf, Transcript, withLine, type Line } from "./transcript";
import "../talk/talk.css";
import "../calls/conversation.css";

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
  /** The call's summary named its audio: there is a recording to play. */
  recorded: boolean;
  /** The seat this page listens from, on a spoken call. */
  ear: Ear;
  /** What is being said this instant and the log has not written yet: the caller as the agent's ear hears it, the agent as its voice says it. */
  saying: Said[];
}

export function useWatched(call: string): Watched {
  const [lines, setLines] = useState<Line[]>([]);
  const [score, setScore] = useState<CallScore | null>(null);
  const [recorded, setRecorded] = useState(false);
  const ear = useListen(call);
  // Read by the log's handler: the segments heard so far, whoever said them.
  const heard = useRef<Said[]>([]);
  heard.current = ear.lines;
  // The segments a turn of the log has taken the place of: a late word of one is not drawn again.
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const onEntry = useCallback((entry: Entry): void => {
    if (entry.type === "turn.user" || entry.type === "turn.agent") {
      const whose = entry.type === "turn.user" ? "user" : "agent";
      const ids = heard.current.filter((one) => one.speaker === whose).map((one) => one.id);
      if (ids.length > 0) setClosed((was) => new Set([...was, ...ids]));
    }
    if (entry.type === "call.summary") {
      const path = (entry.data as Record<string, unknown>)["recording"];
      setRecorded(typeof path === "string" && path !== "");
      return;
    }
    if (entry.type === SCORED) {
      const read = CallScoreSchema.safeParse(entry.data);
      if (read.success) setScore(read.data);
      return;
    }
    const line = lineOf(entry);
    if (line !== null) setLines((was) => withLine(was, line));
  }, []);
  const log = useCall(call, { onEntry });
  const over = log.state.status === "ended";
  const spoken = isSpoken(log.state);

  // The room opens a moment after the call has its id: the log says when, and the ear joins once then.
  const room = useRoomOpen(call);
  const knocked = useRef(false);
  const inside = useRef(false);
  const left = useRef(false);
  useEffect(() => {
    if (over) {
      // The call is over: the seat is given back once.
      if (knocked.current && !left.current) {
        left.current = true;
        void ear.leave();
      }
      return;
    }
    if (spoken && room === "open" && ear.listening === "off" && !knocked.current) {
      knocked.current = true;
      void ear.join();
    }
    // This page is for listening: heard at once, not after a second click.
    if (ear.listening === "muted" && !inside.current) {
      inside.current = true;
      ear.hear(true);
    }
  }, [ear, room, spoken, over]);

  const saying = over ? [] : ear.lines.filter((one) => !closed.has(one.id) && one.text.trim() !== "");
  return { call, lines, state: log.state, score, error: log.error, over, spoken, recorded, ear, saying };
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
      {watched.spoken && !watched.over && <EarButton ear={watched.ear} />}
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
  const { state, over, lines, saying } = watched;
  // The player takes a handle the chat of Calls seeks by; this page only plays it.
  const tape = useRef<TapeControl | null>(null);
  const ready = useCallback((): void => undefined, []);
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
      {lines.length === 0 && saying.length === 0 && !over ? (
        <div className="sim-ringing">
          <span className="sim-ringing-title">Ringing {agent}…</span>
          <span>The call shows up here line by line, the moment somebody speaks.</span>
        </div>
      ) : (
        <Transcript lines={lines} agent={agent} caller={caller} after={saying.length > 0 ? <BeingSaid saying={saying} agent={agent} caller={caller} last={lines.filter((one) => one.kind === "said").at(-1)} /> : undefined} />
      )}
      {watched.recorded && <Recording call={watched.call} control={tape} onReady={ready} />}
    </section>
  );
}

/** The call's numbers and what the judges said, docked beside the conversation. */
export function ResultsPanel({ watched, run, onClose }: { watched: Watched; run: PersonaRun | undefined; onClose: () => void }): ReactNode {
  return (
    <SidePanel title="Results" icon="quality" width={440} onClose={onClose}>
      {watched.over ? <CallSummary log={{ call: watched.call, state: watched.state, score: watched.score }} /> : <p className="ui-panel-about">The numbers and the judges' verdicts land here when the call ends. Each judge reads the whole conversation at hang-up.</p>}
      {watched.over && run?.hearing != null && <HearingCard hearing={run.hearing} />}
    </SidePanel>
  );
}

function share(part: number, whole: number): string {
  return whole === 0 ? "—" : `${part} of ${whole}`;
}

/** How the call was heard, against what its caller really said: what a judge reading the transcript cannot see. */
function HearingCard({ hearing }: { hearing: Hearing }): ReactNode {
  const wrong = hearing.word_error_rate;
  const rows: { name: string; value: string; about: string; bad: boolean }[] = [
    { name: "Lines not answered", value: share(hearing.unanswered, hearing.lines), about: "The caller spoke and the agent said nothing before the next line.", bad: hearing.unanswered > 0 },
    { name: "Cut off by the room", value: String(hearing.cut_by_the_room), about: "Replies the agent stopped with nobody speaking: noise taken for the caller.", bad: hearing.cut_by_the_room > 0 },
    { name: "Turns nobody said", value: String(hearing.phantom_turns), about: "Turns the agent heard while the caller was silent.", bad: hearing.phantom_turns > 0 },
    { name: "Talked over the caller", value: String(hearing.talked_over), about: "Replies begun in the middle of a line.", bad: hearing.talked_over > 0 },
    { name: "Stopped for a murmur", value: String(hearing.cut_by_a_murmur), about: "Replies a listener's mm-hmm alone cut off.", bad: hearing.cut_by_a_murmur > 0 },
    { name: "Words heard wrong", value: wrong === null ? "—" : `${Math.round(Math.min(wrong, 9.99) * 100)}%`, about: "Against what the caller really said; past 100% it heard words nobody said.", bad: wrong !== null && wrong > 0.15 },
    { name: "Reply after the caller stops", value: hearing.reply_s === null ? "—" : `${hearing.reply_s.toFixed(1)} s`, about: hearing.slow_reply_s === null ? "The typical wait." : `The typical wait; nine in ten are under ${hearing.slow_reply_s.toFixed(1)} s.`, bad: false },
  ];
  return (
    <section className="sim-heard" aria-label="How it was heard">
      <span className="sim-heard-title">How it was heard</span>
      <p className="sim-heard-about">Measured against what the caller really said and when. A judge reads the transcript alone, so only these show a line the agent heard badly.</p>
      <dl className="sim-heard-rows">
        {rows.map((row) => (
          <div key={row.name} className={row.bad ? "sim-heard-row sim-heard-bad" : "sim-heard-row"}>
            <dt>
              {row.name}
              <small>{row.about}</small>
            </dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function EarButton({ ear }: { ear: Ear }): ReactNode {
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
