/** The orb in the Playground's bar: who is making a sound on the call, and on a voice call how loud the agent is. */

import { type State } from "@pinecall/core/wire/state";
import { useEffect, useRef, type ReactNode } from "react";

import { type Talking } from "./use-room";
import "./orb.css";

// How far the drawn level moves toward the heard one each frame: quick to swell, never jittery.
const EASE = 0.3;

/**
 * The level is written straight onto the element as `--lvl`, from one animation-frame loop, so a
 * loud syllable swells the core without React drawing the bar sixty times a second. A written chat
 * has no voice to measure: there the orb says only whether the agent is answering, by the log.
 */
export function Orb({ live, agentState }: { live: Talking; agentState: State["agent_state"] }): ReactNode {
  const orb = useRef<HTMLSpanElement>(null);
  const voice = live.mode === "talk";
  const read = useRef<() => number>(() => 0);
  read.current = voice ? live.level : () => 0;

  useEffect(() => {
    let drawn = 0;
    let frame = 0;
    const draw = (): void => {
      drawn += (read.current() - drawn) * EASE;
      orb.current?.style.setProperty("--lvl", drawn.toFixed(3));
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, []);

  const agent = voice ? live.speaking.agent : agentState === "speaking";
  const who = agent ? "agent" : voice && live.speaking.user ? "user" : "idle";
  const said = who === "agent" ? "The agent is speaking" : who === "user" ? "You are speaking" : "Nobody is speaking";
  return (
    <span ref={orb} className={`talk-orb talk-orb-${who}`} role="img" aria-label={said} title={said}>
      <span className="talk-orb-halo" />
      <span className="talk-orb-core" />
    </span>
  );
}
