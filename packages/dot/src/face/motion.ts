/** How the face moves between frames: the mood a call is in, the mouth each quiet mood holds, the easing, the blink. Pure. */

import type { RoomState } from "@pinecall/room";

import type { Mouth } from "./mouth.js";

/** What the face is doing. Speaking is the voice's; the others are poses: listening waits in a call, hearing is the caller speaking. */
export type Mood = "idle" | "listening" | "hearing" | "thinking" | "speaking";

/** The mouth each quiet mood holds. */
export const POSES: Record<Exclude<Mood, "speaking">, Mouth> = {
  idle: { open: 0, width: 0.5, round: 0, teeth: 0, smile: 0.85, shift: 0 },
  listening: { open: 0.04, width: 0.55, round: 0, teeth: 0, smile: 0.55, shift: 0 },
  hearing: { open: 0.1, width: 0.36, round: 0.45, teeth: 0, smile: 0.3, shift: 0 },
  thinking: { open: 0.14, width: 0.2, round: 0.75, teeth: 0, smile: 0, shift: 3.2 },
};

/** A frame louder than this is the agent speaking, whatever its state says: the log's word comes later than the sound. */
export const SOUNDING = 0.06;

/**
 * The mood a call is in: opening thinks, a live call follows the agent's own state and hears while
 * the caller speaks, anything else rests.
 */
export function moodOf(state: RoomState): Mood {
  if (state.phase === "opening") return "thinking";
  if (state.phase !== "live") return "idle";
  switch (state.log.agent_state) {
    case "speaking":
      return "speaking";
    case "thinking":
      return "thinking";
    default:
      return state.speaking.user || (state.log.live.user ?? "") !== "" ? "hearing" : "listening";
  }
}

/** One number moved toward its target over `dt` seconds: `rise` seconds to open, `fall` to close. */
export function eased(now: number, target: number, dt: number, rise: number, fall: number): number {
  const tau = target > now ? rise : fall;
  return now + (target - now) * (1 - Math.exp(-dt / tau));
}

/** The whole mouth moved toward its target: quick to open, slower to close, so it never shivers. */
export function easedMouth(now: Mouth, target: Mouth, dt: number): Mouth {
  return {
    open: eased(now.open, target.open, dt, 0.035, 0.075),
    width: eased(now.width, target.width, dt, 0.05, 0.09),
    round: eased(now.round, target.round, dt, 0.05, 0.09),
    teeth: eased(now.teeth, target.teeth, dt, 0.03, 0.07),
    smile: eased(now.smile, target.smile, dt, 0.15, 0.15),
    shift: eased(now.shift, target.shift, dt, 0.2, 0.2),
  };
}

/** How long a blink takes, in seconds. */
export const BLINK_S = 0.16;

/** How open the eyes are `since` seconds into a blink: 1 open, down to 0.1, and back. */
export function lidAt(since: number): number {
  const p = since / BLINK_S;
  if (p >= 1) return 1;
  return p < 0.5 ? 1 - p * 1.8 : Math.min(1, 0.1 + (p - 0.5) * 1.8);
}

/** Seconds to the next blink, from a random draw in [0, 1): now and then twice in a row, else every 2.5 to 6 s. */
export function nextBlink(draw: number): number {
  return draw < 0.18 ? 0.18 : 2.5 + ((draw - 0.18) / 0.82) * 3.5;
}
