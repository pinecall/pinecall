/** "Pretend to be…": the agent's callers as chips, one of them read for what it phones about and played by a model against the agent as it was last saved — written or out loud, as the chat is — and a new one written without leaving the page. */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { type Said } from "@pinecall/core/transcripts";
import { useListen } from "@pinecall/core/use-listen";
import { useRoomOpen } from "@pinecall/core/use-room-open";
import { sendVerb } from "@pinecall/core/verbs";
import { Button } from "../../ui";
import { Face } from "../personas/face";
import { briefPersona, isPinecalls, type Persona } from "../personas/door";
import { startSimulation } from "../simulations/simulating";
import { rowsOf, useWatchedCall } from "../call";
import { fromCall, Messages, type Message } from "./messages";
import { type Scenario } from "./scenario";

// A few turns are enough to see how the agent takes a caller; the Simulations screen runs fifteen.
const TURNS = 8;
// How many callers the row offers before the rest are left to Simulations.
const SHOWN = 4;

/** A caller picked, what it phones about while that is read, and the call once it is placed: each null until it is. */
export interface Playing {
  persona: string | null;
  /** The caller and what it phones about, read before the call; null once the call is placed, or none is picked. */
  scenario: Scenario | null;
  call: string | null;
  /** What the caller phones about on the call placed. */
  goal: string | null;
  refused: string | null;
  starting: boolean;
  /** Out loud: the room is joined and heard, as a line would be. */
  voice: boolean;
}

export interface Plays {
  playing: Playing;
  /** A caller picked: what it phones about is read — a library caller briefed on the agent — and shown before the call. */
  pick: (persona: Persona) => Promise<void>;
  /** The same library caller briefed again. */
  again: () => Promise<void>;
  /** The caller put down before it phoned. */
  cancel: () => void;
  /** The call placed with the goal as the person left it; out loud when the chat is on Talk. */
  play: (goal: string, voice: boolean) => Promise<void>;
  /** A caller written here phones at once, about its own goal. */
  playNow: (persona: Persona, voice: boolean) => Promise<void>;
  stop: () => Promise<void>;
}

const NOBODY: Playing = { persona: null, scenario: null, call: null, goal: null, refused: null, starting: false, voice: false };

export function usePlaying(agent: string): Plays {
  const credentials = useCredentials();
  const [playing, setPlaying] = useState<Playing>(NOBODY);

  // A library caller's goal is written for every business: the gateway writes the one it phones this
  // agent about, and the person reads it — and may edit it — before the call. One written for the
  // agent phones about its own, shown the same way. A briefing refused leaves the goal as written, and says so.
  const brief = async (persona: Persona): Promise<void> => {
    const library = isPinecalls(persona);
    setPlaying({ ...NOBODY, persona: persona.name, scenario: { persona, goal: persona.goal, facts: persona.facts, briefing: library, missed: null } });
    if (!library) return;
    try {
      const told = await briefPersona(credentials, agent, persona.name);
      setPlaying((was) => (was.scenario?.persona.name === persona.name ? { ...was, scenario: { persona, goal: told.goal, facts: told.facts, briefing: false, missed: null } } : was));
    } catch (failed) {
      setPlaying((was) => (was.scenario?.persona.name === persona.name ? { ...was, scenario: { persona, goal: persona.goal, facts: persona.facts, briefing: false, missed: `The gateway did not brief it (${saidBy(failed)}); it calls as written.` } } : was));
    }
  };

  const again = async (): Promise<void> => {
    if (playing.scenario !== null) await brief(playing.scenario.persona);
  };

  const cancel = (): void => setPlaying(NOBODY);

  // Out loud when the chat is on Talk: the caller speaks and the agent answers in its voice, as on a line.
  // A preview is for hearing the agent, not for testing its patience: the caller answers at once.
  const place = async (persona: Persona, voice: boolean, scenario: { goal: string; facts: Readonly<Record<string, string>> } | null): Promise<void> => {
    const goal = scenario === null ? persona.goal : scenario.goal;
    setPlaying({ ...NOBODY, persona: persona.name, goal, starting: true, voice });
    try {
      const wanted = { agent, persona: persona.name, voice, turns: TURNS, pause_s: 0, ...(scenario === null ? {} : { scenario: { goal: scenario.goal, facts: { ...scenario.facts } } }) };
      const call = await startSimulation(credentials, wanted);
      setPlaying({ ...NOBODY, persona: persona.name, goal, call, voice });
    } catch (failed) {
      setPlaying({ ...NOBODY, refused: saidBy(failed), voice });
    }
  };

  const play = async (goal: string, voice: boolean): Promise<void> => {
    const scenario = playing.scenario;
    if (scenario === null) return;
    await place(scenario.persona, voice, { goal, facts: scenario.facts });
  };

  // A model left playing is a call that costs: ending it is the Stop button's and part of starting over.
  // A key that may not hang up is told so, rather than left on "Stopping…".
  const stop = async (): Promise<void> => {
    const call = playing.call;
    if (call === null) return;
    try {
      await sendVerb(credentials, call, { verb: "end" });
    } catch (failed) {
      setPlaying((was) => ({ ...was, refused: saidBy(failed) }));
    }
  };

  return { playing, pick: brief, again, cancel, play, playNow: (persona, voice) => place(persona, voice, null), stop };
}

