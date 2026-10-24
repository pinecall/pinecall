/** @pinecall/room/face: a face that speaks with the agent's voice, drawn into any element of the page. */
//
// It reads the room it is given and nothing else: the phase and the agent's own state set its mood
// (resting, listening, thinking), and while the agent's voice sounds, its mouth is read from that
// voice frame by frame. Nothing is sent anywhere and nothing is asked of the server.

import type { RoomStore } from "../index.js";

import { drawn, painted } from "./draw.js";
import { Ear } from "./ear.js";
import { BLINK_S, POSES, SOUNDING, eased, easedMouth, lidAt, moodOf, nextBlink } from "./motion.js";
import { spoken, type Bands, type Mouth } from "./mouth.js";

/** A face on the page. */
export interface Face {
  /** Let the face hear the voice. Call it from the click that starts the call: a browser starts audio only inside one. */
  wake(): void;
  /** Take the face off the page and stop listening. */
  close(): void;
}

// Without an ear (never woken, or no Web Audio) the mouth opens with the room's own level, in no shape.
const NO_SHAPE: Bands = { low: 1, mid: 1, high: 0, sib: 0 };

/** Draw a face into `host`, filling it, moving with `call`. The host sets its size. */
export function face(host: Element, call: RoomStore): Face {
  const drawing = drawn(host, `pc-face-${Math.random().toString(36).slice(2, 10)}`);
  const ear = new Ear();
  const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let mouth: Mouth = { ...POSES.idle };
  let level = 0;
  let last = performance.now();
  let blinking: number | null = null;
  let blinkIn = nextBlink(Math.random());
  const gaze = { x: 0, y: 0 };
  const glance = { x: 0, y: 0 };
  let glanceIn = 2;
  let frame = 0;
  let closed = false;

  const tick = (at: number): void => {
    const dt = Math.min(0.05, Math.max(0, (at - last) / 1000));
    last = at;
    const state = call.state;
    ear.hear(state.voice);
    const heard = ear.listen(dt);
    const loud = heard?.level ?? (state.speaking.agent ? state.speaking.level : 0);
    const mood = state.phase === "live" && loud > SOUNDING ? "speaking" : moodOf(state);
    const target = mood === "speaking" ? spoken(loud, heard?.bands ?? NO_SHAPE) : POSES[mood];
    mouth = easedMouth(mouth, target, dt);
    level = eased(level, mood === "speaking" ? loud : 0, dt, 0.03, 0.12);

    blinkIn -= dt;
    if (blinking === null && blinkIn <= 0) blinking = 0;
    let lid = 1;
    if (blinking !== null) {
      blinking += dt;
      lid = lidAt(blinking);
      if (blinking >= BLINK_S) {
        blinking = null;
        blinkIn = nextBlink(Math.random());
      }
    }

    // Thinking looks up and away; otherwise a small glance now and then, smaller while speaking.
    glanceIn -= dt;
    if (mood === "thinking") {
      glance.x = 2.6;
      glance.y = -3.2;
      glanceIn = 0.4;
    } else if (glanceIn <= 0) {
      glanceIn = 1.5 + Math.random() * 3;
      const wander = mood === "speaking" ? 0.8 : 1.6;
      glance.x = (Math.random() - 0.5) * 2 * wander;
      glance.y = (Math.random() - 0.5) * wander;
    }
    gaze.x = eased(gaze.x, glance.x, dt, 0.12, 0.12);
    gaze.y = eased(gaze.y, glance.y, dt, 0.12, 0.12);

    const seconds = at / 1000;
    const breath = still ? 0 : Math.sin(seconds * Math.PI * 2 * 0.22) * 0.018;
    const beat = mood === "listening" && !still ? (Math.sin(seconds * Math.PI * 2 * 0.9) + 1) / 2 : 0;
    const lean = mood === "listening" ? -5 : mood === "thinking" ? 4 : 0;
    painted(drawing, {
      mouth,
      lid,
      eyes: mood === "listening" ? 1.08 : 1,
      gaze,
      tilt: still ? 0 : lean + Math.sin(seconds * 0.7) * 1.2,
      scale: { x: 1 + breath + level * 0.025 - mouth.open * 0.012, y: 1 + breath + level * 0.02 + mouth.open * 0.03 },
      halo: mood === "speaking" ? level : beat * 0.35,
    });
    frame = requestAnimationFrame(tick);
  };
  tick(performance.now());

  return {
    wake() {
      ear.wake();
    },
    close() {
      if (closed) return;
      closed = true;
      cancelAnimationFrame(frame);
      ear.close();
      drawing.svg.remove();
    },
  };
}
