/** "Pretend to be…": the agent's callers as chips, one of them played by a model against the agent as it was last saved — written, and read here as it goes. */

import { useEffect, useState, type ReactNode } from "react";

import { saidBy } from "@pinecall/core/api";
import { useCredentials } from "@pinecall/core/credentials";
import { sendVerb } from "@pinecall/core/verbs";
import { Face } from "../personas/face";
import { isPinecalls, type Persona } from "../personas/door";
import { usePersonas } from "../personas/use-personas";
import { startSimulation } from "../simulations/simulating";
import { rowsOf, useWatchedCall } from "../call";
import { fromCall, Messages, type Message } from "./messages";

// A few turns are enough to see how the agent takes a caller; the Simulations screen runs fifteen.
const TURNS = 8;
// How many callers the row offers before the rest are left to Simulations.
const SHOWN = 4;

/** A simulation started from here, and the call it is: null until one is. */
export interface Playing {
  persona: string | null;
  call: string | null;
  refused: string | null;
  starting: boolean;
}

export function usePlaying(agent: string): { playing: Playing; play: (persona: Persona) => Promise<void>; stop: () => Promise<void> } {
  const credentials = useCredentials();
  const [playing, setPlaying] = useState<Playing>({ persona: null, call: null, refused: null, starting: false });

  const play = async (persona: Persona): Promise<void> => {
    setPlaying({ persona: persona.name, call: null, refused: null, starting: true });
    try {
      const call = await startSimulation(credentials, { agent, persona: persona.name, voice: false, turns: TURNS });
      setPlaying({ persona: persona.name, call, refused: null, starting: false });
    } catch (failed) {
      setPlaying({ persona: null, call: null, refused: saidBy(failed), starting: false });
    }
  };

  // A model left playing is a call that costs: ending it is part of starting over. A call that is over, or a key that may not hang up, is nothing to say.
  const stop = async (): Promise<void> => {
    const call = playing.call;
    if (call === null) return;
    await sendVerb(credentials, call, { verb: "end" }).catch(() => undefined);
  };

  return { playing, play, stop };
}

/** The callers a person has switched on for the agent: its own, and Pinecall's it enabled. */
export function Pretend({ agent, playing, onPlay, disabled }: { agent: string; playing: Playing; onPlay: (persona: Persona) => void; disabled: boolean }): ReactNode {
  const { personas } = usePersonas(agent);
  const on = (personas ?? []).filter((persona) => !isPinecalls(persona) || persona.on).slice(0, SHOWN);
  if (on.length === 0) return null;
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
      </div>
      {playing.refused !== null && <span className="sto-wrong">{playing.refused}</span>}
    </div>
  );
}

/** A call a model plays, read as it is written: its bubbles, and the word that it is over. */
export function Played({ call, onOver }: { call: string; onOver: (over: boolean) => void }): ReactNode {
  const watched = useWatchedCall(call);
  const over = watched.state.status === "ended";
  useEffect(() => onOver(over), [over, onOver]);
  const messages: Message[] = fromCall(rowsOf(watched.entries, watched.state));
  return <Messages messages={over ? [...messages, { kind: "note", id: "over", text: "The simulation is over." }] : messages} empty={<p className="sto-empty-line">The caller is dialling…</p>} />;
}