/** The callers a person has switched on for the agent — its own first, then Pinecall's it enabled — and the way to write one here. */
export function Pretend({ personas, playing, onPlay, onNew, disabled, children }: { personas: readonly Persona[]; playing: Playing; onPlay: (persona: Persona) => void; onNew: () => void; disabled: boolean; children?: ReactNode }): ReactNode {
  const own = personas.filter((persona) => !isPinecalls(persona));
  const library = personas.filter((persona) => isPinecalls(persona) && persona.on);
  const on = [...own, ...library].slice(0, SHOWN);
  return (
    <div className="sto-pretend">
      <span className="sto-pretend-label">Pretend to be…</span>
      <div className="sto-pretend-chips">
        {on.map((persona) => (
          <button key={`${persona.owner}/${persona.name}`} type="button" className={playing.persona === persona.name ? "sto-chip sto-chip-on" : "sto-chip"} disabled={disabled || playing.starting} onClick={() => onPlay(persona)}>
            <Face name={persona.name} size={18} />
            {persona.name}
          </button>
        ))}
        <button type="button" className="sto-chip sto-chip-new" disabled={disabled || playing.starting} onClick={onNew}>
          + New caller
        </button>
      </div>
      {children}
      {playing.refused !== null && <span className="sto-wrong">{playing.refused}</span>}
    </div>
  );
}

/** A call a model plays, read as it is written — heard too when it is spoken — under what the caller phones about, with the one move it has, which is to stop it. */
export function Played({ call, goal, spoken, onOver, onStop }: { call: string; goal: string | null; spoken: boolean; onOver: (over: boolean) => void; onStop: () => Promise<void> }): ReactNode {
  const watched = useWatchedCall(call);
  const ear = useListen(call);
  const over = watched.state.status === "ended";
  const [stopping, setStopping] = useState(false);
  useEffect(() => onOver(over), [over, onOver]);
  // The log's turns, settled; over them the room's segments still being said — the karaoke — until the turn that holds their words lands.
  const settled = fromCall(rowsOf(watched.entries, watched.state));
  const about: Message[] = goal === null ? [] : [{ kind: "note", id: "about", text: `Calls about: ${goal}` }];
  const messages: Message[] = [...about, ...(spoken ? [...settled, ...karaoke(ear.lines, settled)] : settled)];
  return (
    <>
      <div className="sto-played">
        {spoken ? <Ear call={call} ear={ear} over={over} /> : <span className="sto-played-said">{over ? "The simulation is over." : "A model is playing the caller, in writing."}</span>}
        {!over && (
          <Button
            size="sm"
            kind="danger"
            disabled={stopping}
            onClick={() => {
              setStopping(true);
              void onStop();
            }}
          >
            {stopping ? "Stopping…" : "Stop"}
          </Button>
        )}
      </div>
      <Messages messages={over ? [...messages, { kind: "note", id: "over", text: "The simulation is over." }] : messages} empty={<p className="sto-empty-line">The caller is dialling…</p>} />
    </>
  );
}

// The room's segments not yet on the log, by their words: a final one gives way to its turn the
// moment the log carries it, an interim one is drawn dimmed as it grows.
function karaoke(lines: readonly Said[], settled: readonly Message[]): Message[] {
  const words = (text: string): string => text.trim().replace(/\s+/g, " ").toLowerCase();
  const landed = new Set(settled.filter((one) => one.kind === "said").map((one) => words(one.text)));
  return lines
    .filter((line) => line.text.trim() !== "" && !landed.has(words(line.text)))
    .map((line) => ({ kind: "said", id: `r-${line.id}`, who: line.speaker === "user" ? "caller" : "agent", text: line.text, unsettled: !line.final }));
}

// A spoken simulation's room opens a moment after the call has its id; the ear joins then and is
// heard at once, as Simulations does. A join the door refuses is said, never retried.
function Ear({ call, ear, over }: { call: string; ear: ReturnType<typeof useListen>; over: boolean }): ReactNode {
  const room = useRoomOpen(call);
  const knocked = useRef(false);
  const inside = useRef(false);

  useEffect(() => {
    if (room === "open" && ear.listening === "off" && !knocked.current) {
      knocked.current = true;
      void ear.join();
    }
    if (ear.listening === "muted" && !inside.current) {
      inside.current = true;
      ear.hear(true);
    }
  }, [ear, room]);

  // Leaving the page, or the call ending, lets the seat go.
  useEffect(() => {
    if (over) void ear.leave();
  }, [over, ear]);

  const said = ((): string => {
    if (over) return "The simulation is over.";
    switch (ear.listening) {
      case "on":
        return "Listening live";
      case "muted":
        return "Muted";
      case "joining":
        return "Joining the call…";
      case "failed":
        return `Could not join: ${ear.error ?? "no room"}`;
      case "over":
        return "The call is over.";
      case "off":
        return room === "open" ? "Joining the call…" : "The caller is dialling…";
    }
  })();
  return (
    <span className="sto-played-ear">
      <span className={ear.listening === "on" ? "sto-ear-dot sto-ear-dot-on" : "sto-ear-dot"} aria-hidden />
      <span className="sto-played-said">{said}</span>
      {!over && ear.listening === "on" && (
        <button type="button" className="sto-ear-mute" onClick={() => ear.hear(false)}>
          Mute
        </button>
      )}
      {!over && ear.listening === "muted" && inside.current && (
        <button type="button" className="sto-ear-mute" onClick={() => ear.hear(true)}>
          Unmute
        </button>
      )}
    </span>
  );
}
