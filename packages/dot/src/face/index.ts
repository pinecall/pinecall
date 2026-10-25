/** The face: a dot that speaks with the agent's voice, drawn into any element of the page. */
//
// It reads the room it is given and nothing else: the phase and the agent's own state set its mood
// (resting, listening, hearing the caller, thinking), and while the agent's voice sounds, its mouth
// is read from that voice frame by frame. Its body is one of a few shapes, in the page's colour, and
// moves whole with the mood, its outline never bent: it bobs and leans in while it listens, nods with
// its head cocked and its eyes wide while the caller speaks, looks up from side to side with its
// mouth pursed while it thinks, and squashes with the voice. Nothing is sent anywhere and nothing is asked of the server.

import type { RoomStore } from "@pinecall/room";

import { drawn, painted } from "./draw.js";
import { Ear } from "./ear.js";
import { BLINK_S, POSES, SOUNDING, eased, easedMouth, lidAt, moodOf, nextBlink } from "./motion.js";
import { spoken, type Bands, type Mouth } from "./mouth.js";
import { morphed, outlineOf, radii, shapeOf, type Shape } from "./shape.js";

/** A face on the page. */
export interface Face {
  /** Let the face hear the voice. Call it from the click that starts the call: a browser starts audio only inside one. */
  wake(): void;
  /** Change the body's shape: it eases into the new one. */
  reshape(shape: Shape): void;
  /** Speak with this element's audio instead of the call's voice, a recording the page plays; null gives the call back. */
  listen(element: HTMLMediaElement | null): void;
  /** Take the face off the page and stop listening. */
  close(): void;
}

export interface FaceOptions {
  /** The body's shape: `circle` (the default), `squircle` or `blob`. */
  shape?: Shape | undefined;
  /** The body's colour, any CSS colour; the page's `--pc-face` when left out. */
  color?: string | undefined;
}

/** How high the body bobs in each mood, in the box's units, and how often, per second. */
const BOB = {
  idle: { high: 0, often: 0 },
  listening: { high: 1.5, often: 0.8 },
  hearing: { high: 1.3, often: 1.7 },
  thinking: { high: 0.6, often: 0.4 },
  speaking: { high: 0, often: 0 },
} as const;

// Without an ear (never woken, or no Web Audio) the mouth opens with the room's own level, in no shape.
const NO_SHAPE: Bands = { low: 1, mid: 1, high: 0, sib: 0 };

/** Draw a face into `host`, filling it, moving with `call`. The host sets its size. */
export function face(host: Element, call: RoomStore, options: FaceOptions = {}): Face {
  const drawing = drawn(host, `pc-face-${Math.random().toString(36).slice(2, 10)}`);
  if (options.color !== undefined && host instanceof HTMLElement) host.style.setProperty("--pc-face", options.color);
  let rest = radii(shapeOf(options.shape));
  let rim = rest;
  let bob = 0;
  let own: HTMLMediaElement | null = null;
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
    ear.hear(own ?? state.voice);
    const heard = ear.listen(dt);
    const loud = heard?.level ?? (state.speaking.agent ? state.speaking.level : 0);
    // What the mouth reads, on the host, for a page that wants to know: the voice itself, or the room's coarse level.
    if (host instanceof HTMLElement) {
      host.dataset["pcEar"] = ear.hearing;
      host.dataset["pcLevel"] = loud.toFixed(2);
    }
    const mood = (state.phase === "live" || own !== null) && loud > SOUNDING ? "speaking" : moodOf(state);
    const seconds = at / 1000;
    // Thinking purses its mouth and slides it from side to side, "hmm".
    const hmm = still ? 1 : Math.sin(seconds * Math.PI * 2 * 0.32);
    const target =
      mood === "speaking" ? spoken(loud, heard?.bands ?? NO_SHAPE) : mood === "thinking" ? { ...POSES.thinking, shift: 3.2 * hmm } : POSES[mood];
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

    // Thinking looks up, from side to side; hearing looks at the caller, toward the page; otherwise a
    // small glance now and then, smaller while speaking.
    glanceIn -= dt;
    if (mood === "thinking") {
      glance.x = 2.6 * hmm;
      glance.y = -3.2;
      glanceIn = 0.4;
    } else if (mood === "hearing") {
      glance.x = -1.2;
      glance.y = 0.6;
      glanceIn = 0.4;
    } else if (glanceIn <= 0) {
      glanceIn = 1.5 + Math.random() * 3;
      const wander = mood === "speaking" ? 0.8 : 1.6;
      glance.x = (Math.random() - 0.5) * 2 * wander;
      glance.y = (Math.random() - 0.5) * wander;
    }
    gaze.x = eased(gaze.x, glance.x, dt, 0.12, 0.12);
    gaze.y = eased(gaze.y, glance.y, dt, 0.12, 0.12);

    const breath = still ? 0 : Math.sin(seconds * Math.PI * 2 * 0.22) * 0.018;
    rim = morphed(rim, rest, dt);
    bob = eased(bob, still ? 0 : BOB[mood].high, dt, 0.3, 0.4);
    const wave = Math.sin(seconds * Math.PI * 2 * (BOB[mood].often || 0.8));
    // A bob is a little hop: up a touch taller and narrower, down a touch wider, as a soft body does.
    const hop = bob * wave;
    // Hearing cocks its head, as a person does who is following; thinking sways slowly.
    const lean = { idle: 0, listening: -5, hearing: -9, thinking: 4 + 2.5 * hmm, speaking: 0 }[mood];
    painted(drawing, {
      mouth,
      lid,
      eyes: mood === "hearing" ? 1.16 : mood === "listening" ? 1.08 : 1,
      gaze,
      tilt: still ? 0 : lean + Math.sin(seconds * 0.7) * 1.2,
      lift: hop,
      scale: { x: 1 + breath + level * 0.025 - mouth.open * 0.012 - hop * 0.008, y: 1 + breath + level * 0.02 + mouth.open * 0.03 + hop * 0.01 },
      body: outlineOf(rim),
    });
    frame = requestAnimationFrame(tick);
  };
  tick(performance.now());

  return {
    wake() {
      ear.wake();
    },
    reshape(shape) {
      rest = radii(shape);
    },
    listen(element) {
      own = element;
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
